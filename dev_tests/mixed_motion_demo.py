#!/usr/bin/env python3
# coding: utf-8
"""Test fixed-direction chassis motion while turning."""

import argparse
import math
import time
from dataclasses import dataclass


DIRECTION_DEGREES = {
    "right": 0.0,
    "forward": 90.0,
    "left": 180.0,
    "backward": 270.0,
}


@dataclass(frozen=True)
class WheelSpeeds:
    m0: int
    m1: int
    m2: int
    m3: int

    def as_list(self):
        return [self.m0, self.m1, self.m2, self.m3]


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def translation_speeds(speed, deflection_degrees):
    speed = clamp(float(speed), 0.0, 255.0)
    radians = math.radians(float(deflection_degrees))
    vx = speed * math.cos(radians)
    vy = speed * math.sin(radians)
    return [vy + vx, vy - vx, vy - vx, vy + vx]


def mix_translation_turn(speed, deflection_degrees, yaw_speed, max_speed=255):
    base = translation_speeds(speed, deflection_degrees)
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


class ChassisMotionDemoDriver:
    def __init__(self, dry_run=True, i2c_bus=1):
        self.dry_run = bool(dry_run)
        self.bot = None
        if not self.dry_run:
            from raspbot_posture.hardware import Raspbot

            self.bot = Raspbot(i2c_bus=i2c_bus)

    def set_wheel_speeds(self, speeds, reason=""):
        values = speeds.as_list() if hasattr(speeds, "as_list") else list(speeds)
        print(f"motors {values} {reason}".rstrip())
        if self.bot is not None:
            for motor_id, speed in enumerate(values):
                self.bot.Ctrl_Muto(motor_id, int(speed))

    def stop(self):
        self.set_wheel_speeds(WheelSpeeds(0, 0, 0, 0), reason="stop")

    def drive_translation_turn(self, speed, deflection_degrees, yaw_speed, duration, interval=0.1, max_speed=255):
        speeds = mix_translation_turn(speed, deflection_degrees, yaw_speed, max_speed=max_speed)
        deadline = time.time() + max(0.0, float(duration))
        interval = max(0.02, float(interval))

        try:
            while time.time() < deadline:
                self.set_wheel_speeds(
                    speeds,
                    reason=f"deflection={float(deflection_degrees):.1f} yaw={float(yaw_speed):.1f}",
                )
                time.sleep(interval)
        finally:
            self.stop()

        return speeds


def build_parser():
    parser = argparse.ArgumentParser(description="Drive in one direction while turning")
    parser.add_argument("--direction", choices=sorted(DIRECTION_DEGREES), default="forward")
    parser.add_argument("--deflection", type=float, default=None, help="override direction in degrees: 0 right, 90 forward")
    parser.add_argument("--speed", type=float, default=30.0, help="translation speed 0-255")
    parser.add_argument("--turn-speed", type=float, default=8.0, help="turn speed; positive value is used with --turn")
    parser.add_argument("--turn", choices=["left", "right"], default="left")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--max-speed", type=int, default=255)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--live", action="store_true", help="send commands to hardware; omitted means dry-run only")
    return parser


def main():
    args = build_parser().parse_args()
    deflection = args.deflection if args.deflection is not None else DIRECTION_DEGREES[args.direction]
    yaw_speed = abs(args.turn_speed) if args.turn == "left" else -abs(args.turn_speed)
    speeds = mix_translation_turn(args.speed, deflection, yaw_speed, max_speed=args.max_speed)

    mode = "LIVE" if args.live else "DRY-RUN"
    print(
        f"{mode}: direction={args.direction} deflection={deflection:.1f} "
        f"speed={args.speed:.1f} turn={args.turn} yaw_speed={yaw_speed:.1f} "
        f"duration={args.duration:.1f}s"
    )
    print(f"mixed wheel speeds: {speeds.as_list()}")

    driver = ChassisMotionDemoDriver(dry_run=not args.live, i2c_bus=args.i2c_bus)
    driver.drive_translation_turn(
        args.speed,
        deflection,
        yaw_speed,
        duration=args.duration,
        interval=args.interval,
        max_speed=args.max_speed,
    )


if __name__ == "__main__":
    main()
