# Minimal VL53L0X driver for Raspberry Pi 5 (no Blinka)
# Uses smbus2 and direct register access.

import time
from smbus2 import SMBus

VL53_I2C_ADDR = 0x29

class VL53L0X:
    def __init__(self, bus=1):
        self.i2c = SMBus(bus)
        self.address = VL53_I2C_ADDR
        self._init_sensor()

    def _write(self, reg, value):
        self.i2c.write_byte_data(self.address, reg, value)

    def _read16(self, reg):
        data = self.i2c.read_i2c_block_data(self.address, reg, 2)
        return (data[0] << 8) | data[1]

    def _init_sensor(self):
        time.sleep(0.2)   # allow sensor boot
        self._write(0x88, 0x00)
        self._write(0x80, 0x01)
        self._write(0xFF, 0x01)
        self._write(0x00, 0x00)
        self._write(0x91, 0x3c)
        self._write(0x00, 0x01)
        self._write(0xFF, 0x00)
        self._write(0x80, 0x00)
        time.sleep(0.05)

    @property
    def range(self):
        return self._read16(0x14)
