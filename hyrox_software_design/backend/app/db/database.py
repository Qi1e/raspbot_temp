"""SQLite persistence for HYROX backend MVP."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.config import settings


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    robot_session_id TEXT NOT NULL,
    device_id TEXT,
    status TEXT NOT NULL,
    started_at_ms INTEGER,
    ended_at_ms INTEGER,
    robot_started_at_ms INTEGER,
    robot_ended_at_ms INTEGER,
    time_source TEXT NOT NULL DEFAULT 'server_received_at',
    duration_s REAL,
    active_duration_s REAL,
    counts_json TEXT NOT NULL DEFAULT '{}',
    config_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_robot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    robot_session_id TEXT,
    device_id TEXT,
    event_type TEXT NOT NULL,
    schema_version TEXT,
    timestamp_ms INTEGER,
    received_at_ms INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_robot_events_session
ON raw_robot_events(session_id, received_at_ms);

CREATE TABLE IF NOT EXISTS robot_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    robot_session_id TEXT NOT NULL,
    device_id TEXT,
    sample_id INTEGER,
    timestamp_ms INTEGER,
    received_at_ms INTEGER,
    robot_timestamp_ms INTEGER,
    elapsed_ms INTEGER,
    robot_elapsed_ms INTEGER,
    posture TEXT,
    active_action TEXT,
    target_detected INTEGER,
    target_center_x REAL,
    target_center_y REAL,
    target_width REAL,
    target_height REAL,
    target_confidence REAL,
    visibility_json TEXT NOT NULL DEFAULT '{}',
    angles_json TEXT NOT NULL DEFAULT '{}',
    features_json TEXT NOT NULL DEFAULT '{}',
    actions_json TEXT NOT NULL DEFAULT '{}',
    keypoints_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(session_id, device_id, sample_id)
);

CREATE INDEX IF NOT EXISTS idx_robot_samples_session_time
ON robot_samples(session_id, timestamp_ms);

CREATE TABLE IF NOT EXISTS action_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    robot_session_id TEXT NOT NULL,
    device_id TEXT,
    timestamp_ms INTEGER,
    received_at_ms INTEGER,
    robot_timestamp_ms INTEGER,
    elapsed_ms INTEGER,
    robot_elapsed_ms INTEGER,
    action TEXT NOT NULL,
    event TEXT NOT NULL,
    count INTEGER NOT NULL,
    stage TEXT,
    score REAL,
    duration_ms INTEGER,
    faults_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(session_id, device_id, action, count)
);

CREATE INDEX IF NOT EXISTS idx_action_events_session_time
ON action_events(session_id, timestamp_ms);

CREATE TABLE IF NOT EXISTS heart_rate_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    device_id TEXT,
    device_name TEXT,
    timestamp_ms INTEGER NOT NULL,
    bpm INTEGER NOT NULL,
    contact_detected INTEGER,
    source TEXT NOT NULL,
    quality TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heart_rate_samples_session_time
ON heart_rate_samples(session_id, timestamp_ms);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


def to_timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        return int(number)
    return int(number * 1000)


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        """Lightweight additive migrations for local MVP databases."""
        self._add_column(conn, "sessions", "robot_started_at_ms", "INTEGER")
        self._add_column(conn, "sessions", "robot_ended_at_ms", "INTEGER")
        self._add_column(conn, "sessions", "time_source", "TEXT NOT NULL DEFAULT 'server_received_at'")
        self._add_column(conn, "robot_samples", "received_at_ms", "INTEGER")
        self._add_column(conn, "robot_samples", "robot_timestamp_ms", "INTEGER")
        self._add_column(conn, "robot_samples", "robot_elapsed_ms", "INTEGER")
        self._add_column(conn, "action_events", "received_at_ms", "INTEGER")
        self._add_column(conn, "action_events", "robot_timestamp_ms", "INTEGER")
        self._add_column(conn, "action_events", "robot_elapsed_ms", "INTEGER")

    def _add_column(self, conn: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return dict(row) if row else None


db = Database(settings.database_path)


def ensure_session(event: dict[str, Any], status: str = "recording", received_at_ms: int | None = None) -> str | None:
    robot_session_id = event.get("session_id")
    if not robot_session_id:
        return None
    session_id = str(robot_session_id)
    device_id = event.get("device_id")
    timestamp_ms = int(received_at_ms or now_ms())
    robot_timestamp_ms = to_timestamp_ms(event.get("timestamp"))
    config_json = json_dumps(event.get("config", {}))
    current_ms = now_ms()
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (
                id, robot_session_id, device_id, status, started_at_ms,
                robot_started_at_ms, time_source, counts_json, config_json,
                created_at_ms, updated_at_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, 'server_received_at', '{}', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                device_id=COALESCE(excluded.device_id, sessions.device_id),
                status=CASE
                    WHEN sessions.status IN ('finished', 'finished_pending_report')
                    THEN sessions.status
                    ELSE excluded.status
                END,
                started_at_ms=COALESCE(sessions.started_at_ms, excluded.started_at_ms),
                robot_started_at_ms=COALESCE(sessions.robot_started_at_ms, excluded.robot_started_at_ms),
                time_source='server_received_at',
                config_json=CASE
                    WHEN excluded.config_json != '{}' THEN excluded.config_json
                    ELSE sessions.config_json
                END,
                updated_at_ms=excluded.updated_at_ms
            """,
            (
                session_id,
                session_id,
                device_id,
                status,
                timestamp_ms,
                robot_timestamp_ms,
                config_json,
                current_ms,
                current_ms,
            ),
        )
    return session_id


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in (
        "counts_json",
        "config_json",
        "payload_json",
        "visibility_json",
        "angles_json",
        "features_json",
        "actions_json",
        "keypoints_json",
        "faults_json",
        "details_json",
    ):
        if key in result:
            try:
                result[key.replace("_json", "")] = json.loads(result[key] or "{}")
            except json.JSONDecodeError:
                result[key.replace("_json", "")] = result[key]
            del result[key]
    return result
