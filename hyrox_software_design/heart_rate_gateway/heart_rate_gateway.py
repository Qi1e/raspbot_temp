#!/usr/bin/env python3
"""Read heart rate samples from a BLE Heart Rate Service device.

The gateway subscribes to the standard Heart Rate Measurement characteristic
0x2A37 and prints each sample as one JSON line. It is intentionally standalone
so it can be tested before integrating with the HYROX report backend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from dataclasses import dataclass
from typing import Optional

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice
except ImportError:  # pragma: no cover - useful runtime message
    print(
        "Missing dependency: bleak. Install it with:\n"
        "  cd heart_rate_gateway\n"
        "  python3 -m venv .venv\n"
        "  source .venv/bin/activate\n"
        "  pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise


HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


@dataclass
class HeartRateSample:
    device_name: str
    device_address: str
    timestamp_ms: int
    bpm: int
    contact_detected: Optional[bool]
    source: str = "ble_2a37"

    def to_json_line(self) -> str:
        return json.dumps(
            {
                "type": "heart_rate_sample",
                "device_name": self.device_name,
                "device_address": self.device_address,
                "timestamp_ms": self.timestamp_ms,
                "bpm": self.bpm,
                "contact_detected": self.contact_detected,
                "source": self.source,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_heart_rate_measurement(data: bytearray) -> tuple[int, Optional[bool]]:
    """Parse the Bluetooth Heart Rate Measurement characteristic payload.

    Byte 0 is flags. If bit 0 is set, bpm is uint16 little-endian; otherwise it
    is uint8. Contact detection may be present when flags bits 1 and 2 indicate
    support and current contact status.
    """

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


async def scan_devices(timeout: float) -> None:
    print(f"Scanning BLE devices for {timeout:.1f}s...")
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)

    if not devices:
        print("No BLE devices found.")
        return

    for _, (device, adv) in sorted(devices.items(), key=lambda item: item[1][0].name or ""):
        name = device.name or adv.local_name or "(unknown)"
        services = sorted(str(uuid) for uuid in adv.service_uuids)
        service_text = ", ".join(services) if services else "no advertised service UUIDs"
        print(f"- {name} | {device.address} | RSSI {adv.rssi} | {service_text}")


async def find_device(name_filter: str, timeout: float) -> Optional[BLEDevice]:
    print(f"Looking for BLE device containing name: {name_filter!r}")
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        devices = await BleakScanner.discover(timeout=3.0)
        for device in devices:
            if device.name and name_filter.lower() in device.name.lower():
                print(f"Found {device.name} at {device.address}")
                return device

    return None


async def resolve_device(address: Optional[str], name: str, scan_timeout: float) -> BLEDevice:
    if address:
        device = await BleakScanner.find_device_by_address(address, timeout=scan_timeout)
        if device is None:
            raise RuntimeError(f"Device address not found: {address}")
        return device

    device = await find_device(name, scan_timeout)
    if device is None:
        raise RuntimeError(
            f"No BLE device found with name containing {name!r}. "
            "Try --scan first, then use --address."
        )
    return device


async def connect_and_listen(args: argparse.Namespace) -> None:
    stop_event = asyncio.Event()

    def request_stop() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    while not stop_event.is_set():
        device = await resolve_device(args.address, args.name, args.scan_timeout)
        device_name = device.name or args.name

        try:
            async with BleakClient(device, timeout=args.connect_timeout) as client:
                print(f"Connected to {device_name} ({device.address})", file=sys.stderr)

                services = await client.get_services()
                if HEART_RATE_SERVICE_UUID not in [str(s.uuid).lower() for s in services]:
                    print(
                        "Warning: connected device did not expose standard Heart Rate Service.",
                        file=sys.stderr,
                    )

                if args.list_services:
                    for service in services:
                        print(f"Service {service.uuid}", file=sys.stderr)
                        for characteristic in service.characteristics:
                            props = ", ".join(characteristic.properties)
                            print(
                                f"  Characteristic {characteristic.uuid} [{props}]",
                                file=sys.stderr,
                            )

                def on_notify(sender: object, data: bytearray) -> None:
                    try:
                        bpm, contact_detected = parse_heart_rate_measurement(data)
                    except ValueError as exc:
                        print(f"Ignoring invalid HR payload: {exc}", file=sys.stderr)
                        return

                    sample = HeartRateSample(
                        device_name=device_name,
                        device_address=device.address,
                        timestamp_ms=now_ms(),
                        bpm=bpm,
                        contact_detected=contact_detected,
                    )
                    print(sample.to_json_line(), flush=True)

                await client.start_notify(HEART_RATE_MEASUREMENT_UUID, on_notify)
                print("Listening for heart rate samples. Press Ctrl+C to stop.", file=sys.stderr)

                while client.is_connected and not stop_event.is_set():
                    await asyncio.sleep(0.5)

                try:
                    await client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
                except Exception:
                    pass

        except Exception as exc:
            if stop_event.is_set():
                break
            print(f"BLE connection failed: {exc}", file=sys.stderr)

        if args.reconnect and not stop_event.is_set():
            print(f"Reconnecting in {args.reconnect_delay:.1f}s...", file=sys.stderr)
            await asyncio.sleep(args.reconnect_delay)
        else:
            break


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read BLE heart rate samples.")
    parser.add_argument("--scan", action="store_true", help="Scan BLE devices and exit.")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Scan timeout seconds.")
    parser.add_argument("--address", help="Connect to a specific BLE address.")
    parser.add_argument(
        "--name",
        default="vivo WATCH",
        help="Device name substring used when --address is not provided.",
    )
    parser.add_argument("--connect-timeout", type=float, default=15.0)
    parser.add_argument("--list-services", action="store_true", help="Print services after connecting.")
    parser.add_argument("--reconnect", action="store_true", help="Reconnect after disconnection.")
    parser.add_argument("--reconnect-delay", type=float, default=3.0)
    return parser


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.scan:
        await scan_devices(args.scan_timeout)
        return

    await connect_and_listen(args)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
