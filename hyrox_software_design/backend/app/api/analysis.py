"""Analysis and report-preparation API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.analysis import build_aligned_session_dataset, build_analysis_summary, build_session_report


router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.get("/{session_id}/aligned")
async def aligned_dataset(
    session_id: str,
    sample_limit: int = Query(2000, ge=0, le=20000),
    nearest_hr_window_ms: int = Query(5000, ge=0, le=60000),
):
    dataset = build_aligned_session_dataset(
        session_id=session_id,
        sample_limit=sample_limit,
        nearest_hr_window_ms=nearest_hr_window_ms,
    )
    if dataset is None:
        raise HTTPException(status_code=404, detail="session not found")
    return dataset


@router.get("/{session_id}/summary")
async def analysis_summary(session_id: str):
    summary = build_analysis_summary(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="session not found")
    return summary


@router.get("/{session_id}/report")
async def session_report(
    session_id: str,
    heart_rate_limit: int = Query(500, ge=0, le=5000),
):
    report = build_session_report(session_id=session_id, heart_rate_limit=heart_rate_limit)
    if report is None:
        raise HTTPException(status_code=404, detail="session not found")
    return report
