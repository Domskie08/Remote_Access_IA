#!/usr/bin/env python3
import subprocess
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading

CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080
RESOLUTION = "1280x720"
FPS = "30"
BITRATE = "4000k"  # 4 Mbps

# --- FFmpeg H.264 Process ---
def start_ffmpeg():
    cmd = [
        "ffmpeg",
        "-f", "v4l2",
        "-input_format", "yuyv422",
        "-video_size", RESOLUTION,
        "-framerate", FPS,
        "-i", CAM_DEVICE,
        "-c:v", "h264_v4l2m2m",  # Pi hardware H.264
        "-b:v", BITRATE,
        "-f", "mpegts",
        "pipe:1"
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

# --- HTTP Handler ---
class VideoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            # Serve HTML page with video
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = f"""
            <html>
            <body style="margin:0;background:black;">
            <video width="{RESOLUTION.split('x')[0]}" height="{RESOLUTION.split('x')[1]}" controls autoplay muted>
                <source src="/stream" type="video/mp4">
                Your browser does not support video tag.
            </video>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/stream":
            # Serve H.264 stream
            self.send_response(200)
            self.send_header("Content-type", "video/mp4")
            self.end_headers()
            try:
                while True:
                    data = ffmpeg_proc.stdout.read(4096)
                    if not data:
                        break
                    self.wfile.write(data)
            except Exception:
                print("Client disconnected")
        else:
            self.send_response(404)
            self.end_headers()

# --- Run HTTP Server ---
def run_server():
    server = HTTPServer(("0.0.0.0", HTTP_PORT), VideoHandler)
    print(f"[INFO] Open browser at http://<raspi_ip>:{HTTP_PORT}/")
    server.serve_forever()

# --- Main ---
if __name__ == "__main__":
    ffmpeg_proc = start_ffmpeg()
    try:
        run_server()
    except KeyboardInterrupt:
        print("\n[INFO] Stopping stream...")
        ffmpeg_proc.kill()
