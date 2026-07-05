#!/usr/bin/env python3
# coding: utf-8

"""Bootstrap and run the HYROX desktop service."""

from __future__ import annotations

import hashlib
import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
BOOTSTRAP = ROOT / ".bootstrap"
BACKEND_ENV = BACKEND / ".env"
BACKEND_VENV = BACKEND / ".venv"
FRONTEND_DIST = FRONTEND / "dist" / "index.html"
HOST = "0.0.0.0"
PORT = 8000
LOCAL_URL = f"http://127.0.0.1:{PORT}"
INGEST_PATH = "/api/v1/robot/ingest"


def info(message: str) -> None:
    print(f"[HYROX] {message}", flush=True)


def die(message: str, code: int = 1) -> None:
    print(f"\n[HYROX] {message}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    info(f"Run: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=str(cwd), env=env, check=True)
    except FileNotFoundError:
        die(f"Command not found: {cmd[0]}")
    except subprocess.CalledProcessError as exc:
        die(f"Command failed with exit code {exc.returncode}: {' '.join(cmd)}")


def sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not path.exists() or path.is_dir():
            continue
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_stamp(name: str) -> str:
    path = BOOTSTRAP / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def write_stamp(name: str, value: str) -> None:
    BOOTSTRAP.mkdir(parents=True, exist_ok=True)
    (BOOTSTRAP / name).write_text(value + "\n", encoding="utf-8")


def create_default_env() -> None:
    if BACKEND_ENV.exists():
        return
    info("Creating backend/.env with safe local defaults.")
    BACKEND_ENV.write_text(
        "\n".join(
            [
                "HYROX_DATABASE_PATH=./data/hyrox_backend.sqlite3",
                "HYROX_LIVE_PUSH_INTERVAL_SECONDS=0.4",
                "",
                "PUSHOVER_ENABLED=false",
                "PUSHOVER_NOTIFY_REPS=false",
                "PUSHOVER_APP_TOKEN=",
                "PUSHOVER_USER_KEY=",
                "PUSHOVER_DEFAULT_PRIORITY=0",
                "PUSHOVER_REP_THROTTLE_SECONDS=1.0",
                "PUSHOVER_WARNING_THROTTLE_SECONDS=15.0",
                "",
                "HR_BLE_SCAN_TIMEOUT_SECONDS=10.0",
                "HR_BLE_DEFAULT_NAME=",
                "",
            ]
        ),
        encoding="utf-8",
    )


def load_env_file(path: Path) -> dict[str, str]:
    env = os.environ.copy()
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def ensure_python_environment() -> None:
    if sys.version_info < (3, 9):
        die("Python 3.9+ is required. Please install a newer Python and run again.")

    requirements = BACKEND / "requirements.txt"
    requirements_hash = sha256_files([requirements])
    pip_path = BACKEND_VENV / "bin" / "pip"
    python_path = BACKEND_VENV / "bin" / "python"

    if not python_path.exists():
        info("Creating backend virtual environment.")
        run([sys.executable, "-m", "venv", str(BACKEND_VENV)], cwd=BACKEND)

    if read_stamp("backend_requirements.sha256") != requirements_hash:
        info("Installing backend Python dependencies.")
        run([str(pip_path), "install", "--upgrade", "pip"], cwd=BACKEND)
        run([str(pip_path), "install", "-r", str(requirements)], cwd=BACKEND)
        write_stamp("backend_requirements.sha256", requirements_hash)
    else:
        info("Backend Python dependencies are up to date.")


def frontend_sources() -> list[Path]:
    paths = [
        FRONTEND / "package.json",
        FRONTEND / "package-lock.json",
        FRONTEND / "index.html",
        FRONTEND / "vite.config.ts",
        FRONTEND / "tsconfig.json",
        FRONTEND / "tsconfig.node.json",
    ]
    src = FRONTEND / "src"
    if src.exists():
        paths.extend(path for path in src.rglob("*") if path.is_file())
    return paths


