"""BLE heart-rate scanning and connection service."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.db.database import db
from app.services.live_state import live_state

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - reported through API at runtime.
    BleakClient = None
    BleakScanner = None


HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_heart_rate_measurement(data: bytearray) -> tuple[int, bool | None]:
    if len(data) < 2:
        raise ValueError(f"Heart rate payload too short: {data.hex(' ')}")
    flags = data[0]
    is_uint16 = bool(flags & 0x01)
    contact_supported = bool(flags & 0x04)
    contact_detected = bool(flags & 0x02) if contact_supported else None
    if is_uint16:
        if len(data) < 3:
            raise ValueError(f"16-bit heart rate payload too short: {data.hex(' ')}")
        bpm = int.from_bytes(data[1:3], byteorder="little", signed=False)
    else:
        bpm = data[1]
    if bpm < 35 or bpm > 230:
        raise ValueError(f"Unreasonable heart rate {bpm} from payload {data.hex(' ')}")
    return bpm, contact_detected


@dataclass
class ConnectedDevice:
    address: str
    name: str
    session_id: str | None = None


class HeartRateBleService:
    """Single-device BLE heart-rate manager."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._device: ConnectedDevice | None = None
        self._stop_event: asyncio.Event | None = None

    def _require_bleak(self) -> None:
        if BleakScanner is None or BleakClient is None:
            raise RuntimeError("Missing dependency: bleak. Install backend requirements first.")

    async def scan(self, timeout: float) -> list[dict[str, Any]]:
        self._require_bleak()
        devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
        result: list[dict[str, Any]] = []
        for _, (device, adv) in devices.items():
            services = [str(uuid).lower() for uuid in adv.service_uuids]
            name = device.name or adv.local_name or "(unknown)"
            is_hr_candidate = HEART_RATE_SERVICE_UUID in services or "watch" in name.lower() or "hr" in name.lower()
            result.append(
                {
                    "name": name,
                    "address": device.address,
                    "rssi": adv.rssi,
                    "service_uuids": services,
                    "is_heart_rate_candidate": is_hr_candidate,
                }
            )
        result.sort(key=lambda item: (not item["is_heart_rate_candidate"], item["name"]))
        return result

    async def connect(self, address: str | None, name: str, session_id: str | None) -> dict[str, Any]:
        self._require_bleak()
        await self.disconnect()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(address, name, session_id, self._stop_event))
        live_state.set_hr_device_status("connecting", address=address, name=name, session_id=session_id)
        return self.status()

    async def disconnect(self) -> dict[str, Any]:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        self._stop_event = None
        self._device = None
        live_state.set_hr_device_status("disconnected")
        return self.status()

    def status(self) -> dict[str, Any]:
        status = live_state.hr_device_status()
        status["single_device_only"] = True
        return status

    async def _resolve_device(self, address: str | None, name: str):
        if address:
            device = await BleakScanner.find_device_by_address(address, timeout=10.0)
            if device is None:
                raise RuntimeError(f"Device address not found: {address}")
            return device
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            devices = await BleakScanner.discover(timeout=3.0)
            for device in devices:
                if device.name and name.lower() in device.name.lower():
                    return device
        raise RuntimeError(f"No BLE device found with name containing {name!r}")

    async def _run(
        self,
        address: str | None,
        name: str,
        session_id: str | None,
        stop_event: asyncio.Event,
    ) -> None:
        try:
            device = await self._resolve_device(address, name)
            device_name = device.name or name
            self._device = ConnectedDevice(device.address, device_name, session_id=session_id)
            async with BleakClient(device, timeout=15.0) as client:
                loop = asyncio.get_running_loop()
                live_state.set_hr_device_status(
                    "connected",
                    address=device.address,
                    name=device_name,
                    session_id=session_id,
                    samples_received=0,
                    latest_bpm=None,
                    latest_sample_at_ms=None,
                )
                samples_received = 0

                def on_notify(sender: object, data: bytearray) -> None:
                    nonlocal samples_received
                    try:
                        bpm, contact_detected = parse_heart_rate_measurement(data)
                    except ValueError:
                        return
                    samples_received += 1
                    sample = {
                        "type": "heart_rate_sample",
                        "device_name": device_name,
                        "device_address": device.address,
                        "timestamp_ms": now_ms(),
                        "bpm": bpm,
                        "contact_detected": contact_detected,
                        "source": "ble_2a37",
                    }
                    live_state.set_hr_device_status(
                        "listening",
                        address=device.address,
                        name=device_name,
                        session_id=session_id,
                        samples_received=samples_received,
                        latest_bpm=bpm,
                        latest_sample_at_ms=sample["timestamp_ms"],
                        contact_detected=contact_detected,
                    )
                    with db.connect() as conn:
                        conn.execute(
                            """
                            INSERT INTO heart_rate_samples (
                                session_id, device_id, device_name, timestamp_ms, bpm,
                                contact_detected, source, quality
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 'ble_2a37', 'live')
                            """,
                            (
                                session_id or live_state.latest_session_id(),
                                device.address,
                                device_name,
                                sample["timestamp_ms"],
                                bpm,
                                None if contact_detected is None else int(contact_detected),
                            ),
                    )
                    touched_session = live_state.update_heart_rate(sample, session_id)
                    if touched_session:
                        loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(live_state.publish(touched_session))
                        )

                await client.start_notify(HEART_RATE_MEASUREMENT_UUID, on_notify)
                live_state.set_hr_device_status(
                    "listening",
                    address=device.address,
                    name=device_name,
                    session_id=session_id,
                    samples_received=0,
                    latest_bpm=None,
                    latest_sample_at_ms=None,
                )
                while client.is_connected and not stop_event.is_set():
                    await asyncio.sleep(0.5)
                try:
                    await client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001 - status is reported to API/UI.
            live_state.set_hr_device_status("error", message=str(exc), address=address, name=name)
        finally:
            if live_state.hr_device_status().get("status") in {"connected", "listening"}:
                live_state.set_hr_device_status("disconnected")


heart_rate_ble_service = HeartRateBleService()
