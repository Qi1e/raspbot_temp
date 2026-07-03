#!/usr/bin/env python3
# coding: utf-8
"""Posture target tracking demo with conservative pan/tilt and chassis control.

This demo reuses the existing ``raspbot_posture`` pipeline:

- camera capture
- MediaPipe Pose inference worker
- HumanTarget output from AnalysisState
- MJPEG preview

The extra control loop is intentionally slow and conservative. It uses pan/tilt
servos first, then sends short chassis pulses only when the pan servo stays far
from center. This avoids repeating old correction commands when Pose inference
is delayed on the Raspberry Pi.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp


THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
DEFAULT_POSTURE_PATH = PROJECT_ROOT / "Raspbot_Base" / "raspbot_temp"
DEFAULT_PI_RASPBOT_PATH = Path("/home/pi/project_demo/raspbot")


def add_import_path(path: Path) -> None:
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


for posture_path in (
    Path(os.environ["RASPBOT_POSTURE_PATH"]) if "RASPBOT_POSTURE_PATH" in os.environ else None,
    DEFAULT_POSTURE_PATH,
    Path("/home/pi/Raspbot_Base/raspbot_temp"),
    Path("/home/pi/project_demo/raspbot_temp"),
):
    if posture_path is not None and posture_path.exists():
        add_import_path(posture_path)

from raspbot_posture.camera import open_camera
from raspbot_posture.inference import start_inference_worker
from raspbot_posture.model_paths import ensure_pose_model_available
from raspbot_posture.preview import start_preview_server
from raspbot_posture.rendering import draw_label, draw_tracking_target
from raspbot_posture.state import AnalysisState, FpsMeter, FrameMailbox


@dataclass
class SmoothedTarget:
    detected: bool = False
    x: float = 0.5
    y: float = 0.5
    area: float = 0.0
    confidence: float = 0.0
    posture: str = "No person"
    updated_at: float = 0.0


class TargetFilter:
    """Exponential smoother for HumanTarget values."""

    def __init__(self, smoothing: float, min_confidence: float):
        self.smoothing = max(0.0, min(0.98, float(smoothing)))
        self.min_confidence = float(min_confidence)
        self.value = SmoothedTarget()
        self.initialized = False

    def update(self, target) -> SmoothedTarget:
        if not target.detected or target.confidence < self.min_confidence:
            return self.value

        alpha_old = self.smoothing if self.initialized else 0.0
        alpha_new = 1.0 - alpha_old

        self.value = SmoothedTarget(
            detected=True,
            x=self.value.x * alpha_old + target.center_x * alpha_new,
            y=self.value.y * alpha_old + target.center_y * alpha_new,
            area=self.value.area * alpha_old + target.area * alpha_new,
            confidence=target.confidence,
            posture=target.posture,
            updated_at=target.updated_at,
        )
        self.initialized = True
        return self.value


class RobotDriver:
    """Small wrapper around the source Raspbot_Lib API.

    Motor ids and signed Ctrl_Muto behavior follow the original Raspbot_Lib.py.
    Rotation motor patterns follow the source McLumk_Wheel_Sports.py:

    - rotate left:  motors 0,1 backward; motors 2,3 forward
    - rotate right: motors 0,1 forward;  motors 2,3 backward
    """

    def __init__(self, args):
        self.args = args
        self.dry_run = bool(args.dry_run_control)
        self.debug = bool(args.control_debug)
        self.pan_angle = float(args.pan_center)
        self.tilt_angle = float(args.tilt_center)
        self.last_motor_speeds = None
        self.last_servo_angles = {}
        self.bot = None

        if not self.dry_run:
            self.bot = self._load_bot(args.robot_lib_path)

        self.set_servo(1, self.pan_angle, reason="startup pan")
        self.set_servo(2, self.tilt_angle, reason="startup tilt")

    def _load_bot(self, robot_lib_path: str):
        paths = [Path(robot_lib_path), DEFAULT_PI_RASPBOT_PATH, PROJECT_ROOT / "Raspbot_Base"]
        for path in paths:
            if path.exists():
                add_import_path(path)

        try:
            from Raspbot_Lib import Raspbot
        except ImportError as exc:
            raise RuntimeError(
                "Could not import Raspbot_Lib. Run with --dry-run-control on non-Raspberry Pi "
                "machines, or set --robot-lib-path to the folder containing Raspbot_Lib.py."
            ) from exc
        return Raspbot()

    def log(self, message: str) -> None:
        if self.debug or self.dry_run:
            print(message)

    def set_servo(self, servo_id: int, angle: float, reason: str = "") -> None:
        if servo_id == 1:
            angle = max(self.args.pan_min, min(self.args.pan_max, angle))
            self.pan_angle = angle
        elif servo_id == 2:
            angle = max(self.args.tilt_min, min(self.args.tilt_max, angle))
            self.tilt_angle = angle
        else:
            return

        rounded = int(round(angle))
        if self.last_servo_angles.get(servo_id) == rounded:
            return
        self.last_servo_angles[servo_id] = rounded

        self.log(f"servo {servo_id} -> {angle:.1f} {reason}".rstrip())
        if self.bot is not None:
            self.bot.Ctrl_Servo(servo_id, rounded)

    def set_motor_speeds(self, m0: int, m1: int, m2: int, m3: int, reason: str = "") -> None:
        speeds = [self._clamp_speed(m0), self._clamp_speed(m1), self._clamp_speed(m2), self._clamp_speed(m3)]
        if self.last_motor_speeds == speeds:
            return
        self.last_motor_speeds = speeds

        self.log(f"motors {speeds} {reason}".rstrip())
        if self.bot is not None:
            for motor_id, speed in enumerate(speeds):
                self.bot.Ctrl_Muto(motor_id, speed)

    def _clamp_speed(self, speed: int) -> int:
        return max(-255, min(255, int(speed)))

    def stop(self) -> None:
        self.set_motor_speeds(0, 0, 0, 0, reason="stop")

    def pulse_turn(self, direction: str, speed: int, duration: float) -> None:
        if self.args.invert_body_turn:
            direction = "right" if direction == "left" else "left"

        speed = abs(int(speed))
        if direction == "left":
            self.set_motor_speeds(-speed, -speed, speed, speed, reason="turn left pulse")
        else:
            self.set_motor_speeds(speed, speed, -speed, -speed, reason="turn right pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def pulse_forward(self, speed: int, duration: float) -> None:
        speed = abs(int(speed))
        self.set_motor_speeds(speed, speed, speed, speed, reason="forward pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def pulse_backward(self, speed: int, duration: float) -> None:
        speed = -abs(int(speed))
        self.set_motor_speeds(speed, speed, speed, speed, reason="backward pulse")
        time.sleep(max(0.0, duration))
        self.stop()

    def reset_servos(self) -> None:
        self.set_servo(1, self.args.pan_center, reason="reset pan")
        self.set_servo(2, self.args.tilt_rest, reason="reset tilt")


class PostureRobotController:
    """Conservative controller using HumanTarget snapshots."""

    ACTION_POSTURES = {"Squat or sit", "Arms up", "T pose", "Leaning left", "Leaning right"}

    def __init__(self, args, analysis_state: AnalysisState, stop_event: threading.Event):
        self.args = args
        self.analysis_state = analysis_state
        self.stop_event = stop_event
        self.driver = RobotDriver(args)
        self.filter = TargetFilter(args.target_smoothing, args.target_min_confidence)
        self.last_servo_update = 0.0
        self.last_body_pulse = 0.0
        self.last_log = 0.0
        self.pan_offset_started_at = None
        self.standing_started_at = None
        self.action_freeze_until = 0.0

    def start(self) -> threading.Thread:
        worker = threading.Thread(target=self.loop, name="posture-robot-control")
        worker.daemon = True
        worker.start()
        return worker

    def loop(self) -> None:
        print("Robot control loop started.")
        try:
            while not self.stop_event.is_set():
                self.step()
                time.sleep(max(0.02, self.args.control_interval))
        finally:
            self.driver.stop()
            if self.args.reset_servo_on_exit:
                self.driver.reset_servos()

    def step(self) -> None:
        now = time.time()
        analysis = self.analysis_state.get()
        target = analysis.target
        smoothed = self.filter.update(target)

        if self.target_is_stale(target, now):
            self.driver.stop()
            if self.args.return_center_on_lost:
                self.return_servos_to_center(now)
            self.debug_status(now, "target stale/lost", smoothed, analysis)
            return

        self.update_action_freeze(now, analysis, target)
        self.update_pan_tilt(now, smoothed)
        self.update_body_turn(now)
        self.update_distance(now, smoothed, analysis)
        self.debug_status(now, "tracking", smoothed, analysis)

    def target_is_stale(self, target, now: float) -> bool:
        if not target.detected:
            return True
        if target.confidence < self.args.target_min_confidence:
            return True
        return now - target.updated_at > self.args.target_timeout

    def update_action_freeze(self, now: float, analysis, target) -> None:
        squat = analysis.actions.get("squat") if analysis.actions else None
        action_active = target.posture in self.ACTION_POSTURES
        action_active = action_active or (squat is not None and (squat.active or squat.stage == "down"))

        if action_active and self.args.freeze_during_action:
            self.action_freeze_until = now + self.args.action_freeze_time

        if target.posture == "Standing":
            if self.standing_started_at is None:
                self.standing_started_at = now
        else:
            self.standing_started_at = None

    def update_pan_tilt(self, now: float, target: SmoothedTarget) -> None:
        if now - self.last_servo_update < self.args.servo_interval:
            return

        moved = False
        err_x = target.x - 0.5
        err_y = target.y - 0.5

        if abs(err_x) > self.args.pan_deadzone:
            # Source demos decrease servo-1 angle when the target is on image right.
            direction = -1 if err_x > 0 else 1
            if self.args.invert_pan:
                direction *= -1
            step = min(self.args.servo_step, abs(err_x) * self.args.servo_gain)
            self.driver.set_servo(1, self.driver.pan_angle + direction * step, reason="pan tracking")
            moved = True

        if abs(err_y) > self.args.tilt_deadzone:
            # Source demos decrease servo-2 angle when the target is lower in image.
            direction = -1 if err_y > 0 else 1
            if self.args.invert_tilt:
                direction *= -1
            step = min(self.args.servo_step, abs(err_y) * self.args.servo_gain)
            self.driver.set_servo(2, self.driver.tilt_angle + direction * step, reason="tilt tracking")
            moved = True

        if moved:
            self.last_servo_update = now

    def update_body_turn(self, now: float) -> None:
        pan_offset = self.driver.pan_angle - self.args.pan_center
        if abs(pan_offset) < self.args.pan_body_threshold:
            self.pan_offset_started_at = None
            return

        if self.pan_offset_started_at is None:
            self.pan_offset_started_at = now
            return

        if now - self.pan_offset_started_at < self.args.pan_body_hold:
            return
        if now - self.last_body_pulse < self.args.body_cooldown:
            return

        direction = "left" if pan_offset > 0 else "right"
        self.driver.pulse_turn(direction, self.args.body_turn_speed, self.args.body_pulse)
        self.last_body_pulse = time.time()
        self.pan_offset_started_at = self.last_body_pulse

    def update_distance(self, now: float, target: SmoothedTarget, analysis) -> None:
        if not self.args.distance_control:
            return
        if self.args.freeze_during_action and now < self.action_freeze_until:
            return
        if self.standing_started_at is None:
            return
        if now - self.standing_started_at < self.args.distance_stable_time:
            return
        if now - self.last_body_pulse < self.args.body_cooldown:
            return
        if abs(target.x - 0.5) > self.args.distance_x_deadzone:
            return

        if target.area < self.args.target_area_min:
            self.driver.pulse_forward(self.args.body_forward_speed, self.args.body_pulse)
            self.last_body_pulse = time.time()
        elif target.area > self.args.target_area_max:
            self.driver.pulse_backward(self.args.body_backward_speed, self.args.body_pulse)
            self.last_body_pulse = time.time()

    def return_servos_to_center(self, now: float) -> None:
        if now - self.last_servo_update < self.args.servo_interval:
            return

        moved = False
        if abs(self.driver.pan_angle - self.args.pan_center) > 0.5:
            delta = self.args.servo_step if self.driver.pan_angle < self.args.pan_center else -self.args.servo_step
            self.driver.set_servo(1, self.driver.pan_angle + delta, reason="lost target center pan")
            moved = True
        if abs(self.driver.tilt_angle - self.args.tilt_center) > 0.5:
            delta = self.args.servo_step if self.driver.tilt_angle < self.args.tilt_center else -self.args.servo_step
            self.driver.set_servo(2, self.driver.tilt_angle + delta, reason="lost target center tilt")
            moved = True
        if moved:
            self.last_servo_update = now

    def debug_status(self, now: float, label: str, target: SmoothedTarget, analysis) -> None:
        if not self.args.control_debug:
            return
        if now - self.last_log < self.args.control_log_interval:
            return
        self.last_log = now
        print(
            f"{label}: x={target.x:.3f} y={target.y:.3f} area={target.area:.3f} "
            f"conf={target.confidence:.2f} posture={analysis.posture} "
            f"pan={self.driver.pan_angle:.1f} tilt={self.driver.tilt_angle:.1f}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Raspbot posture tracking with tunable robot control")

    # Existing posture/preview runtime knobs.
    parser.add_argument("--source", default="0", help="camera source, usually 0")
    parser.add_argument("--width", type=int, default=640, help="camera width")
    parser.add_argument("--height", type=int, default=480, help="camera height")
    parser.add_argument("--mirror", action="store_true", help="mirror camera image horizontally")
    parser.add_argument("--view-img", action="store_true", help="show local OpenCV window")
    parser.add_argument("--no-preview", action="store_true", help="disable web preview")
    parser.add_argument("--preview-host", default="0.0.0.0", help="preview server bind host")
    parser.add_argument("--preview-port", type=int, default=8080, help="preview server port")
    parser.add_argument("--preview-quality", type=int, default=65, help="preview JPEG quality 1-100")
    parser.add_argument("--preview-width", type=int, default=480, help="preview max width, 0 keeps original size")
    parser.add_argument("--preview-fps", type=float, default=8, help="preview max FPS, 0 disables throttling")
    parser.add_argument("--model-complexity", type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--inference-fps", type=float, default=8.0, help="pose inference FPS cap")
    parser.add_argument("--draw-landmarks", action="store_true", help="draw MediaPipe landmarks")
    parser.add_argument("--no-target-box", action="store_true", help="hide target box")
    parser.add_argument("--min-detection-confidence", type=float, default=0.5)
    parser.add_argument("--min-tracking-confidence", type=float, default=0.5)
    parser.add_argument("--min-visibility", type=float, default=0.55)
    parser.add_argument("--squat-stable-frames", type=int, default=1)
    parser.add_argument("--squat-down-frames", type=int, default=None)
    parser.add_argument("--squat-up-frames", type=int, default=None)
    parser.add_argument("--squat-down-angle", type=float, default=145.0)
    parser.add_argument("--squat-up-angle", type=float, default=155.0)
    parser.add_argument("--squat-cooldown", type=float, default=0.35)

    # Robot control switch and hardware access.
    parser.add_argument("--no-robot-control", action="store_true", help="run posture preview without robot control")
    parser.add_argument("--dry-run-control", action="store_true", help="print robot commands without touching hardware")
    parser.add_argument("--control-debug", action="store_true", help="print target and control decisions")
    parser.add_argument("--control-log-interval", type=float, default=0.5)
    parser.add_argument("--robot-lib-path", default="/home/pi/project_demo/raspbot")

    # Target filtering and safety.
    parser.add_argument("--control-interval", type=float, default=0.05)
    parser.add_argument("--target-smoothing", type=float, default=0.72)
    parser.add_argument("--target-timeout", type=float, default=0.65)
    parser.add_argument("--target-min-confidence", type=float, default=0.55)

    # Servo controls.
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

    # Chassis pulse controls.
    parser.add_argument("--body-turn-speed", type=int, default=10)
    parser.add_argument("--body-forward-speed", type=int, default=12)
    parser.add_argument("--body-backward-speed", type=int, default=10)
    parser.add_argument("--body-pulse", type=float, default=0.15)
    parser.add_argument("--body-cooldown", type=float, default=0.50)
    parser.add_argument("--pan-body-threshold", type=float, default=22.0)
    parser.add_argument("--pan-body-hold", type=float, default=0.55)
    parser.add_argument("--invert-body-turn", action="store_true")

    # Distance and exercise protection.
    parser.add_argument("--distance-control", action="store_true", help="allow slow forward/back pulses")
    parser.add_argument("--target-area-min", type=float, default=0.12)
    parser.add_argument("--target-area-max", type=float, default=0.28)
    parser.add_argument("--distance-stable-time", type=float, default=0.8)
    parser.add_argument("--distance-x-deadzone", type=float, default=0.12)
    parser.add_argument("--freeze-during-action", dest="freeze_during_action", action="store_true")
    parser.add_argument("--no-freeze-during-action", dest="freeze_during_action", action="store_false")
    parser.add_argument("--action-freeze-time", type=float, default=0.9)

    return parser


def print_control_summary(args) -> None:
    if args.no_robot_control:
        print("Robot control disabled.")
        return
    print(
        "Robot control enabled: "
        f"dry_run={args.dry_run_control}, pan_deadzone={args.pan_deadzone}, "
        f"tilt_deadzone={args.tilt_deadzone}, servo_step={args.servo_step}, "
        f"body_turn_speed={args.body_turn_speed}, body_pulse={args.body_pulse}, "
        f"body_cooldown={args.body_cooldown}, distance_control={args.distance_control}"
    )


def run(args) -> None:
    args.inference_fps = max(0.0, float(args.inference_fps))
    source = int(args.source) if str(args.source).isdigit() else args.source

    ensure_pose_model_available(args.model_complexity)
    camera = open_camera(source, args.width, args.height)
    preview_state, preview_server = None, None

    if not args.no_preview:
        preview_state, preview_server = start_preview_server(
            args.preview_host,
            args.preview_port,
            args.preview_quality,
            args.preview_width,
            args.preview_fps,
        )

    mailbox = FrameMailbox()
    analysis_state = AnalysisState()
    stop_event = threading.Event()
    inference_worker = start_inference_worker(args, mailbox, analysis_state, stop_event)
    control_worker = None
    camera_fps_meter = FpsMeter()

    drawing = None
    drawing_styles = None
    if args.draw_landmarks:
        drawing = mp.solutions.drawing_utils
        drawing_styles = mp.solutions.drawing_styles

    inference_interval = 0.0 if args.inference_fps <= 0 else 1.0 / args.inference_fps
    next_inference_at = 0.0

    print(
        "Posture robot control demo started. "
        f"Inference cap: {args.inference_fps:.1f} FPS. Press Ctrl+C to stop."
    )
    print_control_summary(args)

    try:
        if not args.no_robot_control:
            control_worker = PostureRobotController(args, analysis_state, stop_event).start()

        while True:
            ret, frame = camera.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            if args.mirror:
                frame = cv2.flip(frame, 1)

            now = time.time()
            if inference_interval == 0.0 or now >= next_inference_at:
                mailbox.submit(frame)
                next_inference_at = now + inference_interval

            analysis = analysis_state.get()
            if args.draw_landmarks and analysis.landmarks:
                drawing.draw_landmarks(
                    frame,
                    analysis.landmarks,
                    mp.solutions.pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
                )

            if not args.no_target_box:
                draw_tracking_target(frame, analysis.target)

            draw_label(frame, analysis, camera_fps_meter.tick())

            if preview_state:
                preview_state.publish(frame)

            if args.view_img:
                cv2.imshow("Raspbot posture robot control demo", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        print("\nStopping posture robot control demo...")
    finally:
        stop_event.set()
        mailbox.close()
        inference_worker.join(timeout=2.0)
        if control_worker:
            control_worker.join(timeout=2.0)
        camera.release()
        if preview_server:
            preview_server.shutdown()
        if args.view_img:
            cv2.destroyAllWindows()


def main() -> None:
    parser = build_parser()
    run(parser.parse_args())


if __name__ == "__main__":
    main()
