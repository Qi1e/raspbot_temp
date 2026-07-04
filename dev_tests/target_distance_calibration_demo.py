#!/usr/bin/env python3
# coding: utf-8
"""Collect pose target samples for human-distance calibration."""

import argparse
import csv
import gc
import math
import statistics
import time
from collections import Counter
from pathlib import Path

from raspbot_posture.cli import add_posture_arguments
from raspbot_posture.distance_features import extract_distance_features as extract_calibration_features
from raspbot_posture.geometry import build_human_target


CSV_FIELDS = [
    "timestamp",
    "distance_m",
    "area",
    "width",
    "height",
    "center_x",
    "center_y",
    "pan_angle",
    "tilt_angle",
    "posture",
    "confidence",
    "visible_landmark_count",
    "visible_mode",
    "shoulder_width",
    "torso_height",
    "hip_width",
    "head_visible",
    "feet_visible",
]


PAN_FORWARD_ANGLE = 90.0


def repo_root():
    return Path(__file__).resolve().parents[1]


def resolve_output_path(output):
    path = Path(output).expanduser()
    if path.is_absolute():
        return path
    return repo_root() / path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Collect MediaPipe Pose samples for target distance calibration."
    )
    add_posture_arguments(parser)
    parser.set_defaults(no_preview=False)
    parser.add_argument("--distance", type=float, required=True, help="measured person-to-camera distance in meters")
    parser.add_argument("--duration", type=float, default=10.0, help="sample collection seconds")
    parser.add_argument(
        "--confirm-time",
        type=float,
        default=0.0,
        help="preview-only seconds before warmup and CSV collection",
    )
    parser.add_argument("--warmup", type=float, default=1.0, help="seconds to ignore before collecting")
    parser.add_argument("--output", default="dev_tests/target_distance_samples.csv", help="CSV file to append samples to")
    parser.add_argument("--tilt-angle", type=float, default=80.0, help="tilt servo angle for calibration")
    parser.add_argument("--max-center-offset", type=float, default=0.28, help="exclude summary samples beyond this x offset")
    parser.add_argument("--target-distance-min", type=float, default=0.8, help="nearest acceptable follow distance")
    parser.add_argument("--target-distance-max", type=float, default=1.2, help="farthest acceptable follow distance")
    return parser


def row_is_usable(row, max_center_offset):
    try:
        confidence = float(row["confidence"])
        center_x = float(row["center_x"])
        area = float(row["area"])
    except (TypeError, ValueError, KeyError):
        return False

    return (
        confidence > 0.0
        and area > 0.0
        and abs(center_x - 0.5) <= max_center_offset
        and row.get("visible_mode") in ("full_body", "upper_body")
    )


def median(values):
    values = [value for value in values if value > 0.0 and math.isfinite(value)]
    if not values:
        return 0.0
    return statistics.median(values)


def mean(values):
    values = [value for value in values if value > 0.0 and math.isfinite(value)]
    if not values:
        return 0.0
    return statistics.mean(values)


def stdev(values):
    values = [value for value in values if value > 0.0 and math.isfinite(value)]
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def feature_values(rows, name):
    values = []
    for row in rows:
        try:
            values.append(float(row[name]))
        except (TypeError, ValueError, KeyError):
            pass
    return values


def load_rows(path):
    if not path.exists():
        return []
    with path.open("r", newline="") as file_obj:
        return list(csv.DictReader(file_obj))


def append_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def area_from_distance(k_area, distance_m):
    if k_area <= 0.0 or distance_m <= 0.0:
        return 0.0
    return (k_area / distance_m) ** 2


