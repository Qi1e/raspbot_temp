"""In-memory live session state and WebSocket fanout."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any


HYROX_ACTIONS = {"squat", "lunge", "burpee"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        return int(number)
    return int(number * 1000)


def _pose_quality(target_confidence: float | None, visibility: dict[str, Any]) -> str:
    if target_confidence is None:
        return "unknown"
    if target_confidence < 0.55:
        return "poor"
    if not visibility.get("full_body", False):
        return "partial"
    if target_confidence >= 0.8:
        return "good"
    return "ok"


def _resolve_current_action(
    active_action: str | None,
    actions: dict[str, Any],
    previous_action: str | None,
) -> tuple[str, str]:
    if active_action in HYROX_ACTIONS:
        action_status = actions.get(active_action) or {}
        return active_action, action_status.get("stage") or "unknown"

    active_candidates = []
    for action, status in actions.items():
        if action not in HYROX_ACTIONS or not isinstance(status, dict) or not status.get("active"):
            continue
        try:
            confidence = float(status.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        active_candidates.append((confidence, action, status.get("stage") or "unknown"))
    if active_candidates:
        _, action, phase = max(active_candidates)
        return action, phase

    if previous_action in HYROX_ACTIONS:
        previous_status = actions.get(previous_action) or {}
        phase = previous_status.get("stage") if isinstance(previous_status, dict) else None
        return previous_action, phase or "unknown"

    return "none", "unknown"


class LiveState:
    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._latest_session_id: str | None = None
        self._notify_reps = False
        self._pushover_enabled: bool | None = None
        self._hr_device: dict[str, Any] = {"status": "disconnected"}

    @property
    def notify_reps(self) -> bool:
        return self._notify_reps

    def set_notify_reps(self, enabled: bool) -> None:
        self._notify_reps = bool(enabled)
        for snapshot in self._snapshots.values():
            snapshot.setdefault("notifications", {})["notify_reps"] = self._notify_reps

    def set_pushover_enabled(self, enabled: bool) -> None:
        self._pushover_enabled = bool(enabled)
        for snapshot in self._snapshots.values():
            snapshot.setdefault("notifications", {})["pushover_enabled"] = self._pushover_enabled

    def get_snapshot(self, session_id: str) -> dict[str, Any]:
        return self._snapshots.get(session_id) or {
            "type": "live_snapshot",
            "session_id": session_id,
            "timestamp_ms": _now_ms(),
            "status": "idle",
            "timer": {"duration_s": 0, "active_duration_s": 0},
            "current": {"action": "none", "phase": "unknown", "posture": "unknown"},
            "counts": {},
            "heart_rate": {"bpm": None, "zone": None, "status": "missing"},
            "robot": {
                "device_id": None,
                "last_sample_age_ms": None,
                "pose_quality": "unknown",
                "connection_status": "offline",
                "sample_count": 0,
                "latest_sample_id": None,
                "elapsed_ms": 0,
                "server_elapsed_ms": 0,
                "robot_elapsed_ms": None,
                "received_at_ms": None,
                "robot_timestamp_ms": None,
                "target_confidence": None,
                "angles": {},
                "visibility": {},
            },
            "notifications": {
                "pushover_enabled": self._pushover_enabled,
                "notify_reps": self._notify_reps,
            },
            "events": [],
            "warnings": [],
        }

    def latest_session_id(self) -> str | None:
        return self._latest_session_id

    def update_robot_event(
        self,
        event: dict[str, Any],
        received_at_ms: int | None = None,
        server_elapsed_ms: int | None = None,
    ) -> str | None:
        event_type = event.get("type")
        session_id = event.get("session_id")
        if not session_id:
            return None
        session_id = str(session_id)
        self._latest_session_id = session_id
        snapshot = self.get_snapshot(session_id)
        timestamp_ms = int(received_at_ms or _now_ms())
        robot_timestamp_ms = _to_timestamp_ms(event.get("timestamp"))
        snapshot["timestamp_ms"] = timestamp_ms
        snapshot["session_id"] = session_id
        snapshot["time_source"] = "server_received_at"
        snapshot.setdefault("events", [])
        snapshot.setdefault("counts", {})
        snapshot.setdefault("notifications", {})["notify_reps"] = self._notify_reps
        snapshot.setdefault("notifications", {})["pushover_enabled"] = self._pushover_enabled

        if event_type == "session_start":
            snapshot["status"] = "recording"
            snapshot["timer"] = {"duration_s": 0, "active_duration_s": 0}
            snapshot["robot"] = {
                "device_id": event.get("device_id"),
                "last_sample_age_ms": None,
                "pose_quality": "unknown",
                "connection_status": "waiting",
                "sample_count": 0,
                "latest_sample_id": None,
                "elapsed_ms": 0,
                "server_elapsed_ms": 0,
                "robot_elapsed_ms": event.get("elapsed_ms"),
                "received_at_ms": received_at_ms,
                "robot_timestamp_ms": robot_timestamp_ms,
                "target_confidence": None,
                "angles": {},
                "visibility": {},
            }
            snapshot["events"] = [
                {
                    "type": "session_start",
                    "timestamp_ms": timestamp_ms,
                    "robot_timestamp_ms": robot_timestamp_ms,
                }
            ]

        elif event_type == "sample":
            elapsed_ms = int(server_elapsed_ms if server_elapsed_ms is not None else event.get("elapsed_ms") or 0)
            target = event.get("target") or {}
            visibility = event.get("visibility") or {}
            actions = event.get("actions") or {}
            previous_robot = snapshot.get("robot") or {}
            previous_current = snapshot.get("current") or {}
            sample_count = int(previous_robot.get("sample_count") or 0) + 1
            counts = {name: status.get("count", 0) for name, status in actions.items()}
            current_action, phase = _resolve_current_action(
                event.get("active_action"),
                actions,
                previous_current.get("action"),
            )
            snapshot["status"] = "recording"
            snapshot["timer"] = {
                "duration_s": round(elapsed_ms / 1000.0, 1),
                "active_duration_s": round(elapsed_ms / 1000.0, 1),
            }
            snapshot["current"] = {
                "action": current_action,
                "phase": phase,
                "posture": event.get("posture") or "unknown",
                "latest_score": None,
            }
            snapshot["counts"] = counts
            snapshot["robot"] = {
                "device_id": event.get("device_id"),
                "last_sample_age_ms": max(0, _now_ms() - timestamp_ms),
                "target_confidence": target.get("confidence"),
                "pose_quality": _pose_quality(target.get("confidence"), visibility),
                "connection_status": "live",
                "sample_count": sample_count,
                "latest_sample_id": event.get("sample_id"),
                "elapsed_ms": elapsed_ms,
                "server_elapsed_ms": elapsed_ms,
                "robot_elapsed_ms": event.get("elapsed_ms"),
                "received_at_ms": received_at_ms,
                "robot_timestamp_ms": robot_timestamp_ms,
                "angles": event.get("angles") or {},
                "visibility": visibility,
            }

        elif event_type == "rep_event":
            action = event.get("action") or "unknown"
            count = int(event.get("count") or 0)
            snapshot["counts"][action] = count
            snapshot["current"] = {
                "action": action,
                "phase": event.get("stage") or "unknown",
                "posture": snapshot.get("current", {}).get("posture", "unknown"),
                "latest_score": None,
            }
            snapshot["events"] = (
                snapshot.get("events", []) + [
                    {
                        "type": "rep_event",
                        "timestamp_ms": timestamp_ms,
                        "robot_timestamp_ms": robot_timestamp_ms,
                        "elapsed_ms": int(
                            server_elapsed_ms if server_elapsed_ms is not None else event.get("elapsed_ms") or 0
                        ),
                        "robot_elapsed_ms": event.get("elapsed_ms"),
                        "action": action,
                        "count": count,
                    }
                ]
            )[-20:]

        elif event_type == "session_end":
            elapsed_ms = int(server_elapsed_ms if server_elapsed_ms is not None else event.get("elapsed_ms") or 0)
            snapshot["status"] = "finished_pending_report"
            snapshot["timer"] = {
                "duration_s": round(elapsed_ms / 1000.0, 1),
                "active_duration_s": round(elapsed_ms / 1000.0, 1),
            }
            snapshot.setdefault("robot", {})["connection_status"] = "finished"
            snapshot.setdefault("robot", {})["elapsed_ms"] = elapsed_ms
            snapshot.setdefault("robot", {})["server_elapsed_ms"] = elapsed_ms
            snapshot.setdefault("robot", {})["robot_elapsed_ms"] = event.get("elapsed_ms")
            snapshot.setdefault("robot", {})["received_at_ms"] = received_at_ms
            snapshot.setdefault("robot", {})["robot_timestamp_ms"] = robot_timestamp_ms
            snapshot["counts"] = event.get("counts") or snapshot.get("counts", {})
            snapshot["events"] = (
                snapshot.get("events", [])
                + [
                    {
                        "type": "session_end",
                        "timestamp_ms": timestamp_ms,
                        "robot_timestamp_ms": robot_timestamp_ms,
                        "elapsed_ms": elapsed_ms,
                        "robot_elapsed_ms": event.get("elapsed_ms"),
                    }
                ]
            )[-20:]

        self._snapshots[session_id] = snapshot
        return session_id

    def update_heart_rate(self, sample: dict[str, Any], session_id: str | None) -> str | None:
        target_session = session_id or self._latest_session_id
        if target_session is None:
            return None
        snapshot = self.get_snapshot(target_session)
        snapshot["heart_rate"] = {
            "bpm": sample.get("bpm"),
            "zone": None,
            "percent_max": None,
            "status": "live",
            "device_name": sample.get("device_name"),
            "device_id": sample.get("device_address") or sample.get("device_id"),
            "timestamp_ms": sample.get("timestamp_ms"),
        }
        self._snapshots[target_session] = snapshot
        return target_session

    def set_hr_device_status(self, status: str, **values: Any) -> None:
        self._hr_device = {"status": status, **values}

    def hr_device_status(self) -> dict[str, Any]:
        return dict(self._hr_device)

    def register(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._queues[session_id].add(queue)
        return queue

    def unregister(self, session_id: str, queue: asyncio.Queue) -> None:
        self._queues[session_id].discard(queue)

    async def publish(self, session_id: str) -> None:
        snapshot = self.get_snapshot(session_id)
        for queue in list(self._queues.get(session_id, set())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(snapshot)


live_state = LiveState()
