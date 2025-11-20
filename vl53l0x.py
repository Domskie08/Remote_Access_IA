import time
from smbus2 import SMBus

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.address = address
        self.bus = SMBus(bus)

        # Init sequence for VL53L0X (works on Raspberry Pi 5)
        self._write(0x88, 0x00)
        self._write(0x80, 0x01)
        self._write(0xFF, 0x01)
        self._write(0x00, 0x00)
        self._write(0x91, 0x3C)
        self._write(0x00, 0x01)
        self._write(0xFF, 0x00)
        self._write(0x80, 0x00)

    def _write(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)

    def _read16(self, reg):
        high = self.bus.read_byte_data(self.address, reg)
        low = self.bus.read_byte_data(self.address, reg + 1)
        return (high << 8) | low

    @property
    def range(self):
        # Start measurement
        self._write(0x00, 0x01)
        time.sleep(0.01)

        distance = self._read16(0x14)

        # If invalid, return 0
        if distance in (0, 0xFFFF):
            return 0

        return distance
