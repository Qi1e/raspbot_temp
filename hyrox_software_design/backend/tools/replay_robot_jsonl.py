#!/usr/bin/env python3
# coding: utf-8

"""Replay a robot JSONL/NDJSON file into the HYROX backend ingest API."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from urllib import request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay Raspbot JSONL data to backend.")
    parser.add_argument("jsonl_path", help="path to robot JSONL/NDJSON file")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/robot/ingest")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.0, help="seconds between batches")
    return parser


def post_batch(url: str, lines: list[str]) -> None:
    body = "".join(lines).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-ndjson"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as response:
        response.read()


def main() -> int:
    args = build_parser().parse_args()
    path = Path(args.jsonl_path)
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    batch: list[str] = []
    sent = 0
    for line in path.read_text(encoding="utf-8").splitlines(True):
        if not line.strip():
            continue
        batch.append(line)
        if len(batch) >= args.batch_size:
            post_batch(args.url, batch)
            sent += len(batch)
            print(f"sent {sent}")
            batch = []
            if args.sleep > 0:
                time.sleep(args.sleep)
    if batch:
        post_batch(args.url, batch)
        sent += len(batch)
        print(f"sent {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
