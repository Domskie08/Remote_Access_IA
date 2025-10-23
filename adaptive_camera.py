#!/usr/bin/env python3
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080
RESOLUTION = "640x480"
FPS = "15"

# Start FFmpeg process (produces MJPEG to stdout)
def start_ffmpeg():
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-framerate", FPS,
        "-video_size", RESOLUTION,
        "-i", CAM_DEVICE,
        "-vf", "format=yuv420p",
        "-q:v", "5",  # quality (1 = best, 31 = worst)
        "-f", "mjpeg",
        "pipe:1",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

# HTTP handler serving MJPEG
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
            while True:
                # Read frame from ffmpeg stdout
                data = ffmpeg_proc.stdout.readline()
                if not data:
                    break
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
        except Exception:
            print(f"[INFO] Client disconnected: {self.client_address}")

def run_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), StreamHandler)
    print(f"[INFO] MJPEG stream running at http://10.186.3.133:{HTTP_PORT}/camera")
    server.serve_forever()

if __name__ == "__main__":
    ffmpeg_proc = start_ffmpeg()
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping stream...")
        ffmpeg_proc.kill()