def ensure_node_environment() -> None:
    npm = shutil.which("npm")
    node = shutil.which("node")
    if not node or not npm:
        die(
            "Node.js/npm is required to build the frontend. "
            "Install Node.js LTS from https://nodejs.org/ and run this command again."
        )

    package_hash = sha256_files([FRONTEND / "package.json", FRONTEND / "package-lock.json"])
    node_modules = FRONTEND / "node_modules"
    if not node_modules.exists() or read_stamp("frontend_packages.sha256") != package_hash:
        info("Installing frontend Node dependencies.")
        run([npm, "install"], cwd=FRONTEND)
        write_stamp("frontend_packages.sha256", package_hash)
    else:
        info("Frontend Node dependencies are up to date.")

    build_hash = sha256_files(frontend_sources())
    if not FRONTEND_DIST.exists() or read_stamp("frontend_build.sha256") != build_hash:
        info("Building frontend for backend static hosting.")
        run([npm, "run", "build"], cwd=FRONTEND)
        write_stamp("frontend_build.sha256", build_hash)
    else:
        info("Frontend build is up to date.")


def backend_health_ok() -> bool:
    try:
        with urlopen(f"{LOCAL_URL}/health", timeout=1.5) as response:
            return response.status == 200 and b"ok" in response.read()
    except (OSError, URLError):
        return False


def local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []

    ipconfig = shutil.which("ipconfig")
    if ipconfig:
        for iface in ("en0", "en1", "bridge100"):
            try:
                result = subprocess.run(
                    [ipconfig, "getifaddr", iface],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
            except subprocess.SubprocessError:
                continue
            candidate = result.stdout.strip()
            if candidate and candidate not in addresses:
                addresses.append(candidate)

    ifconfig = shutil.which("ifconfig")
    if ifconfig:
        try:
            result = subprocess.run(
                [ifconfig],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            for candidate in re.findall(r"\binet (\d+\.\d+\.\d+\.\d+)\b", result.stdout):
                if not candidate.startswith("127.") and candidate not in addresses:
                    addresses.append(candidate)
        except subprocess.SubprocessError:
            pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = sock.getsockname()[0]
            if candidate and candidate not in addresses:
                addresses.append(candidate)
    except OSError:
        pass

    return addresses


def print_connection_help() -> None:
    addresses = local_ipv4_addresses()
    print("\n================ HYROX Ready ================", flush=True)
    print(f"Open frontend: {LOCAL_URL}", flush=True)
    print("\nRaspbot record-url candidates:", flush=True)
    if addresses:
        for address in addresses:
            print(f"  http://{address}:{PORT}{INGEST_PATH}", flush=True)
    else:
        print("  Could not detect a non-loopback IP. Check System Settings > Wi-Fi > Details.", flush=True)
    print("\nRaspbot command shape:", flush=True)
    print("  python3 posture_demo.py \\", flush=True)
    print("    --record-url http://<computer-ip>:8000/api/v1/robot/ingest \\", flush=True)
    print("    --record-device-id raspbot_01 --record-keypoints", flush=True)
    print("\nNotes:", flush=True)
    print("  - Pushover is disabled by default unless backend/.env has token/key and PUSHOVER_ENABLED=true.", flush=True)
    print("  - The first BLE scan may ask macOS to allow Bluetooth access.", flush=True)
    print("  - If the car Wi-Fi has no internet, Pushover cloud notifications will not send.", flush=True)
    print("=============================================\n", flush=True)


def start_backend(open_browser: bool = True) -> None:
    env = load_env_file(BACKEND_ENV)
    python_path = BACKEND_VENV / "bin" / "python"

    if backend_health_ok():
        info("Backend is already running on port 8000.")
        print_connection_help()
        if open_browser:
            webbrowser.open(LOCAL_URL)
        return

    cmd = [
        str(python_path),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
    ]
    info("Starting backend and serving the frontend from port 8000.")
    process = subprocess.Popen(cmd, cwd=str(BACKEND), env=env)

    try:
        for _ in range(40):
            if backend_health_ok():
                break
            if process.poll() is not None:
                die(f"Backend exited early with code {process.returncode}.")
            time.sleep(0.25)

        print_connection_help()
        if open_browser:
            webbrowser.open(LOCAL_URL)
        info("Press Ctrl+C in this terminal to stop the HYROX desktop service.")
        process.wait()
    except KeyboardInterrupt:
        info("Stopping HYROX desktop service.")
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap and run HYROX desktop service.")
    parser.add_argument("--setup-only", action="store_true", help="install dependencies and build frontend, then exit")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    os.chdir(ROOT)
    BOOTSTRAP.mkdir(parents=True, exist_ok=True)
    create_default_env()
    ensure_python_environment()
    ensure_node_environment()
    if args.setup_only:
        info("Setup complete. Run ./hyrox_start.command to start the service.")
        print_connection_help()
        return 0
    start_backend(open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
