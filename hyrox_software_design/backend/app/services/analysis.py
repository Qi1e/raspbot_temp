"""Session alignment and analysis data preparation."""

from __future__ import annotations

from statistics import mean
from typing import Any

from app.db.database import db, serialize_row

ACTION_LABELS = {
    "squat": "深蹲",
    "lunge": "箭步蹲",
    "burpee": "波比跳",
}

# MVP reference targets used when no athlete profile or custom plan exists.
REFERENCE_ACTION_TARGETS = {
    "squat": 20,
    "lunge": 20,
    "burpee": 10,
}

ADULT_REFERENCE = {
    "weight_kg": 70,
    "max_heart_rate_bpm": 185,
    "base_met": 8.0,
}


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
    bpm = int(row["bpm"]) if row.get("bpm") is not None else None
    return {
        "t_ms": _relative_ms(row.get("timestamp_ms"), started_at_ms),
        "timestamp_ms": row.get("timestamp_ms"),
        "bpm": bpm,
        "zone": _heart_rate_zone(bpm),
        "device_id": row.get("device_id"),
        "device_name": row.get("device_name"),
        "contact_detected": None if row.get("contact_detected") is None else bool(row.get("contact_detected")),
        "source": row.get("source"),
        "quality": row.get("quality"),
    }


def _heart_rate_zone(bpm: int | None) -> str | None:
    if bpm is None:
        return None
    percent = bpm / ADULT_REFERENCE["max_heart_rate_bpm"]
    if percent < 0.5:
        return "恢复"
    if percent < 0.6:
        return "轻松"
    if percent < 0.7:
        return "有氧"
    if percent < 0.85:
        return "强化"
    return "高强度"


