"""Pushover notification service with MVP throttling rules."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from urllib import error, parse, request

from app.core.config import settings


PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


def format_duration(seconds: float | int | None) -> str:
    total_seconds = max(0, int(round(float(seconds or 0))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


@dataclass
class NotificationResult:
    sent: bool
    reason: str = ""
    response: dict | None = None


@dataclass
class NotificationService:
    enabled: bool = settings.pushover_enabled
    notify_reps: bool = settings.pushover_notify_reps
    _last_rep_sent_at: dict[str, float] = field(default_factory=dict)
    _last_warning_sent_at: dict[str, float] = field(default_factory=dict)

    def set_notify_reps(self, enabled: bool) -> None:
        self.notify_reps = bool(enabled)

    def notify_session_started(self, session_id: str) -> NotificationResult:
        return self._send("HYROX", "已开始运动", priority=settings.pushover_default_priority)

    def notify_rep_completed(self, session_id: str, action: str, count: int) -> NotificationResult:
        if not self.notify_reps:
            return NotificationResult(False, "rep notification disabled")
        now = time.monotonic()
        last = self._last_rep_sent_at.get(session_id, 0.0)
        if now - last < settings.pushover_rep_throttle_seconds:
            return NotificationResult(False, "rep notification throttled")
        self._last_rep_sent_at[session_id] = now
        action_text = {"squat": "深蹲", "lunge": "箭步蹲", "burpee": "波比跳"}.get(action, action)
        return self._send("HYROX", f"{action_text} +1，第 {count} 次", priority=0)

    def notify_session_finished(self, session_id: str, duration_seconds: float | int | None) -> NotificationResult:
        message = f"训练结束，本次运动 {format_duration(duration_seconds)}"
        return self._send("HYROX", message, priority=settings.pushover_default_priority)

    def notify_warning(self, session_id: str, warning_type: str, message: str) -> NotificationResult:
        now = time.monotonic()
        key = f"{session_id}:{warning_type}"
        last = self._last_warning_sent_at.get(key, 0.0)
        if now - last < settings.pushover_warning_throttle_seconds:
            return NotificationResult(False, "warning notification throttled")
        self._last_warning_sent_at[key] = now
        return self._send("HYROX", message, priority=1)

    def _send(self, title: str, message: str, priority: int) -> NotificationResult:
        if not self.enabled:
            return NotificationResult(False, "pushover disabled")
        if not settings.pushover_app_token or not settings.pushover_user_key:
            return NotificationResult(False, "missing pushover credentials")

        payload = {
            "token": settings.pushover_app_token,
            "user": settings.pushover_user_key,
            "title": title,
            "message": message,
            "sound": "vibrate",
            "priority": str(priority),
        }
        body = parse.urlencode(payload).encode("utf-8")
        req = request.Request(
            PUSHOVER_API_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            return NotificationResult(False, f"pushover http {exc.code}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001 - service must not crash ingest.
            return NotificationResult(False, f"pushover request failed: {exc}")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return NotificationResult(parsed.get("status") == 1, response=parsed)


notification_service = NotificationService()
