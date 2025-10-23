#!/usr/bin/env python3
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- Configuration ---
CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080
RESOLUTION = "1280x720"  # 720p
FPS = "30"               # smooth and stable

# --- Start FFmpeg process (Direct MJPEG passthrough) ---
def start_ffmpeg():
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-input_format", "mjpeg",      # use webcam’s native MJPEG output
        "-framerate", FPS,
        "-video_size", RESOLUTION,
        "-i", CAM_DEVICE,
        "-f", "mjpeg",
        "-b:v", "4M",                 
        "pipe:1"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

# --- HTTP Stream Handler ---
class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/camera":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()

        print(f"[INFO] Client connected: {self.client_address}")
        try:
            buffer = b""
            while True:
                chunk = ffmpeg_proc.stdout.read(4096)
                if not chunk:
                    break
                buffer += chunk

                # Split JPEG frames by 0xFFD9 (end-of-frame marker)
                while b"\xff\xd9" in buffer:
                    frame, buffer = buffer.split(b"\xff\xd9", 1)
                    frame += b"\xff\xd9"
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
        except Exception:
            print(f"[INFO] Client disconnected: {self.client_address}")

# --- Run HTTP Server ---
def run_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
    print(f"[INFO] MJPEG stream running at http://{get_local_ip()}:{HTTP_PORT}/camera")
    server.serve_forever()

# --- Helper to get local IP ---
import socket
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# --- Main entry point ---
if __name__ == "__main__":
    ffmpeg_proc = start_ffmpeg()
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping stream...")
        ffmpeg_proc.kill()
