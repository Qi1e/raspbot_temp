#!/usr/bin/env python3
# coding: utf-8
"""Interactive raw motor calibration for four basic chassis directions."""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path


MOTOR_LABELS = ("left_front", "left_rear", "right_front", "right_rear")
DIRECTIONS = (
    ("left_roll", (-20, 20, 20, -20)),
    ("forward", (20, 20, 20, 20)),
    ("right_roll", (20, -20, -20, 20)),
    ("backward", (-20, -20, -20, -20)),
)


def clamp_speed(value):
    return max(-255, min(255, int(value)))


def parse_values(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError("expected four numbers: left_front left_rear right_front right_rear")
    return tuple(clamp_speed(part) for part in parts)


def parse_motor_map(text):
    parts = text.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError("--motor-map needs four motor ids")
    motor_ids = tuple(int(part) for part in parts)
    if sorted(motor_ids) != [0, 1, 2, 3]:
        raise ValueError("--motor-map must be a permutation of 0 1 2 3")
    return motor_ids


class RawMotorDriver:
    def __init__(self, dry_run=False, i2c_bus=1, motor_map=(0, 1, 2, 3)):
        self.dry_run = bool(dry_run)
        self.motor_map = tuple(motor_map)
        self.bot = None
        if not self.dry_run:
            from raspbot_posture.hardware import Raspbot

            self.bot = Raspbot(i2c_bus=i2c_bus)

    def set_values(self, values, reason=""):
        values = tuple(clamp_speed(value) for value in values)
        pairs = list(zip(MOTOR_LABELS, self.motor_map, values))
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


def format_values(values):
    return " ".join(str(int(value)) for value in values)


def write_report(path, results, args, complete):
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "complete": bool(complete),
        "duration_s": args.duration,
        "interval_s": args.interval,
        "dry_run": bool(args.dry_run),
        "motor_order": list(MOTOR_LABELS),
        "motor_map": list(args.motor_map),
        "directions": results,
    }
    lines = [
        "# Raspbot motor direction calibration",
        "",
        f"- Created at: {payload['created_at']}",
        f"- Complete: {payload['complete']}",
        f"- Duration per run: {args.duration:.2f}s",
        f"- Motor order: {' '.join(MOTOR_LABELS)}",
        f"- Motor id map: {' '.join(str(item) for item in args.motor_map)}",
        "",
        "| Direction | left_front | right_front | left_rear | right_rear |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for direction, values in results.items():
        lines.append(
            f"| {direction} | {values[0]} | {values[1]} | {values[2]} | {values[3]} |"
        )
    lines.extend(("", "```json", json.dumps(payload, indent=2, sort_keys=True), "```", ""))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def prompt_before_run(direction, values):
    prompt = (
        f"\n[{direction}] current values: {format_values(values)}\n"
        "Press Enter to run, input four numbers to replace, or q to quit: "
    )
    return input(prompt).strip()


def prompt_after_run(direction):
    prompt = (
        f"[{direction}] result? n=accept next, r=retry, "
        "four numbers=replace and retry, q=quit: "
    )
    return input(prompt).strip()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run left/forward/right/backward raw motor tests and save confirmed values."
    )
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument(
        "--motor-map",
        type=parse_motor_map,
        default=(0, 1, 2, 3),
        help="hardware motor ids for left_front left_rear right_front right_rear",
    )
    parser.add_argument(
        "--output",
        default="dev_tests/motor_direction_calibration.md",
        help="report file written after each accepted direction",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without touching hardware")
    return parser


def main():
    args = build_parser().parse_args()
    driver = RawMotorDriver(dry_run=args.dry_run, i2c_bus=args.i2c_bus, motor_map=args.motor_map)
    results = {}
    complete = False

    print("Motor value order: left_front left_rear right_front right_rear", flush=True)
    print("Use Ctrl+C any time to stop motors and save accepted results.", flush=True)

    try:
        for direction, default_values in DIRECTIONS:
            values = tuple(default_values)
            while True:
                command = prompt_before_run(direction, values)
                if command.lower() in ("q", "quit", "exit"):
                    raise KeyboardInterrupt
                if command:
                    try:
                        values = parse_values(command)
                    except ValueError as exc:
                        print(f"Invalid input: {exc}", flush=True)
                        continue

                print(f"Running {direction} for {args.duration:.2f}s...", flush=True)
                driver.run_for(values, args.duration, args.interval, reason=direction)

                while True:
                    command = prompt_after_run(direction)
                    lower = command.lower()
                    if lower in ("n", "next", "y", "yes", ""):
                        results[direction] = list(values)
                        report_path = write_report(args.output, results, args, complete=False)
                        print(f"Accepted {direction}: {format_values(values)}", flush=True)
                        print(f"Saved report: {report_path}", flush=True)
                        break
                    if lower in ("r", "retry"):
                        break
                    if lower in ("q", "quit", "exit"):
                        raise KeyboardInterrupt
                    try:
                        values = parse_values(command)
                        break
                    except ValueError as exc:
                        print(f"Invalid input: {exc}", flush=True)
                if direction in results:
                    break

        complete = True
    except KeyboardInterrupt:
        print("\nStopping calibration.", flush=True)
    finally:
        driver.stop()
        if results:
            report_path = write_report(args.output, results, args, complete=complete)
            print(f"Saved report: {report_path}", flush=True)
        else:
            print("No accepted results to save.", flush=True)


if __name__ == "__main__":
    main()
