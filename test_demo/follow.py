#!/usr/bin/env python3
# coding: utf-8

import argparse
import math
import socket
import sys
import threading
import time

import cv2
import mediapipe as mp

sys.path.append('/home/pi/project_demo/lib')

import PID
from McLumk_Wheel_Sports import *


RASPBOT_AP_IP = '192.168.1.11'


def bgr8_to_jpeg(value, quality=75):
    ok, encoded = cv2.imencode(
        '.jpg',
        value,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, quality)))],
    )
    if not ok:
        return None
    return encoded.tobytes()


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

        jpeg = bgr8_to_jpeg(frame, quality=self.quality)
        if jpeg is None:
            return

        with self.condition:
            self.jpeg = jpeg
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
  <title>Raspbot Face Follow</title>
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
  <header>Raspbot Face Follow - {RASPBOT_AP_IP}</header>
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


direction_pid = PID.PositionalPID(0.8, 0, 0.2)
yservo_pid = PID.PositionalPID(0.8, 0.2, 0.01)
speed_pid = PID.PositionalPID(1.1, 0, 0.2)


def servo_reset():
    bot.Ctrl_Servo(1, 90)
    bot.Ctrl_Servo(2, 80)


def safe_stop(reset_servo=False):
    try:
        stop_robot()
    except Exception as exc:
        print(f'stop_robot failed: {exc}')

    if reset_servo:
        try:
            bot.Ctrl_Servo(1, 90)
            bot.Ctrl_Servo(2, 25)
        except Exception as exc:
            print(f'servo reset failed: {exc}')


class FaceDetector:
    def __init__(self, min_detection_confidence=0.5):
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            min_detection_confidence=min_detection_confidence,
        )

    def find_faces(self, frame):
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_detection.process(img_rgb)
        bbox = (0, 0, 0, 0)
        center_x = 0

        if results.detections:
            for detection_id, detection in enumerate(results.detections):
                bbox_c = detection.location_data.relative_bounding_box
                ih, iw, _ = frame.shape
                bbox = (
                    int(bbox_c.xmin * iw),
                    int(bbox_c.ymin * ih),
                    int(bbox_c.width * iw),
                    int(bbox_c.height * ih),
                )
                center_x = bbox[0] + bbox[2] // 2
                frame = self.fancy_draw(frame, bbox)
                break

        return frame, results.detections, bbox, center_x

    def fancy_draw(self, frame, bbox, l=30, t=5):
        x, y, w, h = bbox
        x1, y1 = x + w, y + h
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.line(frame, (x, y), (x + l, y), (0, 255, 0), t)
        cv2.line(frame, (x, y), (x, y + l), (0, 255, 0), t)
        cv2.line(frame, (x1, y), (x1 - l, y), (0, 255, 0), t)
        cv2.line(frame, (x1, y), (x1, y + l), (0, 255, 0), t)
        cv2.line(frame, (x, y1), (x + l, y1), (0, 255, 0), t)
        cv2.line(frame, (x, y1), (x, y1 - l), (0, 255, 0), t)
        cv2.line(frame, (x1, y1), (x1 - l, y1), (0, 255, 0), t)
        cv2.line(frame, (x1, y1), (x1, y1 - l), (0, 255, 0), t)
        return frame


def open_camera(source, width, height):
    camera = cv2.VideoCapture(source)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not camera.isOpened():
        raise RuntimeError(f'camera source {source} could not be opened')
    return camera


def draw_status(frame, radius, target_valuex, speed_value):
    text = f'face_radius {int(radius)} target_x {target_valuex} speed {speed_value}'
    cv2.putText(frame, text, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)


def face_follow(camera, preview_state, stop_event):
    speed = 30
    face_detector = FaceDetector(0.75)
    image_width = camera.get(cv2.CAP_PROP_FRAME_WIDTH) or 640
    image_height = camera.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480

    while not stop_event.is_set():
        ret, frame = camera.read()
        if not ret or frame is None:
            safe_stop()
            time.sleep(0.05)
            continue

        faces, detections, bbox, center_x = face_detector.find_faces(frame)
        x, y, w, h = bbox

        if detections:
            direction_pid.SystemOutput = center_x
            direction_pid.SetStepSignal(int(image_width / 2))
            direction_pid.SetInertiaTime(0.01, 0.05)
            target_valuex = int(direction_pid.SystemOutput + 65)

            if math.fabs(int(image_height / 2) - (y + h / 2)) > 40:
                yservo_pid.SystemOutput = y + h / 2
                yservo_pid.SetStepSignal(int(image_height / 2))
                yservo_pid.SetInertiaTime(0.01, 0.05)
                target_valuey = int(850 + yservo_pid.SystemOutput)
                target_servoy = int((target_valuey - 500) / 10)
                target_servoy = max(0, min(100, target_servoy))
                bot.Ctrl_Servo(2, target_servoy)

            speed_pid.SystemOutput = int(h / 2)
            speed_pid.SetStepSignal(80)
            speed_pid.SetInertiaTime(0.01, 0.1)
            speed_value = int(speed_pid.SystemOutput)
            speed_value = max(0, min(255, speed_value))

            draw_status(faces, h / 2, target_valuex, speed_value)

            if target_valuex > 50:
                rotate_left(int(speed / 5))
            elif target_valuex < -50:
                rotate_right(int(speed / 5))
            elif 75 < h / 2 < 100:
                stop_robot()
            elif h / 2 > 60:
                if abs(target_valuex) < 30:
                    move_backward(speed)
            elif 20 < h / 2 < 55:
                if abs(target_valuex) < 30:
                    move_forward(speed_value)
            else:
                stop_robot()
        else:
            stop_robot()

        if preview_state:
            preview_state.publish(faces)


def parse_args():
    parser = argparse.ArgumentParser(description='Raspbot face-follow controller with web preview')
    parser.add_argument('--source', default='0', help='camera source, usually 0')
    parser.add_argument('--width', type=int, default=640, help='camera width')
    parser.add_argument('--height', type=int, default=480, help='camera height')
    parser.add_argument('--no-preview', action='store_true', help='disable web preview')
    parser.add_argument('--preview-host', default='0.0.0.0', help='preview server bind host')
    parser.add_argument('--preview-port', type=int, default=8080, help='preview server port')
    parser.add_argument('--preview-quality', type=int, default=70, help='preview JPEG quality 1-100')
    parser.add_argument('--preview-width', type=int, default=640, help='preview max width, 0 keeps original size')
    parser.add_argument('--preview-fps', type=float, default=10, help='preview max FPS, 0 disables throttling')
    return parser.parse_args()


def main():
    args = parse_args()
    source = int(args.source) if str(args.source).isdigit() else args.source
    preview_state, preview_server = None, None
    stop_event = threading.Event()
    camera = None

    try:
        servo_reset()
        camera = open_camera(source, args.width, args.height)

        if not args.no_preview:
            preview_state, preview_server = start_preview_server(
                args.preview_host,
                args.preview_port,
                args.preview_quality,
                args.preview_width,
                args.preview_fps,
            )

        print('Face follow started. Press Ctrl+C to stop.')
        face_follow(camera, preview_state, stop_event)
    except KeyboardInterrupt:
        print('\nStopping face follow...')
    finally:
        stop_event.set()
        safe_stop(reset_servo=True)
        if camera is not None:
            camera.release()
        if preview_server:
            preview_server.shutdown()


if __name__ == '__main__':
    main()
