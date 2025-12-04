#!/usr/bin/env python3
"""
Raspberry Pi 5 Turnstile Controller
====================================
Connects to SvelteKit SSE endpoint and controls solenoid via GPIO

Hardware Setup:
- GPIO 17: Solenoid relay (unlock turnstile)
- GPIO 27: LED indicator (optional status LED)
- Yuriot ScanCode Box: USB QR/Barcode scanner (auto-detected)

Requirements:
- pip3 install requests lgpio
- Run with sudo: sudo python3 turnstile-controller.py
- Connect Yuriot ScanCode Box scanner before starting
- Test scanner: sudo python3 turnstile-controller.py test
"""

import time
import json
import requests
import lgpio
import subprocess
import threading
import urllib3
import glob
import os

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------- CONFIGURATION ----------------
SOLENOID_PIN = 17       # GPIO pin for solenoid relay
LED_PIN = 27            # GPIO pin for status LED (optional)
PORT = "5173"           # SvelteKit dev port (use 4173 for preview)
UNLOCK_DURATION = 3     # Seconds to keep solenoid energized
WEB_URL = f"https://172.27.44.17:{PORT}/"
SSE_URL = f"https://172.27.44.17:{PORT}/api/turnstile"
DEVICE_NAME = "device1"  # Default device name
# ------------------------------------------------

# ---------------- GLOBAL VARIABLES --------------
chip = None
sse_thread = None
running = False
# ------------------------------------------------


def wait_for_scanner():
    """Wait for Yuriot ScanCode Box scanner to be connected"""
    print("🔍 Looking for Yuriot ScanCode Box scanner...")

    max_attempts = 30  # Wait up to 30 seconds
    attempt = 0

    while attempt < max_attempts:
        try:
            # Check if scanner is connected via lsusb
            result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
            print(f"🔍 lsusb output: {result.stdout[:200]}...")  # Debug: show first 200 chars

            # Check for various possible names
            scanner_names = ['Yuriot', 'YuRiot', 'ScanCode Box', 'Scan Box', 'Barcode', 'Scanner']
            detected = False
            for name in scanner_names:
                if name.lower() in result.stdout.lower():
                    print(f"✅ Scanner detected via lsusb: {name}")
                    detected = True
                    break

            if detected:
                return True

            # Check recent kernel messages for USB connections
            dmesg_result = subprocess.run(['dmesg', '--time-format=iso', '--since=-30seconds'],
                                        capture_output=True, text=True, timeout=5)
            print(f"🔍 Recent dmesg: {dmesg_result.stdout[-200:]}...")  # Debug: show last 200 chars

            for name in scanner_names:
                if name.lower() in dmesg_result.stdout.lower():
                    print(f"✅ Scanner detected in logs: {name}")
                    return True

            # Check HID devices and their details
            hid_devices = glob.glob('/dev/hidraw*')
            print(f"🔍 Found HID devices: {hid_devices}")

            if hid_devices:
                for device in hid_devices:
                    try:
                        # Check device name
                        device_name_path = f"/sys/class/hidraw/{os.path.basename(device)}/device/uevent"
                        if os.path.exists(device_name_path):
                            with open(device_name_path, 'r') as f:
                                uevent_content = f.read()
                                print(f"🔍 HID device {device}: {uevent_content[:100]}...")

                                for name in scanner_names:
                                    if name.lower() in uevent_content.lower():
                                        print(f"✅ Scanner detected via HID: {name}")
                                        return True

                        # Check manufacturer and product
                        manufacturer_path = f"/sys/class/hidraw/{os.path.basename(device)}/device/manufacturer"
                        product_path = f"/sys/class/hidraw/{os.path.basename(device)}/device/product"

                        manufacturer = ""
                        product = ""

                        if os.path.exists(manufacturer_path):
                            with open(manufacturer_path, 'r') as f:
                                manufacturer = f.read().strip()
                        if os.path.exists(product_path):
                            with open(product_path, 'r') as f:
                                product = f.read().strip()

                        print(f"🔍 HID {device} - Manufacturer: '{manufacturer}', Product: '{product}'")

                        # Check if this looks like a scanner
                        scanner_keywords = ['yuriot', 'scan', 'barcode', 'scanner', 'reader']
                        if any(keyword in (manufacturer + product).lower() for keyword in scanner_keywords):
                            print(f"✅ Scanner detected by keywords: {manufacturer} {product}")
                            return True

                    except Exception as e:
                        print(f"⚠️ Error checking HID device {device}: {e}")
                        continue

        except Exception as e:
            print(f"⚠️ Error checking for scanner: {e}")

        attempt += 1
        if attempt < max_attempts:
            print(f"⏳ Waiting for scanner... ({attempt}/{max_attempts})")
            time.sleep(1)

    print("❌ Yuriot ScanCode Box scanner not found within timeout")
    print("💡 Make sure the scanner is connected and powered on")
    print("💡 Try running: lsusb | grep -i scan")
    print("💡 Or check: ls -la /dev/hidraw*")
    return False


