"""Robot NDJSON ingest service."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import (
    db,
    ensure_session,
    json_dumps,
    now_ms,
    serialize_row,
    to_timestamp_ms,
)
from app.services.live_state import live_state
from app.services.notification_service import notification_service


class IngestError(ValueError):
    """Raised when an NDJSON batch cannot be parsed."""


RECEIVER_TIME_FIELDS = (
    "server_received_at_ms",
    "receiver_received_at_ms",
    "received_at_ms",
    "server_received_at",
    "receiver_received_at",
    "received_at",
)


def parse_ndjson(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(body.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise IngestError(f"Invalid JSON at line {line_number}: {exc}") from exc
        if not isinstance(event, dict):
            raise IngestError(f"Line {line_number} is not a JSON object")
        if not event.get("type"):
            raise IngestError(f"Line {line_number} missing type")
        events.append(event)
    return events


def _effective_received_at_ms(event: dict[str, Any]) -> int:
    for field in RECEIVER_TIME_FIELDS:
        raw_value = event.get(field)
        if raw_value is None:
            continue
        if field.endswith("_ms"):
            try:
                return int(float(raw_value))
            except (TypeError, ValueError):
                continue
        timestamp_ms = to_timestamp_ms(raw_value)
        if timestamp_ms is not None:
            return timestamp_ms
    return now_ms()


def _server_elapsed_ms(session_id: str, received_at_ms: int) -> int:
    row = db.query_one("SELECT started_at_ms FROM sessions WHERE id=?", (session_id,))
    started_at_ms = row.get("started_at_ms") if row else None
    if started_at_ms is None:
        return 0
    return max(0, received_at_ms - int(started_at_ms))


def _store_raw_event(event: dict[str, Any], session_id: str | None, received_at_ms: int) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO raw_robot_events (
                session_id, robot_session_id, device_id, event_type, schema_version,
                timestamp_ms, received_at_ms, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event.get("session_id"),
                event.get("device_id"),
                event.get("type"),
                event.get("schema_version"),
                to_timestamp_ms(event.get("timestamp")),
                received_at_ms,
                json_dumps(event),
            ),
        )


def _store_sample(event: dict[str, Any], session_id: str, received_at_ms: int, server_elapsed_ms: int) -> None:
    target = event.get("target") or {}
    with db.connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO robot_samples (
                session_id, robot_session_id, device_id, sample_id, timestamp_ms,
                received_at_ms, robot_timestamp_ms, elapsed_ms, robot_elapsed_ms,
                posture, active_action, target_detected,
                target_center_x, target_center_y, target_width, target_height,
                target_confidence, visibility_json, angles_json, features_json,
                actions_json, keypoints_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event.get("session_id"),
                event.get("device_id"),
                event.get("sample_id"),
                received_at_ms,
                received_at_ms,
                to_timestamp_ms(event.get("timestamp")),
                server_elapsed_ms,
                event.get("elapsed_ms"),
                event.get("posture"),
                event.get("active_action"),
                1 if target.get("detected") else 0,
                target.get("center_x"),
                target.get("center_y"),
                target.get("width"),
                target.get("height"),
                target.get("confidence"),
                json_dumps(event.get("visibility", {})),
                json_dumps(event.get("angles", {})),
                json_dumps(event.get("features", {})),
                json_dumps(event.get("actions", {})),
                json_dumps(event.get("keypoints", {})),
            ),
        )


def _store_rep_event(event: dict[str, Any], session_id: str, received_at_ms: int, server_elapsed_ms: int) -> bool:
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO action_events (
                session_id, robot_session_id, device_id, timestamp_ms, received_at_ms,
                robot_timestamp_ms, elapsed_ms, robot_elapsed_ms, action, event, count,
                stage, faults_json, details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'rep_completed', ?, ?, '[]', ?)
            """,
            (
                session_id,
                event.get("session_id"),
                event.get("device_id"),
                received_at_ms,
                received_at_ms,
                to_timestamp_ms(event.get("timestamp")),
                server_elapsed_ms,
                event.get("elapsed_ms"),
                event.get("action"),
                int(event.get("count") or 0),
                event.get("stage"),
                json_dumps(event.get("details", {})),
            ),
        )
        return cursor.rowcount > 0


