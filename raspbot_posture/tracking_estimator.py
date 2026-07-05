"""Convert pose target features into camera, yaw, and distance inputs."""

import time
from collections import deque
from dataclasses import dataclass, field
from dataclasses import replace
from typing import Dict, Optional

from .distance_models import agreement_confidence, model_confidence, select_model, weighted_distance


@dataclass(frozen=True)
class TargetPoseConfig:
    desired_min_distance: float = 2.7
    desired_max_distance: float = 3.3
    desired_distance: float = 3.0
    max_reasonable_distance: float = 10.0
    x_deadzone: float = 0.08
    y_deadzone: float = 0.10
    distance_x_deadzone: float = 0.12
    distance_backward_x_deadzone: float = 0.32
    pan_center: float = 90.0
    tilt_center: float = 50.0
    body_turn_pan_deadzone: float = 22.0
    min_confidence: float = 0.7
    distance_confidence_threshold: float = 0.35
    distance_stability_window_s: float = 1.5
    distance_stability_max_range_m: float = 0.3
    distance_stability_min_confidence: float = 0.25
    distance_stability_min_target_confidence: float = 0.75
    distance_stability_bonus: float = 0.12
    horizontal_fov_degrees: float = 62.0
    vertical_fov_degrees: float = 49.0


@dataclass(frozen=True)
class TargetPoseEstimate:
    detected: bool
    visible_mode: str
    model_name: str = "none"
    distance_m: Optional[float] = None
    distance_confidence: float = 0.0
    effective_distance_confidence: float = 0.0
    distance_stability_bonus: float = 0.0
    distance_stability_s: float = 0.0
    distance_stability_range_m: float = 0.0
    distance_state: str = "unknown"
    x_offset: float = 0.0
    y_offset: float = 0.0
    screen_direction: str = "center"
    pan_offset_deg: float = 0.0
    tilt_angle_deg: float = 0.0
    body_turn_direction: str = "none"
    motion_direction: str = "stop"
    area: float = 0.0
    shoulder_width: float = 0.0
    torso_height: float = 0.0
    confidence: float = 0.0
    motion_allowed: bool = False
    reason: str = "not evaluated"
    feature_distances: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class MotionTrackingInput:
    """Control input derived from the currently tracked person."""

    detected: bool
    tracking_allowed: bool
    confidence: float
    raw_distance_confidence: float
    distance_stability_bonus: float
    distance_stability_s: float
    distance_stability_range_m: float
    reason: str
    camera_pan_direction: str
    camera_tilt_direction: str
    pan_error_degrees: float
    tilt_error_degrees: float
    body_turn_direction: str
    body_yaw_error_degrees: float
    distance_m: Optional[float]
    distance_error_m: float
    distance_state: str
    chassis_motion_direction: str
    chassis_direction_degrees: float
    motion_allowed: bool
    target: TargetPoseEstimate

    def as_distance_control_kwargs(self, servo_idle_s, posture="Standing", action_active=False, updated_at=0.0):
        return {
            "detected": self.detected,
            "confidence": self.confidence,
            "pan_error_degrees": self.pan_error_degrees,
            "distance_error_m": self.distance_error_m,
            "distance_state": self.distance_state,
            "servo_idle_s": servo_idle_s,
            "posture": posture,
            "action_active": action_active,
            "motion_allowed": self.motion_allowed,
            "updated_at": updated_at,
        }


def screen_direction(x_offset, deadzone):
    if x_offset < -deadzone:
        return "left"
    if x_offset > deadzone:
        return "right"
    return "center"


def tilt_direction(y_offset, deadzone):
    if y_offset < -deadzone:
        return "up"
    if y_offset > deadzone:
        return "down"
    return "center"


def distance_state(distance_m, config):
    if distance_m is None:
        return "unknown"
    if distance_m < config.desired_min_distance:
        return "too_close"
    if distance_m > config.desired_max_distance:
        return "too_far"
    return "ok"


def body_turn_direction(pan_offset, deadzone):
    if pan_offset > deadzone:
        return "left"
    if pan_offset < -deadzone:
        return "right"
    return "none"


def camera_pan_error_degrees(x_offset, config):
    return -float(x_offset) * float(config.horizontal_fov_degrees)


def camera_tilt_error_degrees(y_offset, config):
    return -float(y_offset) * float(config.vertical_fov_degrees)


def distance_error(distance_m, config):
    if distance_m is None:
        return 0.0
    return float(distance_m) - float(config.desired_distance)


def _clamp01(value):
    return max(0.0, min(1.0, float(value)))


def motion_allowed_for(target, config, confidence):
    x_limit = distance_x_limit_for(target, config)
    return (
        target.distance_m is not None
        and abs(target.x_offset) <= x_limit
        and float(confidence) >= config.distance_confidence_threshold
        and target.distance_state != "unknown"
    )


