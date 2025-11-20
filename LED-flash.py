# -------------------------------------------------------------------
# VL53L0X Distance Detector + LED + Camera Trigger for Raspberry Pi 5
# (NO Blinka, NO board, NO busio — fully Pi5 compatible)
# -------------------------------------------------------------------

import time
import smbus2
import RPi.GPIO as GPIO
import requests

# ---------------- Configuration ----------------
VL53_THRESHOLD = 1000       # 1000 mm = 1 meter
LED_PIN = 18                # GPIO pin for LED flash
SERVER_URL = "http://YOUR_SERVER_IP:4173/api/camera"
SENSOR_POLL_DELAY = 0.1     # 100ms
AUTO_STOP_DELAY = 10        # 10 seconds after no detection
# ------------------------------------------------

# VL53L0X I2C address
VL53_ADDR = 0x29
bus = smbus2.SMBus(1)

# ------------- VL53L0X BASIC INITIALIZATION -------------
def write_reg(reg, value):
    bus.write_byte_data(VL53_ADDR, reg, value)

def read_range_mm():
    # Read distance registers (high + low bytes)
    high = bus.read_byte_data(VL53_ADDR, 0x1E)
    low = bus.read_byte_data(VL53_ADDR, 0x1F)
    distance = (high << 8) + low
    return distance
# ----------------------------------------------------------

# Setup GPIO LED
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

def trigger_camera(action: str):
    """Send POST to SvelteKit /api/camera endpoint."""
    try:
        requests.post(SERVER_URL, json={"action": action}, timeout=1)
        print(f"📡 Camera action sent: {action}")
    except Exception as e:
        print(f"❌ Failed to send camera action: {e}")

print("Starting VL53L0X distance monitoring...")

last_seen = 0
is_camera_on = False

try:
    while True:
        try:
            distance = read_range_mm()

            # Presence detected
            if 0 < distance <= VL53_THRESHOLD:
                last_seen = time.time()
                if not is_camera_on:
                    is_camera_on = True
                    trigger_camera("start_camera")
                    GPIO.output(LED_PIN, GPIO.HIGH)
                    print(f"🎥 Camera started! Distance: {distance} mm")

            # Auto-stop camera
            if is_camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
                is_camera_on = False
                trigger_camera("stop_camera")
                GPIO.output(LED_PIN, GPIO.LOW)
                print("🛑 Camera stopped (timeout)")

            print(f"Distance: {distance} mm | Camera ON: {is_camera_on}")
            time.sleep(SENSOR_POLL_DELAY)

        except OSError:
            print("⚠ I2C read failed, retrying...")
            time.sleep(0.2)

except KeyboardInterrupt:
    print("\nExiting...")
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.cleanup()
