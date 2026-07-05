"""Robot ingest API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.services.robot_ingest import IngestError, ingest_ndjson
from app.services.live_state import live_state


router = APIRouter(prefix="/api/v1/robot", tags=["robot"])


@router.post("/ingest")
async def ingest_robot_events(request: Request):
    body = (await request.body()).decode("utf-8")
    try:
        result = ingest_ndjson(body)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for session_id in result["sessions"]:
        await live_state.publish(session_id)
    return result


@router.post("/{robot_id}/heartbeat")
async def robot_heartbeat(robot_id: str):
    return {"ok": True, "robot_id": robot_id}
