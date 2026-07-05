"""Frontend-facing state serialization helpers."""


def _round(value, digits=4):
    if value is None:
        return None
    if isinstance(value, float):
        return round(value, digits)
    return value


def target_payload(target):
    """Return a JSON-safe human target payload."""
    return {
        'detected': target.detected,
        'center_x': _round(target.center_x),
        'center_y': _round(target.center_y),
        'width': _round(target.width),
        'height': _round(target.height),
        'area': _round(target.area, 6),
        'confidence': _round(target.confidence),
        'posture': target.posture,
        'updated_at': _round(target.updated_at, 3),
    }


def action_payload(status):
    """Return a JSON-safe action status payload."""
    return {
        'name': status.name,
        'count': status.count,
        'target_count': status.target_count,
        'stage': status.stage,
        'active': status.active,
        'confidence': _round(status.confidence),
        'rep_quality': _round(status.rep_quality),
        'details': status.details,
        'updated_at': _round(status.updated_at, 3),
    }


def workout_payload(workout):
    """Return a JSON-safe workout status payload."""
    return {
        'session_id': workout.session_id,
        'program_name': workout.program_name,
        'current_station': workout.current_station,
        'current_action': workout.current_action,
        'station_index': workout.station_index,
        'total_stations': workout.total_stations,
        'target_count': workout.target_count,
        'current_count': workout.current_count,
        'elapsed_ms': workout.elapsed_ms,
        'action_progress': _round(workout.action_progress),
        'overall_progress': _round(workout.overall_progress),
        'completed': workout.completed,
        'events': list(workout.events),
    }


def tracking_payload(tracking):
    """Return a JSON-safe tracking summary payload."""
    return {
        'enabled': tracking.enabled,
        'mode': tracking.mode,
        'reason': tracking.reason,
        'distance_m': _round(tracking.distance_m),
        'distance_state': tracking.distance_state,
        'pan_error_degrees': _round(tracking.pan_error_degrees),
        'tilt_error_degrees': _round(tracking.tilt_error_degrees),
        'body_yaw_error_degrees': _round(tracking.body_yaw_error_degrees),
        'chassis_motion_direction': tracking.chassis_motion_direction,
        'chassis_direction_degrees': _round(tracking.chassis_direction_degrees),
        'motion_allowed': tracking.motion_allowed,
        'frozen': tracking.frozen,
    }


def obstacle_payload(obstacle):
    """Return a JSON-safe obstacle-avoidance summary payload."""
    return {
        'enabled': obstacle.enabled,
        'active': obstacle.active,
        'distance_mm': _round(obstacle.distance_mm),
        'raw_mm': _round(obstacle.raw_mm),
        'valid': obstacle.valid,
        'phase': obstacle.phase,
        'reason': obstacle.reason,
        'cooldown_remaining_s': _round(obstacle.cooldown_remaining_s, 2),
        'updated_at': _round(obstacle.updated_at, 3),
    }


def pose_features_payload(features):
    """Return compact pose feature payload, omitting raw landmarks."""
    if features is None:
        return {}
    return {
        'full_body': features.full_body,
        'arms_visible': features.arms_visible,
        'legs_visible': features.legs_visible,
        'torso_height': _round(features.torso_height),
        'shoulder_width': _round(features.shoulder_width),
        'hip_width': _round(features.hip_width),
        'knee_angle': _round(features.knee_angle),
        'knee_angle_gap': _round(features.knee_angle_gap),
        'left_knee_angle': _round(features.left_knee_angle),
        'right_knee_angle': _round(features.right_knee_angle),
        'left_elbow_angle': _round(features.left_elbow_angle),
        'right_elbow_angle': _round(features.right_elbow_angle),
    }


def analysis_payload(analysis, camera_fps=None):
    """Return the canonical frontend payload for a pose analysis snapshot."""
    payload = {
        'posture': analysis.posture,
        'camera_fps': _round(camera_fps, 2),
        'inference_fps': _round(analysis.inference_fps, 2),
        'latency_ms': _round(analysis.latency_ms, 2),
        'target': target_payload(analysis.target),
        'actions': {name: action_payload(status) for name, status in analysis.actions.items()},
        'workout': workout_payload(analysis.workout),
        'tracking': tracking_payload(analysis.tracking),
        'obstacle': obstacle_payload(analysis.obstacle),
        'pose_features': pose_features_payload(analysis.pose_features),
        'updated_at': _round(analysis.updated_at, 3),
    }
    if analysis.frontend_payload:
        payload.update(analysis.frontend_payload)
    return payload
