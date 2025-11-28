import time
import requests
import urllib3
import lgpio
from VL53L0X import VL53L0X
import subprocess
import tkinter as tk
from tkinter import messagebox

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1

MAX_RETRIES = 3
RETRY_DELAY = 1
# ------------------------------------------------

# ---------------- GLOBAL VARIABLES --------------
WEB_URL = ""
SERVER_URL = ""
DEVICE_NAME = ""
# ------------------------------------------------


def start_program():
    """Triggered after user presses Enter on GUI"""
    global WEB_URL, SERVER_URL, DEVICE_NAME

    WEB_URL = url_entry.get().strip()
    DEVICE_NAME = device_entry.get().strip()

    if WEB_URL.endswith("/"):
        SERVER_URL = WEB_URL + "api/camera"
    else:
        SERVER_URL = WEB_URL + "/api/camera"

    if not WEB_URL or not DEVICE_NAME:
        messagebox.showerror("Error", "Please enter both URL and Device Name.")
        return

    print(f"WEB_URL: {WEB_URL}")
    print(f"SERVER_URL: {SERVER_URL}")
    print(f"DEVICE_NAME: {DEVICE_NAME}")

    # Close GUI window
    root.destroy()

    # Open Chromium in kiosk mode
    print("Launching Chromium kiosk...")
    subprocess.Popen([
        "chromium-browser",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--incognito",
        WEB_URL
    ])

    # Start the VL53L0X sensor loop
    start_sensor_loop()


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


def start_sensor_loop():
    """Main sensor loop AFTER GUI"""
    print("Initializing GPIO and VL53L0X...")

    chip = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(chip, LED_PIN)
    lgpio.gpio_write(chip, LED_PIN, 0)

    sensor = VL53L0X()
    sensor.open()
    sensor.start_ranging()
    time.sleep(0.05)

    last_seen = 0
    camera_on = False

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

            if 0 < distance <= THRESHOLD:
                last_seen = time.time()

                if not camera_on:
                    camera_on = True
                    trigger_camera("start_camera")
                    lgpio.gpio_write(chip, LED_PIN, 1)

            if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
                camera_on = False
                trigger_camera("stop_camera")
                lgpio.gpio_write(chip, LED_PIN, 0)

            time.sleep(SENSOR_POLL_DELAY)

    except KeyboardInterrupt:
        print("\nExiting program...")

    finally:
        sensor.stop_ranging()
        sensor.close()
        lgpio.gpio_write(chip, LED_PIN, 0)
        lgpio.gpiochip_close(chip)
        print("Cleaned up GPIO and sensor")


# ---------------- GUI SETUP ----------------
root = tk.Tk()
root.title("Sensor Configuration")
root.geometry("400x200")

tk.Label(root, text="Enter Web URL (example: https://172.27.44.17:4173)").pack(pady=5)
url_entry = tk.Entry(root, width=40)
url_entry.pack()

tk.Label(root, text="Enter Device Name (example: device1)").pack(pady=5)
device_entry = tk.Entry(root, width=40)
device_entry.pack()

start_button = tk.Button(root, text="ENTER", command=start_program, width=20)
start_button.pack(pady=20)

root.mainloop()
# ------------------------------------------------
