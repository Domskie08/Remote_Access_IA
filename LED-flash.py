# raspi_device.py
import asyncio
import websockets
import json
import base64
import cv2
import time
import ssl
import os
import lgpio
from VL53L0X import VL53L0X

# ---------------- CONFIG ----------------
LED_PIN = 17
THRESHOLD = 400            # Sensor threshold in mm
AUTO_STOP_DELAY = 10       # LED auto-off delay (seconds)
SENSOR_POLL_DELAY = 0.1    # Sensor polling interval
CAMERA_DEVICE = 0
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 15
DEVICE_NAME = "device1"
CENTRAL_WS = "wss://172.27.44.17:8765"  # Central server WSS URL

# ---------------- TLS CONFIG ----------------
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE  # For self-signed certs

# ---------------- GPIO ----------------
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# ---------------- SENSOR ----------------
sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.2)  # Give sensor time to stabilize

# ---------------- CAMERA ----------------
class CameraController:
    def __init__(self, device=0, width=1280, height=720, fps=15):
        self.cap = cv2.VideoCapture(device)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.running = True

    def get_frame_base64(self):
        if not self.running:
            return None
        ret, frame = self.cap.read()
        if not ret:
            return None
        ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            return None
        return base64.b64encode(jpeg.tobytes()).decode("utf-8")

    def stop(self):
        self.running = False
        self.cap.release()

camera = CameraController(CAMERA_DEVICE, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS)

# ---------------- SENSOR + LED STATE ----------------
last_seen = 0
led_on = False

def poll_sensor():
    global last_seen, led_on
    distance = sensor.get_distance()
    if 0 < distance <= THRESHOLD:
        last_seen = time.time()
        if not led_on:
            lgpio.gpio_write(chip, LED_PIN, 1)
            led_on = True
    elif led_on and (time.time() - last_seen > AUTO_STOP_DELAY):
        lgpio.gpio_write(chip, LED_PIN, 0)
        led_on = False
    return distance

# ---------------- WEBSOCKET CLIENT ----------------
async def connect_to_central():
    while True:
        try:
            async with websockets.connect(CENTRAL_WS, ssl=ssl_context) as ws:
                print(f"✅ Connected to central server as {DEVICE_NAME}")

                # Register device
                await ws.send(json.dumps({
                    "type": "register",
                    "device": DEVICE_NAME
                }))

                # Main loop: capture frame + sensor
                while True:
                    frame_data = camera.get_frame_base64()
                    distance = poll_sensor()

                    if frame_data:
                        msg = {
                            "type": "frame",
                            "device": DEVICE_NAME,
                            "data": frame_data,
                            "sensor": {"distance_mm": distance}
                        }
                        await ws.send(json.dumps(msg))

                    await asyncio.sleep(1 / CAMERA_FPS)

        except Exception as e:
            print(f"❌ Connection lost: {e}. Reconnecting in 3s...")
            await asyncio.sleep(3)

# ---------------- MAIN ----------------
try:
    asyncio.run(connect_to_central())

except KeyboardInterrupt:
    print("Exiting...")

finally:
    sensor.stop_ranging()
    sensor.close()
    camera.stop()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