def print_summary(rows, args):
    usable = [row for row in rows if row_is_usable(row, args.max_center_offset)]
    mode_counts = Counter(row.get("visible_mode", "unknown") for row in rows)
    usable_mode_counts = Counter(row.get("visible_mode", "unknown") for row in usable)

    print("\nCalibration summary")
    print(f"rows={len(rows)} usable={len(usable)} modes={dict(mode_counts)} usable_modes={dict(usable_mode_counts)}")
    if not usable:
        print("No usable rows yet. Keep the person centered and ensure shoulders/hips are visible.")
        return

    by_distance = {}
    for row in usable:
        try:
            key = round(float(row["distance_m"]), 3)
        except (TypeError, ValueError, KeyError):
            continue
        by_distance.setdefault(key, []).append(row)

    print("\nPer-distance medians")
    for distance_m in sorted(by_distance):
        group = by_distance[distance_m]
        print(
            f"{distance_m:.3f}m n={len(group)} "
            f"area={median(feature_values(group, 'area')):.4f} "
            f"shoulder={median(feature_values(group, 'shoulder_width')):.4f} "
            f"torso={median(feature_values(group, 'torso_height')):.4f} "
            f"confidence={median(feature_values(group, 'confidence')):.3f}"
        )

    k_area_values = []
    k_shoulder_values = []
    k_torso_values = []
    for row in usable:
        distance_m = float(row["distance_m"])
        area = float(row["area"])
        shoulder_width = float(row["shoulder_width"])
        torso_height = float(row["torso_height"])
        if area > 0.0:
            k_area_values.append(distance_m * math.sqrt(area))
        if shoulder_width > 0.0:
            k_shoulder_values.append(distance_m * shoulder_width)
        if torso_height > 0.0:
            k_torso_values.append(distance_m * torso_height)

    k_area = median(k_area_values)
    k_shoulder = median(k_shoulder_values)
    k_torso = median(k_torso_values)
    print("\nSimple distance models")
    print(f"distance_m ~= {k_area:.4f} / sqrt(area)      k_std={stdev(k_area_values):.4f}")
    print(f"distance_m ~= {k_shoulder:.4f} / shoulder_width k_std={stdev(k_shoulder_values):.4f}")
    print(f"distance_m ~= {k_torso:.4f} / torso_height    k_std={stdev(k_torso_values):.4f}")

    area_min = area_from_distance(k_area, args.target_distance_max)
    area_max = area_from_distance(k_area, args.target_distance_min)
    print("\nRecommended area thresholds from requested follow band")
    print(f"follow_band={args.target_distance_min:.2f}m..{args.target_distance_max:.2f}m")
    print(f"--target-area-min {area_min:.4f}")
    print(f"--target-area-max {area_max:.4f}")

    print("\nFeature stability on usable rows")
    for name in ("area", "shoulder_width", "torso_height"):
        values = feature_values(usable, name)
        print(f"{name}: mean={mean(values):.4f} median={median(values):.4f} std={stdev(values):.4f}")


