"""Action detectors built on top of PoseMetrics."""

import time

from .state import ActionStatus


class ActionDetectorRegistry:
    """Runs a list of action detectors and returns statuses by action name."""

    def __init__(self, detectors):
        self.detectors = list(detectors)

    def update(self, metrics, posture, target):
        """Run all detectors and return {action_name: ActionStatus}."""
        statuses = {}
        for detector in self.detectors:
            status = detector.update(metrics, posture, target)
            statuses[status.name] = status
        return statuses


class SquatCounter:
    """Squat counter using knee-angle hysteresis for faster movements."""

    name = 'squat'

    def __init__(
        self,
        stable_frames=1,
        down_angle=145.0,
        up_angle=155.0,
        cooldown=0.35,
        down_frames=None,
        up_frames=None,
    ):
        fallback_frames = max(1, int(stable_frames))
        self.down_frames_required = max(1, int(down_frames or fallback_frames))
        self.up_frames_required = max(1, int(up_frames or fallback_frames))
        self.down_angle = float(down_angle)
        self.up_angle = float(up_angle)
        self.cooldown = max(0.0, float(cooldown))
        self.count = 0
        self.stage = 'unknown'
        self.down_frames = 0
        self.up_frames = 0
        self.last_count_time = 0.0

    def update(self, metrics, posture, target):
        """Update squat state and return ActionStatus."""
        now = time.time()
        is_down = False
        is_up = False
        confidence = 0.0

        if metrics.legs_visible:
            is_down = metrics.knee_angle <= self.down_angle and metrics.hips_low
            is_up = metrics.knee_angle >= self.up_angle and abs(metrics.torso_offset) < 0.28
            confidence = max(0.0, min(1.0, target.confidence))

        if posture == 'Squat or sit':
            is_down = True
        elif posture == 'Standing':
            is_up = True

        self.down_frames = self.down_frames + 1 if is_down else 0
        self.up_frames = self.up_frames + 1 if is_up else 0

        if self.down_frames >= self.down_frames_required:
            self.stage = 'down'

        if self.up_frames >= self.up_frames_required:
            if self.stage == 'down' and now - self.last_count_time >= self.cooldown:
                self.count += 1
                self.last_count_time = now
            self.stage = 'up'

        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=is_down,
            confidence=confidence,
            updated_at=now,
        )


def build_action_registry(args):
    """Build the action detector set from runtime arguments."""
    return ActionDetectorRegistry(
        [
            SquatCounter(
                stable_frames=args.squat_stable_frames,
                down_angle=args.squat_down_angle,
                up_angle=args.squat_up_angle,
                cooldown=args.squat_cooldown,
                down_frames=args.squat_down_frames,
                up_frames=args.squat_up_frames,
            )
        ]
    )

