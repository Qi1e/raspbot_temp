"""Session query API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.live_state import live_state
from app.services.robot_ingest import (
    finish_session_manually,
    get_action_events,
    get_samples,
    get_session,
    list_sessions,
)


router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("")
async def sessions(limit: int = Query(50, ge=1, le=500)):
    return {"items": list_sessions(limit)}


@router.get("/latest")
async def latest_session():
    session_id = live_state.latest_session_id()
    if session_id is None:
        return {"session": None}
    return {"session": get_session(session_id), "live_snapshot": live_state.get_snapshot(session_id)}


@router.get("/{session_id}")
async def session_detail(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {
        "session": session,
        "live_snapshot": live_state.get_snapshot(session_id),
        "action_events": get_action_events(session_id, limit=100),
    }


@router.get("/{session_id}/samples")
async def session_samples(session_id: str, limit: int = Query(200, ge=1, le=1000)):
    return {"items": get_samples(session_id, limit)}


@router.get("/{session_id}/events")
async def session_events(session_id: str, limit: int = Query(200, ge=1, le=1000)):
    return {"items": get_action_events(session_id, limit)}


@router.post("/{session_id}/finish")
async def finish_session(session_id: str):
    result = finish_session_manually(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="session not found")
    await live_state.publish(session_id)
    return result
