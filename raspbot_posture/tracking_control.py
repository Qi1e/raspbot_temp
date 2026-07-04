"""Motion planning and wheel mixing for synchronized tracking."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DistanceControlInput:
    detected: bool
    confidence: float
    pan_error_degrees: float
    distance_error_m: float
    servo_idle_s: float
    posture: str
    action_active: bool
    motion_allowed: bool
    updated_at: float
    chassis_direction_degrees: float = 90.0
    tracking_reason: str = ""


@dataclass(frozen=True)
class MotionGoal:
    active: bool
    direction_degrees: float = 90.0
    speed: float = 0.0
    expires_at: float = 0.0
    reason: str = "idle"


@dataclass(frozen=True)
class WheelSpeeds:
    m0: int
    m1: int
    m2: int
    m3: int

    def as_list(self):
        return [self.m0, self.m1, self.m2, self.m3]


@dataclass(frozen=True)
class YawDecision:
    speed: float = 0.0
    reason: str = "idle"


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def signed_direction(value, deadband=0.0):
    value = float(value)
    deadband = abs(float(deadband))
    if value > deadband:
        return 1
    if value < -deadband:
        return -1
    return 0


def translation_speeds(speed, direction_degrees):
    speed = clamp(float(speed), 0.0, 255.0)
    radians = math.radians(float(direction_degrees))
    vx = speed * math.cos(radians)
    vy = speed * math.sin(radians)
    return [vy + vx, vy - vx, vy - vx, vy + vx]


def mix_translation_yaw(speed, direction_degrees, yaw_speed, max_speed=255):
    base = translation_speeds(speed, direction_degrees)
    yaw = clamp(float(yaw_speed), -float(max_speed), float(max_speed))
    mixed = [
        base[0] - yaw,
        base[1] - yaw,
        base[2] + yaw,
        base[3] + yaw,
    ]

    largest = max(abs(value) for value in mixed) or 1.0
    if largest > max_speed:
        scale = float(max_speed) / largest
        mixed = [value * scale for value in mixed]

    return WheelSpeeds(*(int(round(clamp(value, -max_speed, max_speed))) for value in mixed))


def distance_input_from_tracking(tracking, servo_idle_s, posture, action_active, updated_at):
    kwargs = tracking.as_distance_control_kwargs(
        servo_idle_s=servo_idle_s,
        posture=posture,
        action_active=action_active,
        updated_at=updated_at,
    )
    return DistanceControlInput(
        **kwargs,
        chassis_direction_degrees=tracking.chassis_direction_degrees,
        tracking_reason=tracking.reason,
    )


def yaw_from_tracking(tracking, args, now, action_active):
    if args.tracking_mode == "camera":
        return YawDecision(0.0, "camera tracking only")
    if action_active and not args.allow_yaw_during_action:
        return YawDecision(0.0, "action active")
    if not tracking.detected or not tracking.tracking_allowed:
        return YawDecision(0.0, "target unavailable")

    body_error = float(tracking.body_yaw_error_degrees)
    body_sign = signed_direction(body_error, args.body_yaw_deadband_degrees)
    if body_sign == 0:
        return YawDecision(0.0, "body yaw deadband")

    screen_gate = float(args.body_yaw_screen_gate_degrees)
    if screen_gate > 0.0:
        screen_error = float(tracking.pan_error_degrees)
        screen_sign = signed_direction(screen_error, screen_gate)
        if screen_sign and screen_sign != body_sign:
            return YawDecision(0.0, "screen/body yaw conflict")

    speed = clamp(body_error * args.body_yaw_gain, -args.max_yaw_speed, args.max_yaw_speed)
    return YawDecision(speed, "pan offset yaw")


class DistancePlanner:
    def __init__(self, args):
        self.args = args
        self.next_plan_at = 0.0
        self.goal = MotionGoal(active=False)

    def update(self, sample, now):
        if now < self.next_plan_at:
            return self.goal

        self.next_plan_at = now + self.args.plan_interval
        self.goal = self.plan(sample, now)
        if getattr(self.args, "print_planner", False):
            print(f"planner goal={self.goal}")
        return self.goal

    def plan(self, sample, now):
        if not sample.detected:
            return MotionGoal(active=False, reason="target lost")
        if now - sample.updated_at > self.args.max_input_age:
            return MotionGoal(active=False, reason="stale input")
        if sample.confidence < self.args.min_confidence:
            return MotionGoal(active=False, reason="low confidence")
        if sample.servo_idle_s < self.args.servo_idle_required:
            return MotionGoal(active=False, reason="servo moving")
        if sample.action_active:
            return MotionGoal(active=False, reason=f"action active: {sample.posture}")
        if not sample.motion_allowed:
            return MotionGoal(active=False, reason="motion blocked")
        if abs(sample.distance_error_m) <= self.args.distance_deadband:
            return MotionGoal(active=False, reason="distance ok")

        if sample.distance_error_m > 0:
            direction = sample.chassis_direction_degrees
            reason = "too far"
        else:
            direction = sample.chassis_direction_degrees
            reason = "too close"

        error = abs(sample.distance_error_m)
        speed = clamp(
            self.args.min_move_speed + error * self.args.distance_speed_gain,
            self.args.min_move_speed,
            self.args.max_move_speed,
        )
        duration = clamp(
            error * self.args.distance_duration_gain,
            self.args.min_goal_duration,
            self.args.max_goal_duration,
        )
        return MotionGoal(
            active=True,
            direction_degrees=direction % 360.0,
            speed=speed,
            expires_at=now + duration,
            reason=reason,
        )
