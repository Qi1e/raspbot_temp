"""Session alignment and analysis data preparation."""

from __future__ import annotations

from statistics import mean
from typing import Any

from app.db.database import db, serialize_row


def _relative_ms(timestamp_ms: int | None, started_at_ms: int | None) -> int | None:
    if timestamp_ms is None or started_at_ms is None:
        return None
    return int(timestamp_ms) - int(started_at_ms)


def _nearest_heart_rate(
    timestamp_ms: int | None,
    heart_rates: list[dict[str, Any]],
    window_ms: int,
) -> dict[str, Any] | None:
    if timestamp_ms is None or not heart_rates:
        return None
    nearest = min(heart_rates, key=lambda item: abs(int(item["timestamp_ms"]) - int(timestamp_ms)))
    delta_ms = int(nearest["timestamp_ms"]) - int(timestamp_ms)
    if abs(delta_ms) > window_ms:
        return None
    return {
        "bpm": nearest["bpm"],
        "timestamp_ms": nearest["timestamp_ms"],
        "delta_ms": delta_ms,
        "device_name": nearest.get("device_name"),
    }


def _stream_robot_sample(row: dict[str, Any], started_at_ms: int | None) -> dict[str, Any]:
    return {
        "t_ms": _relative_ms(row.get("timestamp_ms"), started_at_ms),
        "timestamp_ms": row.get("timestamp_ms"),
        "received_at_ms": row.get("received_at_ms"),
        "robot_timestamp_ms": row.get("robot_timestamp_ms"),
        "elapsed_ms": row.get("elapsed_ms"),
        "robot_elapsed_ms": row.get("robot_elapsed_ms"),
        "sample_id": row.get("sample_id"),
        "active_action": row.get("active_action"),
        "posture": row.get("posture"),
        "target_confidence": row.get("target_confidence"),
        "visibility": row.get("visibility") or {},
        "angles": row.get("angles") or {},
    }


def _stream_action_event(row: dict[str, Any], started_at_ms: int | None) -> dict[str, Any]:
    return {
        "t_ms": _relative_ms(row.get("timestamp_ms"), started_at_ms),
        "timestamp_ms": row.get("timestamp_ms"),
        "received_at_ms": row.get("received_at_ms"),
        "robot_timestamp_ms": row.get("robot_timestamp_ms"),
        "elapsed_ms": row.get("elapsed_ms"),
        "robot_elapsed_ms": row.get("robot_elapsed_ms"),
        "action": row.get("action"),
        "event": row.get("event"),
        "count": row.get("count"),
        "stage": row.get("stage"),
        "score": row.get("score"),
        "duration_ms": row.get("duration_ms"),
        "details": row.get("details") or {},
    }


def _stream_heart_rate(row: dict[str, Any], started_at_ms: int | None) -> dict[str, Any]:
    return {
        "t_ms": _relative_ms(row.get("timestamp_ms"), started_at_ms),
        "timestamp_ms": row.get("timestamp_ms"),
        "bpm": row.get("bpm"),
        "device_id": row.get("device_id"),
        "device_name": row.get("device_name"),
        "contact_detected": None if row.get("contact_detected") is None else bool(row.get("contact_detected")),
        "source": row.get("source"),
        "quality": row.get("quality"),
    }


