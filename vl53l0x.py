import VL53L0X

class VL53L0X:
    def __init__(self, address=0x29, bus=1):
        self.tof = VL53L0X.VL53L0X(i2c_bus=bus, i2c_address=address)
        self.tof.start_ranging(VL53L0X.VL53L0X_BEST_ACCURACY_MODE)

    def read_range(self):
        return self.tof.get_distance()

    # Keep old methods for compatibility, but they do nothing
    def _write(self, reg, value):
        pass

    def _read(self, reg):
        return 0

    def _read16(self, reg):
        return 0
