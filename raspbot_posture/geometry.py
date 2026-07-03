"""Geometry helpers for MediaPipe landmarks."""

import math
import time
from dataclasses import dataclass

from .state import HumanTarget


def landmark_visible(lm, min_visibility=0.55):
    """Return whether a landmark is reliable enough to use."""
    return lm.visibility >= min_visibility


def point(lm, width, height):
    """Convert a normalized landmark to image pixel coordinates."""
    return int(lm.x * width), int(lm.y * height)


def midpoint(a, b):
    """Return the normalized midpoint between two landmarks."""
    return (a.x + b.x) / 2.0, (a.y + b.y) / 2.0


def distance(a, b):
    """Return 2D normalized distance between two landmarks."""
    return math.hypot(a.x - b.x, a.y - b.y)


def angle(a, b, c):
    """Return the angle in degrees formed by landmarks a-b-c at b."""
    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)
    dot = ab[0] * cb[0] + ab[1] * cb[1]
    mag = math.hypot(*ab) * math.hypot(*cb)
    if mag == 0:
        return 0
    cos_value = max(-1.0, min(1.0, dot / mag))
    return math.degrees(math.acos(cos_value))


def clip01(value):
    """Clip a normalized value to the 0-1 range."""
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class PoseMetrics:
    """Reusable pose features shared by posture and action detectors."""

    full_body: bool = False
    arms_visible: bool = False
    legs_visible: bool = False
    wrists_above_shoulders: bool = False
    wrists_sideways: bool = False
    knee_angle: float = 0.0
    hips_low: bool = False
    torso_offset: float = 0.0
    torso_height: float = 0.0


def build_human_target(landmarks, posture, min_visibility):
    """Estimate a normalized body box and center from visible landmarks."""
    visible_points = [lm for lm in landmarks if landmark_visible(lm, min_visibility)]
    if len(visible_points) < 4:
        return HumanTarget(posture=posture, updated_at=time.time())

    min_x = clip01(min(lm.x for lm in visible_points))
    max_x = clip01(max(lm.x for lm in visible_points))
    min_y = clip01(min(lm.y for lm in visible_points))
    max_y = clip01(max(lm.y for lm in visible_points))
    width = max_x - min_x
    height = max_y - min_y
    confidence = sum(lm.visibility for lm in visible_points) / float(len(visible_points))

    return HumanTarget(
        detected=True,
        center_x=clip01((min_x + max_x) / 2.0),
        center_y=clip01((min_y + max_y) / 2.0),
        width=width,
        height=height,
        area=width * height,
        confidence=confidence,
        posture=posture,
        updated_at=time.time(),
    )

