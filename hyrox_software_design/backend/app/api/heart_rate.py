"""Heart-rate BLE API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.services.heart_rate_ble import heart_rate_ble_service


router = APIRouter(prefix="/api/v1/hr", tags=["heart-rate"])


@router.post("/ble/scan")
async def scan_ble_devices(timeout: float = Query(settings.hr_ble_scan_timeout_seconds, ge=1, le=30)):
    try:
        devices = await heart_rate_ble_service.scan(timeout)
    except Exception as exc:  # noqa: BLE001 - BLE backend errors should be shown as API state.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"timeout": timeout, "items": devices}


@router.post("/ble/connect")
async def connect_ble_device(request: Request):
    payload = await request.json()
    address = payload.get("address")
    name = payload.get("name") or settings.hr_ble_default_name
    session_id = payload.get("session_id")
    try:
        status = await heart_rate_ble_service.connect(address=address, name=name, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 - BLE backend errors should be shown as API state.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return status


@router.post("/ble/disconnect")
async def disconnect_ble_device():
    return await heart_rate_ble_service.disconnect()


@router.get("/ble/status")
async def ble_status():
    return heart_rate_ble_service.status()
