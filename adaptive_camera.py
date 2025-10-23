#!/usr/bin/env python3
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080
FPS = "30"
RESOLUTIONS = {
    "1080p": ("1920x1080", "8M"),
    "720p": ("1280x720", "4M"),
    "480p": ("640x480", "2M"),
}
CURRENT_MODE = "720p"
RESOLUTION, BITRATE = RESOLUTIONS[CURRENT_MODE]
def start_ffmpeg():
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-input_format", "mjpeg",  # use mjpeg if available
        "-framerate", FPS,
        "-video_size", RESOLUTION,
        "-i", CAM_DEVICE,
        "-vf", f"scale={RESOLUTION}",
        "-f", "mjpeg",
        "pipe:1",
        "-preset", "ultrafast", "-tune", "zerolatency"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

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
                # Split by JPEG frame boundary (FF D9 = end of JPEG)
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
