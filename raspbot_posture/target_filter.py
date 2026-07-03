"""Target smoothing helpers for robot follow control."""

from dataclasses import dataclass


@dataclass
class SmoothedTarget:
    detected: bool = False
    x: float = 0.5
    y: float = 0.5
    area: float = 0.0
    confidence: float = 0.0
    posture: str = "No person"
    updated_at: float = 0.0


class TargetFilter:
    """Exponential smoother for HumanTarget values."""

    def __init__(self, smoothing, min_confidence):
        self.smoothing = max(0.0, min(0.98, float(smoothing)))
        self.min_confidence = float(min_confidence)
        self.value = SmoothedTarget()
        self.initialized = False

    def update(self, target):
        """Return the smoothed target, ignoring low-confidence samples."""
        if not target.detected or target.confidence < self.min_confidence:
            return self.value

        alpha_old = self.smoothing if self.initialized else 0.0
        alpha_new = 1.0 - alpha_old

        self.value = SmoothedTarget(
            detected=True,
            x=self.value.x * alpha_old + target.center_x * alpha_new,
            y=self.value.y * alpha_old + target.center_y * alpha_new,
            area=self.value.area * alpha_old + target.area * alpha_new,
            confidence=target.confidence,
            posture=target.posture,
            updated_at=target.updated_at,
        )
        self.initialized = True
        return self.value
