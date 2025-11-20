import time
import requests
import board
import busio
import adafruit_vl53l0x
import RPi.GPIO as GPIO

# ==== SETTINGS ====
SERVER_URL = "http://DESKTOP-R98PM6A.local:4173/api/camera"  # ✅ FIXED: No /start_camera
DISTANCE_THRESHOLD = 500  # mm
NO_PERSON_TIMEOUT = 10    # seconds before stop
LED_PIN = 17             # GPIO pin for LED

# ==== INITIALIZE ====
i2c = busio.I2C(board.SCL, board.SDA)
vl53 = adafruit_vl53l0x.VL53L0X(i2c)

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

camera_started = False
last_seen_time = 0

print("📏 VL53L0X distance sensor monitoring started...")

try:
    while True:
        distance = vl53.range  # distance in mm
        now = time.time()

        print(f"Distance: {distance} mm")

        # ✅ Person detected (<= 500mm)
        if distance <= DISTANCE_THRESHOLD:
            last_seen_time = now
            if not camera_started:
                print("👤 Person detected - starting camera & LED ON")
                GPIO.output(LED_PIN, GPIO.HIGH)
                try:
                    resp = requests.post(SERVER_URL, json={"action": "start_camera"}, timeout=5)
                    print("✅ Server responded:", resp.status_code, resp.text)
                except Exception as e:
                    print("⚠️ Failed to notify server:", e)
                camera_started = True

        # 🚫 No person detected for a while
        elif camera_started and (now - last_seen_time) > NO_PERSON_TIMEOUT:
            print("🚶 No person for 10s - stopping camera & LED OFF")
            GPIO.output(LED_PIN, GPIO.LOW)
            try:
                resp = requests.post(SERVER_URL, json={"action": "stop_camera"}, timeout=5)
                print("✅ Server responded:", resp.status_code, resp.text)
            except Exception as e:
                print("⚠️ Failed to notify server:", e)
            camera_started = False

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n🛑 Stopped by user")

finally:
    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.cleanup()