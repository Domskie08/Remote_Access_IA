import time
import threading
import requests
import urllib3
import lgpio
from VL53L0X import VL53L0X
import json
import sys
import traceback

# ---------------- CONFIGURATION ----------------
LED_PIN = 17
# central server base URL (example)
SERVER_URL = "https://<central_server_ip>:4173"
KIOSK_ID = "Kiosk_1"          # set per-device
TOKEN = None                  # if you use a token, set it here (will be appended to SSE URL as query param)
THRESHOLD = 400               # mm - sensor distance threshold to consider a person present
AUTO_STOP_DELAY = 10          # seconds to auto-stop camera after last detection
SENSOR_POLL_DELAY = 0.1       # seconds between sensor reads
HEARTBEAT_INTERVAL = 15       # seconds between heartbeats
SSE_RECONNECT_BASE = 1        # initial reconnect delay (sec)
SSE_RECONNECT_MAX = 30        # max reconnect delay (sec)
REQUEST_TIMEOUT = 5           # seconds for POSTs
# ----------------------------------------------

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------- GPIO SETUP --------------------
chip = None
try:
    chip = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(chip, LED_PIN)
    lgpio.gpio_write(chip, LED_PIN, 0)
except Exception as e:
    print("⚠️  Could not initialize lgpio:", e)
    chip = None
# ----------------------------------------------

# ---------------- SENSOR SETUP ------------------
sensor = None
try:
    sensor = VL53L0X()
    sensor.open()
    sensor.start_ranging()
    time.sleep(0.05)
except Exception as e:
    print("⚠️  VL53L0X init error:", e)
    sensor = None
# ----------------------------------------------

# State
camera_on = False
last_seen = 0.0
seen_request_ids = set()
stop_event = threading.Event()


def start_camera_local():
    """Start camera hardware/process and update LED/state. Replace with real camera start logic."""
    global camera_on
    if camera_on:
        return
    camera_on = True
    print("🎥 Camera started (local).")
    if chip:
        try:
            lgpio.gpio_write(chip, LED_PIN, 1)
        except Exception:
            pass
    # TODO: integrate real camera process start (e.g., start ffmpeg or capture service)


def stop_camera_local():
    """Stop camera hardware/process and update LED/state. Replace with real camera stop logic."""
    global camera_on
    if not camera_on:
        return
    camera_on = False
    print("🛑 Camera stopped (local).")
    if chip:
        try:
            lgpio.gpio_write(chip, LED_PIN, 0)
        except Exception:
            pass
    # TODO: integrate real camera stop (terminate process, release device)


def post_ack(requestId, status="executed", message="OK"):
    """Post ACK back to central server so it knows the command was executed."""
    url = f"{SERVER_URL}/api/device/ack"
    payload = {
        "requestId": requestId,
        "deviceId": KIOSK_ID,
        "status": status,
        "message": message,
        "timestamp": int(time.time())
    }
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT, verify=False)
        # optional: check resp.status_code
        # print("ACK posted:", resp.status_code, resp.text)
    except Exception as e:
        print("⚠️ Failed to post ACK:", e)


def post_heartbeat():
    """Periodic heartbeat to tell the server we're alive."""
    url = f"{SERVER_URL}/api/device/heartbeat"
    payload = {
        "deviceId": KIOSK_ID,
        "roomId": None,
        "cameraOn": camera_on,
        "uptime": int(time.time()),
        "timestamp": int(time.time())
    }
    headers = {"Content-Type": "application/json"}
    while not stop_event.is_set():
        try:
            requests.post(url, json=payload, timeout=REQUEST_TIMEOUT, verify=False)
        except Exception:
            # don't spam; just print minimal message
            print("⚠️ Heartbeat failed (server may be unreachable).")
        # send every HEARTBEAT_INTERVAL seconds
        for _ in range(HEARTBEAT_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)


