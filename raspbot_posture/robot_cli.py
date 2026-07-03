"""Command-line entrypoint for posture robot control."""

import argparse

from .cli import add_posture_arguments


def add_robot_control_arguments(parser):
    """Add robot-control mode and tuning arguments."""
    parser.add_argument(
        "--run-mode",
        choices=["camera", "steering", "full"],
        default="camera",
        help="camera: camera preview only; steering: pan/tilt and body turning; full: also enable distance control",
    )

    parser.add_argument("--dry-run-control", action="store_true", help="print robot commands without touching hardware")
    parser.add_argument("--control-debug", action="store_true", help="print target and control decisions")
    parser.add_argument("--control-log-interval", type=float, default=0.5)

    parser.add_argument("--control-interval", type=float, default=0.05)
    parser.add_argument("--target-smoothing", type=float, default=0.72)
    parser.add_argument("--target-timeout", type=float, default=0.65)
    parser.add_argument("--target-min-confidence", type=float, default=0.55)

    parser.add_argument("--pan-center", type=float, default=90.0)
    parser.add_argument("--tilt-center", type=float, default=80.0)
    parser.add_argument("--tilt-rest", type=float, default=25.0)
    parser.add_argument("--pan-min", type=float, default=20.0)
    parser.add_argument("--pan-max", type=float, default=160.0)
    parser.add_argument("--tilt-min", type=float, default=0.0)
    parser.add_argument("--tilt-max", type=float, default=100.0)
    parser.add_argument("--pan-deadzone", type=float, default=0.08)
    parser.add_argument("--tilt-deadzone", type=float, default=0.11)
    parser.add_argument("--servo-step", type=float, default=1.5)
    parser.add_argument("--servo-gain", type=float, default=32.0)
    parser.add_argument("--servo-interval", type=float, default=0.20)
    parser.add_argument("--invert-pan", action="store_true")
    parser.add_argument("--invert-tilt", action="store_true")
    parser.add_argument("--return-center-on-lost", action="store_true")
    parser.set_defaults(reset_servo_on_exit=True, freeze_during_action=True)
    parser.add_argument("--reset-servo-on-exit", dest="reset_servo_on_exit", action="store_true")
    parser.add_argument("--no-reset-servo-on-exit", dest="reset_servo_on_exit", action="store_false")

    parser.add_argument("--body-turn-speed", type=int, default=10)
    parser.add_argument("--body-forward-speed", type=int, default=12)
    parser.add_argument("--body-backward-speed", type=int, default=10)
    parser.add_argument("--body-pulse", type=float, default=0.15)
    parser.add_argument("--body-cooldown", type=float, default=0.50)
    parser.add_argument("--pan-body-threshold", type=float, default=22.0)
    parser.add_argument("--pan-body-hold", type=float, default=0.55)
    parser.add_argument("--invert-body-turn", action="store_true")

    parser.add_argument("--target-area-min", type=float, default=0.12)
    parser.add_argument("--target-area-max", type=float, default=0.28)
    parser.add_argument("--distance-stable-time", type=float, default=0.8)
    parser.add_argument("--distance-x-deadzone", type=float, default=0.12)
    parser.add_argument("--freeze-during-action", dest="freeze_during_action", action="store_true")
    parser.add_argument("--no-freeze-during-action", dest="freeze_during_action", action="store_false")
    parser.add_argument("--action-freeze-time", type=float, default=0.9)
    return parser


def build_parser():
    """Build the posture robot control argument parser."""
    parser = argparse.ArgumentParser(description="Raspbot posture tracking with tunable robot control")
    add_posture_arguments(parser)
    add_robot_control_arguments(parser)
    return parser


def parse_args():
    """Parse command-line arguments for posture robot control."""
    return build_parser().parse_args()


def main():
    """Run the posture robot control demo using CLI arguments."""
    args = parse_args()
    from .robot_app import run_robot_control_demo

    run_robot_control_demo(args)
