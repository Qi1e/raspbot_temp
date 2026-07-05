#!/usr/bin/env python3
# coding: utf-8
"""Interactive left/right mecanum roll model calibration."""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


MOTOR_LABELS = ("left_front", "left_rear", "right_front", "right_rear")
ROLL_DIRECTIONS = ("left_roll", "right_roll")
DEFAULT_CALIBRATION_SPEED = 35.0
LEFT_FB_RATIO = 2.0 / DEFAULT_CALIBRATION_SPEED
LEFT_YAW_RATIO = 5.0 / DEFAULT_CALIBRATION_SPEED
RIGHT_FB_RATIO = 1.0 / DEFAULT_CALIBRATION_SPEED
RIGHT_YAW_RATIO = -5.0 / DEFAULT_CALIBRATION_SPEED
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def clamp_int(value, lower=-255, upper=255):
    return max(lower, min(upper, int(round(float(value)))))


def parse_motor_map(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--motor-map needs four motor ids")
    try:
        motor_ids = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--motor-map must contain integers") from exc
    if sorted(motor_ids) != [0, 1, 2, 3]:
        raise argparse.ArgumentTypeError("--motor-map must be a permutation of 0 1 2 3")
    return motor_ids


def roll_speeds(direction, speed, fb=0.0, yaw=0.0, max_speed=255):
    """Return LF, LR, RF, RR speeds for a lateral roll test."""
    if direction not in ROLL_DIRECTIONS:
        raise ValueError(f"direction must be one of {ROLL_DIRECTIONS}")

    side = 1.0 if direction == "right_roll" else -1.0
    base = (
        side * speed,
        -side * speed,
        -side * speed,
        side * speed,
    )
    mixed = (
        base[0] + fb - yaw,
        base[1] + fb - yaw,
        base[2] + fb + yaw,
        base[3] + fb + yaw,
    )
    return tuple(clamp_int(value, -max_speed, max_speed) for value in mixed)


def parse_model_params(text, current):
    parts = text.replace(",", " ").split()
    if not parts:
        return dict(current)

    if all("=" not in part for part in parts):
        if len(parts) != 3:
            raise ValueError("expected three numbers: speed fb yaw")
        speed, fb, yaw = (float(part) for part in parts)
        return {"speed": speed, "fb": fb, "yaw": yaw}

    next_params = dict(current)
    key_map = {
        "s": "speed",
        "speed": "speed",
        "f": "fb",
        "fb": "fb",
        "forward": "fb",
        "y": "yaw",
        "yaw": "yaw",
    }
    for part in parts:
        if "=" not in part:
            raise ValueError("mixing raw numbers and key=value is not supported")
        key, value = part.split("=", 1)
        key = key_map.get(key.strip().lower())
        if key is None:
            raise ValueError("allowed keys: speed/s, fb/f, yaw/y")
        next_params[key] = float(value)
    return next_params


def format_params(params):
    return "speed={speed:.1f} fb={fb:.1f} yaw={yaw:.1f}".format(**params)


def format_values(values):
    return " ".join(str(int(value)) for value in values)


class RollModelDriver:
    def __init__(self, dry_run=False, i2c_bus=1, motor_map=(0, 1, 2, 3)):
        self.dry_run = bool(dry_run)
        self.motor_map = tuple(motor_map)
        self.bot = None
        if not self.dry_run:
            from raspbot_posture.hardware import Raspbot

            self.bot = Raspbot(i2c_bus=i2c_bus)

    def set_values(self, values, reason=""):
        pairs = tuple(zip(MOTOR_LABELS, self.motor_map, values))
        print(
            "motors "
            + " ".join(f"{label}=id{motor_id}:{speed}" for label, motor_id, speed in pairs)
            + (f" {reason}" if reason else ""),
            flush=True,
        )
        if self.bot is not None:
            for _, motor_id, speed in pairs:
                self.bot.Ctrl_Muto(motor_id, speed)

    def stop(self):
        self.set_values((0, 0, 0, 0), reason="stop")

    def run_for(self, values, duration, interval, reason=""):
        deadline = time.time() + max(0.0, float(duration))
        interval = max(0.02, float(interval))
        try:
            while time.time() < deadline:
                self.set_values(values, reason=reason)
                time.sleep(interval)
        finally:
            self.stop()


def default_params_for_direction(direction, args):
    if direction == "left_roll":
        fb = args.left_fb if args.left_fb is not None else args.speed * LEFT_FB_RATIO
        yaw = args.left_yaw if args.left_yaw is not None else args.speed * LEFT_YAW_RATIO
        return {"speed": args.speed, "fb": fb, "yaw": yaw}
    fb = args.right_fb if args.right_fb is not None else args.speed * RIGHT_FB_RATIO
    yaw = args.right_yaw if args.right_yaw is not None else args.speed * RIGHT_YAW_RATIO
    return {"speed": args.speed, "fb": fb, "yaw": yaw}


def write_report(path, results, args, complete):
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "complete": bool(complete),
        "duration_s": args.duration,
        "interval_s": args.interval,
        "dry_run": bool(args.dry_run),
        "motor_order": list(MOTOR_LABELS),
        "motor_map": list(args.motor_map),
        "formula": "LF=base+fb-yaw LR=base+fb-yaw RF=base+fb+yaw RR=base+fb+yaw",
        "directions": results,
    }

    lines = [
        "# Raspbot roll model calibration",
        "",
        f"- Created at: {payload['created_at']}",
        f"- Complete: {payload['complete']}",
        f"- Duration per run: {args.duration:.2f}s",
        f"- Motor order: {' '.join(MOTOR_LABELS)}",
        f"- Motor id map: {' '.join(str(item) for item in args.motor_map)}",
        f"- Formula: {payload['formula']}",
        "",
        "| Direction | speed | fb | yaw | left_front | left_rear | right_front | right_rear |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for direction, data in results.items():
        params = data["params"]
        values = data["values"]
        lines.append(
            f"| {direction} | {params['speed']} | {params['fb']} | {params['yaw']} | "
            f"{values[0]} | {values[1]} | {values[2]} | {values[3]} |"
        )
    lines.extend(("", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def prompt_before_run(direction, params, values):
    prompt = (
        f"\n[{direction}] current params: {format_params(params)}\n"
        f"[{direction}] motor values: {format_values(values)}\n"
        "Press Enter to run, input 'speed fb yaw' or 'speed=.. fb=.. yaw=..', q to quit: "
    )
    return input(prompt).strip()


def prompt_after_run(direction):
    prompt = (
        f"[{direction}] result? n=accept next, r=retry, "
        "'speed fb yaw'=replace and retry, q=quit: "
    )
    return input(prompt).strip()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Interactively calibrate left/right roll with mecanum fb/yaw compensation."
    )
    parser.add_argument("--speed", type=float, default=35.0, help="initial base lateral speed")
    parser.add_argument("--left-fb", type=float, default=None, help="initial left_roll fb compensation")
    parser.add_argument("--left-yaw", type=float, default=None, help="initial left_roll yaw compensation")
    parser.add_argument("--right-fb", type=float, default=None, help="initial right_roll fb compensation")
    parser.add_argument("--right-yaw", type=float, default=None, help="initial right_roll yaw compensation")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--max-speed", type=int, default=255)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument(
        "--motor-map",
        type=parse_motor_map,
        default=(0, 1, 2, 3),
        help="hardware motor ids for left_front left_rear right_front right_rear",
    )
    parser.add_argument(
        "--output",
        default="dev_tests/roll_model_calibration.md",
        help="report file written after each accepted direction",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without touching hardware")
    return parser


def main():
    args = build_parser().parse_args()
    driver = RollModelDriver(dry_run=args.dry_run, i2c_bus=args.i2c_bus, motor_map=args.motor_map)
    results = {}
    complete = False

    print("Motor value order: left_front left_rear right_front right_rear", flush=True)
    print("Model: roll base + fb drift compensation + yaw rotation compensation", flush=True)
    print("Formula: LF=base+fb-yaw LR=base+fb-yaw RF=base+fb+yaw RR=base+fb+yaw", flush=True)
    print("Default compensation scales from speed=35 calibration.", flush=True)
    print("Use Ctrl+C any time to stop motors and save accepted results.", flush=True)

    try:
        for direction in ROLL_DIRECTIONS:
            params = default_params_for_direction(direction, args)
            while True:
                values = roll_speeds(
                    direction,
                    params["speed"],
                    fb=params["fb"],
                    yaw=params["yaw"],
                    max_speed=args.max_speed,
                )
                command = prompt_before_run(direction, params, values)
                if command.lower() in ("q", "quit", "exit"):
                    raise KeyboardInterrupt
                if command:
                    try:
                        params = parse_model_params(command, params)
                    except ValueError as exc:
                        print(f"Invalid input: {exc}", flush=True)
                        continue
                    continue

                reason = f"{direction} {format_params(params)}"
                print(f"Running {direction} for {args.duration:.2f}s...", flush=True)
                driver.run_for(values, args.duration, args.interval, reason=reason)

                while True:
                    command = prompt_after_run(direction)
                    lower = command.lower()
                    if lower in ("n", "next", "y", "yes", ""):
                        results[direction] = {
                            "params": {
                                "speed": params["speed"],
                                "fb": params["fb"],
                                "yaw": params["yaw"],
                            },
                            "values": list(values),
                        }
                        report_path = write_report(args.output, results, args, complete=False)
                        print(f"Accepted {direction}: {format_params(params)} values={format_values(values)}", flush=True)
                        print(f"Saved report: {report_path}", flush=True)
                        break
                    if lower in ("r", "retry"):
                        break
                    if lower in ("q", "quit", "exit"):
                        raise KeyboardInterrupt
                    try:
                        params = parse_model_params(command, params)
                        break
                    except ValueError as exc:
                        print(f"Invalid input: {exc}", flush=True)
                if direction in results:
                    break
        complete = True
    except KeyboardInterrupt:
        print("\nStopping roll model test.", flush=True)
    finally:
        driver.stop()
        if results:
            report_path = write_report(args.output, results, args, complete=complete)
            print(f"Saved report: {report_path}", flush=True)
        else:
            print("No accepted results to save.", flush=True)


if __name__ == "__main__":
    main()