def draw_overlay(frame, row, collected, total_seconds, phase="collect"):
    import cv2

    from raspbot_posture.rendering import draw_tracking_target

    draw_tracking_target(frame, type("TargetView", (), {
        "detected": float(row["area"]) > 0.0,
        "center_x": float(row["center_x"]),
        "center_y": float(row["center_y"]),
        "width": float(row["width"]),
        "height": float(row["height"]),
    })())
    cv2.putText(frame, f"{phase}: samples {collected} / {total_seconds:.1f}s", (20, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (80, 255, 80), 2)
    cv2.putText(frame, f"mode: {row['visible_mode']} area: {float(row['area']):.3f}", (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 240, 245), 2)
    cv2.putText(frame, f"shoulder: {float(row['shoulder_width']):.3f} torso: {float(row['torso_height']):.3f}", (20, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 240, 245), 2)


def empty_display_row():
    return {
        "area": "0.0",
        "center_x": "0.5",
        "center_y": "0.5",
        "width": "0.0",
        "height": "0.0",
        "visible_mode": "waiting",
        "shoulder_width": "0.0",
        "torso_height": "0.0",
    }


def collection_phase(now, confirm_until, warmup_until, end_at):
    if now < confirm_until:
        return "confirm", confirm_until - now
    if now < warmup_until:
        return "warmup", warmup_until - now
    return "collect", end_at - now


def set_calibration_servos(args):
    from raspbot_posture.hardware import Raspbot

    pan = int(round(PAN_FORWARD_ANGLE))
    tilt = max(0, min(100, int(round(args.tilt_angle))))
    bot = Raspbot()
    bot.Ctrl_Servo(1, pan)
    time.sleep(0.15)
    bot.Ctrl_Servo(2, tilt)
    time.sleep(0.35)
    print(f"Servos set for calibration: pan={pan}, tilt={tilt}")


def release_runtime(camera, pose, cv2_module, view_img, preview_server=None):
    if pose is not None:
        try:
            pose.close()
        except Exception as exc:
            print(f"Warning: failed to close MediaPipe Pose: {exc}")

    if camera is not None:
        try:
            camera.release()
        except Exception as exc:
            print(f"Warning: failed to release camera: {exc}")

    if preview_server is not None:
        try:
            preview_server.shutdown()
        except Exception as exc:
            print(f"Warning: failed to stop preview server: {exc}")

    if view_img and cv2_module is not None:
        try:
            cv2_module.destroyAllWindows()
            for _ in range(3):
                cv2_module.waitKey(1)
        except Exception as exc:
            print(f"Warning: failed to close OpenCV windows: {exc}")

    gc.collect()


def collect_samples(args):
    import cv2
    import mediapipe as mp

    from raspbot_posture.camera import open_camera
    from raspbot_posture.model_paths import ensure_pose_model_available
    from raspbot_posture.vision import PostureClassifier

    camera = None
    pose = None
    preview_state = None
    preview_server = None
    rows = []
    try:
        ensure_pose_model_available(args.model_complexity)
        set_calibration_servos(args)
        source = int(args.source) if str(args.source).isdigit() else args.source
        camera = open_camera(source, args.width, args.height)
        classifier = PostureClassifier(min_visibility=args.min_visibility)
        pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=args.model_complexity,
            smooth_landmarks=True,
            min_detection_confidence=args.min_detection_confidence,
            min_tracking_confidence=args.min_tracking_confidence,
        )

        if not args.no_preview:
            from raspbot_posture.preview import start_preview_server

            preview_state, preview_server = start_preview_server(
                args.preview_host,
                args.preview_port,
                args.preview_quality,
                args.preview_width,
                args.preview_fps,
            )

        started_at = time.time()
        confirm_until = started_at + max(0.0, args.confirm_time)
        warmup_until = confirm_until + max(0.0, args.warmup)
        end_at = warmup_until + max(0.0, args.duration)
        inference_interval = 0.0 if args.inference_fps <= 0.0 else 1.0 / float(args.inference_fps)
        next_inference_at = 0.0
        last_display_row = empty_display_row()

        print(
            f"Collecting distance={args.distance:.3f}m confirm={args.confirm_time:.1f}s warmup={args.warmup:.1f}s "
            f"duration={args.duration:.1f}s. Press q or Ctrl+C to stop early."
        )

        while time.time() < end_at:
            ok, frame = camera.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            if args.mirror:
                frame = cv2.flip(frame, 1)

            now = time.time()
            phase, remaining = collection_phase(now, confirm_until, warmup_until, end_at)
            preview_frame = frame.copy()
            draw_overlay(preview_frame, last_display_row, len(rows), max(0.0, remaining), phase=phase)
            if preview_state is not None:
                preview_state.publish(preview_frame)

            if args.view_img:
                cv2.imshow("target distance calibration", preview_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            row = None
            if now >= next_inference_at:
                next_inference_at = now + inference_interval
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = pose.process(rgb)
                rgb.flags.writeable = True

                if results.pose_landmarks:
                    landmarks = results.pose_landmarks.landmark
                    metrics = classifier.measure(landmarks)
                    posture, _ = classifier.classify(metrics)
                    target = build_human_target(landmarks, posture, args.min_visibility)
                    features = extract_calibration_features(landmarks, target, posture, args.min_visibility)
                    row = {
                        "timestamp": f"{now:.3f}",
                        "distance_m": f"{args.distance:.4f}",
                        "area": f"{target.area:.6f}",
                        "width": f"{target.width:.6f}",
                        "height": f"{target.height:.6f}",
                        "center_x": f"{target.center_x:.6f}",
                        "center_y": f"{target.center_y:.6f}",
                        "pan_angle": f"{PAN_FORWARD_ANGLE:.3f}",
                        "tilt_angle": f"{args.tilt_angle:.3f}",
                        **features,
                    }
                else:
                    row = {
                        "timestamp": f"{now:.3f}",
                        "distance_m": f"{args.distance:.4f}",
                        "area": "0.000000",
                        "width": "0.000000",
                        "height": "0.000000",
                        "center_x": "0.500000",
                        "center_y": "0.500000",
                        "pan_angle": f"{PAN_FORWARD_ANGLE:.3f}",
                        "tilt_angle": f"{args.tilt_angle:.3f}",
                        "posture": "No person",
                        "confidence": "0.000000",
                        "visible_landmark_count": 0,
                        "visible_mode": "lost",
                        "shoulder_width": "0.000000",
                        "torso_height": "0.000000",
                        "hip_width": "0.000000",
                        "head_visible": 0,
                        "feet_visible": 0,
                    }

                if now >= warmup_until:
                    rows.append(row)
                last_display_row = row
    except KeyboardInterrupt:
        print("\nInterrupted. Releasing camera and saving collected samples.")
    finally:
        release_runtime(camera, pose, cv2, args.view_img, preview_server=preview_server)

    return rows


def main():
    args = build_parser().parse_args()
    output_path = resolve_output_path(args.output)
    rows = collect_samples(args)
    append_rows(output_path, rows)
    print(f"\nAppended {len(rows)} rows to {output_path.resolve()}")
    print_summary(load_rows(output_path), args)


if __name__ == "__main__":
    main()