def _format_t_ms(t_ms: int | None) -> str:
    if t_ms is None:
        return "--"
    total_seconds = max(0, int(round(t_ms / 1000)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _counts_from_rows(action_rows: list[dict[str, Any]], session: dict[str, Any]) -> dict[str, int]:
    counts = {action: 0 for action in REFERENCE_ACTION_TARGETS}
    for row in action_rows:
        action = row.get("action")
        if action not in counts:
            continue
        counts[action] = max(counts[action], int(row.get("count") or 0))
    if any(counts.values()):
        return counts

    for action, count in (session.get("counts") or {}).items():
        if action in counts:
            counts[action] = int(count or 0)
    return counts


def _duration_seconds(session: dict[str, Any], robot_rows: list[dict[str, Any]]) -> float:
    if session.get("active_duration_s") is not None:
        return float(session["active_duration_s"])
    if session.get("duration_s") is not None:
        return float(session["duration_s"])
    if session.get("started_at_ms") and session.get("ended_at_ms"):
        return max(0.0, (int(session["ended_at_ms"]) - int(session["started_at_ms"])) / 1000.0)
    timestamps = [int(row["timestamp_ms"]) for row in robot_rows if row.get("timestamp_ms") is not None]
    if len(timestamps) >= 2:
        return max(0.0, (max(timestamps) - min(timestamps)) / 1000.0)
    return 0.0


def _pose_quality_score(robot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not robot_rows:
        return {
            "score": 0,
            "avg_target_confidence": None,
            "full_body_visible_rate": None,
            "sample_count": 0,
        }

    confidence_values = [
        float(row["target_confidence"])
        for row in robot_rows
        if row.get("target_confidence") is not None
    ]
    full_body_values = [
        1.0 if (row.get("visibility") or {}).get("full_body") else 0.0
        for row in robot_rows
        if isinstance(row.get("visibility"), dict) and "full_body" in row.get("visibility", {})
    ]
    avg_confidence = mean(confidence_values) if confidence_values else None
    full_body_rate = mean(full_body_values) if full_body_values else None
    confidence_score = (avg_confidence or 0.0) * 70
    visibility_score = (full_body_rate if full_body_rate is not None else 0.5) * 30
    return {
        "score": round(min(100.0, confidence_score + visibility_score), 1),
        "avg_target_confidence": round(avg_confidence, 3) if avg_confidence is not None else None,
        "full_body_visible_rate": round(full_body_rate, 3) if full_body_rate is not None else None,
        "sample_count": len(robot_rows),
    }


def _completion_analysis(counts: dict[str, int], robot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_total = sum(REFERENCE_ACTION_TARGETS.values())
    total_reps = sum(counts.values())
    target_ratios = {
        action: (counts.get(action, 0) / target if target else 0.0)
        for action, target in REFERENCE_ACTION_TARGETS.items()
    }
    volume_score = min(100.0, total_reps / target_total * 100.0) if target_total else 0.0
    balance_score = mean(min(1.0, ratio) for ratio in target_ratios.values()) * 100.0
    pose_quality = _pose_quality_score(robot_rows)
    score = volume_score * 0.55 + balance_score * 0.25 + float(pose_quality["score"]) * 0.20
    if score >= 85:
        level = "优秀"
    elif score >= 70:
        level = "良好"
    elif score >= 50:
        level = "基础完成"
    elif total_reps > 0:
        level = "进行中"
    else:
        level = "暂无有效动作"

    by_action = []
    for action, target in REFERENCE_ACTION_TARGETS.items():
        count = counts.get(action, 0)
        by_action.append(
            {
                "action": action,
                "label": ACTION_LABELS.get(action, action),
                "count": count,
                "target": target,
                "completion_percent": round(min(100.0, count / target * 100.0), 1) if target else 0.0,
            }
        )

    return {
        "score": round(score, 1),
        "level": level,
        "total_reps": total_reps,
        "target_reps": target_total,
        "volume_score": round(volume_score, 1),
        "balance_score": round(balance_score, 1),
        "pose_quality_score": pose_quality["score"],
        "pose_quality": pose_quality,
        "by_action": by_action,
        "reference": {
            "name": "MVP 成人基础训练量",
            "targets": REFERENCE_ACTION_TARGETS,
            "note": "未配置个人训练计划时，用该基准估算综合完成度。",
        },
    }


def _estimated_met(avg_bpm: float | None) -> float:
    if avg_bpm is None:
        return ADULT_REFERENCE["base_met"]
    percent = avg_bpm / ADULT_REFERENCE["max_heart_rate_bpm"]
    if percent >= 0.85:
        return 9.5
    if percent >= 0.7:
        return 8.0
    if percent >= 0.6:
        return 6.5
    return 5.0


def _calorie_estimate(duration_s: float, avg_bpm: float | None) -> dict[str, Any]:
    met = _estimated_met(avg_bpm)
    minutes = max(0.0, duration_s / 60.0)
    weight_kg = ADULT_REFERENCE["weight_kg"]
    calories = met * 3.5 * weight_kg / 200.0 * minutes
    return {
        "kcal": round(calories, 1),
        "duration_min": round(minutes, 1),
        "estimated_met": met,
        "adult_reference": {
            "weight_kg": weight_kg,
            "max_heart_rate_bpm": ADULT_REFERENCE["max_heart_rate_bpm"],
        },
        "method": "MET * 3.5 * 成人参考体重(kg) / 200 * 运动分钟数；MET 会按平均心率粗略分档。",
        "confidence": "estimate",
    }


def _heart_rate_table(
    heart_rate_rows: list[dict[str, Any]],
    action_rows: list[dict[str, Any]],
    started_at_ms: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    rows = []
    for row in heart_rate_rows[:limit]:
        timestamp_ms = row.get("timestamp_ms")
        t_ms = _relative_ms(timestamp_ms, started_at_ms)
        nearest_action = None
        if timestamp_ms is not None and action_rows:
            matching = min(action_rows, key=lambda item: abs(int(item["timestamp_ms"]) - int(timestamp_ms)))
            delta_ms = int(matching["timestamp_ms"]) - int(timestamp_ms)
            if abs(delta_ms) <= 5000:
                nearest_action = {
                    "action": matching.get("action"),
                    "label": ACTION_LABELS.get(str(matching.get("action")), str(matching.get("action") or "")),
                    "count": matching.get("count"),
                    "delta_ms": delta_ms,
                }
        if nearest_action is not None:
            nearest_action = {
                **nearest_action,
                "text": f"{nearest_action['label']} {nearest_action.get('count') or ''}".strip(),
            }
        bpm = int(row["bpm"]) if row.get("bpm") is not None else None
        rows.append(
            {
                "t_ms": t_ms,
                "time": _format_t_ms(t_ms),
                "timestamp_ms": timestamp_ms,
                "bpm": bpm,
                "zone": _heart_rate_zone(bpm),
                "nearest_action": nearest_action,
            }
        )
    return rows


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


def build_session_report(session_id: str, heart_rate_limit: int = 500) -> dict[str, Any] | None:
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
            """,
            (session_id,),
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

    counts = _counts_from_rows(action_rows, session)
    duration_s = _duration_seconds(session, robot_rows)
    bpm_values = [int(row["bpm"]) for row in heart_rate_rows if row.get("bpm") is not None]
    avg_bpm = round(mean(bpm_values), 1) if bpm_values else None
    max_bpm = max(bpm_values) if bpm_values else None
    min_bpm = min(bpm_values) if bpm_values else None
    completion = _completion_analysis(counts, robot_rows)
    calories = _calorie_estimate(duration_s, avg_bpm)
    heart_rate_table = _heart_rate_table(
        heart_rate_rows=heart_rate_rows,
        action_rows=action_rows,
        started_at_ms=started_at_ms,
        limit=heart_rate_limit,
    )

    return {
        "type": "session_report",
        "session_id": session_id,
        "generated_at_ms": db.query_one("SELECT CAST(strftime('%s','now') AS INTEGER) * 1000 AS now_ms")["now_ms"],
        "session": {
            "id": session.get("id"),
            "status": session.get("status"),
            "device_id": session.get("device_id"),
            "started_at_ms": session.get("started_at_ms"),
            "ended_at_ms": session.get("ended_at_ms"),
            "duration_s": round(duration_s, 1),
            "time_source": session.get("time_source") or "server_received_at",
        },
        "summary": {
            "duration_s": round(duration_s, 1),
            "total_reps": completion["total_reps"],
            "completion_score": completion["score"],
            "completion_level": completion["level"],
            "calories_kcal": calories["kcal"],
            "avg_bpm": avg_bpm,
            "max_bpm": max_bpm,
            "min_bpm": min_bpm,
            "heart_rate_sample_count": len(heart_rate_rows),
            "robot_sample_count": len(robot_rows),
            "action_event_count": len(action_rows),
        },
        "heart_rate": {
            "table": heart_rate_table,
            "stats": {
                "sample_count": len(heart_rate_rows),
                "avg_bpm": avg_bpm,
                "max_bpm": max_bpm,
                "min_bpm": min_bpm,
            },
            "time_axis": {
                "started_at_ms": started_at_ms,
                "description": "心率时间轴使用电脑收到 BLE 心率 notify 的时间，并相对 session started_at_ms 展示。",
            },
        },
        "movement": {
            "counts": completion["by_action"],
            "raw_counts": counts,
            "completion": completion,
        },
        "calories": calories,
        "notes": [
            "热量为成年人平均体重和心率分档下的估算值，不等同于医学或设备级能量消耗测量。",
            "综合完成度使用当前 MVP 动作基准、动作均衡性和姿态数据质量计算。",
        ],
    }
