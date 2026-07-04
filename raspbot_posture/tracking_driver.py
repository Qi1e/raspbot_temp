"""Robot driver for synchronized tracking demos and controllers."""

from dataclasses import dataclass

from .tracking_control import WheelSpeeds, clamp


@dataclass(frozen=True)
class ServoUpdate:
    moved: bool = False
    visual_pan_delta: float = 0.0
    yaw_comp_delta: float = 0.0
    yaw_comp_residual: float = 0.0
    final_pan_delta: float = 0.0
    tilt_delta: float = 0.0


class TrackingRobotDriver:
    """Small stateful hardware wrapper for continuous pan/tilt and wheel control."""

    def __init__(self, live=False, i2c_bus=1, print_motors=False):
        self.live = bool(live)
        self.print_motors = bool(print_motors)
        self.bot = None
        if live:
            from .hardware import Raspbot

            self.bot = Raspbot(i2c_bus=i2c_bus)
        self.pan_angle = 90.0
        self.tilt_angle = 50.0
        self.last_servo_motion_at = 0.0
        self.last_servo_update_at = 0.0
        self.yaw_servo_compensation_residual = 0.0

    def configure_servos(self, pan_angle, tilt_angle):
        self.pan_angle = float(pan_angle)
        self.tilt_angle = float(tilt_angle)
        self.set_servo(1, self.pan_angle, reason="startup pan")
        self.set_servo(2, self.tilt_angle, reason="startup tilt")

    def servo_idle_s(self, now):
        if self.last_servo_motion_at <= 0.0:
            return 999.0
        return max(0.0, now - self.last_servo_motion_at)

    def set_servo(self, servo_id, angle, reason=""):
        if servo_id == 1:
            self.pan_angle = angle
        elif servo_id == 2:
            self.tilt_angle = angle
        rounded = int(round(angle))
        print(f"servo {servo_id} -> {rounded} {reason}".rstrip())
        if self.bot is not None:
            self.bot.Ctrl_Servo(servo_id, rounded)

    def yaw_servo_compensation_delta(self, args, now, yaw_speed):
        if args.tracking_mode != "full":
            self.yaw_servo_compensation_residual = 0.0
            return 0.0
        if args.yaw_servo_compensation_gain <= 0.0:
            self.yaw_servo_compensation_residual = 0.0
            return 0.0
        if abs(yaw_speed) < args.yaw_servo_compensation_deadband:
            self.yaw_servo_compensation_residual = 0.0
            return 0.0

        if self.last_servo_update_at <= 0.0:
            dt = args.servo_interval
        else:
            dt = now - self.last_servo_update_at
        dt = clamp(dt, 0.0, args.servo_interval)

        delta = (
            float(args.yaw_servo_compensation_sign)
            * float(yaw_speed)
            * float(args.yaw_servo_compensation_gain)
            * dt
        )
        self.yaw_servo_compensation_residual += delta
        return clamp(
            self.yaw_servo_compensation_residual,
            -args.yaw_servo_compensation_max_step,
            args.yaw_servo_compensation_max_step,
        )

    def update_camera(self, tracking, args, now, yaw_speed=0.0):
        if now - self.last_servo_update_at < args.servo_interval:
            return ServoUpdate(yaw_comp_residual=self.yaw_servo_compensation_residual)
        if not tracking.detected or not tracking.tracking_allowed:
            self.yaw_servo_compensation_residual = 0.0
            return ServoUpdate(yaw_comp_residual=self.yaw_servo_compensation_residual)

        moved = False
        pan_before = self.pan_angle
        tilt_before = self.tilt_angle
        visual_delta = 0.0
        compensation_delta = 0.0
        applied_compensation_delta = 0.0
        pan_delta = 0.0
        reasons = []
        if abs(tracking.pan_error_degrees) >= args.camera_pan_deadband_degrees:
            visual_delta = clamp(
                tracking.pan_error_degrees * args.camera_servo_gain,
                -args.camera_servo_step,
                args.camera_servo_step,
            )
            pan_delta += visual_delta
            reasons.append(f"pan err={tracking.pan_error_degrees:.1f}")

        compensation_delta = self.yaw_servo_compensation_delta(args, now, yaw_speed)
        if compensation_delta:
            pan_delta += compensation_delta
            reasons.append(f"yaw comp={compensation_delta:.2f}")

        if pan_delta:
            pan_limit = float(args.camera_servo_step)
            if compensation_delta:
                pan_limit += float(args.yaw_servo_compensation_max_step)
            pan_delta = clamp(pan_delta, -pan_limit, pan_limit)
            next_angle = clamp(self.pan_angle + pan_delta, args.pan_min, args.pan_max)
            actual_pan_delta = next_angle - pan_before
            if compensation_delta:
                applied_compensation_delta = clamp(
                    actual_pan_delta - visual_delta,
                    min(0.0, compensation_delta),
                    max(0.0, compensation_delta),
                )
            if int(round(next_angle)) != int(round(self.pan_angle)):
                self.set_servo(1, next_angle, reason=", ".join(reasons))
                if compensation_delta:
                    self.yaw_servo_compensation_residual -= applied_compensation_delta
                    if abs(self.yaw_servo_compensation_residual) < 1e-6:
                        self.yaw_servo_compensation_residual = 0.0
                moved = True

        if abs(tracking.tilt_error_degrees) >= args.camera_tilt_deadband_degrees:
            delta = clamp(
                tracking.tilt_error_degrees * args.camera_servo_gain,
                -args.camera_servo_step,
                args.camera_servo_step,
            )
            next_angle = clamp(self.tilt_angle + delta, args.tilt_min, args.tilt_max)
            if int(round(next_angle)) != int(round(self.tilt_angle)):
                self.set_servo(2, next_angle, reason=f"tilt err={tracking.tilt_error_degrees:.1f}")
                moved = True

        if moved:
            self.last_servo_motion_at = now
        self.last_servo_update_at = now
        return ServoUpdate(
            moved=moved,
            visual_pan_delta=visual_delta,
            yaw_comp_delta=compensation_delta,
            yaw_comp_residual=self.yaw_servo_compensation_residual,
            final_pan_delta=self.pan_angle - pan_before,
            tilt_delta=self.tilt_angle - tilt_before,
        )

    def set_wheel_speeds(self, speeds, reason=""):
        values = speeds.as_list()
        if self.print_motors:
            print(f"motors {values} {reason}".rstrip())
        if self.bot is not None:
            for motor_id, speed in enumerate(values):
                self.bot.Ctrl_Muto(motor_id, int(speed))

    def stop(self):
        self.set_wheel_speeds(WheelSpeeds(0, 0, 0, 0), reason="stop")
