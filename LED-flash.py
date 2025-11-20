import time
import lgpio
import requests
from VL53L0X import VL53L0X  # from Gadgetoid library

# Config
LED_PIN = 18
SERVER_URL = "https://172.27.44.17:4173/api/camera"
THRESHOLD = 1000
TIMEOUT = 10

# Setup LED
chip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_output(chip, LED_PIN)
lgpio.gpio_write(chip, LED_PIN, 0)

# Init sensor
sensor = VL53L0X()
sensor.open()        # open / init sensor
sensor.start_ranging()  # start measuring

last_seen = 0
camera_on = False

try:
    while True:
        distance = sensor.get_distance()

        if 0 < distance <= THRESHOLD:
            last_seen = time.time()
            if not camera_on:
                camera_on = True
                requests.post(SERVER_URL, json={"action": "start_camera"})
                lgpio.gpio_write(chip, LED_PIN, 1)
                print("Camera started, distance:", distance)

        if camera_on and (time.time() - last_seen > TIMEOUT):
            camera_on = False
            requests.post(SERVER_URL, json={"action": "stop_camera"})
            lgpio.gpio_write(chip, LED_PIN, 0)
            print("Camera stopped due to timeout")

        print("Distance:", distance)
        time.sleep(0.1)

except KeyboardInterrupt:
    sensor.stop_ranging()
    sensor.close()
    lgpio.gpio_write(chip, LED_PIN, 0)
    lgpio.gpiochip_close(chip)
