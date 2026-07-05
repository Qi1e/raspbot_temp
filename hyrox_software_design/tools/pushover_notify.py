#!/usr/bin/env python3
# coding: utf-8

"""Send a HYROX test notification through Pushover."""

import argparse
import json
import os
import sys
from urllib import error, parse, request


PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"


def format_duration(seconds):
    """Format duration seconds as a compact Chinese display string."""
    total_seconds = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分{secs}秒"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def build_message(event, message, duration_seconds):
    """Build a default message for common HYROX notification events."""
    if message:
        return message
    if event == "started":
        return "已开始运动"
    if event == "finished":
        if duration_seconds is None:
            return "训练结束"
        return f"训练结束，本次运动 {format_duration(duration_seconds)}"
    return "已开始运动"


def build_parser():
    parser = argparse.ArgumentParser(description="Send a Pushover HYROX test notification.")
    parser.add_argument("--title", default="HYROX", help="notification title")
    parser.add_argument(
        "--event",
        default="started",
        choices=["started", "finished"],
        help="predefined HYROX notification event",
    )
    parser.add_argument("--message", default="", help="notification message")
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="training duration used by --event finished",
    )
    parser.add_argument("--sound", default="vibrate", help="Pushover sound name")
    parser.add_argument(
        "--priority",
        type=int,
        default=0,
        choices=[-2, -1, 0, 1],
        help="Pushover priority; 0 triggers normal notification behavior",
    )
    return parser


def send_pushover(token, user_key, title, message, sound, priority):
    payload = {
        "token": token,
        "user": user_key,
        "title": title,
        "message": message,
        "sound": sound,
        "priority": str(priority),
    }
    body = parse.urlencode(payload).encode("utf-8")
    req = request.Request(
        PUSHOVER_API_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def main():
    args = build_parser().parse_args()
    token = os.environ.get("PUSHOVER_APP_TOKEN", "").strip()
    user_key = os.environ.get("PUSHOVER_USER_KEY", "").strip()

    if not token or not user_key:
        print(
            "Missing credentials. Set PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY first.",
            file=sys.stderr,
        )
        return 2

    try:
        message = build_message(args.event, args.message, args.duration_seconds)
        result = send_pushover(
            token=token,
            user_key=user_key,
            title=args.title,
            message=message,
            sound=args.sound,
            priority=args.priority,
        )
    except error.HTTPError as exc:
        print(f"Pushover HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI should print a clear failure.
        print(f"Pushover request failed: {exc}", file=sys.stderr)
        return 1

    if result.get("status") == 1:
        print("Pushover notification sent.")
        print(f"request={result.get('request')}")
        return 0

    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
