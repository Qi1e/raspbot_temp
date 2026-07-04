#!/usr/bin/env python3
# coding: utf-8
"""Replay calibration CSV through the package target pose estimator."""

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path

from raspbot_posture.tracking_estimator import TargetPoseConfig, TargetTrackingInputBuilder


def build_parser():
    parser = argparse.ArgumentParser(description="Check fitted target pose estimator against a calibration CSV")
    parser.add_argument("--input", default="dev_tests/target_distance_samples.csv")
    parser.add_argument("--desired-min-distance", type=float, default=0.8)
    parser.add_argument("--desired-max-distance", type=float, default=1.2)
    parser.add_argument("--max-reasonable-distance", type=float, default=10.0)
    parser.add_argument("--min-confidence", type=float, default=0.7)
    return parser


def resolve_path(value):
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def row_usable(row, min_confidence):
    try:
        return (
            float(row["confidence"]) >= min_confidence
            and float(row["area"]) > 0.0
            and row.get("visible_mode") in ("full_body", "upper_body")
        )
    except (KeyError, TypeError, ValueError):
        return False


def summarize(label, items):
    if not items:
        print(f"{label}: no rows")
        return
    errors = [estimated - actual for actual, estimated in items]
    abs_errors = [abs(value) for value in errors]
    mae = statistics.mean(abs_errors)
    rmse = math.sqrt(statistics.mean(value * value for value in errors))
    bias = statistics.mean(errors)
    print(f"{label}: n={len(items)} mae={mae:.3f}m rmse={rmse:.3f}m bias={bias:+.3f}m")


def main():
    args = build_parser().parse_args()
    config = TargetPoseConfig(
        desired_min_distance=args.desired_min_distance,
        desired_max_distance=args.desired_max_distance,
        desired_distance=(args.desired_min_distance + args.desired_max_distance) / 2.0,
        max_reasonable_distance=args.max_reasonable_distance,
        min_confidence=args.min_confidence,
    )
    builder = TargetTrackingInputBuilder(config)
    path = resolve_path(args.input)
    with path.open("r", newline="") as file_obj:
        rows = list(csv.DictReader(file_obj))

    all_items = []
    by_model = defaultdict(list)
    by_distance = defaultdict(list)
    by_tilt = defaultdict(list)
    states = defaultdict(int)
    motions = defaultdict(int)
    camera_pan = defaultdict(int)
    camera_tilt = defaultdict(int)
    body_turn = defaultdict(int)

    for row in rows:
        if not row_usable(row, args.min_confidence):
            continue
        tracking = builder.from_csv_row(row)
        estimate = tracking.target
        if estimate.distance_m is None:
            continue
        actual = float(row["distance_m"])
        item = (actual, estimate.distance_m)
        all_items.append(item)
        by_model[estimate.model_name].append(item)
        by_distance[actual].append(item)
        by_tilt[float(row["tilt_angle"])].append(item)
        states[estimate.distance_state] += 1
        motions[tracking.chassis_motion_direction] += 1
        camera_pan[tracking.camera_pan_direction] += 1
        camera_tilt[tracking.camera_tilt_direction] += 1
        body_turn[tracking.body_turn_direction] += 1

    print(f"input={path}")
    print(f"rows={len(rows)} estimated={len(all_items)}")
    summarize("overall", all_items)

    print("\nBy model")
    for key in sorted(by_model):
        summarize(key, by_model[key])

    print("\nBy tilt")
    for key in sorted(by_tilt):
        summarize(f"tilt={key:.1f}", by_tilt[key])

    print("\nBy distance")
    for key in sorted(by_distance):
        summarize(f"distance={key:.2f}m", by_distance[key])

    print("\nControl states")
    print(f"distance_state={dict(sorted(states.items()))}")
    print(f"camera_pan_direction={dict(sorted(camera_pan.items()))}")
    print(f"camera_tilt_direction={dict(sorted(camera_tilt.items()))}")
    print(f"body_turn_direction={dict(sorted(body_turn.items()))}")
    print(f"chassis_motion_direction={dict(sorted(motions.items()))}")


if __name__ == "__main__":
    main()
