import time
import lgpio
import requests
from vl53l0x import VL53L0X

# ---------------- CONFIG ----------------
VL53_THRESHOLD = 1000       # mm
LED_PIN = 18                # GPIO18
SERVER_URL = "http://YOUR_SERVER_IP:4173/api/camera"
SENSOR_POLL_DELAY = 0.1     # 100ms
AUTO_STOP_DELAY = 10        # 10s no presence
# ----------------------------------------

# Setup LED via lgpio
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# Initialize VL53L0X
print("Initializing VL53L0X...")
sensor = VL53L0X()
print("Sensor ready!")

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

        # Person detected
        if 0 < distance <= VL53_THRESHOLD:
            last_seen = time.time()
            if not is_camera_on:
                is_camera_on = True
                trigger_camera("start_camera")
                lgpio.gpio_write(chip, LED_PIN, 1)
                print(f"🎥 START — Distance: {distance}mm")

        # Auto-stop
        if is_camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            is_camera_on = False
            trigger_camera("stop_camera")
            lgpio.gpio_write(chip, LED_PIN, 0)
            print("🛑 STOP — no presence")

        print(f"Distance: {distance}mm | Camera: {is_camera_on}")
        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("Exiting...")
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
