"""Voice-gated supervisor for the full posture tracking runtime."""

import os
import signal
import subprocess
import sys
import time


START_CODE = 95
PAUSE_CODE = 96
RESERVED_CODE = 97
STOP_CODE = 104
NO_COMMAND_CODE = 999


def _load_speech():
    try:
        from Speech_Lib import Speech
    except ImportError as exc:
        raise RuntimeError(
            "Speech_Lib is not available. Run voice mode on the Raspberry Pi "
            "environment that provides the speech recognition library, or start "
            "tracking directly with: python3 posture_demo.py --run-mode full"
        ) from exc
    return Speech()


def _tracking_command():
    return [
        sys.executable,
        "-m",
        "raspbot_posture",
        "--voice-child",
        "--run-mode",
        "full",
    ]


def _start_process():
    kwargs = {}
    if os.name != "nt":
        kwargs["preexec_fn"] = os.setsid
    return subprocess.Popen(_tracking_command(), **kwargs)


def _signal_process(process, sig):
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), sig)
        else:
            process.send_signal(sig)
    except ProcessLookupError:
        return


def _stop_process(process, reason, grace_timeout=5.0):
    if process is None:
        return None
    if process.poll() is not None:
        print(f"Tracking child already exited with code {process.returncode}.")
        return None

    print(f"Stopping tracking child ({reason})...")
    try:
        _signal_process(process, signal.SIGINT)
        process.wait(timeout=grace_timeout)
    except subprocess.TimeoutExpired:
        _signal_process(process, signal.SIGTERM)
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                _signal_process(process, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=2.0)
    return None


def _acknowledge(speech, code):
    try:
        speech.void_write(code)
    except Exception as exc:
        print(f"Voice acknowledgement failed for code {code}: {exc}")


def run_voice_supervisor(poll_interval=0.2):
    """Wait for speech commands and launch or stop the tracking child."""
    speech = _load_speech()
    process = None
    print("Voice control ready. Say command 95 to start, 96 to pause, 104 to stop.")

    try:
        while True:
            time.sleep(poll_interval)
            code = speech.speech_read()
            if code == NO_COMMAND_CODE:
                if process is not None and process.poll() is not None:
                    print(f"Tracking child exited with code {process.returncode}.")
                    process = None
                continue

            if code == START_CODE:
                _acknowledge(speech, code)
                if process is None or process.poll() is not None:
                    print("Voice command 95: starting full tracking.")
                    process = _start_process()
                else:
                    print("Voice command 95 ignored: tracking is already running.")
            elif code == PAUSE_CODE:
                _acknowledge(speech, code)
                print("Voice command 96: pausing full tracking.")
                process = _stop_process(process, "voice pause")
            elif code == RESERVED_CODE:
                _acknowledge(speech, code)
                print("Voice command 97 received: reserved, no tracking action.")
            elif code == STOP_CODE:
                _acknowledge(speech, code)
                print("Voice command 104: terminating voice supervisor.")
                process = _stop_process(process, "voice stop", grace_timeout=2.0)
                return 0
            elif code == 0:
                _acknowledge(speech, code)
            else:
                print(f"Voice command {code} received: no mapped tracking action.")
    except KeyboardInterrupt:
        process = _stop_process(process, "keyboard interrupt", grace_timeout=2.0)
        print("Voice control stopped.")
        return 130
