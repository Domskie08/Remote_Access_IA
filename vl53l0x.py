import time
from smbus2 import SMBus

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.address = address
        self.bus = SMBus(bus)

        # Proper initialization for VL53L0X
        self._write(0x88, 0x00)
        self._write(0x80, 0x01)
        self._write(0xFF, 0x01)
        self._write(0x00, 0x00)
        self.stop_variable = self._read(0x91)
        self._write(0x00, 0x01)
        self._write(0xFF, 0x00)
        self._write(0x80, 0x00)

    def _write(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)

    def _read(self, reg):
        return self.bus.read_byte_data(self.address, reg)

    def _read16(self, reg):
        high = self._read(reg)
        low  = self._read(reg + 1)
        return (high << 8) | low

    @property
    def range(self):
        # Trigger measurement
        self._write(0x00, 0x01)
        time.sleep(0.01)

        # Wait for measurement ready
        for _ in range(20):
            status = self._read(0x13)
            if status & 0x07:
                break
            time.sleep(0.001)

        # Correct distance register for VL53L0X
        distance = self._read16(0x1E)

        # Clear interrupt
        self._write(0x0B, 0x01)

        return distance if distance < 8190 else 0
