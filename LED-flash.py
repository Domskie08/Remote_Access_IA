import time
import requests
import urllib3
import lgpio
from VL53L0X import VL53L0X

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SERVER_URL = "https://172.27.44.17:4173/api/camera"
DEVICE_NAME = "device1"  # Change per Raspberry Pi

THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1

MAX_RETRIES = 3        # Retry up to 3 times on request failure
RETRY_DELAY = 1        # Delay between retries (seconds)
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
time.sleep(0.05)  # warm-up delay
# ------------------------------------------------

# ---------------- STATE VARIABLES ----------------
last_seen = 0
camera_on = False
# ------------------------------------------------

def trigger_camera(action):
    """Send camera trigger with retries"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                SERVER_URL,
                json={"action": action, "device": DEVICE_NAME},
                verify=False,
                timeout=5
            )
            print(f"📸 {action} -> {response.status_code}")
            return True
        except Exception as e:
            print(f"❌ Attempt {attempt}: Failed to trigger camera ({e})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print("⚠ All retries failed.")
                return False

print("Starting VL53L0X monitoring loop...")

try:
    while True:
        try:
            distance = sensor.get_distance()
        except Exception as e:
            print("⚠ Sensor read error:", e)
            distance = 0

        if distance == 0:
            print("Distance: out of range / not ready")
        else:
            print(f"Distance: {distance} mm")

        # Person detected
        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                camera_on = True
                trigger_camera("start_camera")
                lgpio.gpio_write(chip, LED_PIN, 1)  # LED on

        # Auto-stop after timeout
        if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            camera_on = False
            trigger_camera("stop_camera")
            lgpio.gpio_write(chip, LED_PIN, 0)  # LED off

        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("\nExiting program...")
finally:
    # Cleanup
    sensor.stop_ranging()
    sensor.close()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
    print("Cleaned up GPIO and sensor")
