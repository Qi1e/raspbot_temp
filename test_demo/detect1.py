import argparse
import socket
import time
import threading
from pathlib import Path

import cv2
import torch
import torch.backends.cudnn as cudnn
from numpy import random

from models.experimental import attempt_load
from utils.datasets import LoadStreams, LoadImages
from utils.general import check_img_size, check_requirements, check_imshow, non_max_suppression, apply_classifier, \
    scale_coords, xyxy2xywh, strip_optimizer, set_logging, increment_path
from utils.plots import plot_one_box
from utils.torch_utils import select_device, load_classifier, time_synchronized


RASPBOT_AP_IP = '192.168.1.11'


class PreviewState:
    def __init__(self, quality=70, width=640, fps=10):
        self.quality = int(max(1, min(100, quality)))
        self.width = max(0, int(width))
        self.min_interval = 0 if fps <= 0 else 1.0 / float(fps)
        self.last_publish = 0.0
        self.jpeg = None
        self.frame_id = 0
        self.condition = threading.Condition()

    def publish(self, frame):
        now = time.time()
        if self.min_interval and now - self.last_publish < self.min_interval:
            return
        self.last_publish = now

        if self.width and frame.shape[1] > self.width:
            scale = self.width / float(frame.shape[1])
            size = (self.width, int(frame.shape[0] * scale))
            frame = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(
            '.jpg',
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.quality],
        )
        if not ok:
            return

        with self.condition:
            self.jpeg = encoded.tobytes()
            self.frame_id += 1
            self.condition.notify_all()


