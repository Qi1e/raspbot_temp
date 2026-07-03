"""Robot command wrapper for posture follow control."""

import time


class RobotDriver:
    """Small wrapper around the local Raspbot hardware adapter."""

    def __init__(self, args):
        self.args = args
        self.dry_run = bool(args.dry_run_control)
        self.debug = bool(args.control_debug)
        self.pan_angle = float(args.pan_center)
        self.tilt_angle = float(args.tilt_center)
        self.last_motor_speeds = None
        self.last_servo_angles = {}
        self.bot = None

        if not self.dry_run:
            self.bot = self._load_bot()

        self.set_servo(1, self.pan_angle, reason="startup pan")
        self.set_servo(2, self.tilt_angle, reason="startup tilt")

    def _load_bot(self):
        try:
            from .hardware import Raspbot

            return Raspbot()
        except ImportError as exc:
            raise RuntimeError(
                "Could not import the Raspbot hardware driver. Run with --dry-run-control "
                "on non-Raspberry Pi machines, or install the smbus package on the robot."
            ) from exc

    def log(self, message):
        if self.debug or self.dry_run:
            print(message)

    def set_servo(self, servo_id, angle, reason=""):
        if servo_id == 1:
            angle = max(self.args.pan_min, min(self.args.pan_max, angle))
            self.pan_angle = angle
        elif servo_id == 2:
            angle = max(self.args.tilt_min, min(self.args.tilt_max, angle))
            self.tilt_angle = angle
        else:
            return

        rounded = int(round(angle))
        if self.last_servo_angles.get(servo_id) == rounded:
            return
        self.last_servo_angles[servo_id] = rounded

        self.log(f"servo {servo_id} -> {angle:.1f} {reason}".rstrip())
        if self.bot is not None:
            self.bot.Ctrl_Servo(servo_id, rounded)

    def set_motor_speeds(self, m0, m1, m2, m3, reason=""):
        speeds = [self._clamp_speed(m0), self._clamp_speed(m1), self._clamp_speed(m2), self._clamp_speed(m3)]
        if self.last_motor_speeds == speeds:
            return
        self.last_motor_speeds = speeds

        self.log(f"motors {speeds} {reason}".rstrip())
        if self.bot is not None:
            for motor_id, speed in enumerate(speeds):
                self.bot.Ctrl_Muto(motor_id, speed)

    def _clamp_speed(self, speed):
        return max(-255, min(255, int(speed)))

    def stop(self):
        self.set_motor_speeds(0, 0, 0, 0, reason="stop")

    def pulse_turn(self, direction, speed, duration):
        if self.args.invert_body_turn:
            direction = "right" if direction == "left" else "left"

        speed = abs(int(speed))
        if direction == "left":
            self.set_motor_speeds(-speed, -speed, speed, speed, reason="turn left pulse")
        else:
            self.set_motor_speeds(speed, speed, -speed, -speed, reason="turn right pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def pulse_forward(self, speed, duration):
        speed = abs(int(speed))
        self.set_motor_speeds(speed, speed, speed, speed, reason="forward pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def pulse_backward(self, speed, duration):
        speed = -abs(int(speed))
        self.set_motor_speeds(speed, speed, speed, speed, reason="backward pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def reset_servos(self):
        self.set_servo(1, self.args.pan_center, reason="reset pan")
        self.set_servo(2, self.args.tilt_rest, reason="reset tilt")
