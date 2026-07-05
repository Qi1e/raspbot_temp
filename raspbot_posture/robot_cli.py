"""Unified command-line entrypoint for posture preview and robot control modes."""

import argparse
import sys

from .cli import add_posture_arguments


def add_robot_control_arguments(parser):
    """Add robot-control mode and tuning arguments."""
    parser.add_argument(
        "--run-mode",
        choices=["posture", "camera", "steering", "full"],
        default="full",
        help=(
            "posture: pose preview; camera: camera preview only; "
            "steering: pan/tilt and body turning; full: also enable distance control"
        ),
    )

    parser.set_defaults(dry_run_control=None)
    parser.add_argument("--dry-run-control", dest="dry_run_control", action="store_true", help="print robot commands without touching hardware")
    parser.add_argument("--live-control", dest="dry_run_control", action="store_false", help="send robot commands to Raspbot hardware")
    parser.add_argument("--control-debug", action="store_true", help="print target and control decisions")
    parser.add_argument("--control-log-interval", type=float, default=0.5)

    parser.add_argument("--control-interval", type=float, default=0.05)
    parser.add_argument("--target-smoothing", type=float, default=0.72)
    parser.add_argument("--target-timeout", type=float, default=0.65)
    parser.add_argument("--target-min-confidence", type=float, default=0.55)

    parser.add_argument("--pan-center", type=float, default=90.0)
    parser.add_argument("--tilt-center", type=float, default=30.0)
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

    parser.add_argument("--tracking-mode", choices=["camera", "full"], default="full")
    parser.add_argument("--duration", type=float, default=0.0, help="tracking runtime seconds; 0 runs until Ctrl+C")
    parser.add_argument("--plan-interval", type=float, default=1.5)
    parser.add_argument("--max-input-age", type=float, default=0.4)
    parser.add_argument("--min-confidence", type=float, default=0.3)
    parser.add_argument("--servo-idle-required", type=float, default=0.4)
    parser.add_argument("--desired-min-distance", type=float, default=2.7)
    parser.add_argument("--desired-max-distance", type=float, default=3.3)
    parser.add_argument("--desired-distance", type=float, default=3.0)
    parser.add_argument("--max-reasonable-distance", type=float, default=10.0)
    parser.add_argument("--estimator-min-confidence", type=float, default=0.7)
    parser.add_argument("--distance-deadband", type=float, default=0.08)
    parser.add_argument("--min-move-speed", type=float, default=8.0)
    parser.add_argument("--max-move-speed", type=float, default=22.0)
    parser.add_argument("--distance-speed-gain", type=float, default=25.0)
    parser.add_argument("--min-goal-duration", type=float, default=0.15)
    parser.add_argument("--max-goal-duration", type=float, default=0.45)
    parser.add_argument("--distance-duration-gain", type=float, default=0.8)
    parser.add_argument("--body-yaw-deadband-degrees", type=float, default=4.0)
    parser.add_argument("--body-yaw-gain", type=float, default=0.12)
    parser.add_argument("--body-yaw-screen-gate-degrees", type=float, default=3.0)
    parser.add_argument("--max-yaw-speed", type=float, default=3.5)
    parser.add_argument("--max-wheel-speed", type=int, default=255)
    parser.add_argument("--horizontal-fov-degrees", type=float, default=62.0)
    parser.add_argument("--vertical-fov-degrees", type=float, default=49.0)
    parser.add_argument("--camera-pan-deadband-degrees", type=float, default=3.0)
    parser.add_argument("--camera-tilt-deadband-degrees", type=float, default=3.0)
    parser.add_argument("--camera-servo-step", type=float, default=1.0)
    parser.add_argument("--camera-servo-gain", type=float, default=0.16)
    parser.add_argument("--yaw-servo-compensation-gain", type=float, default=0.5)
    parser.add_argument("--yaw-servo-compensation-max-step", type=float, default=0.6)
    parser.add_argument("--yaw-servo-compensation-deadband", type=float, default=0.5)
    parser.add_argument("--yaw-servo-compensation-sign", type=int, choices=[-1, 1], default=-1)
    parser.add_argument("--allow-yaw-during-action", action="store_true")
    parser.add_argument("--log-dir", default="", help="write run args JSON and control CSV logs into this directory")
    parser.add_argument("--log-prefix", default="tracking", help="prefix for generated log files")
    parser.add_argument("--log-interval", type=float, default=0.05)
    parser.add_argument("--print-motors", action="store_true")
    parser.add_argument("--print-servos", action="store_true")
    parser.add_argument("--print-planner", action="store_true")
    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--enable-obstacle-avoidance", action="store_true")
    parser.add_argument("--ultrasonic-poll-interval", type=float, default=0.05)
    parser.add_argument("--ultrasonic-filter-size", type=int, default=5)
    parser.add_argument("--obstacle-enter-mm", type=float, default=280.0)
    parser.add_argument("--obstacle-too-close-mm", type=float, default=240.0)
    parser.add_argument("--obstacle-exit-mm", type=float, default=430.0)
    parser.add_argument("--obstacle-enter-stable-count", type=int, default=3)
    parser.add_argument("--obstacle-exit-stable-count", type=int, default=5)
    parser.add_argument("--obstacle-cooldown", type=float, default=1.5)
    parser.add_argument("--obstacle-speed", type=float, default=18.0)
    parser.add_argument("--obstacle-return-speed", type=float, default=16.0)
    parser.add_argument("--obstacle-backward-speed", type=float, default=16.0)
    parser.add_argument("--obstacle-pulse", type=float, default=0.25)
    parser.add_argument("--obstacle-max-steps", type=int, default=15)
    parser.add_argument("--obstacle-max-active-time", type=float, default=6.0)
    parser.add_argument("--obstacle-fail-backup-time", type=float, default=0.5)
    parser.add_argument("--obstacle-fail-stop-time", type=float, default=1.0)
    parser.add_argument("--obstacle-left-direction-degrees", type=float, default=135.0)
    parser.add_argument("--obstacle-right-direction-degrees", type=float, default=45.0)
    parser.add_argument("--obstacle-backward-direction-degrees", type=float, default=270.0)
    return parser