def _finish_session(event: dict[str, Any], session_id: str, received_at_ms: int, server_elapsed_ms: int) -> float:
    duration_s = server_elapsed_ms / 1000.0 if server_elapsed_ms > 0 else None
    with db.connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status='finished_pending_report',
                ended_at_ms=?,
                robot_ended_at_ms=?,
                time_source='server_received_at',
                duration_s=?,
                active_duration_s=?,
                counts_json=?,
                updated_at_ms=?
            WHERE id=?
            """,
            (
                received_at_ms,
                to_timestamp_ms(event.get("timestamp")),
                duration_s,
                duration_s,
                json_dumps(event.get("counts", {})),
                now_ms(),
                session_id,
            ),
        )
    return float(duration_s or 0.0)


def ingest_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = 0
    ignored = 0
    touched_sessions: set[str] = set()
    notification_results: list[dict[str, Any]] = []

    for event in events:
        event_type = event.get("type")
        received_at_ms = _effective_received_at_ms(event)
        session_id = None

        if event_type == "ping":
            _store_raw_event(event, None, received_at_ms)
            accepted += 1
            continue

        if event_type not in {"session_start", "sample", "rep_event", "session_end"}:
            _store_raw_event(event, None, received_at_ms)
            ignored += 1
            continue

        session_id = ensure_session(event, received_at_ms=received_at_ms)
        if session_id is None:
            _store_raw_event(event, None, received_at_ms)
            ignored += 1
            continue

        server_elapsed_ms = _server_elapsed_ms(session_id, received_at_ms)
        _store_raw_event(event, session_id, received_at_ms)
        touched_sessions.add(session_id)

        if event_type == "session_start":
            notification_results.append(
                {
                    "event": "session_start",
                    "result": notification_service.notify_session_started(session_id).__dict__,
                }
            )

        elif event_type == "sample":
            _store_sample(event, session_id, received_at_ms, server_elapsed_ms)

        elif event_type == "rep_event":
            inserted = _store_rep_event(event, session_id, received_at_ms, server_elapsed_ms)
            if inserted:
                notification_results.append(
                    {
                        "event": "rep_event",
                        "result": notification_service.notify_rep_completed(
                            session_id,
                            str(event.get("action") or "unknown"),
                            int(event.get("count") or 0),
                        ).__dict__,
                    }
                )

        elif event_type == "session_end":
            duration_s = _finish_session(event, session_id, received_at_ms, server_elapsed_ms)
            notification_results.append(
                {
                    "event": "session_end",
                    "result": notification_service.notify_session_finished(session_id, duration_s).__dict__,
                }
            )

        live_state.update_robot_event(event, received_at_ms=received_at_ms, server_elapsed_ms=server_elapsed_ms)
        accepted += 1

    return {
        "ok": True,
        "accepted": accepted,
        "ignored": ignored,
        "sessions": sorted(touched_sessions),
        "notifications": notification_results,
    }


def ingest_ndjson(body: str) -> dict[str, Any]:
    return ingest_events(parse_ndjson(body))


def _counts_for_session(session_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    rows = db.query_all(
        """
        SELECT action, MAX(count) AS count
        FROM action_events
        WHERE session_id=?
        GROUP BY action
        """,
        (session_id,),
    )
    for row in rows:
        if row.get("action"):
            counts[str(row["action"])] = int(row.get("count") or 0)
    if counts:
        return counts

    latest_sample = db.query_one(
        """
        SELECT actions_json
        FROM robot_samples
        WHERE session_id=?
        ORDER BY timestamp_ms DESC
        LIMIT 1
        """,
        (session_id,),
    )
    if not latest_sample:
        return counts
    try:
        actions = json.loads(latest_sample.get("actions_json") or "{}")
    except json.JSONDecodeError:
        return counts
    for action, status in actions.items():
        if isinstance(status, dict):
            counts[action] = int(status.get("count") or 0)
    return counts


def finish_session_manually(session_id: str) -> dict[str, Any] | None:
    session = get_session(session_id)
    if session is None:
        return None

    ended_at_ms = now_ms()
    started_at_ms = session.get("started_at_ms") or session.get("created_at_ms") or ended_at_ms
    elapsed_ms = max(0, int(ended_at_ms) - int(started_at_ms))
    duration_s = elapsed_ms / 1000.0
    counts = _counts_for_session(session_id)
    already_finished = session.get("status") in {"finished", "finished_pending_report"}

    with db.connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status='finished_pending_report',
                ended_at_ms=COALESCE(ended_at_ms, ?),
                time_source='server_received_at',
                duration_s=COALESCE(duration_s, ?),
                active_duration_s=COALESCE(active_duration_s, ?),
                counts_json=CASE WHEN counts_json='{}' THEN ? ELSE counts_json END,
                updated_at_ms=?
            WHERE id=?
            """,
            (
                ended_at_ms,
                duration_s,
                duration_s,
                json_dumps(counts),
                now_ms(),
                session_id,
            ),
        )

    live_state.update_robot_event(
        {
            "type": "session_end",
            "session_id": session_id,
            "counts": counts,
        },
        received_at_ms=ended_at_ms,
        server_elapsed_ms=elapsed_ms,
    )
    notification_result = (
        notification_service.notify_session_finished(session_id, duration_s)
        if not already_finished
        else None
    )
    return {
        "session": get_session(session_id),
        "live_snapshot": live_state.get_snapshot(session_id),
        "notification": notification_result.__dict__ if notification_result else {"sent": False, "reason": "already finished"},
    }


def list_sessions(limit: int = 50) -> list[dict[str, Any]]:
    rows = db.query_all(
        """
        SELECT *
        FROM sessions
        ORDER BY COALESCE(started_at_ms, created_at_ms) DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [serialize_row(row) for row in rows]


def get_session(session_id: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    return serialize_row(row) if row else None


def get_samples(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.query_all(
        """
        SELECT *
        FROM robot_samples
        WHERE session_id=?
        ORDER BY timestamp_ms DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    return [serialize_row(row) for row in rows]


def get_action_events(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = db.query_all(
        """
        SELECT *
        FROM action_events
        WHERE session_id=?
        ORDER BY timestamp_ms DESC
        LIMIT ?
        """,
        (session_id, limit),
    )
    return [serialize_row(row) for row in rows]
