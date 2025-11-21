import time
import requests
import urllib3
import lgpio
import os
import subprocess
from VL53L0X import VL53L0X

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SERVER_URL = "https://172.27.44.17:4173/api/camera"  # <-- change this
THRESHOLD = 400       # mm; person detected if distance <= threshold
AUTO_STOP_DELAY = 10    # seconds to turn off camera/LED/USB after no detection
SENSOR_POLL_DELAY = 0.1 # 100ms between distance reads
USB_FAILSAFE = True     # If True, skips USB ports that appear to be controllers (keyboard/mouse)
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

def usb_off():
    usb_devices = os.listdir("/sys/bus/usb/drivers/usb")
    for dev in usb_devices:
        if dev.startswith("usb"):
            continue
        if USB_FAILSAFE and ("1-1" in dev or "1-2" in dev):
            continue
        try:
            subprocess.run(
                f"echo {dev} | sudo tee /sys/bus/usb/drivers/usb/unbind",
                shell=True, check=True
            )
            print(f"🔌 USB {dev} OFF")
        except Exception as e:
            print(f"❌ Failed to unbind {dev}: {e}")

def usb_on():
    usb_devices = os.listdir("/sys/bus/usb/drivers/usb")
    for dev in usb_devices:
        if dev.startswith("usb"):
            continue
        try:
            subprocess.run(
                f"echo {dev} | sudo tee /sys/bus/usb/drivers/usb/bind",
                shell=True, check=True
            )
            print(f"🔌 USB {dev} ON")
        except Exception as e:
            print(f"❌ Failed to bind {dev}: {e}")

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
                try:
                    requests.post(SERVER_URL, json={"action": "start_camera"}, timeout=5,verify=False)
                    print(f"🎥 Camera started! Distance: {distance} mm")
                except Exception as e:
                    print(f"❌ Camera start request failed: {e}")
                lgpio.gpio_write(chip, LED_PIN, 1)  # LED on
                usb_on()  # Turn on USB devices (touchscreen)

        # Auto-stop after timeout
        if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
            camera_on = False
            try:
                requests.post(SERVER_URL, json={"action": "stop_camera"}, timeout=5,verify=False)
                print("🛑 Camera stopped (no presence)")
            except Exception as e:
                print(f"❌ Camera stop request failed: {e}")
            lgpio.gpio_write(chip, LED_PIN, 0)  # LED off
            usb_off()  # Turn off USB devices

        time.sleep(SENSOR_POLL_DELAY)

except KeyboardInterrupt:
    print("\nExiting program...")
finally:
    # Cleanup
    sensor.stop_ranging()
    sensor.close()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
    usb_on()  # Ensure USB is back on after exit
    print("Cleaned up GPIO, sensor, and USB devices")
