#!/usr/bin/env python3
# coding: utf-8
"""Demo for synchronized camera pan/tilt and chassis follow control."""

import argparse
import time
from dataclasses import dataclass

from raspbot_posture.cli import add_posture_arguments
from raspbot_posture.distance_features import extract_distance_features
from raspbot_posture.tracking_control import (
    DistancePlanner,
    MotionGoal,
    clamp,
    distance_input_from_tracking,
    mix_translation_yaw,
    yaw_from_tracking,
)
from raspbot_posture.tracking_driver import TrackingRobotDriver
from raspbot_posture.tracking_estimator import TargetPoseConfig, TargetTrackingInputBuilder
from raspbot_posture.tracking_log import TrackingLogger


@dataclass(frozen=True)
class TrackingFrame:
    tracking: object
    posture: str
    action_active: bool
    updated_at: float


def format_distance_m(distance_m):
    if distance_m is None:
        return "unknown"
    return f"{distance_m:.2f} m"


class SimulatedVisionInputProvider:
    """Estimator input source for repeatable dry-run tests."""

    def __init__(self, args):
        self.started_at = time.time()
        self.args = args
        config = TargetPoseConfig(
            desired_min_distance=args.desired_min_distance,
            desired_max_distance=args.desired_max_distance,
            desired_distance=args.desired_distance,
            max_reasonable_distance=args.max_reasonable_distance,
            min_confidence=args.estimator_min_confidence,
            pan_center=args.pan_center,
            tilt_center=args.tilt_center,
            body_turn_pan_deadzone=args.body_yaw_deadband_degrees,
            horizontal_fov_degrees=args.horizontal_fov_degrees,
            vertical_fov_degrees=args.vertical_fov_degrees,
        )
        self.builder = TargetTrackingInputBuilder(config)

    def read(self, pan_angle, tilt_angle):
        now = time.time()
        elapsed = now - self.started_at
        center_x = self.args.center_x
        center_y = self.args.center_y
        area = self.args.area
        shoulder_width = self.args.shoulder_width
        torso_height = self.args.torso_height

        if self.args.simulate_changes:
            center_x = 0.5 + (self.args.center_x - 0.5) * math.cos(elapsed * 0.7)
            center_y = 0.5 + (self.args.center_y - 0.5) * math.cos(elapsed * 0.5)
            area = max(0.001, self.args.area * (1.0 + 0.18 * math.sin(elapsed * 0.35)))
            shoulder_width = max(0.001, self.args.shoulder_width * (1.0 + 0.08 * math.sin(elapsed * 0.35)))
            torso_height = max(0.001, self.args.torso_height * (1.0 + 0.08 * math.sin(elapsed * 0.35)))

        center_x = center_x + (float(pan_angle) - self.args.pan_center) / self.args.horizontal_fov_degrees
        center_y = center_y + (float(tilt_angle) - self.args.tilt_center) / self.args.vertical_fov_degrees
        center_x = clamp(center_x, 0.0, 1.0)
        center_y = clamp(center_y, 0.0, 1.0)

        tracking = self.builder.from_features(
            detected=not self.args.target_lost,
            area=area,
            center_x=center_x,
            center_y=center_y,
            confidence=self.args.confidence,
            visible_mode=self.args.visible_mode,
            shoulder_width=shoulder_width,
            torso_height=torso_height,
            tilt_angle=tilt_angle,
            pan_angle=pan_angle,
        )
        return TrackingFrame(
            tracking=tracking,
            posture=self.args.posture,
            action_active=self.args.action_active,
            updated_at=now,
        )

    def release(self):
        pass

    def should_stop(self):
        return False


