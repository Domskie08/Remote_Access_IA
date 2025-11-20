import time
import lgpio
import requests
import VL53L0X

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.tof = VL53L0X.VL53L0X(i2c_bus=bus, i2c_address=address)
        self.tof.start_ranging(VL53L0X.VL53L0X_BEST_ACCURACY_MODE)

    def read_range(self):
        return self.tof.get_distance()

    # Keep old methods for compatibility, but they do nothing
    def _write(self, reg, value):
        pass

    def _read(self, reg):
        return 0

    def _read16(self, reg):
        return 0

# ------------ CONFIG ----------------
VL53_THRESHOLD = 1000
LED_PIN = 18
SERVER_URL = "http://YOUR_SERVER_IP:4173/api/camera"
SENSOR_POLL_DELAY = 0.1
AUTO_STOP_DELAY = 10
# ------------------------------------

# GPIO setup
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# VL53L0X setup
print("Initializing VL53L0X...")
sensor = VL53L0X()
time.sleep(0.2)
print("VL53L0X ready!")

last_seen = 0
is_camera_on = False

def trigger_camera(action):
    try:
        requests.post(SERVER_URL, json={"action": action}, timeout=1)
        print(f"📡 Camera: {action}")
    except Exception as e:
        print(f"❌ Camera request failed: {e}")

print("Starting monitoring loop...")

try:
    while True:
        distance = sensor.read_range()

        if 0 < distance <= VL53_THRESHOLD:
            last_seen = time.time()
            if not is_camera_on:
                is_camera_on = True
                trigger_camera("start_camera")
                lgpio.gpio_write(chip, LED_PIN, 1)
                print(f"🎥 START — Distance: {distance}mm")

        if is_camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            is_camera_on = False
            trigger_camera("stop_camera")
            lgpio.gpio_write(chip, LED_PIN, 0)
            print("🛑 STOP — no presence")

        print(f"Distance: {distance}mm  | Camera: {is_camera_on}")
        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("Exiting...")
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
