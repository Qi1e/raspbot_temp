"""Background ultrasonic distance sampling for tracking control."""

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class UltrasonicReading:
    enabled: bool = False
    distance_mm: object = None
    raw_mm: object = None
    valid: bool = False
    updated_at: float = 0.0
    reason: str = "disabled"


class UltrasonicMonitor:
    """Continuously read ultrasonic distance without owning motor control."""

    def __init__(self, bot=None, enabled=False, poll_interval=0.05, buffer_size=5):
        self.bot = bot
        self.enabled = bool(enabled)
        self.poll_interval = max(0.02, float(poll_interval))
        self._buffer = deque(maxlen=max(1, int(buffer_size)))
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        reason = "ready" if self.enabled and self.bot is not None else "disabled"
        if self.enabled and self.bot is None:
            reason = "hardware unavailable"
        self._reading = UltrasonicReading(enabled=self.enabled, updated_at=time.time(), reason=reason)

    def start(self):
        if not self.enabled or self.bot is None:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="ultrasonic-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self.enabled and self.bot is not None:
            try:
                self.bot.Ctrl_Ulatist_Switch(0)
            except Exception as exc:
                self._set_reading(UltrasonicReading(enabled=self.enabled, updated_at=time.time(), reason=str(exc)))

    def latest(self):
        with self._lock:
            return self._reading

    def _set_reading(self, reading):
        with self._lock:
            self._reading = reading

    def _loop(self):
        try:
            self.bot.Ctrl_Ulatist_Switch(1)
            time.sleep(0.08)
        except Exception as exc:
            self._set_reading(UltrasonicReading(enabled=self.enabled, updated_at=time.time(), reason=str(exc)))
            return

        while not self._stop_event.is_set():
            now = time.time()
            try:
                raw = self.bot.read_ultrasonic_mm()
                valid = 0 < raw < 9999
                if valid:
                    self._buffer.append(raw)
                distance = None
                if self._buffer:
                    sorted_values = sorted(self._buffer)
                    distance = sorted_values[len(sorted_values) // 2]
                reason = "ok" if distance is not None else "waiting for valid sample"
                self._set_reading(
                    UltrasonicReading(
                        enabled=self.enabled,
                        distance_mm=distance,
                        raw_mm=raw,
                        valid=distance is not None,
                        updated_at=now,
                        reason=reason,
                    )
                )
            except Exception as exc:
                self._set_reading(
                    UltrasonicReading(
                        enabled=self.enabled,
                        distance_mm=None,
                        raw_mm=None,
                        valid=False,
                        updated_at=now,
                        reason=str(exc),
                    )
                )
            self._stop_event.wait(self.poll_interval)
