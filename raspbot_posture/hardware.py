"""Minimal Raspbot hardware adapter used by posture robot control."""

try:
    import smbus
except ImportError as exc:  # pragma: no cover - depends on Raspberry Pi runtime
    smbus = None
    SMBUS_IMPORT_ERROR = exc
else:
    SMBUS_IMPORT_ERROR = None


PI5CAR_I2C_ADDR = 0x2B
MOTOR_REG = 0x01
SERVO_REG = 0x02
ULTRASONIC_SWITCH_REG = 0x07
ULTRASONIC_LOW_REG = 0x1A
ULTRASONIC_HIGH_REG = 0x1B


class Raspbot:
    """Small subset of the vendor Raspbot API needed by this project."""

    def __init__(self, i2c_bus=1, address=PI5CAR_I2C_ADDR):
        if smbus is None:
            raise ImportError("smbus is required for Raspbot hardware control") from SMBUS_IMPORT_ERROR
        self._addr = address
        self._device = smbus.SMBus(i2c_bus)

    def write_array(self, reg, data):
        self._device.write_i2c_block_data(self._addr, reg, data)

    def read_data_array(self, reg, length):
        return self._device.read_i2c_block_data(self._addr, reg, length)

    def Ctrl_Muto(self, motor_id, motor_speed):
        motor_speed = max(-255, min(255, int(motor_speed)))
        motor_dir = 1 if motor_speed < 0 else 0
        self.write_array(MOTOR_REG, [int(motor_id), motor_dir, abs(motor_speed)])

    def Ctrl_Servo(self, servo_id, angle):
        angle = max(0, min(180, int(angle)))
        if servo_id == 2:
            angle = min(100, angle)
        self.write_array(SERVO_REG, [int(servo_id), angle])

    def Ctrl_Ulatist_Switch(self, state):
        self.write_array(ULTRASONIC_SWITCH_REG, [1 if state else 0])

    def read_ultrasonic_mm(self):
        high = self.read_data_array(ULTRASONIC_HIGH_REG, 1)[0]
        low = self.read_data_array(ULTRASONIC_LOW_REG, 1)[0]
        return (high << 8) | low
