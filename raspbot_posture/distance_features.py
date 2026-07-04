"""Feature extraction for human-distance estimation."""

from .geometry import distance, landmark_visible, midpoint


def pose_landmark_enum():
    import mediapipe as mp

    return mp.solutions.pose.PoseLandmark


def get_landmark(landmarks, name):
    return landmarks[pose_landmark_enum()[name].value]


def all_visible(landmarks, min_visibility, *names):
    return all(landmark_visible(get_landmark(landmarks, name), min_visibility) for name in names)


def any_visible(landmarks, min_visibility, *names):
    return any(landmark_visible(get_landmark(landmarks, name), min_visibility) for name in names)


def normalized_distance(landmarks, left_name, right_name):
    return distance(get_landmark(landmarks, left_name), get_landmark(landmarks, right_name))


def extract_distance_features(landmarks, target, posture, min_visibility):
    """Return pose features used by distance calibration and tracking."""
    visible_count = sum(1 for lm in landmarks if landmark_visible(lm, min_visibility))
    upper_body_visible = all_visible(
        landmarks,
        min_visibility,
        "LEFT_SHOULDER",
        "RIGHT_SHOULDER",
        "LEFT_HIP",
        "RIGHT_HIP",
    )
    legs_visible = all_visible(
        landmarks,
        min_visibility,
        "LEFT_HIP",
        "RIGHT_HIP",
        "LEFT_KNEE",
        "RIGHT_KNEE",
        "LEFT_ANKLE",
        "RIGHT_ANKLE",
    )
    head_visible = any_visible(
        landmarks,
        min_visibility,
        "NOSE",
        "LEFT_EYE",
        "RIGHT_EYE",
        "LEFT_EAR",
        "RIGHT_EAR",
    )
    feet_visible = any_visible(
        landmarks,
        min_visibility,
        "LEFT_ANKLE",
        "RIGHT_ANKLE",
        "LEFT_FOOT_INDEX",
        "RIGHT_FOOT_INDEX",
    )

    shoulder_width = 0.0
    torso_height = 0.0
    hip_width = 0.0
    if upper_body_visible:
        shoulder_width = normalized_distance(landmarks, "LEFT_SHOULDER", "RIGHT_SHOULDER")
        hip_width = normalized_distance(landmarks, "LEFT_HIP", "RIGHT_HIP")
        shoulder_mid = midpoint(get_landmark(landmarks, "LEFT_SHOULDER"), get_landmark(landmarks, "RIGHT_SHOULDER"))
        hip_mid = midpoint(get_landmark(landmarks, "LEFT_HIP"), get_landmark(landmarks, "RIGHT_HIP"))
        torso_height = abs(hip_mid[1] - shoulder_mid[1])

    if target.detected and upper_body_visible and legs_visible and head_visible and feet_visible:
        visible_mode = "full_body"
    elif target.detected and upper_body_visible:
        visible_mode = "upper_body"
    elif target.detected:
        visible_mode = "partial_body"
    else:
        visible_mode = "lost"

    return {
        "posture": posture,
        "confidence": target.confidence,
        "visible_landmark_count": visible_count,
        "visible_mode": visible_mode,
        "shoulder_width": shoulder_width,
        "torso_height": torso_height,
        "hip_width": hip_width,
        "head_visible": int(head_visible),
        "feet_visible": int(feet_visible),
    }


extract_calibration_features = extract_distance_features
