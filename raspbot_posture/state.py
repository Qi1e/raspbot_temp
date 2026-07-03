"""Thread-safe shared state and small data models."""

import threading
import time
from dataclasses import dataclass, field

from .constants import NO_PERSON_COLOR


@dataclass(frozen=True)
class HumanTarget:
    """Lightweight normalized human target for later car-follow control."""

    detected: bool = False
    center_x: float = 0.5
    center_y: float = 0.5
    width: float = 0.0
    height: float = 0.0
    area: float = 0.0
    confidence: float = 0.0
    posture: str = 'No person'
    updated_at: float = 0.0


@dataclass(frozen=True)
class ActionStatus:
    """Standard output from one action detector."""

    name: str
    count: int = 0
    stage: str = 'unknown'
    active: bool = False
    confidence: float = 0.0
    updated_at: float = 0.0


@dataclass(frozen=True)
class PoseAnalysis:
    """Immutable snapshot produced by one pose inference pass."""

    posture: str = 'No person'
    color: tuple = NO_PERSON_COLOR
    squat_count: int = 0
    squat_stage: str = 'unknown'
    actions: dict = field(default_factory=dict)
    inference_fps: float = 0.0
    latency_ms: float = 0.0
    target: HumanTarget = field(default_factory=HumanTarget)
    landmarks: object = None
    updated_at: float = 0.0


class AnalysisState:
    """Thread-safe holder for the latest PoseAnalysis."""

    def __init__(self):
        self.lock = threading.Lock()
        self.value = PoseAnalysis()

    def update(self, analysis):
        """Replace the latest analysis snapshot."""
        with self.lock:
            self.value = analysis

    def get(self):
        """Read the latest analysis snapshot."""
        with self.lock:
            return self.value

    def get_tracking_target(self):
        """Return the current HumanTarget for follow-control code."""
        return self.get().target

    def get_actions(self):
        """Return all current action states."""
        return self.get().actions

    def get_action_status(self, name):
        """Return one ActionStatus by name, such as squat or wave."""
        return self.get().actions.get(name)


class FrameMailbox:
    """Latest-frame-only handoff from camera loop to inference loop."""

    def __init__(self):
        self.condition = threading.Condition()
        self.frame = None
        self.frame_id = 0
        self.closed = False

    def submit(self, frame):
        """Submit the newest camera frame to the inference worker."""
        with self.condition:
            if self.closed:
                return
            self.frame = frame.copy()
            self.frame_id += 1
            self.condition.notify()

    def wait_latest(self, last_id, timeout=0.5):
        """Wait for a new frame and return (frame, frame_id)."""
        with self.condition:
            self.condition.wait_for(
                lambda: self.closed or (self.frame is not None and self.frame_id != last_id),
                timeout=timeout,
            )
            if self.closed or self.frame is None or self.frame_id == last_id:
                return None, last_id
            return self.frame.copy(), self.frame_id

    def close(self):
        """Wake the inference worker and stop waiting."""
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class FpsMeter:
    """Smoothed FPS meter for camera and inference loops."""

    def __init__(self, smoothing=0.85):
        self.smoothing = smoothing
        self.last_time = None
        self.fps = 0.0

    def tick(self):
        """Record one iteration and return smoothed FPS."""
        now = time.time()
        if self.last_time is None:
            self.last_time = now
            return self.fps

        instant = 1.0 / max(now - self.last_time, 0.001)
        self.last_time = now
        if self.fps <= 0:
            self.fps = instant
        else:
            self.fps = self.fps * self.smoothing + instant * (1.0 - self.smoothing)
        return self.fps

