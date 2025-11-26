import time
import subprocess
import lgpio
import socket
from flask import Flask, jsonify
from VL53L0X import VL53L0X
from threading import Thread

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
MJPEG_STREAM_CMD = [
    "mjpg_streamer",
    "-i", "input_uvc.so -r 640x480 -f 30",
    "-o", "output_http.so -p 8080 -w ./www"
]
THRESHOLD = 400
AUTO_STOP_DELAY = 10
SENSOR_POLL_DELAY = 0.1
# ------------------------------------------------

# ---------------- AUTO DETECT IP ----------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

RASPI_IP = get_local_ip()
MJPEG_STREAM_URL = f"http://{RASPI_IP}:8080/?action=stream"
print(f"📡 Detected MJPEG stream URL: {MJPEG_STREAM_URL}")
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

# ---------------- STATE VARIABLES ----------------
last_seen = 0
camera_on = False
mjpeg_process = None
# ------------------------------------------------

# ---------------- FLASK SERVER ------------------
app = Flask(__name__)

@app.route("/api/stream-url")
def stream_url():
    return jsonify({"url": MJPEG_STREAM_URL})

def run_server():
    app.run(host="0.0.0.0", port=5000)
# ------------------------------------------------

# ---------------- SENSOR LOOP ------------------
def sensor_loop():
    global camera_on, mjpeg_process, last_seen

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

            # Person detected → start MJPEG
            if 0 < distance <= THRESHOLD:
                last_seen = time.time()
                if not camera_on:
                    camera_on = True
                    try:
                        mjpeg_process = subprocess.Popen(MJPEG_STREAM_CMD)
                        print(f"🎥 MJPEG-Streamer started! Stream URL: {MJPEG_STREAM_URL}")
                    except Exception as e:
                        print(f"❌ Failed to start MJPEG-Streamer: {e}")
                    lgpio.gpio_write(chip, LED_PIN, 1)

            # Auto-stop after timeout
            if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
                camera_on = False
                if mjpeg_process:
                    try:
                        mjpeg_process.terminate()
                        mjpeg_process.wait()
                        mjpeg_process = None
                        print("🛑 MJPEG-Streamer stopped (no presence)")
                    except Exception as e:
                        print(f"❌ Failed to stop MJPEG-Streamer: {e}")
                lgpio.gpio_write(chip, LED_PIN, 0)

            time.sleep(SENSOR_POLL_DELAY)

    except KeyboardInterrupt:
        print("\nExiting sensor loop...")
    finally:
        sensor.stop_ranging()
        sensor.close()
        lgpio.gpio_write(chip, LED_PIN, 0)
        lgpio.gpiochip_close(chip)
        if mjpeg_process:
            mjpeg_process.terminate()
            mjpeg_process.wait()
        print("Cleaned up GPIO, sensor, and MJPEG-Streamer")
# ------------------------------------------------

# ---------------- MAIN ------------------
if __name__ == "__main__":
    # Run Flask server in a separate thread
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()

    # Run sensor loop in main thread
    sensor_loop()
