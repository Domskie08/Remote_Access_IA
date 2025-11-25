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
THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1
CAMERA_DEVICE = 0       # /dev/video0

# *** IMPORTANT: Set to your camera USB path (example: "1-1.2") ***
USB_CAMERA_PATH = "1-3.5"
# ------------------------------------------------


# ---------------- USB CAMERA RESET ---------------
def usb_cam_off():
    """Unbind (turn OFF) the USB camera."""
    try:
        with open(f"/sys/bus/usb/devices/{USB_CAMERA_PATH}/driver/unbind", "w") as f:
            f.write(USB_CAMERA_PATH)
        print("🔌 USB Camera OFF (unbind)")
    except Exception as e:
        print("⚠ Failed to unbind camera:", e)

def usb_cam_on():
    """Rebind (turn ON) the USB camera."""
    try:
        with open(f"/sys/bus/usb/devices/{USB_CAMERA_PATH}/driver/bind", "w") as f:
            f.write(USB_CAMERA_PATH)
        print("🔌 USB Camera ON (bind)")
    except Exception as e:
        print("⚠ Failed to bind camera:", e)

def force_camera_reset():
    """Full USB reset: OFF → wait → ON."""
    print("♻️  FULL CAMERA RESET...")
    usb_cam_off()
    time.sleep(1)
    usb_cam_on()
    time.sleep(1)
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
    def __init__(self, device=0):
        self.device = device
        self.cap = None
        self.thread = None
        self.running = False

    def start(self):
        if self.cap is not None:
            return

        dev_path = f"/dev/video{self.device}"

        # Check device busy holders
        try:
            out = subprocess.check_output(["lsof", "-t", dev_path], stderr=subprocess.DEVNULL)
            holders = [int(x) for x in out.decode().split() if x.strip()]
            if holders:
                print(f"❌ {dev_path} busy by PIDs {holders}. Resetting USB...")
                force_camera_reset()
        except subprocess.CalledProcessError:
            pass  # free

        # Try to open camera after reset
        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            print("❌ Camera failed to open, retrying USB reset...")
            force_camera_reset()
            self.cap = cv2.VideoCapture(self.device)

        if not self.cap.isOpened():
            self.cap = None
            raise RuntimeError(f"Failed to open camera device {self.device}")

        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        while self.running and self.cap is not None:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            time.sleep(0.01)

    def stop(self):
        if self.cap is None:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
            self.thread = None
        try:
            self.cap.release()
        except:
            pass
        self.cap = None


camera = CameraController(device=CAMERA_DEVICE)
# ------------------------------------------------


# ---------------- STATE VARIABLES ----------------
last_seen = 0
camera_on = False
led_on = False
# ------------------------------------------------

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

        # ------------- PERSON DETECTED -------------
        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                try:
                    camera.start()
                    camera_on = True
                    print(f"🎥 Camera started! {distance} mm")
                except Exception as e:
                    print(f"❌ Camera unavailable: {e}")
                    camera_on = False

                lgpio.gpio_write(chip, LED_PIN, 1)
                led_on = True

        # ------------- STOP AFTER TIMEOUT -------------
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
    print("\nExiting...")

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
