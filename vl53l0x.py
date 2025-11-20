import time
import smbus2

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.address = address
        self.bus = smbus2.SMBus(bus)

        # VL53L0X initialization
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

    def _write(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)

    def _read(self, reg):
        return self.bus.read_byte_data(self.address, reg)

    def _read16(self, reg):
        return (self._read(reg) << 8) | self._read(reg + 1)

    def read_range(self):
        # Wait for measurement ready
        for _ in range(50):
            if self._read(0x13) & 0x07:
                break
            time.sleep(0.001)

        # Correct distance register for VL53L0X
        distance = self._read16(0x14)

        # Clear interrupt
        self._write(0x0B, 0x01)

        # Out-of-range returns 0
        return distance if distance < 8190 else 0