def sensor_loop():
    """Poll the VL53L0X sensor; control camera locally and notify server (optional)."""
    global last_seen, camera_on
    while not stop_event.is_set():
        try:
            distance = 0
            if sensor:
                try:
                    distance = sensor.get_distance()
                except Exception:
                    distance = 0

            if 0 < distance <= THRESHOLD:
                last_seen = time.time()
                if not camera_on:
                    start_camera_local()
                    # optionally notify central server that camera started due to sensor:
                    try:
                        requests.post(
                            f"{SERVER_URL}/api/device/event",
                            json={"deviceId": KIOSK_ID, "type": "sensor_trigger", "distance_mm": distance, "timestamp": int(time.time())},
                            timeout=REQUEST_TIMEOUT, verify=False
                        )
                    except Exception:
                        pass

            # auto-stop if no detection for AUTO_STOP_DELAY
            if camera_on and (time.time() - last_seen > AUTO_STOP_DELAY):
                stop_camera_local()
                # optionally notify central server that camera stopped automatically
                try:
                    requests.post(
                        f"{SERVER_URL}/api/device/event",
                        json={"deviceId": KIOSK_ID, "type": "auto_stop", "timestamp": int(time.time())},
                        timeout=REQUEST_TIMEOUT, verify=False
                    )
                except Exception:
                    pass

        except Exception as e:
            print("Sensor loop error:", e)
            traceback.print_exc()

        # small sleep between polls
        time.sleep(SENSOR_POLL_DELAY)


def handle_command(command):
    """
    command is expected to be a dict with keys:
      - type: "command"
      - requestId
      - action: "start_camera" | "stop_camera"
    """
    try:
        if not isinstance(command, dict):
            return

        if command.get("type") != "command":
            return

        requestId = command.get("requestId") or command.get("id")
        if not requestId:
            # generate local id to ack if needed
            requestId = str(int(time.time() * 1000))

        # dedupe
        if requestId in seen_request_ids:
            print("Duplicate command, ignoring:", requestId)
            return
        seen_request_ids.add(requestId)

        action = command.get("action")
        print(f"Received command {requestId}: {action}")

        if action == "start_camera":
            start_camera_local()
            post_ack(requestId, status="executed", message="camera started")
        elif action == "stop_camera":
            stop_camera_local()
            post_ack(requestId, status="executed", message="camera stopped")
        else:
            print("Unknown action:", action)
            post_ack(requestId, status="failed", message=f"unknown action: {action}")

    except Exception as e:
        print("Error handling command:", e)
        traceback.print_exc()
        try:
            post_ack(requestId, status="failed", message=str(e))
        except Exception:
            pass


def sse_listener_loop():
    """
    Connect to SSE and stream incoming server events.
    Parses lines starting with 'data:' and expects JSON payload.
    Reconnects with exponential backoff on failure.
    """
    reconnect_delay = SSE_RECONNECT_BASE
    while not stop_event.is_set():
        try:
            url = f"{SERVER_URL}/sse?kiosk_id={KIOSK_ID}"
            if TOKEN:
                url += f"&token={TOKEN}"
            print("Connecting to SSE:", url)
            # stream=True to get continuous response
            with requests.get(url, stream=True, timeout=(5, None), verify=False) as resp:
                if resp.status_code != 200:
                    print("SSE server returned", resp.status_code, resp.text)
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, SSE_RECONNECT_MAX)
                    continue

                reconnect_delay = SSE_RECONNECT_BASE
                buffer = ""
                for raw in resp.iter_lines(decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if raw is None:
                        continue
                    line = raw.strip()
                    if not line:
                        # empty line = dispatch the event; handled as we parse data lines immediately
                        continue
                    if line.startswith(":"):
                        # comment / keep-alive
                        continue
                    if line.startswith("data:"):
                        data_text = line[len("data:"):].strip()
                        # data may be multi-line in SSE; requests iter_lines returns lines so we handle single-line JSON
                        try:
                            payload = json.loads(data_text)
                        except Exception:
                            # sometimes server sends plain text; ignore
                            print("SSE data not JSON:", data_text)
                            continue
                        # handle payload
                        handle_command(payload)
                    # ignore other fields (event:, id:, retry:) for now

        except Exception as e:
            print("SSE connection error:", e)
            # exponential backoff on reconnect
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, SSE_RECONNECT_MAX)

    print("SSE listener exiting.")


def main():
    print("Starting kiosk device:", KIOSK_ID)
    # Start sensor loop thread
    sensor_thread = threading.Thread(target=sensor_loop, daemon=True)
    sensor_thread.start()

    # Start heartbeat thread
    hb_thread = threading.Thread(target=post_heartbeat, daemon=True)
    hb_thread.start()

    # Start SSE listener (blocking loop in a thread so we can handle signals)
    sse_thread = threading.Thread(target=sse_listener_loop, daemon=True)
    sse_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        stop_event.set()
        # cleanup
        try:
            if sensor:
                sensor.stop_ranging()
                sensor.close()
        except Exception:
            pass
        try:
            if chip:
                lgpio.gpio_write(chip, LED_PIN, 0)
                lgpio.gpiochip_close(chip)
        except Exception:
            pass
        # give threads a moment
        time.sleep(1)
        print("Exited.")


if __name__ == "__main__":
    main()