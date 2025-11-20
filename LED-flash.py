#!/usr/bin/env python3
"""
Raspberry Pi 5: VL53L0X + LED + Camera Trigger (SvelteKit)
Runs inside venv.
"""

import time
import requests
import urllib3
import lgpio
from VL53L0X import VL53L0X

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SERVER_URL = "https://172.27.44.17:4173/api/camera"  # <-- change this
#curl -k -X POST https://172.27.44.17:4173/api/camera -H "Content-Type: application/json" -d '{"action": "start_camera"}'
THRESHOLD = 400       # mm; person detected if distance <= threshold
AUTO_STOP_DELAY = 10    # seconds to turn off camera/LED after no detection
SENSOR_POLL_DELAY = 0.1 # 100ms between distance reads
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

        # Person detected
        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                camera_on = True
                try:
                    requests.post(SERVER_URL, json={"action": "start_camera"}, timeout=5,verify=False)
                    print(f"🎥 Camera started! Distance: {distance} mm")
                except Exception as e:
                    print(f"❌ Camera start request failed: {e}")
                lgpio.gpio_write(chip, LED_PIN, 1)  # LED on

        # Auto-stop after timeout
        if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            camera_on = False
            try:
                requests.post(SERVER_URL, json={"action": "stop_camera"}, timeout=5,verify=False)
                print("🛑 Camera stopped (no presence)")
            except Exception as e:
                print(f"❌ Camera stop request failed: {e}")
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