def gpio_setup():
    """Initialize GPIO pins"""
    global chip

    chip = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_output(chip, SOLENOID_PIN)
    lgpio.gpio_claim_output(chip, LED_PIN)
    lgpio.gpio_write(chip, SOLENOID_PIN, 0)  # Start locked
    lgpio.gpio_write(chip, LED_PIN, 0)       # LED off
    print("✅ GPIO initialized")


def gpio_cleanup():
    """Clean up GPIO on exit"""
    global chip
    if chip:
        lgpio.gpio_write(chip, SOLENOID_PIN, 0)
        lgpio.gpio_write(chip, LED_PIN, 0)
        lgpio.gpiochip_close(chip)
        print("✅ GPIO cleaned up")


def unlock_turnstile(student_name=None):
    """Energize solenoid to unlock turnstile"""
    print(f"🔓 UNLOCKING TURNSTILE" + (f" for {student_name}" if student_name else ""))
    lgpio.gpio_write(chip, SOLENOID_PIN, 1)
    lgpio.gpio_write(chip, LED_PIN, 1)  # LED on
    time.sleep(UNLOCK_DURATION)
    lgpio.gpio_write(chip, SOLENOID_PIN, 0)
    lgpio.gpio_write(chip, LED_PIN, 0)
    print("🔒 Turnstile locked")


def lock_turnstile():
    """De-energize solenoid to lock turnstile"""
    lgpio.gpio_write(chip, SOLENOID_PIN, 0)
    lgpio.gpio_write(chip, LED_PIN, 0)
    print("🔒 Turnstile locked")