class CameraVisionInputProvider:
    """Live camera input source for tracking feasibility tests."""

    def __init__(self, args):
        import cv2
        import mediapipe as mp

        from raspbot_posture.actions import build_action_registry
        from raspbot_posture.camera import open_camera
        from raspbot_posture.geometry import build_human_target
        from raspbot_posture.model_paths import ensure_pose_model_available
        from raspbot_posture.rendering import draw_tracking_target
        from raspbot_posture.state import HumanTarget
        from raspbot_posture.vision import PostureClassifier

        self.args = args
        self.cv2 = cv2
        self.mp = mp
        self.build_human_target = build_human_target
        self.draw_tracking_target = draw_tracking_target
        self.extract_calibration_features = extract_distance_features
        self.human_target_type = HumanTarget
        self.stop_requested = False
        self.last_human_target = HumanTarget(updated_at=time.time())
        self.last_landmarks = None
        self.last_frame = None
        self.last_tracking_frame = None
        self.preview_state = None
        self.preview_server = None
        self.camera = None
        self.pose = None

        config = TargetPoseConfig(
            desired_min_distance=args.desired_min_distance,
            desired_max_distance=args.desired_max_distance,
            desired_distance=args.desired_distance,
            max_reasonable_distance=args.max_reasonable_distance,
            min_confidence=args.estimator_min_confidence,
            pan_center=args.pan_center,
            tilt_center=args.tilt_center,
            body_turn_pan_deadzone=args.body_yaw_deadband_degrees,
            horizontal_fov_degrees=args.horizontal_fov_degrees,
            vertical_fov_degrees=args.vertical_fov_degrees,
        )
        self.builder = TargetTrackingInputBuilder(config)

        try:
            ensure_pose_model_available(args.model_complexity)
            source = int(args.source) if str(args.source).isdigit() else args.source
            self.camera = open_camera(source, args.width, args.height)
            self.classifier = PostureClassifier(min_visibility=args.min_visibility)
            self.action_registry = build_action_registry(args)
            self.pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=args.model_complexity,
                smooth_landmarks=True,
                min_detection_confidence=args.min_detection_confidence,
                min_tracking_confidence=args.min_tracking_confidence,
            )
            self.inference_interval = 0.0 if args.inference_fps <= 0.0 else 1.0 / float(args.inference_fps)
            self.next_inference_at = 0.0

            if not args.no_preview:
                from raspbot_posture.preview import start_preview_server

                self.preview_state, self.preview_server = start_preview_server(
                    args.preview_host,
                    args.preview_port,
                    args.preview_quality,
                    args.preview_width,
                    args.preview_fps,
                )
        except Exception:
            self.release()
            raise

    def read(self, pan_angle, tilt_angle):
        ok, frame = self.camera.read()
        now = time.time()
        if not ok or frame is None:
            time.sleep(0.02)
            if self.last_tracking_frame is not None:
                return self.last_tracking_frame
            return self._empty_tracking_frame(pan_angle, tilt_angle, now)

        if self.args.mirror:
            frame = self.cv2.flip(frame, 1)
        self.last_frame = frame

        if now >= self.next_inference_at:
            self.next_inference_at = now + self.inference_interval
            self.last_tracking_frame = self._process_frame(frame, pan_angle, tilt_angle, now)

        if self.last_tracking_frame is None:
            self.last_tracking_frame = self._empty_tracking_frame(pan_angle, tilt_angle, now)

        self._publish_preview(frame, self.last_tracking_frame)
        return self.last_tracking_frame

    def _empty_tracking_frame(self, pan_angle, tilt_angle, now):
        tracking = self.builder.from_features(
            detected=False,
            area=0.0,
            center_x=0.5,
            center_y=0.5,
            confidence=0.0,
            visible_mode="lost",
            shoulder_width=0.0,
            torso_height=0.0,
            tilt_angle=tilt_angle,
            pan_angle=pan_angle,
        )
        self.last_human_target = self.human_target_type(updated_at=now)
        self.last_landmarks = None
        return TrackingFrame(
            tracking=tracking,
            posture="No person",
            action_active=False,
            updated_at=now,
        )

    def _process_frame(self, frame, pan_angle, tilt_angle, now):
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.pose.process(rgb)
        rgb.flags.writeable = True

        if not results.pose_landmarks:
            return self._empty_tracking_frame(pan_angle, tilt_angle, now)

        landmarks = results.pose_landmarks.landmark
        metrics = self.classifier.measure(landmarks)
        posture, _ = self.classifier.classify(metrics)
        human_target = self.build_human_target(landmarks, posture, self.args.min_visibility)
        features = self.extract_calibration_features(landmarks, human_target, posture, self.args.min_visibility)
        actions = self.action_registry.update(metrics, posture, human_target)
        action_active = any(status.active for status in actions.values())

        self.last_human_target = human_target
        self.last_landmarks = results.pose_landmarks if self.args.draw_landmarks else None
        tracking = self.builder.from_features(
            detected=human_target.detected,
            area=human_target.area,
            center_x=human_target.center_x,
            center_y=human_target.center_y,
            confidence=features["confidence"],
            visible_mode=features["visible_mode"],
            shoulder_width=features["shoulder_width"],
            torso_height=features["torso_height"],
            tilt_angle=tilt_angle,
            pan_angle=pan_angle,
        )
        return TrackingFrame(
            tracking=tracking,
            posture=posture,
            action_active=action_active,
            updated_at=now,
        )

    def _publish_preview(self, frame, tracking_frame):
        if self.preview_state is None and not self.args.view_img:
            return

        preview_frame = frame.copy()
        if self.last_landmarks is not None:
            self.mp.solutions.drawing_utils.draw_landmarks(
                preview_frame,
                self.last_landmarks,
                self.mp.solutions.pose.POSE_CONNECTIONS,
            )
        if not self.args.no_target_box:
            self.draw_tracking_target(preview_frame, self.last_human_target)
        self._draw_overlay(preview_frame, tracking_frame)

        if self.preview_state is not None:
            self.preview_state.publish(preview_frame)
        if self.args.view_img:
            self.cv2.imshow("distance control tracking", preview_frame)
            if self.cv2.waitKey(1) & 0xFF == ord("q"):
                self.stop_requested = True

    def _draw_overlay(self, frame, tracking_frame):
        tracking = tracking_frame.tracking
        distance_text = format_distance_m(tracking.distance_m)
        if self.args.tracking_mode == "camera":
            move_text = "disabled (camera tracking only)"
            move_allowed = 0
        else:
            move_text = f"{tracking.chassis_motion_direction} @ {tracking.chassis_direction_degrees:.0f} deg"
            move_allowed = int(tracking.motion_allowed)
        camera_text = f"pan {tracking.camera_pan_direction}, tilt {tracking.camera_tilt_direction}"
        body_text = f"{tracking.body_turn_direction} ({tracking.body_yaw_error_degrees:.1f} deg)"
        text = [
            f"Distance: {distance_text}  State: {tracking.distance_state}  Confidence: {tracking.confidence:.2f}",
            f"Move direction: {move_text}  Allowed: {move_allowed}",
            f"Camera direction: {camera_text}  Body turn: {body_text}",
            f"Posture: {tracking_frame.posture}  Action: {int(tracking_frame.action_active)}  {tracking.reason}",
        ]
        self.cv2.rectangle(frame, (10, 10), (min(frame.shape[1] - 10, 760), 126), (16, 19, 22), -1)
        y = 36
        for line in text:
            self.cv2.putText(
                frame,
                line[:92],
                (20, y),
                self.cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (230, 240, 245),
                2,
            )
            y += 28

    def release(self):
        if self.pose is not None:
            self.pose.close()
        if self.camera is not None:
            self.camera.release()
        if self.preview_server is not None:
            self.preview_server.shutdown()
        if self.args.view_img:
            self.cv2.destroyAllWindows()
            for _ in range(3):
                self.cv2.waitKey(1)

    def should_stop(self):
        return self.stop_requested