def distance_x_limit_for(target, config):
    if target.distance_state == "too_close":
        return max(float(config.distance_x_deadzone), float(config.distance_backward_x_deadzone))
    return float(config.distance_x_deadzone)


def motion_reason_for(target, config, motion_allowed, stability_bonus=0.0):
    if abs(target.x_offset) > distance_x_limit_for(target, config):
        return "target is not centered enough for distance control"
    if target.distance_state == "ok":
        return "distance is inside desired band"
    if motion_allowed and stability_bonus > 0.0:
        return f"{target.model_name} estimates target is {target.distance_state} (stable distance)"
    if motion_allowed:
        return f"{target.model_name} estimates target is {target.distance_state}"
    return "distance estimate confidence is too low"


def chassis_motion(distance_error_m, pan_error_degrees, motion_allowed):
    if not motion_allowed:
        return "stop", 90.0
    if distance_error_m > 0.0:
        return "forward", (90.0 + pan_error_degrees) % 360.0
    if distance_error_m < 0.0:
        return "backward", (270.0 + pan_error_degrees) % 360.0
    return "stop", 90.0


def estimate_target_pose(
    detected,
    area,
    center_x,
    center_y,
    confidence,
    visible_mode,
    shoulder_width,
    torso_height,
    tilt_angle,
    pan_angle=90.0,
    config=None,
):
    """Estimate target distance and control direction from calibrated features."""
    config = config or TargetPoseConfig()
    area = float(area or 0.0)
    center_x = float(center_x or 0.5)
    center_y = float(center_y or 0.5)
    confidence = float(confidence or 0.0)
    shoulder_width = float(shoulder_width or 0.0)
    torso_height = float(torso_height or 0.0)
    tilt_angle = float(tilt_angle or 0.0)
    pan_angle = float(pan_angle or config.pan_center)

    x_offset = center_x - 0.5
    y_offset = center_y - 0.5
    screen_dir = screen_direction(x_offset, config.x_deadzone)
    pan_offset = pan_angle - config.pan_center
    body_dir = body_turn_direction(pan_offset, config.body_turn_pan_deadzone)

    base = {
        "visible_mode": visible_mode or "lost",
        "x_offset": x_offset,
        "y_offset": y_offset,
        "screen_direction": screen_dir,
        "pan_offset_deg": pan_offset,
        "tilt_angle_deg": tilt_angle,
        "body_turn_direction": body_dir,
        "area": area,
        "shoulder_width": shoulder_width,
        "torso_height": torso_height,
        "confidence": confidence,
    }
    if not detected or confidence < config.min_confidence:
        return TargetPoseEstimate(detected=False, reason="target lost or low confidence", **base)

    if visible_mode not in ("full_body", "upper_body"):
        return TargetPoseEstimate(
            detected=True,
            reason="visible body mode is not reliable for distance",
            **base,
        )

    model = select_model(tilt_angle)
    features = {"area": area, "shoulder_width": shoulder_width, "torso_height": torso_height}
    distance_m, feature_distances = weighted_distance(model, features)
    if distance_m is not None and config.max_reasonable_distance > 0.0 and distance_m > config.max_reasonable_distance:
        return TargetPoseEstimate(
            detected=True,
            model_name=model.name,
            distance_m=None,
            distance_confidence=0.0,
            distance_state="unknown",
            motion_allowed=False,
            reason=f"distance estimate exceeds {config.max_reasonable_distance:.1f}m limit",
            feature_distances=feature_distances,
            **base,
        )

    feature_values = list(feature_distances.values())
    agreement = agreement_confidence(feature_values)
    model_score = model_confidence(model, tilt_angle, distance_m)
    visible_score = 1.0 if visible_mode == "full_body" else 0.82
    distance_confidence = max(0.0, min(1.0, confidence * agreement * model_score * visible_score))
    state = distance_state(distance_m, config)

    target = TargetPoseEstimate(
        detected=True,
        model_name=model.name,
        distance_m=distance_m,
        distance_confidence=distance_confidence,
        effective_distance_confidence=distance_confidence,
        distance_state=state,
        feature_distances=feature_distances,
        **base,
    )
    motion_allowed = motion_allowed_for(target, config, distance_confidence)
    if motion_allowed and state == "too_far":
        motion_direction = "forward"
    elif motion_allowed and state == "too_close":
        motion_direction = "backward"
    else:
        motion_direction = "stop"

    return replace(
        target,
        motion_allowed=motion_allowed,
        motion_direction=motion_direction,
        reason=motion_reason_for(target, config, motion_allowed),
    )


