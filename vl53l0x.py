import time
import smbus2

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.address = address
        self.bus = smbus2.SMBus(bus)

        try:
            # Basic setup - note: full init requires data init sequence
            self._write(0x88, 0x00)
            self._write(0x80, 0x01)
            self._write(0xFF, 0x01)
            self._write(0x00, 0x00)
            self.stop_variable = self._read(0x91)
            self._write(0x00, 0x01)
            self._write(0xFF, 0x00)
            self._write(0x80, 0x00)

            # Start continuous ranging
            self._write(0x00, 0x02)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize VL53L0X: {e}")

    def _write(self, reg, value):
        try:
            self.bus.write_byte_data(self.address, reg, value)
        except Exception as e:
            raise RuntimeError(f"I2C write error at reg {reg}: {e}")

    def _read(self, reg):
        try:
            return self.bus.read_byte_data(self.address, reg)
        except Exception as e:
            raise RuntimeError(f"I2C read error at reg {reg}: {e}")

    def _read16(self, reg):
        try:
            high = self._read(reg)
            low = self._read(reg + 1)
            return (high << 8) | low
        except Exception as e:
            raise RuntimeError(f"I2C read16 error at reg {reg}: {e}")

    def read_range(self):
        try:
            # Wait for measurement ready (bit 0 of 0x13)
            for _ in range(50):
                if self._read(0x13) & 0x01:
                    break
                time.sleep(0.001)
            else:
                raise RuntimeError("Timeout waiting for measurement")

            # Read distance
            distance = self._read16(0x14)

            # Clear interrupt
            self._write(0x0B, 0x01)

            return distance
        except Exception as e:
            raise RuntimeError(f"Error reading range: {e}")