def build_aligned_session_dataset(
    session_id: str,
    sample_limit: int = 2000,
    nearest_hr_window_ms: int = 5000,
) -> dict[str, Any] | None:
    session_row = db.query_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if session_row is None:
        return None
    session = serialize_row(session_row)
    started_at_ms = session.get("started_at_ms")

    robot_rows = [
        serialize_row(row)
        for row in db.query_all(
            """
            SELECT *
            FROM robot_samples
            WHERE session_id=?
            ORDER BY timestamp_ms ASC
            LIMIT ?
            """,
            (session_id, sample_limit),
        )
    ]
    action_rows = [
        serialize_row(row)
        for row in db.query_all(
            """
            SELECT *
            FROM action_events
            WHERE session_id=?
            ORDER BY timestamp_ms ASC
            """,
            (session_id,),
        )
    ]
    heart_rate_rows = db.query_all(
        """
        SELECT *
        FROM heart_rate_samples
        WHERE session_id=?
        ORDER BY timestamp_ms ASC
        """,
        (session_id,),
    )
    robot_count = db.query_one("SELECT COUNT(*) AS count FROM robot_samples WHERE session_id=?", (session_id,))

    robot_stream = [_stream_robot_sample(row, started_at_ms) for row in robot_rows]
    action_stream = [_stream_action_event(row, started_at_ms) for row in action_rows]
    heart_rate_stream = [_stream_heart_rate(row, started_at_ms) for row in heart_rate_rows]
    bpm_values = [int(row["bpm"]) for row in heart_rate_rows if row.get("bpm") is not None]

    actions_with_hr = []
    for action in action_stream:
        actions_with_hr.append(
            {
                **action,
                "nearest_heart_rate": _nearest_heart_rate(
                    action.get("timestamp_ms"),
                    heart_rate_rows,
                    nearest_hr_window_ms,
                ),
            }
        )

    return {
        "session_id": session_id,
        "time_source": session.get("time_source") or "server_received_at",
        "time_axis": {
            "started_at_ms": started_at_ms,
            "ended_at_ms": session.get("ended_at_ms"),
            "description": "timestamp_ms/t_ms use backend computer receive time for robot data and BLE receive time for heart rate.",
        },
        "summary": {
            "duration_s": session.get("duration_s"),
            "robot_sample_count": int((robot_count or {}).get("count") or 0),
            "returned_robot_sample_count": len(robot_stream),
            "action_event_count": len(action_stream),
            "heart_rate_sample_count": len(heart_rate_stream),
            "avg_bpm": round(mean(bpm_values), 1) if bpm_values else None,
            "max_bpm": max(bpm_values) if bpm_values else None,
            "calories_kcal": None,
            "training_effect": None,
        },
        "streams": {
            "robot_samples": robot_stream,
            "action_events": action_stream,
            "heart_rate_samples": heart_rate_stream,
            "action_events_with_heart_rate": actions_with_hr,
        },
        "analysis_modules": {
            "alignment": "ready",
            "calories": "pending_profile_and_algorithm",
            "training_effect": "pending_scoring_model",
        },
    }


def build_analysis_summary(session_id: str) -> dict[str, Any] | None:
    session_row = db.query_one("SELECT * FROM sessions WHERE id=?", (session_id,))
    if session_row is None:
        return None
    session = serialize_row(session_row)
    robot_count = db.query_one("SELECT COUNT(*) AS count FROM robot_samples WHERE session_id=?", (session_id,))
    action_count = db.query_one("SELECT COUNT(*) AS count FROM action_events WHERE session_id=?", (session_id,))
    hr_stats = db.query_one(
        "SELECT COUNT(*) AS count, AVG(bpm) AS avg_bpm, MAX(bpm) AS max_bpm FROM heart_rate_samples WHERE session_id=?",
        (session_id,),
    )
    return {
        "session_id": session_id,
        "time_source": session.get("time_source") or "server_received_at",
        "time_axis": {
            "started_at_ms": session.get("started_at_ms"),
            "ended_at_ms": session.get("ended_at_ms"),
            "description": "timestamp_ms/t_ms use backend computer receive time for robot data and BLE receive time for heart rate.",
        },
        "summary": {
            "duration_s": session.get("duration_s"),
            "robot_sample_count": int((robot_count or {}).get("count") or 0),
            "action_event_count": int((action_count or {}).get("count") or 0),
            "heart_rate_sample_count": int((hr_stats or {}).get("count") or 0),
            "avg_bpm": round(float(hr_stats["avg_bpm"]), 1) if hr_stats and hr_stats.get("avg_bpm") else None,
            "max_bpm": int(hr_stats["max_bpm"]) if hr_stats and hr_stats.get("max_bpm") else None,
            "calories_kcal": None,
            "training_effect": None,
        },
        "analysis_modules": {
            "alignment": "ready",
            "calories": "pending_profile_and_algorithm",
            "training_effect": "pending_scoring_model",
        },
    }