def sse_listener():
    """Listen to SSE events from SvelteKit server"""
    global running

    print(f"📡 Connecting to SSE: {SSE_URL}")

    while running:
        try:
            # Use requests with stream=True for SSE
            response = requests.get(SSE_URL, stream=True, verify=False, timeout=60)

            for line in response.iter_lines():
                if not running:
                    break

                if line:
                    line_str = line.decode('utf-8')

                    # Skip heartbeat comments
                    if line_str.startswith(':'):
                        continue

                    # Parse SSE data
                    if line_str.startswith('data:'):
                        data_str = line_str[5:].strip()
                        try:
                            data = json.loads(data_str)
                            handle_sse_event(data)
                        except json.JSONDecodeError:
                            print(f"⚠️ Invalid JSON: {data_str}")

        except requests.exceptions.Timeout:
            print("⏱️ SSE connection timeout, reconnecting...")
        except requests.exceptions.ConnectionError as e:
            print(f"❌ Connection error: {e}")
            print("🔄 Reconnecting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            print(f"❌ SSE error: {e}")
            time.sleep(5)


def handle_sse_event(data):
    """Handle incoming SSE events"""
    event = data.get('event')
    device = data.get('device', 'all')
    my_device = DEVICE_NAME

    # Only react if message is for this device or for "all"
    if device != my_device and device != 'all':
        print(f"📡 Ignoring event for {device} (I am {my_device})")
        return

    print(f"📨 Event received: {event} | Device: {device}")

    if event == 'connected':
        print("✅ SSE Connected to server!")
        lgpio.gpio_write(chip, LED_PIN, 1)
        time.sleep(0.2)
        lgpio.gpio_write(chip, LED_PIN, 0)

    elif event == 'unlock' or event == 'verified':
        student_name = data.get('studentName')
        student_id = data.get('studentId')
        print(f"✅ VERIFIED: {student_name} ({student_id})")
        # Run unlock in separate thread to not block SSE listener
        threading.Thread(target=unlock_turnstile, args=(student_name,)).start()

    elif event == 'lock':
        lock_turnstile()

    elif event == 'failed':
        print("❌ Verification failed")
        # Blink LED to indicate failure
        for _ in range(3):
            lgpio.gpio_write(chip, LED_PIN, 1)
            time.sleep(0.1)
            lgpio.gpio_write(chip, LED_PIN, 0)
            time.sleep(0.1)


def start_program():
    """Start the turnstile controller"""
    global running, sse_thread

    print(f"📍 WEB_URL: {WEB_URL}")
    print(f"📡 SSE_URL: {SSE_URL}")
    print(f"🏷️ DEVICE_NAME: {DEVICE_NAME}")

    # Set HID permissions first
    print("🔧 Setting HID device permissions...")
    try:
        subprocess.run('sudo chmod 666 /dev/hidraw*', shell=True, check=False)
        print("✅ HID device permissions set")
    except Exception as e:
        print(f"⚠️ Failed to set HID permissions: {e}")

    # Initialize GPIO
    gpio_setup()

    # Now wait for Yuriot ScanCode Box scanner to connect
    if not wait_for_scanner():
        print("⚠️ Continuing without scanner detection...")

    # Open Chromium in kiosk mode with auto-permissions
    print("🌐 Launching Chromium kiosk with auto-permissions...")
    subprocess.Popen([
        "/usr/bin/chromium",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--incognito",
        "--ignore-certificate-errors",
        # Auto-grant camera and microphone permissions
        "--use-fake-ui-for-media-stream",
        # Enable WebHID API
        "--enable-features=WebHID",
        # Disable permission prompts
        "--disable-features=TranslateUI",
        "--disable-popup-blocking",
        "--autoplay-policy=no-user-gesture-required",
        # Performance optimizations for Raspberry Pi
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        # Allow insecure localhost for self-signed certs
        "--allow-insecure-localhost",
        WEB_URL
    ])

    # Start SSE listener
    running = True
    sse_thread = threading.Thread(target=sse_listener, daemon=True)
    sse_thread.start()

    print("🚀 Turnstile controller started!")
    print("📡 Listening for SSE events...")
    print("💡 Make sure to run with sudo for HID device access: sudo python3 turnstile-controller.py")
    print("🔍 Yuriot ScanCode Box scanner should be connected and detected")
    print("Press Ctrl+C to exit")

    # Keep main thread alive
    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        running = False
    finally:
        gpio_cleanup()


def test_scanner_detection():
    """Test function to debug scanner detection"""
    print("🧪 Testing scanner detection...")

    print("\n1. Checking lsusb:")
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        print(result.stdout)
    except Exception as e:
        print(f"Error: {e}")

    print("\n2. Checking HID devices:")
    try:
        hid_devices = glob.glob('/dev/hidraw*')
        print(f"HID devices: {hid_devices}")

        for device in hid_devices:
            try:
                manufacturer_path = f"/sys/class/hidraw/{os.path.basename(device)}/device/manufacturer"
                product_path = f"/sys/class/hidraw/{os.path.basename(device)}/device/product"

                manufacturer = "Unknown"
                product = "Unknown"

                if os.path.exists(manufacturer_path):
                    with open(manufacturer_path, 'r') as f:
                        manufacturer = f.read().strip()
                if os.path.exists(product_path):
                    with open(product_path, 'r') as f:
                        product = f.read().strip()

                print(f"  {device}: {manufacturer} - {product}")
            except Exception as e:
                print(f"  {device}: Error reading info - {e}")
    except Exception as e:
        print(f"Error checking HID devices: {e}")

    print("\n3. Checking recent dmesg:")
    try:
        result = subprocess.run(['dmesg', '--time-format=iso', '--since=-60seconds'],
                              capture_output=True, text=True, timeout=5)
        # Filter for USB-related messages
        usb_lines = [line for line in result.stdout.split('\n') if 'usb' in line.lower() or 'hid' in line.lower()]
        for line in usb_lines[-10:]:  # Show last 10 USB/HID related lines
            print(f"  {line}")
    except Exception as e:
        print(f"Error checking dmesg: {e}")


# Allow running test function
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_scanner_detection()
    else:
        start_program()