def build_parser():
    """Build the unified posture demo argument parser."""
    parser = argparse.ArgumentParser(description="Raspbot posture demo with optional robot control modes")
    parser.add_argument("--voice-child", action="store_true", help=argparse.SUPPRESS)
    add_posture_arguments(parser)
    add_robot_control_arguments(parser)
    return parser


def _has_option(argv, option):
    """Return True when argv contains --option or --option=value."""
    return any(item == option or item.startswith(option + "=") for item in argv)


def _uses_voice_supervisor(args, argv):
    return not args.voice_child and not _has_option(argv, "--run-mode")


def parse_args(argv=None):
    """Parse command-line arguments for the unified posture demo."""
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not _uses_voice_supervisor(args, argv):
        apply_control_default(args, argv)
    return args


def apply_control_default(args, argv):
    """Default explicit robot modes to live control while keeping bare startup safe."""
    argv = list(argv)
    explicit_control = _has_option(argv, "--dry-run-control") or _has_option(argv, "--live-control")
    explicit_run_mode = _has_option(argv, "--run-mode")
    if args.dry_run_control is None:
        args.dry_run_control = not (explicit_run_mode and args.run_mode in ("steering", "full"))
    if not explicit_control and explicit_run_mode and args.run_mode in ("steering", "full"):
        print("Robot hardware control is live. Add --dry-run-control to disable motor/servo output.")
    elif args.dry_run_control and args.run_mode in ("steering", "full"):
        print("Robot hardware control is dry-run. Add --live-control to send motor/servo output.")
    return args


def main(argv=None):
    """Run the unified posture demo using CLI arguments."""
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    args = parse_args(argv)
    if _uses_voice_supervisor(args, argv):
        from .voice_supervisor import run_voice_supervisor

        raise SystemExit(run_voice_supervisor(child_args=argv))

    from .robot_app import run_robot_control_demo

    run_robot_control_demo(args)
