"""CSV logging for synchronized tracking runs."""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path


LOG_FIELDS = [
    "timestamp",
    "elapsed_s",
    "dt",
    "input_mode",
    "tracking_mode",
    "live",
    "detected",
    "tracking_allowed",
    "confidence",
    "distance_confidence_raw",
    "distance_stability_bonus",
    "distance_stability_s",
    "distance_stability_range_m",
    "target_confidence",
    "posture",
    "action_active",
    "target_center_x",
    "target_center_y",
    "target_area",
    "visible_mode",
    "distance_m",
    "distance_state",
    "distance_error_m",
    "pan_error_degrees",
    "tilt_error_degrees",
    "body_yaw_error_degrees",
    "chassis_motion_direction",
    "chassis_direction_degrees",
    "motion_allowed",
    "pan_angle",
    "tilt_angle",
    "visual_pan_delta",
    "yaw_comp_delta",
    "yaw_comp_residual",
    "final_pan_delta",
    "tilt_delta",
    "yaw_speed",
    "yaw_reason",
    "move_speed",
    "move_direction_degrees",
    "wheel_m0",
    "wheel_m1",
    "wheel_m2",
    "wheel_m3",
    "motion_goal_active",
    "motion_goal_reason",
    "obstacle_enabled",
    "obstacle_active",
    "obstacle_distance_mm",
    "obstacle_phase",
    "obstacle_reason",
    "obstacle_cooldown_s",
    "servo_idle_s",
    "tracking_reason",
]


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    return value


class TrackingLogger:
    def __init__(self, args):
        self.args = args
        self.enabled = bool(args.log_dir)
        self.file_obj = None
        self.writer = None
        self.csv_path = None
        self.args_path = None
        self.last_log_at = None
        self.next_log_at = 0.0

        if not self.enabled:
            return

        log_dir = Path(args.log_dir).expanduser()
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = args.log_prefix
        self.csv_path = log_dir / f"{prefix}_{stamp}.csv"
        self.args_path = log_dir / f"{prefix}_{stamp}_args.json"

        with self.args_path.open("w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "command": sys.argv,
                    "args": vars(args),
                    "fields": LOG_FIELDS,
                },
                file_obj,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

        self.file_obj = self.csv_path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file_obj, fieldnames=LOG_FIELDS)
        self.writer.writeheader()
        self.file_obj.flush()
        print(f"Tracking log: {self.csv_path}")
        print(f"Run args log: {self.args_path}")

    def maybe_log(
        self,
        now,
        started_at,
        tracking_frame,
        sample,
        goal,
        servo_update,
        yaw_decision,
        move_speed,
        move_direction_degrees,
        wheels,
        driver,
        obstacle_status=None,
    ):
        if not self.enabled:
            return
        if now < self.next_log_at:
            return

        interval = max(0.0, float(self.args.log_interval))
        self.next_log_at = now + interval
        dt = 0.0 if self.last_log_at is None else now - self.last_log_at
        self.last_log_at = now

        tracking = tracking_frame.tracking
        target = tracking.target
        target_center_x = 0.5 + getattr(target, "x_offset", 0.0)
        target_center_y = 0.5 + getattr(target, "y_offset", 0.0)
        obstacle_distance = "" if obstacle_status is None or obstacle_status.distance_mm is None else f"{obstacle_status.distance_mm:.1f}"
        row = {
            "timestamp": f"{now:.3f}",
            "elapsed_s": f"{now - started_at:.3f}",
            "dt": f"{dt:.3f}",
            "input_mode": self.args.input_mode,
            "tracking_mode": self.args.tracking_mode,
            "live": self.args.live,
            "detected": tracking.detected,
            "tracking_allowed": tracking.tracking_allowed,
            "confidence": f"{tracking.confidence:.4f}",
            "distance_confidence_raw": f"{getattr(tracking, 'raw_distance_confidence', tracking.confidence):.4f}",
            "distance_stability_bonus": f"{getattr(tracking, 'distance_stability_bonus', 0.0):.4f}",
            "distance_stability_s": f"{getattr(tracking, 'distance_stability_s', 0.0):.3f}",
            "distance_stability_range_m": f"{getattr(tracking, 'distance_stability_range_m', 0.0):.4f}",
            "target_confidence": f"{getattr(target, 'confidence', 0.0):.4f}",
            "posture": tracking_frame.posture,
            "action_active": tracking_frame.action_active,
            "target_center_x": f"{target_center_x:.4f}",
            "target_center_y": f"{target_center_y:.4f}",
            "target_area": f"{getattr(target, 'area', 0.0):.6f}",
            "visible_mode": getattr(target, "visible_mode", ""),
            "distance_m": tracking.distance_m,
            "distance_state": tracking.distance_state,
            "distance_error_m": f"{tracking.distance_error_m:.4f}",
            "pan_error_degrees": f"{tracking.pan_error_degrees:.3f}",
            "tilt_error_degrees": f"{tracking.tilt_error_degrees:.3f}",
            "body_yaw_error_degrees": f"{tracking.body_yaw_error_degrees:.3f}",
            "chassis_motion_direction": tracking.chassis_motion_direction,
            "chassis_direction_degrees": f"{tracking.chassis_direction_degrees:.3f}",
            "motion_allowed": tracking.motion_allowed,
            "pan_angle": f"{driver.pan_angle:.3f}",
            "tilt_angle": f"{driver.tilt_angle:.3f}",
            "visual_pan_delta": f"{servo_update.visual_pan_delta:.3f}",
            "yaw_comp_delta": f"{servo_update.yaw_comp_delta:.3f}",
            "yaw_comp_residual": f"{servo_update.yaw_comp_residual:.3f}",
            "final_pan_delta": f"{servo_update.final_pan_delta:.3f}",
            "tilt_delta": f"{servo_update.tilt_delta:.3f}",
            "yaw_speed": f"{yaw_decision.speed:.3f}",
            "yaw_reason": yaw_decision.reason,
            "move_speed": f"{move_speed:.3f}",
            "move_direction_degrees": f"{move_direction_degrees:.3f}",
            "wheel_m0": wheels.m0,
            "wheel_m1": wheels.m1,
            "wheel_m2": wheels.m2,
            "wheel_m3": wheels.m3,
            "motion_goal_active": goal.active,
            "motion_goal_reason": goal.reason,
            "obstacle_enabled": bool(getattr(obstacle_status, "enabled", False)),
            "obstacle_active": bool(getattr(obstacle_status, "active", False)),
            "obstacle_distance_mm": obstacle_distance,
            "obstacle_phase": getattr(obstacle_status, "phase", ""),
            "obstacle_reason": getattr(obstacle_status, "reason", ""),
            "obstacle_cooldown_s": f"{getattr(obstacle_status, 'cooldown_remaining_s', 0.0):.3f}",
            "servo_idle_s": f"{sample.servo_idle_s:.3f}",
            "tracking_reason": sample.tracking_reason,
        }
        self.writer.writerow({name: csv_value(row.get(name)) for name in LOG_FIELDS})
        self.file_obj.flush()

    def close(self):
        if self.file_obj is not None:
            self.file_obj.close()
            self.file_obj = None
