import asyncio
import websockets
import cv2
import threading
import time
import lgpio
from VL53L0X import VL53L0X
import json

# ---------------- CONFIG ----------------
LED_PIN = 17
THRESHOLD = 400  # mm
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1
CAMERA_DEVICE = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 25
DEVICE_NAME = "device1"  # Hardcoded per device

WS_PORT = 8765
# ----------------------------------------

# GPIO Setup
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# Sensor Setup
sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.05)

# Camera Controller
class CameraController:
    def __init__(self, device=0, width=1280, height=720, fps=25):
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
            ret, jpeg = cv2.imencode(".jpg", self.frame)
            if not ret:
                return None
            return jpeg.tobytes()

    def stop(self):
        self.running = False
        self.cap.release()

camera = CameraController(CAMERA_DEVICE, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS)

# ---------------- WebSocket Server ----------------
connected_frontends = set()

async def ws_handler(ws, path):
    print("Frontend connected")
    connected_frontends.add(ws)

    # Register device name on connection
    await ws.send(json.dumps({"type": "stream_url", "device": DEVICE_NAME}))

    try:
        while True:
            frame = camera.get_frame_bytes()
            if frame:
                # Send JPEG as base64
                await ws.send(json.dumps({
                    "type": "frame",
                    "device": DEVICE_NAME,
                    "data": frame.hex()  # can also use base64 if preferred
                }))
            await asyncio.sleep(1 / CAMERA_FPS)
    except websockets.exceptions.ConnectionClosed:
        print("Frontend disconnected")
    finally:
        connected_frontends.discard(ws)

async def main():
    server = await websockets.serve(ws_handler, "0.0.0.0", WS_PORT)
    print(f"🚀 Device {DEVICE_NAME} WebSocket server running on ws://0.0.0.0:{WS_PORT}")
    await server.wait_closed()

# ---------------- Sensor Loop ----------------
last_seen = 0
led_on = False
try:
    threading.Thread(target=lambda: asyncio.run(main()), daemon=True).start()
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
