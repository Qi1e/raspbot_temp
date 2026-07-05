"""Live snapshot API and WebSocket."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.live_state import live_state


router = APIRouter(tags=["live"])


@router.get("/api/v1/live/{session_id}")
async def live_snapshot(session_id: str):
    return live_state.get_snapshot(session_id)


@router.websocket("/ws/v1/live/{session_id}")
async def live_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    queue = live_state.register(session_id)
    try:
        await websocket.send_json(live_state.get_snapshot(session_id))
        while True:
            try:
                snapshot = await asyncio.wait_for(
                    queue.get(),
                    timeout=settings.live_push_interval_seconds,
                )
            except asyncio.TimeoutError:
                snapshot = live_state.get_snapshot(session_id)
            await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        pass
    finally:
        live_state.unregister(session_id, queue)
