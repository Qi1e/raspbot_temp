"""Pose landmark feature extraction and posture classification."""

import mediapipe as mp

from .constants import NO_PERSON_COLOR
from .geometry import PoseMetrics, angle, distance, landmark_visible, midpoint


class PostureClassifier:
    """Convert MediaPipe Pose landmarks into reusable metrics and labels."""

    def __init__(self, min_visibility=0.55):
        self.min_visibility = min_visibility
        self.pose_landmark = mp.solutions.pose.PoseLandmark

    def get(self, landmarks, name):
        """Read one landmark by MediaPipe PoseLandmark name."""
        return landmarks[self.pose_landmark[name].value]

    def visible(self, landmarks, *names):
        """Return whether all named landmarks pass the visibility threshold."""
        return all(landmark_visible(self.get(landmarks, name), self.min_visibility) for name in names)

    def measure(self, landmarks):
        """Extract reusable shoulder, hip, wrist, and knee pose metrics."""
        left_shoulder = self.get(landmarks, 'LEFT_SHOULDER')
        right_shoulder = self.get(landmarks, 'RIGHT_SHOULDER')
        left_wrist = self.get(landmarks, 'LEFT_WRIST')
        right_wrist = self.get(landmarks, 'RIGHT_WRIST')
        left_hip = self.get(landmarks, 'LEFT_HIP')
        right_hip = self.get(landmarks, 'RIGHT_HIP')
        left_knee = self.get(landmarks, 'LEFT_KNEE')
        right_knee = self.get(landmarks, 'RIGHT_KNEE')
        left_ankle = self.get(landmarks, 'LEFT_ANKLE')
        right_ankle = self.get(landmarks, 'RIGHT_ANKLE')

        full_body = self.visible(landmarks, 'LEFT_SHOULDER', 'RIGHT_SHOULDER', 'LEFT_HIP', 'RIGHT_HIP')
        if not full_body:
            return PoseMetrics()

        shoulder_width = max(distance(left_shoulder, right_shoulder), 0.01)
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

        knee_angle = 0.0
        hips_low = False
        if legs_visible:
            left_knee_angle = angle(left_hip, left_knee, left_ankle)
            right_knee_angle = angle(right_hip, right_knee, right_ankle)
            knee_angle = (left_knee_angle + right_knee_angle) / 2.0
            hips_low = hip_mid_y > shoulder_mid_y + 0.45 * torso_height

        return PoseMetrics(
            full_body=full_body,
            arms_visible=arms_visible,
            legs_visible=legs_visible,
            wrists_above_shoulders=wrists_above_shoulders,
            wrists_sideways=wrists_sideways,
            knee_angle=knee_angle,
            hips_low=hips_low,
            torso_offset=torso_offset,
            torso_height=torso_height,
        )

    def classify(self, metrics):
        """Return a display posture label and color from PoseMetrics."""
        if not metrics.full_body:
            return 'No full body', NO_PERSON_COLOR

        if metrics.arms_visible:
            if metrics.wrists_above_shoulders:
                return 'Arms up', (0, 220, 255)
            if metrics.wrists_sideways:
                return 'T pose', (255, 180, 0)

        if metrics.legs_visible:
            if metrics.knee_angle < 140 and metrics.hips_low:
                return 'Squat or sit', (0, 165, 255)
            if metrics.knee_angle > 155 and abs(metrics.torso_offset) < 0.22:
                return 'Standing', (80, 255, 80)

        if metrics.torso_offset > 0.28:
            return 'Leaning left', (255, 120, 120)
        if metrics.torso_offset < -0.28:
            return 'Leaning right', (255, 120, 120)

        return 'Body detected', (180, 255, 180)