class PreviewServer:
    def __init__(self, host, port, state):
        self.host = host
        self.port = port
        self.state = state
        self.running = False
        self.sock = None
        self.thread = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.sock.settimeout(1.0)
        self.running = True
        self.thread = threading.Thread(target=self.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def shutdown(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except socket.error:
                pass
            self.sock = None

    def server_close(self):
        self.shutdown()

    def serve_forever(self):
        while self.running:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except socket.error:
                if self.running:
                    raise
                break

            worker = threading.Thread(target=self.handle_client, args=(conn,))
            worker.daemon = True
            worker.start()

    def handle_client(self, conn):
        try:
            request = conn.recv(1024).decode('iso-8859-1', errors='ignore')
            first_line = request.splitlines()[0] if request else ''
            parts = first_line.split()
            path = parts[1].split('?', 1)[0] if len(parts) >= 2 else '/'

            if path in ('/', '/index.html'):
                self.send_index(conn)
            elif path in ('/stream.mjpg', '/stream'):
                self.send_stream(conn)
            elif path == '/snapshot.jpg':
                self.send_snapshot(conn)
            else:
                self.send_response(conn, '404 Not Found', 'text/plain', b'Not found')
        except (socket.error, ValueError, IndexError):
            return
        finally:
            try:
                conn.close()
            except socket.error:
                pass

    def send_response(self, conn, status, content_type, body):
        headers = [
            f'HTTP/1.0 {status}',
            f'Content-Type: {content_type}',
            f'Content-Length: {len(body)}',
            'Cache-Control: no-cache',
            'Connection: close',
        ]
        response = ('\r\n'.join(headers) + '\r\n\r\n').encode('ascii') + body
        conn.sendall(response)

    def send_index(self, conn):
        content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raspbot Preview</title>
  <style>
    html, body {{
      margin: 0;
      min-height: 100%;
      background: #101316;
      color: #eef3f7;
      font-family: Arial, sans-serif;
    }}
    header {{
      padding: 12px 16px;
      background: #191f24;
      border-bottom: 1px solid #2d363d;
      font-size: 16px;
      font-weight: 700;
    }}
    main {{
      display: grid;
      min-height: calc(100vh - 50px);
      place-items: center;
      padding: 12px;
      box-sizing: border-box;
    }}
    img {{
      width: min(100%, 1100px);
      max-height: calc(100vh - 80px);
      object-fit: contain;
      background: #000;
      border: 1px solid #2d363d;
    }}
  </style>
</head>
<body>
  <header>Raspbot YOLO Preview - {RASPBOT_AP_IP}</header>
  <main><img src="/stream.mjpg" alt="Raspbot preview stream"></main>
</body>
</html>
""".encode('utf-8')
        self.send_response(conn, '200 OK', 'text/html; charset=utf-8', content)

    def send_snapshot(self, conn):
        with self.state.condition:
            frame = self.state.jpeg
        if frame is None:
            self.send_response(conn, '503 Service Unavailable', 'text/plain', b'No preview frame yet')
            return
        self.send_response(conn, '200 OK', 'image/jpeg', frame)

    def send_stream(self, conn):
        headers = [
            'HTTP/1.0 200 OK',
            'Age: 0',
            'Cache-Control: no-cache, private',
            'Pragma: no-cache',
            'Content-Type: multipart/x-mixed-replace; boundary=frame',
            'Connection: close',
            '\r\n',
        ]
        conn.sendall(('\r\n'.join(headers)).encode('ascii'))

        last_id = -1
        while self.running:
            with self.state.condition:
                updated = self.state.condition.wait_for(
                    lambda: self.state.jpeg is not None and self.state.frame_id != last_id,
                    timeout=5.0,
                )
                if not updated:
                    continue
                frame = self.state.jpeg
                last_id = self.state.frame_id

            chunk_header = (
                '--frame\r\n'
                'Content-Type: image/jpeg\r\n'
                f'Content-Length: {len(frame)}\r\n\r\n'
            ).encode('ascii')
            try:
                conn.sendall(chunk_header)
                conn.sendall(frame)
                conn.sendall(b'\r\n')
            except socket.error:
                return


def start_preview_server(host, port, quality, width, fps):
    state = PreviewState(quality=quality, width=width, fps=fps)
    server = PreviewServer(host, port, state)
    server.start()
    print(f'Preview server started: http://{RASPBOT_AP_IP}:{port}/ (bind {host}:{port})')
    return state, server


def detect(save_img=False):
    source, weights, view_img, save_txt, imgsz = opt.source, opt.weights, opt.view_img, opt.save_txt, opt.img_size
    save_img = not opt.nosave and not source.endswith('.txt')  # save inference images
    webcam = source.isnumeric() or source.endswith('.txt') or source.lower().startswith(
        ('rtsp://', 'rtmp://', 'http://', 'https://'))

    # Directories
    save_dir = Path(increment_path(Path(opt.project) / opt.name, exist_ok=opt.exist_ok))  # increment run
    (save_dir / 'labels' if save_txt else save_dir).mkdir(parents=True, exist_ok=True)  # make dir

    # Initialize
    set_logging()
    preview_state, preview_server = None, None
    if opt.preview:
        preview_state, preview_server = start_preview_server(
            opt.preview_host,
            opt.preview_port,
            opt.preview_quality,
            opt.preview_width,
            opt.preview_fps,
        )

    device = select_device(opt.device)
    half = device.type != 'cpu'  # half precision only supported on CUDA

    # Load model
    model = attempt_load(weights, map_location=device)  # load FP32 model
    stride = int(model.stride.max())  # model stride
    imgsz = check_img_size(imgsz, s=stride)  # check img_size
    if half:
        model.half()  # to FP16

    # Second-stage classifier
    classify = False
    if classify:
        modelc = load_classifier(name='resnet101', n=2)  # initialize
        modelc.load_state_dict(torch.load('weights/resnet101.pt', map_location=device)['model']).to(device).eval()

    # Set Dataloader
    vid_path, vid_writer = None, None
    if webcam:
        if view_img:
            view_img = check_imshow()
        cudnn.benchmark = True  # set True to speed up constant image size inference
        dataset = LoadStreams(source, img_size=imgsz, stride=stride)
    else:
        dataset = LoadImages(source, img_size=imgsz, stride=stride)

    # Get names and colors
    names = model.module.names if hasattr(model, 'module') else model.names
    colors = [[random.randint(0, 255) for _ in range(3)] for _ in names]

    frame_count = 0
    start_time = time.time()

    # Run inference
    if device.type != 'cpu':
        model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))  # run once
    t0 = time.time()
    try:
        for path, img, im0s, vid_cap in dataset:
            img = torch.from_numpy(img).to(device)
            img = img.half() if half else img.float()  # uint8 to fp16/32
            img /= 255.0  # 0 - 255 to 0.0 - 1.0
            if img.ndimension() == 3:
                img = img.unsqueeze(0)

            # Inference
            t1 = time_synchronized()
            pred = model(img, augment=opt.augment)[0]

            # Apply NMS
            pred = non_max_suppression(pred, opt.conf_thres, opt.iou_thres, classes=opt.classes, agnostic=opt.agnostic_nms)
            t2 = time_synchronized()

            # Apply Classifier
            if classify:
                pred = apply_classifier(pred, modelc, img, im0s)

            # Process detections
            for i, det in enumerate(pred):  # detections per image
                if webcam:  # batch_size >= 1
                    p, s, im0, frame = path[i], '%g: ' % i, im0s[i].copy(), dataset.count
                else:
                    p, s, im0, frame = path, '', im0s, getattr(dataset, 'frame', 0)

                p = Path(p)  # to Path
                save_path = str(save_dir / p.name)  # img.jpg
                txt_path = str(save_dir / 'labels' / p.stem) + ('' if dataset.mode == 'image' else f'_{frame}')  # img.txt
                s += '%gx%g ' % img.shape[2:]  # print string
                gn = torch.tensor(im0.shape)[[1, 0, 1, 0]]  # normalization gain whwh
                if len(det):
                    # Rescale boxes from img_size to im0 size
                    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                    # Print results
                    for c in det[:, -1].unique():
                        n = (det[:, -1] == c).sum()  # detections per class
                        s += f"{n} {names[int(c)]}{'s' * (n > 1)}, "  # add to string

                    # Write results
                    for *xyxy, conf, cls in reversed(det):
                        if save_txt:  # Write to file
                            xywh = (xyxy2xywh(torch.tensor(xyxy).view(1, 4)) / gn).view(-1).tolist()  # normalized xywh
                            line = (cls, *xywh, conf) if opt.save_conf else (cls, *xywh)  # label format
                            with open(txt_path + '.txt', 'a') as f:
                                f.write(('%g ' * len(line)).rstrip() % line + '\n')

                        if save_img or view_img or preview_state:  # Add bbox to image
                            label = f'{names[int(cls)]} {conf:.2f}'
                            plot_one_box(xyxy, im0, label=label, color=colors[int(cls)], line_thickness=3)

                # Print time (inference + NMS)
                print(f'{s}Done. ({t2 - t1:.3f}s)')

                # 更新帧数计数
                frame_count += 1

                # 计算FPS
                current_time = time.time()
                elapsed_time = current_time - start_time
                fps = frame_count / elapsed_time
                if view_img or preview_state:
                    # 在图像上绘制FPS信息
                    cv2.putText(im0, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                if preview_state:
                    preview_state.publish(im0)

                # Stream results
                if view_img:
                    cv2.imshow(str(p), im0)
                    cv2.waitKey(1)  # 1 millisecond

                # Save results (image with detections)
                if save_img:
                    if dataset.mode == 'image':
                        cv2.imwrite(save_path, im0)
                    else:  # 'video' or 'stream'
                        if vid_path != save_path:  # new video
                            vid_path = save_path
                            if isinstance(vid_writer, cv2.VideoWriter):
                                vid_writer.release()  # release previous video writer
                            if vid_cap:  # video
                                fps = vid_cap.get(cv2.CAP_PROP_FPS)
                                w = int(vid_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                                h = int(vid_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            else:  # stream
                                fps, w, h = 30, im0.shape[1], im0.shape[0]
                                save_path += '.mp4'
                            vid_writer = cv2.VideoWriter(save_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
                        vid_writer.write(im0)
    finally:
        if isinstance(vid_writer, cv2.VideoWriter):
            vid_writer.release()
        if preview_server:
            preview_server.shutdown()
            preview_server.server_close()

    if save_txt or save_img:
        s = f"\n{len(list(save_dir.glob('labels/*.txt')))} labels saved to {save_dir / 'labels'}" if save_txt else ''
        print(f"Results saved to {save_dir}{s}")

    print(f'Done. ({time.time() - t0:.3f}s)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights', nargs='+', type=str, default='weights/v5lite-c.pt', help='model.pt path(s)')
    parser.add_argument('--source', type=str, default='sample', help='source')  # file/folder, 0 for webcam
    parser.add_argument('--img-size', type=int, default=320, help='inference size (pixels)')
    parser.add_argument('--conf-thres', type=float, default=0.45, help='object confidence threshold')
    parser.add_argument('--iou-thres', type=float, default=0.5, help='IOU threshold for NMS')
    parser.add_argument('--device', default='', help='cuda device, i.e. 0 or 0,1,2,3 or cpu')
    parser.add_argument('--view-img', action='store_true', help='display results')
    parser.add_argument('--save-txt', action='store_true', help='save results to *.txt')
    parser.add_argument('--save-conf', action='store_true', help='save confidences in --save-txt labels')
    parser.add_argument('--nosave', action='store_true', help='do not save images/videos')
    parser.add_argument('--classes', nargs='+', type=int, help='filter by class: --class 0, or --class 0 2 3')
    parser.add_argument('--agnostic-nms', action='store_true', help='class-agnostic NMS')
    parser.add_argument('--augment', action='store_true', help='augmented inference')
    parser.add_argument('--update', action='store_true', help='update all models')
    parser.add_argument('--project', default='runs/detect', help='save results to project/name')
    parser.add_argument('--name', default='exp', help='save results to project/name')
    parser.add_argument('--exist-ok', action='store_true', help='existing project/name ok, do not increment')
    parser.add_argument('--preview', action='store_true', help='serve detected frames as an MJPEG preview page')
    parser.add_argument('--preview-host', default='0.0.0.0', help='preview server bind host')
    parser.add_argument('--preview-port', type=int, default=8080, help='preview server port')
    parser.add_argument('--preview-quality', type=int, default=70, help='preview JPEG quality 1-100')
    parser.add_argument('--preview-width', type=int, default=640, help='preview max width, 0 keeps original size')
    parser.add_argument('--preview-fps', type=float, default=10, help='preview max FPS, 0 disables throttling')
    opt = parser.parse_args()
    print(opt)
    check_requirements(exclude=('pycocotools', 'thop'))

    with torch.no_grad():
        if opt.update:  # update all models (to fix SourceChangeWarning)
            for opt.weights in ['yolov5s.pt', 'yolov5m.pt', 'yolov5l.pt', 'yolov5x.pt']:
                detect()
                strip_optimizer(opt.weights)
        else:
            detect()