def build_parser():
    parser = argparse.ArgumentParser(description="Synchronized pan/tilt and chassis tracking demo")
    parser.add_argument("--input-mode", choices=["sim", "camera"], default="sim")
    parser.add_argument(
        "--tracking-mode",
        choices=["camera", "full"],
        default="full",
        help="camera: pan/tilt tracking only; full: pan/tilt plus chassis yaw and distance motion",
    )
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--control-interval", type=float, default=0.05)
    parser.add_argument("--plan-interval", type=float, default=1.5)
    parser.add_argument("--max-input-age", type=float, default=0.4)
    parser.add_argument("--min-confidence", type=float, default=0.3)
    parser.add_argument("--servo-idle-required", type=float, default=0.4)

    parser.add_argument("--center-x", type=float, default=0.35)
    parser.add_argument("--center-y", type=float, default=0.48)
    parser.add_argument("--area", type=float, default=0.08)
    parser.add_argument("--shoulder-width", type=float, default=0.18)
    parser.add_argument("--torso-height", type=float, default=0.38)
    parser.add_argument("--visible-mode", choices=["full_body", "upper_body", "partial_body", "lost"], default="full_body")
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--target-lost", action="store_true")
    parser.add_argument("--posture", default="Standing")
    parser.add_argument("--action-active", action="store_true", help="simulate squat/gesture activity blocking motion")
    parser.add_argument("--simulate-changes", action="store_true")

    parser.add_argument("--desired-min-distance", type=float, default=0.8)
    parser.add_argument("--desired-max-distance", type=float, default=1.2)
    parser.add_argument("--desired-distance", type=float, default=1.0)
    parser.add_argument(
        "--max-reasonable-distance",
        type=float,
        default=10.0,
        help="discard distance estimates above this many meters; set <=0 to disable",
    )
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
    parser.add_argument(
        "--body-yaw-screen-gate-degrees",
        type=float,
        default=3.0,
        help="hold body yaw when screen pan error beyond this and pan offset asks for the opposite turn; <=0 disables",
    )
    parser.add_argument("--max-yaw-speed", type=float, default=3.5)
    parser.add_argument("--max-wheel-speed", type=int, default=255)

    parser.add_argument("--pan-center", type=float, default=90.0)
    parser.add_argument("--tilt-center", type=float, default=50.0)
    parser.add_argument("--pan-min", type=float, default=20.0)
    parser.add_argument("--pan-max", type=float, default=160.0)
    parser.add_argument("--tilt-min", type=float, default=0.0)
    parser.add_argument("--tilt-max", type=float, default=100.0)
    parser.add_argument("--horizontal-fov-degrees", type=float, default=62.0)
    parser.add_argument("--vertical-fov-degrees", type=float, default=49.0)
    parser.add_argument("--camera-pan-deadband-degrees", type=float, default=3.0)
    parser.add_argument("--camera-tilt-deadband-degrees", type=float, default=3.0)
    parser.add_argument("--camera-servo-step", type=float, default=1.0)
    parser.add_argument("--camera-servo-gain", type=float, default=0.16)
    parser.add_argument(
        "--yaw-servo-compensation-gain",
        type=float,
        default=0.5,
        help="pan feed-forward gain in degrees per yaw-speed unit per second; set 0 to disable",
    )
    parser.add_argument(
        "--yaw-servo-compensation-max-step",
        type=float,
        default=0.6,
        help="max pan feed-forward degrees added per servo update",
    )
    parser.add_argument(
        "--yaw-servo-compensation-deadband",
        type=float,
        default=0.5,
        help="ignore yaw-speed commands smaller than this absolute value",
    )
    parser.add_argument(
        "--yaw-servo-compensation-sign",
        type=int,
        choices=[-1, 1],
        default=-1,
        help="-1 means pan moves opposite positive yaw; use 1 if the real car compensation is reversed",
    )
    parser.add_argument("--servo-interval", type=float, default=0.15)
    parser.add_argument("--allow-yaw-during-action", action="store_true")

    parser.add_argument("--log-dir", default="", help="write run args JSON and control CSV logs into this directory")
    parser.add_argument("--log-prefix", default="tracking", help="prefix for generated log files")
    parser.add_argument("--log-interval", type=float, default=0.05, help="minimum seconds between logged control rows")
    parser.add_argument("--print-motors", action="store_true", help="print every wheel-speed command for debugging")

    parser.add_argument("--i2c-bus", type=int, default=1)
    parser.add_argument("--live", action="store_true")
    return add_posture_arguments(parser)


