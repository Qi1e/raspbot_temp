"""Environment-backed backend configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    database_path: Path
    live_push_interval_seconds: float
    pushover_enabled: bool
    pushover_notify_reps: bool
    pushover_app_token: str
    pushover_user_key: str
    pushover_default_priority: int
    pushover_rep_throttle_seconds: float
    pushover_warning_throttle_seconds: float
    hr_ble_scan_timeout_seconds: float
    hr_ble_default_name: str


def load_settings() -> Settings:
    return Settings(
        database_path=Path(os.environ.get("HYROX_DATABASE_PATH", "./data/hyrox_backend.sqlite3")),
        live_push_interval_seconds=_float_env("HYROX_LIVE_PUSH_INTERVAL_SECONDS", 0.4),
        pushover_enabled=_bool_env("PUSHOVER_ENABLED", True),
        pushover_notify_reps=_bool_env("PUSHOVER_NOTIFY_REPS", False),
        pushover_app_token=os.environ.get("PUSHOVER_APP_TOKEN", "").strip(),
        pushover_user_key=os.environ.get("PUSHOVER_USER_KEY", "").strip(),
        pushover_default_priority=_int_env("PUSHOVER_DEFAULT_PRIORITY", 0),
        pushover_rep_throttle_seconds=_float_env("PUSHOVER_REP_THROTTLE_SECONDS", 1.0),
        pushover_warning_throttle_seconds=_float_env("PUSHOVER_WARNING_THROTTLE_SECONDS", 15.0),
        hr_ble_scan_timeout_seconds=_float_env("HR_BLE_SCAN_TIMEOUT_SECONDS", 10.0),
        hr_ble_default_name=os.environ.get("HR_BLE_DEFAULT_NAME", "vivo WATCH").strip(),
    )


settings = load_settings()
