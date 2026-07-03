"""Raw-socket HTTP/MJPEG preview server.

This module intentionally avoids socketserver/http.server so the demo keeps
working on minimal Raspberry Pi environments.
"""

import socket
import threading
import time

import cv2

from .constants import RASPBOT_AP_IP


def bgr8_to_jpeg(value, quality=75):
    """Encode an OpenCV BGR image as JPEG bytes for browser preview."""
    ok, encoded = cv2.imencode(
        '.jpg',
        value,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(max(1, min(100, quality)))],
    )
    if not ok:
        return None
    return encoded.tobytes()


class PreviewState:
    """Stores the latest JPEG frame and notifies MJPEG clients when it changes."""

    def __init__(self, quality=70, width=640, fps=10):
        self.quality = int(max(1, min(100, quality)))
        self.width = max(0, int(width))
        self.min_interval = 0 if fps <= 0 else 1.0 / float(fps)
        self.last_publish = 0.0
        self.jpeg = None
        self.frame_id = 0
        self.condition = threading.Condition()

    def publish(self, frame):
        """Publish a preview frame with FPS, width, and JPEG-quality throttling."""
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
    """Minimal HTTP/MJPEG server for remote browser preview."""

    def __init__(self, host, port, state):
        self.host = host
        self.port = port
        self.state = state
        self.running = False
        self.sock = None
        self.thread = None

    def start(self):
        """Start the background socket listener."""
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
        """Stop accepting new preview clients."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except socket.error:
                pass
            self.sock = None

    def serve_forever(self):
        """Accept HTTP clients and handle each client in a short-lived thread."""
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
        """Route one HTTP request to the index page, MJPEG stream, or snapshot."""
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
        """Send a normal HTTP response."""
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
        """Send the browser preview page."""
        content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Raspbot Posture Demo</title>
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
  <header>Raspbot Posture Demo - {RASPBOT_AP_IP}</header>
  <main><img src="/stream.mjpg" alt="Raspbot posture stream"></main>
</body>
</html>
""".encode('utf-8')
        self.send_response(conn, '200 OK', 'text/html; charset=utf-8', content)

    def send_snapshot(self, conn):
        """Send one JPEG snapshot."""
        with self.state.condition:
            frame = self.state.jpeg
        if frame is None:
            self.send_response(conn, '503 Service Unavailable', 'text/plain', b'No preview frame yet')
            return
        self.send_response(conn, '200 OK', 'image/jpeg', frame)

    def send_stream(self, conn):
        """Send a multipart MJPEG stream."""
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
    """Create preview state and start the MJPEG server."""
    state = PreviewState(quality=quality, width=width, fps=fps)
    server = PreviewServer(host, port, state)
    server.start()
    print(f'Preview server started: http://{RASPBOT_AP_IP}:{port}/ (bind {host}:{port})')
    return state, server

