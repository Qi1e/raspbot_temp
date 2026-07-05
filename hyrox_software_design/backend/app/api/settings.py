"""Runtime settings API for MVP toggles."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.services.live_state import live_state
from app.services.notification_service import notification_service


router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("/notifications")
async def get_notification_settings():
    return {
        "pushover_enabled": notification_service.enabled,
        "notify_reps": notification_service.notify_reps,
    }


@router.put("/notifications")
async def update_notification_settings(request: Request):
    payload = await request.json()
    if "notify_reps" in payload:
        notification_service.set_notify_reps(bool(payload["notify_reps"]))
        live_state.set_notify_reps(bool(payload["notify_reps"]))
    if "pushover_enabled" in payload:
        notification_service.enabled = bool(payload["pushover_enabled"])
        live_state.set_pushover_enabled(bool(payload["pushover_enabled"]))
    return {
        "pushover_enabled": notification_service.enabled,
        "notify_reps": notification_service.notify_reps,
    }
