import time
import lgpio
import threading
import cv2
from flask import Flask, Response
from VL53L0X import VL53L0X
import socket
import os
import asyncio
import websockets
import json
import threading

# -----------------------------------
# HARD-CODE DEVICE NAME HERE
DEVICE_NAME = "device1"
CENTRAL_WS = "ws://192.168.100.15:8765"      # <--- change to your laptop/server IP
CERT_DIR = "/home/admin/certs"
CERT_FILE = os.path.join(CERT_DIR, "mjpeg.crt")
KEY_FILE = os.path.join(CERT_DIR, "mjpeg.key")
# -----------------------------------

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1
CAMERA_DEVICE = 0
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_FPS = 25
MJPEG_QUALITY = 90
FLASK_PORT = 8080
# ------------------------------------------------

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

# ---------------- GPIO SETUP --------------------
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# -------------- SENSOR SETUP --------------------
sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.05)

# ---------------- CAMERA ------------------------
class CameraController:
    def __init__(self, device=0, width=1920, height=1080, fps=25, quality=90):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.quality = quality
        self.cap = None
        self.running = False
        self.thread = None
        self.frame = None
        self.lock = threading.Lock()

    def start(self):
        if self.cap is not None:
            return

        self.cap = cv2.VideoCapture(self.device)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        if not self.cap.isOpened():
            self.cap = None
            raise RuntimeError(f"Failed to open camera device {self.device}")

        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            with self.lock:
                self.frame = frame
            time.sleep(0.01)

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            ret, jpeg = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if not ret:
                return None
            return jpeg.tobytes()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
            self.thread = None
        if self.cap:
            self.cap.release()
            self.cap = None

camera = CameraController(
    device=CAMERA_DEVICE,
    width=CAMERA_WIDTH,
    height=CAMERA_HEIGHT,
    fps=CAMERA_FPS,
    quality=MJPEG_QUALITY
)

# ---------------- FLASK MJPEG SERVER -------------
app = Flask(__name__)

def mjpeg_generator():
    while True:
        try:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                frame +
                b"\r\n"
            )
        except (BrokenPipeError, ConnectionResetError):
            print("Client disconnected")
            break
        except Exception as e:
            print("MJPEG generator error:", e)
            time.sleep(0.01)

@app.route("/stream.mjpg")
def stream():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/")
def root():
    return "MJPEG Camera running over HTTP."

@app.route("/api/pi-ip")
def api_pi_ip():
    return {"ip": get_local_ip()}

# ---------------- START FLASK SERVER ----------------
def run_flask():
    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        raise RuntimeError(f"Certificate or key file missing! Generate in {CERT_DIR}")
    
    # Enable HTTPS
    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        threaded=True,
        ssl_context=(CERT_FILE, KEY_FILE)  # <-- this enables HTTPS
    )

threading.Thread(target=run_flask, daemon=True).start()
pi_ip = get_local_ip()
print(f"🎥 MJPEG streaming available at https://{pi_ip}:{FLASK_PORT}/stream.mjpg")
# ------------------------------------------------

# ---------------- WEBSOCKET CLIENT ----------------
async def ws_loop():
    while True:
        try:
            async with websockets.connect(CENTRAL_WS) as ws:
                print("Connected to central WebSocket server")

                # register device
                await ws.send(json.dumps({
                    "type": "register",
                    "device": DEVICE_NAME
                }))

                async for msg in ws:
                    data = json.loads(msg)
                    if data["type"] == "stream_url":
                        print(f"Central server confirmed stream URL: {data['url']}")

        except Exception as e:
            print("WebSocket error:", e)
            await asyncio.sleep(5)

# run WS in background thread
def start_ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_loop())

threading.Thread(target=start_ws_thread, daemon=True).start()

# ---------------- VL53L0X LOOP ----------------
print("Starting VL53L0X monitoring loop...")

last_seen = 0
camera_on = False
led_on = False

try:
    while True:
        try:
            distance = sensor.get_distance()
        except:
            distance = 0

        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                try:
                    camera.start()
                    camera_on = True
                    print(f"🎥 Camera started! {distance} mm")
                except Exception as e:
                    print("Camera start failed:", e)

            lgpio.gpio_write(chip, LED_PIN, 1)
            led_on = True

        if (camera_on or led_on) and (time.time() - last_seen > AUTO_STOP_DELAY):
            if camera_on:
                camera.stop()
                camera_on = False
                print("🛑 Camera stopped (no presence)")

            if led_on:
                lgpio.gpio_write(chip, LED_PIN, 0)
                led_on = False

        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    try:
        sensor.stop_ranging()
        sensor.close()
    except:
        pass
    camera.stop()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
    print("Cleanup done.")
