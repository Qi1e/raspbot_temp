"""Pose feature extraction for HYROX action detectors."""

import time
from dataclasses import dataclass, field

from raspbot_posture.geometry import angle, clip01, distance, landmark_visible, midpoint


@dataclass(frozen=True)
class TargetBox:
    """Normalized visible-body box."""

    detected: bool = False
    center_x: float = 0.5
    center_y: float = 0.5
    width: float = 0.0
    height: float = 0.0
    area: float = 0.0
    confidence: float = 0.0


@dataclass(frozen=True)
class PoseFeatures:
    """Reusable 2D MediaPipe features for action detection and recording."""

    full_body: bool = False
    arms_visible: bool = False
    legs_visible: bool = False
    wrists_above_shoulders: bool = False
    wrists_sideways: bool = False
    hips_low: bool = False
    torso_offset: float = 0.0
    torso_height: float = 0.0
    shoulder_width: float = 0.0
    hip_width: float = 0.0
    shoulder_mid_x: float = 0.0
    shoulder_mid_y: float = 0.0
    hip_mid_x: float = 0.0
    hip_mid_y: float = 0.0
    knee_mid_x: float = 0.0
    knee_mid_y: float = 0.0
    ankle_mid_x: float = 0.0
    ankle_mid_y: float = 0.0
    ankle_width: float = 0.0
    ankle_width_ratio: float = 0.0
    ankle_y_gap: float = 0.0
    knee_y_gap: float = 0.0
    hip_ankle_mid_x_gap: float = 0.0
    left_knee_ankle_x_gap: float = 0.0
    right_knee_ankle_x_gap: float = 0.0
    knee_angle: float = 0.0
    left_knee_angle: float = 0.0
    right_knee_angle: float = 0.0
    knee_angle_gap: float = 0.0
    left_hip_angle: float = 0.0
    right_hip_angle: float = 0.0
    left_elbow_angle: float = 0.0
    right_elbow_angle: float = 0.0
    left_shoulder_angle: float = 0.0
    right_shoulder_angle: float = 0.0
    target: TargetBox = field(default_factory=TargetBox)
    updated_at: float = 0.0

    def key_angles(self):
        """Return joint angles for backend completion scoring."""
        return {
            'left_knee': self.left_knee_angle,
            'right_knee': self.right_knee_angle,
            'left_hip': self.left_hip_angle,
            'right_hip': self.right_hip_angle,
            'left_elbow': self.left_elbow_angle,
            'right_elbow': self.right_elbow_angle,
            'left_shoulder': self.left_shoulder_angle,
            'right_shoulder': self.right_shoulder_angle,
        }

    def key_features(self):
        """Return normalized non-angle features for backend scoring."""
        return {
            'hips_low': self.hips_low,
            'torso_offset': self.torso_offset,
            'torso_height': self.torso_height,
            'shoulder_width': self.shoulder_width,
            'hip_width': self.hip_width,
            'shoulder_mid_x': self.shoulder_mid_x,
            'shoulder_mid_y': self.shoulder_mid_y,
            'hip_mid_x': self.hip_mid_x,
            'hip_mid_y': self.hip_mid_y,
            'knee_mid_x': self.knee_mid_x,
            'knee_mid_y': self.knee_mid_y,
            'ankle_mid_x': self.ankle_mid_x,
            'ankle_mid_y': self.ankle_mid_y,
            'ankle_width': self.ankle_width,
            'ankle_width_ratio': self.ankle_width_ratio,
            'ankle_y_gap': self.ankle_y_gap,
            'knee_y_gap': self.knee_y_gap,
            'hip_ankle_mid_x_gap': self.hip_ankle_mid_x_gap,
            'left_knee_ankle_x_gap': self.left_knee_ankle_x_gap,
            'right_knee_ankle_x_gap': self.right_knee_ankle_x_gap,
            'knee_angle_avg': self.knee_angle,
            'knee_angle_gap': self.knee_angle_gap,
        }


