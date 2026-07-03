#!/usr/bin/env python3
# coding: utf-8
"""Full-control dry run using package runtime APIs."""

from raspbot_posture.robot_app import run_robot_control_demo
from raspbot_posture.robot_cli import build_parser


def main():
    parser = build_parser()
    args = parser.parse_args(["--run-mode", "full", "--dry-run-control", "--control-debug"])
    run_robot_control_demo(args)


if __name__ == "__main__":
    main()
