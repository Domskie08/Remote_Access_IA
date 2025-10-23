#!/usr/bin/env python3
import subprocess
import time
import psutil

CAM_DEVICE = "/dev/video0"
HTTP_PORT = 8080

RESOLUTIONS = {
    "1080p": ("1920x1080", "3M"),
    "720p": ("1280x720", "1.5M"),
    "480p": ("640x480", "800k"),
}

THRESHOLDS = [
    ("1080p", 25),  # ≤25 users
    ("720p", 30),  # 26–30 users
    ("480p", 40),  # 31–40 users
]

current_proc = None
current_res = None

def count_viewers():
    count = 0
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr.port == HTTP_PORT and conn.status == "ESTABLISHED":
            count += 1
    return count

def start_stream(res, bitrate):
    global current_proc
    if current_proc:
        current_proc.kill()

    print(f"[INFO] Starting camera at {res}, bitrate {bitrate}")
    cmd = [
        "ffmpeg",
        "-f", "v4l2", "-framerate", "25", "-video_size", res, "-i", CAM_DEVICE,
        "-vcodec", "h264_v4l2m2m", "-b:v", bitrate,
        "-f", "mpegts", f"tcp://0.0.0.0:{HTTP_PORT}?listen=1"
    ]
    current_proc = subprocess.Popen(cmd)

def choose_resolution(viewers):
    for res, limit in THRESHOLDS:
        if viewers <= limit:
            return res
    return "480p"

def main():
    global current_res
    while True:
        viewers = count_viewers()
        target_res = choose_resolution(viewers)

        if target_res != current_res:
            res, bitrate = RESOLUTIONS[target_res]
            start_stream(res, bitrate)
            current_res = target_res

        print(f"[INFO] Viewers={viewers}, Resolution={current_res}")
        time.sleep(10)

if __name__ == "__main__":
    main()