class PoseFeatureExtractor:
    """Convert MediaPipe landmarks into HYROX-friendly features."""

    def __init__(self, min_visibility=0.55):
        import mediapipe as mp

        self.min_visibility = float(min_visibility)
        self.pose_landmark = mp.solutions.pose.PoseLandmark

    def get(self, landmarks, name):
        """Read one MediaPipe PoseLandmark by name."""
        return landmarks[self.pose_landmark[name].value]

    def visible(self, landmarks, *names):
        """Return whether all named landmarks pass the visibility threshold."""
        return all(landmark_visible(self.get(landmarks, name), self.min_visibility) for name in names)

    def target_box(self, landmarks):
        """Estimate a normalized visible-body box."""
        visible_points = [lm for lm in landmarks if landmark_visible(lm, self.min_visibility)]
        if len(visible_points) < 4:
            return TargetBox()

        min_x = clip01(min(lm.x for lm in visible_points))
        max_x = clip01(max(lm.x for lm in visible_points))
        min_y = clip01(min(lm.y for lm in visible_points))
        max_y = clip01(max(lm.y for lm in visible_points))
        width = max_x - min_x
        height = max_y - min_y
        confidence = sum(lm.visibility for lm in visible_points) / float(len(visible_points))
        return TargetBox(
            detected=True,
            center_x=clip01((min_x + max_x) / 2.0),
            center_y=clip01((min_y + max_y) / 2.0),
            width=width,
            height=height,
            area=width * height,
            confidence=confidence,
        )

    def extract(self, landmarks):
        """Extract one feature snapshot from MediaPipe pose landmarks."""
        now = time.time()
        target = self.target_box(landmarks)

        left_shoulder = self.get(landmarks, 'LEFT_SHOULDER')
        right_shoulder = self.get(landmarks, 'RIGHT_SHOULDER')
        left_hip = self.get(landmarks, 'LEFT_HIP')
        right_hip = self.get(landmarks, 'RIGHT_HIP')

        full_body = self.visible(landmarks, 'LEFT_SHOULDER', 'RIGHT_SHOULDER', 'LEFT_HIP', 'RIGHT_HIP')
        if not full_body:
            return PoseFeatures(target=target, updated_at=now)

        left_elbow = self.get(landmarks, 'LEFT_ELBOW')
        right_elbow = self.get(landmarks, 'RIGHT_ELBOW')
        left_wrist = self.get(landmarks, 'LEFT_WRIST')
        right_wrist = self.get(landmarks, 'RIGHT_WRIST')
        left_knee = self.get(landmarks, 'LEFT_KNEE')
        right_knee = self.get(landmarks, 'RIGHT_KNEE')
        left_ankle = self.get(landmarks, 'LEFT_ANKLE')
        right_ankle = self.get(landmarks, 'RIGHT_ANKLE')

        shoulder_width = max(distance(left_shoulder, right_shoulder), 0.01)
        hip_width = distance(left_hip, right_hip)
        shoulder_mid_x, shoulder_mid_y = midpoint(left_shoulder, right_shoulder)
        hip_mid_x, hip_mid_y = midpoint(left_hip, right_hip)
        torso_height = max(abs(hip_mid_y - shoulder_mid_y), 0.01)
        torso_offset = (shoulder_mid_x - hip_mid_x) / shoulder_width

        arms_visible = self.visible(
            landmarks,
            'LEFT_SHOULDER',
            'RIGHT_SHOULDER',
            'LEFT_ELBOW',
            'RIGHT_ELBOW',
            'LEFT_WRIST',
            'RIGHT_WRIST',
        )
        legs_visible = self.visible(
            landmarks,
            'LEFT_HIP',
            'RIGHT_HIP',
            'LEFT_KNEE',
            'RIGHT_KNEE',
            'LEFT_ANKLE',
            'RIGHT_ANKLE',
        )

        wrists_above_shoulders = False
        wrists_sideways = False
        left_elbow_angle = 0.0
        right_elbow_angle = 0.0
        left_shoulder_angle = 0.0
        right_shoulder_angle = 0.0
        if arms_visible:
            wrists_above_shoulders = (
                left_wrist.y < left_shoulder.y - 0.08 * torso_height
                and right_wrist.y < right_shoulder.y - 0.08 * torso_height
            )
            wrists_sideways = (
                abs(left_wrist.y - left_shoulder.y) < 0.45 * torso_height
                and abs(right_wrist.y - right_shoulder.y) < 0.45 * torso_height
                and left_wrist.x < left_shoulder.x - 0.45 * shoulder_width
                and right_wrist.x > right_shoulder.x + 0.45 * shoulder_width
            )
            left_elbow_angle = angle(left_shoulder, left_elbow, left_wrist)
            right_elbow_angle = angle(right_shoulder, right_elbow, right_wrist)
            left_shoulder_angle = angle(left_elbow, left_shoulder, left_hip)
            right_shoulder_angle = angle(right_elbow, right_shoulder, right_hip)

        knee_angle = 0.0
        left_knee_angle = 0.0
        right_knee_angle = 0.0
        knee_angle_gap = 0.0
        left_hip_angle = 0.0
        right_hip_angle = 0.0
        knee_mid_x = 0.0
        knee_mid_y = 0.0
        ankle_mid_x = 0.0
        ankle_mid_y = 0.0
        ankle_width = 0.0
        ankle_width_ratio = 0.0
        ankle_y_gap = 0.0
        knee_y_gap = 0.0
        hip_ankle_mid_x_gap = 0.0
        left_knee_ankle_x_gap = 0.0
        right_knee_ankle_x_gap = 0.0
        hips_low = False
        if legs_visible:
            knee_mid_x, knee_mid_y = midpoint(left_knee, right_knee)
            ankle_mid_x, ankle_mid_y = midpoint(left_ankle, right_ankle)
            left_knee_angle = angle(left_hip, left_knee, left_ankle)
            right_knee_angle = angle(right_hip, right_knee, right_ankle)
            knee_angle = (left_knee_angle + right_knee_angle) / 2.0
            knee_angle_gap = abs(left_knee_angle - right_knee_angle)
            left_hip_angle = angle(left_shoulder, left_hip, left_knee)
            right_hip_angle = angle(right_shoulder, right_hip, right_knee)
            ankle_width = abs(left_ankle.x - right_ankle.x)
            ankle_width_ratio = ankle_width / shoulder_width
            ankle_y_gap = abs(left_ankle.y - right_ankle.y)
            knee_y_gap = abs(left_knee.y - right_knee.y)
            hip_ankle_mid_x_gap = abs(hip_mid_x - ankle_mid_x) / shoulder_width
            left_knee_ankle_x_gap = abs(left_knee.x - left_ankle.x) / shoulder_width
            right_knee_ankle_x_gap = abs(right_knee.x - right_ankle.x) / shoulder_width
            hips_low = hip_mid_y > shoulder_mid_y + 0.45 * torso_height

        return PoseFeatures(
            full_body=full_body,
            arms_visible=arms_visible,
            legs_visible=legs_visible,
            wrists_above_shoulders=wrists_above_shoulders,
            wrists_sideways=wrists_sideways,
            hips_low=hips_low,
            torso_offset=torso_offset,
            torso_height=torso_height,
            shoulder_width=shoulder_width,
            hip_width=hip_width,
            shoulder_mid_x=shoulder_mid_x,
            shoulder_mid_y=shoulder_mid_y,
            hip_mid_x=hip_mid_x,
            hip_mid_y=hip_mid_y,
            knee_mid_x=knee_mid_x,
            knee_mid_y=knee_mid_y,
            ankle_mid_x=ankle_mid_x,
            ankle_mid_y=ankle_mid_y,
            ankle_width=ankle_width,
            ankle_width_ratio=ankle_width_ratio,
            ankle_y_gap=ankle_y_gap,
            knee_y_gap=knee_y_gap,
            hip_ankle_mid_x_gap=hip_ankle_mid_x_gap,
            left_knee_ankle_x_gap=left_knee_ankle_x_gap,
            right_knee_ankle_x_gap=right_knee_ankle_x_gap,
            knee_angle=knee_angle,
            left_knee_angle=left_knee_angle,
            right_knee_angle=right_knee_angle,
            knee_angle_gap=knee_angle_gap,
            left_hip_angle=left_hip_angle,
            right_hip_angle=right_hip_angle,
            left_elbow_angle=left_elbow_angle,
            right_elbow_angle=right_elbow_angle,
            left_shoulder_angle=left_shoulder_angle,
            right_shoulder_angle=right_shoulder_angle,
            target=target,
            updated_at=now,
        )


def classify_posture(features):
    """Return a simple posture label from HYROX features."""
    if not features.full_body:
        return 'No full body'
    if features.arms_visible and features.wrists_above_shoulders:
        return 'Arms up'
    if features.arms_visible and features.wrists_sideways:
        return 'T pose'
    if features.legs_visible:
        if features.knee_angle < 140 and features.hips_low:
            return 'Squat or sit'
        if features.knee_angle > 155 and abs(features.torso_offset) < 0.22:
            return 'Standing'
    if features.torso_offset > 0.28:
        return 'Leaning left'
    if features.torso_offset < -0.28:
        return 'Leaning right'
    return 'Body detected'
