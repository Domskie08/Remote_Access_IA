#!/usr/bin/env python3
"""
Raspberry Pi 5 Turnstile Controller
====================================
Connects to SvelteKit SSE endpoint and controls solenoid via GPIO

Hardware Setup:
- GPIO 17: Solenoid relay (unlock turnstile)
- GPIO 27: LED indicator (optional status LED)

Requirements:
- pip3 install requests lgpio
"""

import time
import json
import requests
import lgpio
import subprocess
import threading
import urllib3

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


def gpio_setup():
    """Initialize GPIO pins"""
    global chip

    # Set HID device permissions for barcode scanner
    try:
        subprocess.run('sudo chmod 666 /dev/hidraw*', shell=True, check=False)
        print("✅ HID device permissions set")
    except Exception as e:
        print(f"⚠️ Failed to set HID permissions: {e}")
        
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
    
    # Initialize GPIO
    gpio_setup()
    
    # Open Chromium in kiosk mode
    print("🌐 Launching Chromium kiosk...")
    subprocess.Popen([
        "/usr/bin/chromium",
        "--kiosk",
        "--noerrdialogs",
        "--disable-infobars",
        "--incognito",
        "--ignore-certificate-errors",
        WEB_URL
    ])
    
    # Start SSE listener
    running = True
    sse_thread = threading.Thread(target=sse_listener, daemon=True)
    sse_thread.start()
    
    print("🚀 Turnstile controller started!")
    print("📡 Listening for SSE events...")
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


if __name__ == "__main__":
    start_program()
