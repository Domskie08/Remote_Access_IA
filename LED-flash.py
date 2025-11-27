import asyncio
import websockets
import cv2
import threading
import time
import lgpio
from VL53L0X import VL53L0X
import json
import base64
import os
import ssl

# ---------------- CONFIG ----------------
LED_PIN = 17
THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1
CAMERA_DEVICE = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 15
DEVICE_NAME = "device1"  # Change per device: device1, device2, etc.

# Central server info
CENTRAL_WS = "wss://172.27.44.17:8765"  # laptop/server IP with TLS
CERT_DIR = "/home/admin/certs"
CERT_FILE = os.path.join(CERT_DIR, "mjpeg.crt")
KEY_FILE = os.path.join(CERT_DIR, "mjpeg.key")
# ----------------------------------------

# ---------------- TLS CONFIG ----------------
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.check_hostname = False  # skip hostname verification for local LAN
ssl_context.verify_mode = ssl.CERT_NONE  # skip cert verification if self-signed
# You could also use: ssl_context.load_verify_locations(CERT_FILE)

# ---------------- GPIO + SENSOR ----------------
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.05)

# ---------------- CAMERA ----------------
class CameraController:
    def __init__(self, device=0, width=1280, height=720, fps=15):
        self.cap = cv2.VideoCapture(device)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
            time.sleep(0.01)

    def get_frame_bytes(self):
        with self.lock:
            if self.frame is None:
                return None
            ret, jpeg = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ret:
                return None
            return base64.b64encode(jpeg.tobytes()).decode("utf-8")

    def stop(self):
        self.running = False
        self.cap.release()

camera = CameraController(CAMERA_DEVICE, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS)

# ---------------- WEBSOCKET CLIENT ----------------
async def connect_to_central():
    while True:
        try:
            async with websockets.connect(CENTRAL_WS, ssl=ssl_context) as ws:
                print(f"✅ Connected to central server as {DEVICE_NAME}")
                
                # Register this device
                await ws.send(json.dumps({
                    "type": "register",
                    "device": DEVICE_NAME
                }))

                # Send frames continuously
                while True:
                    frame_data = camera.get_frame_bytes()
                    if frame_data:
                        await ws.send(json.dumps({
                            "type": "frame",
                            "device": DEVICE_NAME,
                            "data": frame_data
                        }))
                    await asyncio.sleep(1 / CAMERA_FPS)

        except Exception as e:
            print(f"❌ Connection lost: {e}. Reconnecting in 3s...")
            await asyncio.sleep(3)

def start_ws_client():
    asyncio.run(connect_to_central())

threading.Thread(target=start_ws_client, daemon=True).start()

# ---------------- SENSOR LOOP ----------------
last_seen = 0
led_on = False

try:
    while True:
        distance = sensor.get_distance()
        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            lgpio.gpio_write(chip, LED_PIN, 1)
            led_on = True
        elif led_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            lgpio.gpio_write(chip, LED_PIN, 0)
            led_on = False
        time.sleep(SENSOR_POLL_DELAY)
except KeyboardInterrupt:
    print("Exiting...")
finally:
    sensor.stop_ranging()
    sensor.close()
    camera.stop()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
