# --------------------------------------------------------------------
# VL53L0X Distance Detector for Raspberry Pi (I2C)
#
# This script continuously reads the distance from the VL53L0X sensor
# and prints the measurement in millimeters (mm) to the terminal.
#
# PREREQUISITES:
# 1. Hardware: VL53L0X sensor connected to Raspberry Pi's 3.3V, GND,
#    SDA (GPIO 2, Pin 3), and SCL (GPIO 3, Pin 5).
# 2. Software: I2C must be enabled via raspi-config.
# 3. Library: Install the required library using:
#    pip3 install adafruit-circuitpython-vl53l0x
# --------------------------------------------------------------------

import time
import board
import busio
import adafruit_vl53l0x
import sys

# --- Configuration ---
# Set the distance threshold (in millimeters) for presence detection.
# If the distance is below this value, we consider a person present.
PRESENCE_THRESHOLD_MM = 1000  # 1000 mm = 1 meter

def initialize_sensor():
    """Initializes the I2C bus and the VL53L0X sensor."""
    print("Initializing I2C bus and VL53L0X sensor...")
    try:
        # Initialize I2C bus (SCL=GPIO3, SDA=GPIO2)
        i2c = busio.I2C(board.SCL, board.SDA)

        # Initialize the VL53L0X sensor
        vl53 = adafruit_vl53l0x.VL53L0X(i2c)
        
        # Optional: Adjust timing budget for speed/accuracy trade-off.
        # Default is around 33ms. Increasing it improves range/accuracy.
        # vl53.measurement_timing_budget = 40000 # Example for 40ms budget
        
        print("Sensor ready! Starting continuous measurement...")
        return vl53
    except ValueError:
        print("\nERROR: VL53L0X sensor not detected at default I2C address (0x29).")
        print("Please check wiring and ensure I2C is enabled on your Raspberry Pi.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred during initialization: {e}")
        sys.exit(1)

def run_detector(vl53):
    """Reads the distance from the sensor continuously and prints status."""
    
    while True:
        try:
            # Read the distance in millimeters (mm)
            distance_mm = vl53.range

            # Range is returned as an integer (e.g., 500 for 500mm)
            
            status = "Monitoring..."
            # Check against the defined threshold
            if distance_mm > 0 and distance_mm <= PRESENCE_THRESHOLD_MM:
                status = "PERSON DETECTED (Activate Kiosk/Camera)"
                
            elif distance_mm == 8190:
                 # 8190mm is a common value for "out of range" or no target.
                 status = "Out of Range (Sleep Mode)"

            # Print the output to the terminal
            print(f"Distance: {distance_mm:4d} mm | Status: {status}")

            # Wait for 100 milliseconds before the next reading
            time.sleep(0.1) 

        except RuntimeError:
            print("Warning: Sensor read failed. Retrying...")
            time.sleep(0.5)
        except KeyboardInterrupt:
            # Handle Ctrl+C exit gracefully
            print("\nDetector stopped by user.")
            break

# Main execution block
if __name__ == "__main__":
    sensor = initialize_sensor()
    run_detector(sensor)