class TargetTrackingInputBuilder:
    """Build camera/chassis tracking inputs from calibrated pose features."""

    def __init__(self, config=None):
        self.config = config or TargetPoseConfig()
        self._distance_history = deque()

    def _reset_distance_history(self):
        self._distance_history.clear()

    def _stability_bonus(self, target, now):
        config = self.config
        if (
            not target.detected
            or target.distance_m is None
            or target.visible_mode not in ("full_body", "upper_body")
            or target.confidence < config.distance_stability_min_target_confidence
            or target.distance_confidence < config.distance_stability_min_confidence
        ):
            self._reset_distance_history()
            return 0.0, 0.0, 0.0

        window = max(0.0, float(config.distance_stability_window_s))
        if window <= 0.0 or config.distance_stability_bonus <= 0.0:
            return 0.0, 0.0, 0.0

        now = time.monotonic() if now is None else float(now)
        self._distance_history.append((now, float(target.distance_m)))
        cutoff = now - window
        while self._distance_history and self._distance_history[0][0] < cutoff:
            self._distance_history.popleft()

        if len(self._distance_history) < 2:
            return 0.0, 0.0, 0.0

        span = self._distance_history[-1][0] - self._distance_history[0][0]
        values = [item[1] for item in self._distance_history]
        distance_range = max(values) - min(values)
        if span < window or distance_range > config.distance_stability_max_range_m:
            return 0.0, span, distance_range
        return float(config.distance_stability_bonus), span, distance_range

    def _apply_effective_confidence(self, target, now):
        bonus, stable_s, stable_range = self._stability_bonus(target, now)
        effective = _clamp01(target.distance_confidence + bonus)
        motion_allowed = motion_allowed_for(target, self.config, effective)
        if motion_allowed and target.distance_state == "too_far":
            motion_direction = "forward"
        elif motion_allowed and target.distance_state == "too_close":
            motion_direction = "backward"
        else:
            motion_direction = "stop"

        return replace(
            target,
            effective_distance_confidence=effective,
            distance_stability_bonus=bonus,
            distance_stability_s=stable_s,
            distance_stability_range_m=stable_range,
            motion_allowed=motion_allowed,
            motion_direction=motion_direction,
            reason=motion_reason_for(target, self.config, motion_allowed, bonus),
        )

    def from_features(
        self,
        detected,
        area,
        center_x,
        center_y,
        confidence,
        visible_mode,
        shoulder_width,
        torso_height,
        tilt_angle,
        pan_angle=90.0,
        now=None,
    ):
        target = estimate_target_pose(
            detected=detected,
            area=area,
            center_x=center_x,
            center_y=center_y,
            confidence=confidence,
            visible_mode=visible_mode,
            shoulder_width=shoulder_width,
            torso_height=torso_height,
            tilt_angle=tilt_angle,
            pan_angle=pan_angle,
            config=self.config,
        )
        return self.from_estimate(target, now=now)

    def from_estimate(self, target, now=None):
        target = self._apply_effective_confidence(target, now)
        pan_error = camera_pan_error_degrees(target.x_offset, self.config)
        tilt_error = camera_tilt_error_degrees(target.y_offset, self.config)
        camera_pan_direction = screen_direction(target.x_offset, self.config.x_deadzone)
        camera_tilt_direction = tilt_direction(target.y_offset, self.config.y_deadzone)
        dist_error = distance_error(target.distance_m, self.config)
        chassis_direction, chassis_direction_degrees = chassis_motion(dist_error, pan_error, target.motion_allowed)

        tracking_allowed = (
            target.detected
            and target.confidence >= self.config.min_confidence
            and target.visible_mode in ("full_body", "upper_body")
        )

        return MotionTrackingInput(
            detected=target.detected,
            tracking_allowed=tracking_allowed,
            confidence=target.effective_distance_confidence,
            raw_distance_confidence=target.distance_confidence,
            distance_stability_bonus=target.distance_stability_bonus,
            distance_stability_s=target.distance_stability_s,
            distance_stability_range_m=target.distance_stability_range_m,
            reason=target.reason,
            camera_pan_direction=camera_pan_direction,
            camera_tilt_direction=camera_tilt_direction,
            pan_error_degrees=pan_error,
            tilt_error_degrees=tilt_error,
            body_turn_direction=target.body_turn_direction,
            body_yaw_error_degrees=target.pan_offset_deg,
            distance_m=target.distance_m,
            distance_error_m=dist_error,
            distance_state=target.distance_state,
            chassis_motion_direction=chassis_direction,
            chassis_direction_degrees=chassis_direction_degrees,
            motion_allowed=target.motion_allowed,
            target=target,
        )

    def from_csv_row(self, row):
        return self.from_features(
            detected=float(row["area"]) > 0.0,
            area=float(row["area"]),
            center_x=float(row["center_x"]),
            center_y=float(row["center_y"]),
            confidence=float(row["confidence"]),
            visible_mode=row["visible_mode"],
            shoulder_width=float(row["shoulder_width"]),
            torso_height=float(row["torso_height"]),
            tilt_angle=float(row["tilt_angle"]),
            pan_angle=float(row.get("pan_angle", self.config.pan_center)),
        )
