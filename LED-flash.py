import time
import lgpio
import threading
import cv2
from flask import Flask, Response
from VL53L0X import VL53L0X
import socket
import os

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
THRESHOLD = 400         # mm; person detected if distance <= threshold
AUTO_STOP_DELAY = 10    # seconds to turn off camera/LED after no detection
SENSOR_POLL_DELAY = 0.1
CAMERA_DEVICE = 0       # /dev/video0
CAMERA_WIDTH = 1920     # 1080p width
CAMERA_HEIGHT = 1080
CAMERA_FPS = 25
MJPEG_QUALITY = 90

FLASK_PORT = 8443       # HTTPS port
CERT_DIR = "/home/admin/certs"
CERT_FILE = os.path.join(CERT_DIR, "mjpeg.crt")
KEY_FILE = os.path.join(CERT_DIR, "mjpeg.key")
# ------------------------------------------------

# ---------------- HELPER: AUTO IP ----------------
def get_local_ip():
    """Returns the Raspberry Pi's local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip
# ------------------------------------------------

# ---------------- GPIO SETUP --------------------
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)
# ------------------------------------------------

# ---------------- SENSOR SETUP ------------------
sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.05)
# ------------------------------------------------

# ---------------- CAMERA CONTROLLER -------------
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
# ------------------------------------------------

# ---------------- FLASK MJPEG SERVER -------------
app = Flask(__name__)

def mjpeg_generator():
    # Wait until the first frame is available
    while camera.get_frame() is None:
        time.sleep(0.01)
    while True:
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

@app.route("/stream.mjpg")
def stream():
    return Response(mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/")
def root():
    return "MJPEG Camera running over HTTPS."
# ------------------------------------------------

# ---------------- STATE VARIABLES ----------------
last_seen = 0
camera_on = False
led_on = False
# ------------------------------------------------

# ---------------- START FLASK SERVER ----------------
def run_flask():
    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        raise RuntimeError(f"Certificate or key file missing! Generate in {CERT_DIR}")
    app.run(host="0.0.0.0", port=FLASK_PORT, threaded=True,
            ssl_context=(CERT_FILE, KEY_FILE))

threading.Thread(target=run_flask, daemon=True).start()
pi_ip = get_local_ip()
print(f"🎥 MJPEG streaming available at https://{pi_ip}:{FLASK_PORT}/stream.mjpg")
# ------------------------------------------------

# ---------------- VL53L0X LOOP ----------------
print("Starting VL53L0X monitoring loop...")

try:
    while True:
        try:
            distance = sensor.get_distance()
        except Exception as e:
            print("⚠ Sensor read error:", e)
            distance = 0

        if distance == 0:
            print("Distance: out of range")
        else:
            print(f"Distance: {distance} mm")

        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                try:
                    camera.start()
                    camera_on = True
                    print(f"🎥 Camera started! Distance: {distance} mm")
                except Exception as e:
                    print(f"❌ Camera unavailable: {e}")
                    camera_on = False

            lgpio.gpio_write(chip, LED_PIN, 1)
            led_on = True

        if (camera_on or led_on) and (time.time() - last_seen > AUTO_STOP_DELAY):
            if camera_on:
                try:
                    camera.stop()
                    print("🛑 Camera stopped (no presence)")
                except Exception as e:
                    print(f"❌ Failed to stop camera: {e}")
                camera_on = False

            if led_on:
                lgpio.gpio_write(chip, LED_PIN, 0)
                led_on = False

        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("\nExiting program...")

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
