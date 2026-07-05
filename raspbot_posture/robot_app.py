"""Runtime glue for posture robot control modes."""

from .app import run_posture_demo
from .robot_controller import PostureRobotController


def apply_robot_run_mode(args):
    """Derive runtime switches from the selected robot test mode."""
    args.camera_only = args.run_mode == "camera"
    args.robot_control_enabled = args.run_mode in ("steering", "full")
    args.distance_control = args.run_mode == "full"
    return args


def build_robot_controller(args, analysis_state, stop_event):
    """Create the posture robot controller used by the shared app loop."""
    return PostureRobotController(args, analysis_state, stop_event)


def print_control_summary(args):
    """Print the active robot-control mode and important tuning knobs."""
    if args.run_mode == "posture":
        print("Run mode: posture preview. Pose inference is enabled; robot control is disabled.")
        return
    if args.run_mode == "camera":
        print("Run mode: camera only. Pose inference and robot control are disabled.")
        return

    print(
        "Robot control enabled: "
        f"mode={args.run_mode}, dry_run={args.dry_run_control}, "
        f"pan_deadzone={args.pan_deadzone}, tilt_deadzone={args.tilt_deadzone}, "
        f"servo_step={args.servo_step}, body_turn_speed={args.body_turn_speed}, "
        f"body_pulse={args.body_pulse}, body_cooldown={args.body_cooldown}, "
        f"distance_control={args.distance_control}"
    )


def run_robot_control_demo(args):
    """Run posture preview plus optional robot steering and distance control."""
    apply_robot_run_mode(args)
    if args.run_mode == "full":
        from .tracking_app import run_full_tracking_demo

        run_full_tracking_demo(args)
        return

    control_factory = build_robot_controller if args.robot_control_enabled else None
    run_posture_demo(
        args,
        control_factory=control_factory,
        start_label="Raspbot posture demo started.",
        window_title="Raspbot posture demo",
        summary_printer=print_control_summary,
    )
