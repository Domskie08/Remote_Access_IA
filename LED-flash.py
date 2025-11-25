import time
import lgpio
import threading
import cv2
import subprocess
import os
import signal
from VL53L0X import VL53L0X

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
THRESHOLD = 400       # mm; person detected if distance <= threshold
AUTO_STOP_DELAY = 10    # seconds to turn off camera/LED after no detection
SENSOR_POLL_DELAY = 0.1 # 100ms between distance reads
CAMERA_DEVICE = 0       # /dev/video0
# ------------------------------------------------

# ---------------- GPIO SETUP --------------------
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)  # LED off
# ------------------------------------------------

# ---------------- SENSOR SETUP ------------------
sensor = VL53L0X()
sensor.open()
sensor.start_ranging()
time.sleep(0.05)  # warm-up delay for first measurement
# ------------------------------------------------

# ---------------- CAMERA CONTROLLER -------------
def release_device(dev='/dev/video0', term_timeout=1.0):
    """Try to free a V4L2 device by sending SIGTERM then SIGKILL to holders.
    Returns a list of PIDs that were signalled.
    """
    stopped = []
    try:
        out = subprocess.check_output(['lsof', '-t', dev], stderr=subprocess.DEVNULL)
        pids = [int(x) for x in out.decode().split() if x.strip()]
    except subprocess.CalledProcessError:
        # no process holds it
        return stopped

    # First try graceful termination
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
            print(f"Sent SIGTERM to PID {pid} holding {dev}")
        except Exception as e:
            print(f"Could not SIGTERM PID {pid}: {e}")

    # wait a bit
    time.sleep(term_timeout)

    # Force kill remaining holders if any
    try:
        out2 = subprocess.check_output(['lsof', '-t', dev], stderr=subprocess.DEVNULL)
        remaining = [int(x) for x in out2.decode().split() if x.strip()]
    except subprocess.CalledProcessError:
        remaining = []

    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"Sent SIGKILL to PID {pid} holding {dev}")
        except Exception as e:
            print(f"Could not SIGKILL PID {pid}: {e}")

    return stopped

class CameraController:
    """Simple controller to open/release a USB camera.
    Keeps a background thread reading frames so the device stays active."""
    def __init__(self, device=0):
        self.device = device
        self.cap = None
        self.thread = None
        self.running = False

    def start(self):
        if self.cap is not None:
            return  # already started
        # Try to release any process holding the device (e.g., a web streamer)
        dev_path = f"/dev/video{self.device}"
        try:
            release_device(dev_path)
        except Exception as e:
            print(f"Warning: failed to release device {dev_path}: {e}")

        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            self.cap = None
            raise RuntimeError(f"Failed to open camera device {self.device}")
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        # Continuous read; discard frames (prevents driver from sleeping)
        while self.running and self.cap is not None:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            # Frame consumed and discarded. Add processing here if needed.
            time.sleep(0.01)

    def stop(self):
        if self.cap is None:
            return
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=0.5)
            self.thread = None
        try:
            self.cap.release()
        except Exception:
            pass
        self.cap = None

camera = CameraController(device=CAMERA_DEVICE)
# ------------------------------------------------

# ---------------- STATE VARIABLES ----------------
last_seen = 0
camera_on = False
# ------------------------------------------------

print("Starting VL53L0X monitoring loop...")

try:
    while True:
        try:
            distance = sensor.get_distance()
        except Exception as e:
            print("⚠ Sensor read error:", e)
            distance = 0

        # Print distance every loop
        if distance == 0:
            print("Distance: out of range / not ready")
        else:
            print(f"Distance: {distance} mm")

        # Person detected -> start camera + LED
        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                camera_on = True
                try:
                    camera.start()
                    print(f"🎥 Camera started! Distance: {distance} mm")
                except Exception as e:
                    print(f"❌ Failed to start camera: {e}")
                    camera_on = False
                lgpio.gpio_write(chip, LED_PIN, 1)  # LED on

        # Auto-stop after timeout -> stop camera + LED
        if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            camera_on = False
            try:
                camera.stop()
                print("🛑 Camera stopped (no presence)")
            except Exception as e:
                print(f"❌ Failed to stop camera: {e}")
            lgpio.gpio_write(chip, LED_PIN, 0)  # LED off

        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("\nExiting program...")

finally:
    # Cleanup
    try:
        sensor.stop_ranging()
        sensor.close()
    except Exception:
        pass
    camera.stop()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
    print("Cleaned up GPIO, camera and sensor")