def build_input_provider(args):
    if args.input_mode == "camera":
        return CameraVisionInputProvider(args)
    return SimulatedVisionInputProvider(args)


def main():
    args = build_parser().parse_args()
    provider = None
    driver = None
    logger = None

    try:
        logger = TrackingLogger(args)
        provider = build_input_provider(args)
        planner = DistancePlanner(args)
        driver = TrackingRobotDriver(live=args.live, i2c_bus=args.i2c_bus, print_motors=args.print_motors)
        driver.configure_servos(args.pan_center, args.tilt_center)
        started_at = time.time()
        interval = max(0.02, args.control_interval)

        print(
            f"{'LIVE' if args.live else 'DRY-RUN'} {args.input_mode}/{args.tracking_mode}: "
            f"plan_interval={args.plan_interval:.2f}s "
            f"control_interval={interval:.2f}s"
        )

        while time.time() - started_at < args.duration and not provider.should_stop():
            now = time.time()
            tracking_frame = provider.read(driver.pan_angle, driver.tilt_angle)
            tracking = tracking_frame.tracking
            yaw_decision = yaw_from_tracking(tracking, args, now, tracking_frame.action_active)
            yaw_speed = yaw_decision.speed
            servo_update = driver.update_camera(tracking, args, now, yaw_speed=yaw_speed)
            sample = distance_input_from_tracking(
                tracking,
                servo_idle_s=driver.servo_idle_s(now),
                posture=tracking_frame.posture,
                action_active=tracking_frame.action_active,
                updated_at=tracking_frame.updated_at,
            )
            if args.tracking_mode == "camera":
                goal = MotionGoal(active=False, reason="camera tracking only")
            else:
                goal = planner.update(sample, now)

            move_speed = 0.0
            direction = 90.0
            if goal.active and now < goal.expires_at:
                move_speed = goal.speed
                direction = goal.direction_degrees

            wheels = mix_translation_yaw(move_speed, direction, yaw_speed, max_speed=args.max_wheel_speed)
            driver.set_wheel_speeds(
                wheels,
                reason=(
                    f"move={move_speed:.1f}@{direction:.1f} "
                    f"yaw={yaw_speed:.1f} pan_err={tracking.pan_error_degrees:.1f} "
                    f"body_err={tracking.body_yaw_error_degrees:.1f} "
                    f"dist={tracking.distance_m} state={tracking.distance_state} "
                    f"posture={sample.posture} yaw_reason={yaw_decision.reason}"
                ),
            )
            logger.maybe_log(
                now,
                started_at,
                tracking_frame,
                sample,
                goal,
                servo_update,
                yaw_decision,
                move_speed,
                direction,
                wheels,
                driver,
            )
            time.sleep(interval)
    finally:
        if driver is not None:
            driver.stop()
        if provider is not None:
            provider.release()
        if logger is not None:
            logger.close()


if __name__ == "__main__":
    main()
