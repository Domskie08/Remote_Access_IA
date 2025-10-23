#!/usr/bin/env python3
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

# --- Configuration ---
CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080
RESOLUTION = "1280x720"
FPS = "30"
BITRATE = "4000k"  # 4 Mbps

# --- Start FFmpeg H.264 ---
def start_ffmpeg():
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-input_format", "yuyv422",       # raw frames for best quality
        "-video_size", RESOLUTION,
        "-framerate", FPS,
        "-i", CAM_DEVICE,
        "-c:v", "h264_v4l2m2m",           # hardware H.264 encoder
        "-b:v", BITRATE,
        "-f", "mpegts",
        "pipe:1"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

# --- HTTP Handler ---
class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/camera":  # ✅ same URL
            self.send_response(200)
            self.send_header("Content-type", "video/mp4")
            self.end_headers()
            print(f"[INFO] Client connected: {self.client_address}")
            try:
                while True:
                    data = ffmpeg_proc.stdout.read(4096)
                    if not data:
                        break
                    self.wfile.write(data)
            except Exception:
                print(f"[INFO] Client disconnected: {self.client_address}")
        else:
            self.send_response(404)
            self.end_headers()

# --- Helper to get local IP ---
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

# --- Run HTTP Server ---
def run_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
    print(f"[INFO] H.264 stream running at http://{get_local_ip()}:{HTTP_PORT}/camera")
    server.serve_forever()

# --- Main ---
if __name__ == "__main__":
    ffmpeg_proc = start_ffmpeg()
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping stream...")
        ffmpeg_proc.kill()
