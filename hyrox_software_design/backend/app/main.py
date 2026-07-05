"""HYROX report backend entrypoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import analysis, heart_rate, live, robot, sessions, settings as settings_api
from app.db.database import db
from app.services.live_state import live_state
from app.services.notification_service import notification_service


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    """Serve the built frontend when frontend/dist exists."""
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        return

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def frontend_index():
        return FileResponse(index_file)

    @app.get("/{path:path}")
    async def frontend_fallback(path: str):
        if path.startswith(("api/", "ws/")):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="not found")
        candidate = FRONTEND_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


def create_app() -> FastAPI:
    app = FastAPI(title="HYROX Report Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        db.init_schema()
        live_state.set_notify_reps(notification_service.notify_reps)
        live_state.set_pushover_enabled(notification_service.enabled)

    @app.get("/health")
    async def health():
        return {"ok": True}

    app.include_router(robot.router)
    app.include_router(sessions.router)
    app.include_router(heart_rate.router)
    app.include_router(live.router)
    app.include_router(settings_api.router)
    app.include_router(analysis.router)
    mount_frontend(app)
    return app


app = create_app()
