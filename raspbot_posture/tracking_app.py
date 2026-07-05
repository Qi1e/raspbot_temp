"""Package runtime for full camera, workout, and synchronized tracking."""

import time
from dataclasses import dataclass
from dataclasses import replace

from .avoidance import ObstacleAvoidanceController
from .actions import build_action_registry
from .camera import open_camera
from .distance_features import extract_distance_features
from .model_paths import ensure_pose_model_available
from .output import analysis_payload
from .pose_features import PoseFeatureExtractor, classify_posture
from .preview import start_preview_server
from .recorder import JsonlRecorder
from .rendering import draw_label, draw_tracking_target
from .state import FpsMeter, ObstacleStatus, PoseAnalysis, TrackingStatus
from .tracking_control import (
    DistancePlanner,
    MotionGoal,
    YawDecision,
    distance_input_from_tracking,
    mix_translation_yaw,
    yaw_from_tracking,
)
from .tracking_driver import TrackingRobotDriver
from .tracking_estimator import TargetPoseConfig, TargetTrackingInputBuilder
from .tracking_log import TrackingLogger
from .ultrasonic import UltrasonicMonitor
from .workout import WorkoutSession, build_hyrox_program


@dataclass(frozen=True)
class TrackingFrame:
    """Vision and workout state consumed by the tracking controller."""

    analysis: PoseAnalysis
    tracking: object
    action_active: bool
    updated_at: float

    @property
    def posture(self):
        return self.analysis.posture


def _arg(args, name, default):
    return getattr(args, name, default)


def _action_active(actions):
    for status in actions.values():
        if status.active:
            return True
        if status.stage in ('down', 'pushup_down', 'pushup_up', 'stand_recovery', 'broad_jump'):
            return True
    return False


def _tracking_config(args):
    return TargetPoseConfig(
        desired_min_distance=_arg(args, 'desired_min_distance', 2.7),
        desired_max_distance=_arg(args, 'desired_max_distance', 3.3),
        desired_distance=_arg(args, 'desired_distance', 3.0),
        max_reasonable_distance=_arg(args, 'max_reasonable_distance', 10.0),
        min_confidence=_arg(args, 'estimator_min_confidence', 0.7),
        pan_center=_arg(args, 'pan_center', 90.0),
        tilt_center=_arg(args, 'tilt_center', 50.0),
        body_turn_pan_deadzone=_arg(args, 'body_yaw_deadband_degrees', 4.0),
        horizontal_fov_degrees=_arg(args, 'horizontal_fov_degrees', 62.0),
        vertical_fov_degrees=_arg(args, 'vertical_fov_degrees', 49.0),
    )


def _empty_tracking(builder, pan_angle, tilt_angle):
    return builder.from_features(
        detected=False,
        area=0.0,
        center_x=0.5,
        center_y=0.5,
        confidence=0.0,
        visible_mode='lost',
        shoulder_width=0.0,
        torso_height=0.0,
        tilt_angle=tilt_angle,
        pan_angle=pan_angle,
    )


def _tracking_status(args, tracking, frozen=False):
    return TrackingStatus(
        enabled=True,
        mode=_arg(args, 'tracking_mode', 'full'),
        reason=tracking.reason,
        distance_m=tracking.distance_m,
        distance_state=tracking.distance_state,
        pan_error_degrees=tracking.pan_error_degrees,
        tilt_error_degrees=tracking.tilt_error_degrees,
        body_yaw_error_degrees=tracking.body_yaw_error_degrees,
        chassis_motion_direction=tracking.chassis_motion_direction,
        chassis_direction_degrees=tracking.chassis_direction_degrees,
        motion_allowed=tracking.motion_allowed,
        frozen=frozen,
    )


def _obstacle_status(reading, decision, enabled):
    if decision is None:
        return ObstacleStatus(
            enabled=bool(enabled),
            raw_mm=getattr(reading, 'raw_mm', None),
            valid=getattr(reading, 'valid', False),
            phase='disabled' if not enabled else 'normal',
            reason=getattr(reading, 'reason', ''),
            updated_at=getattr(reading, 'updated_at', 0.0),
        )
    return ObstacleStatus(
        enabled=bool(enabled),
        active=decision.active,
        distance_mm=decision.distance_mm,
        raw_mm=getattr(reading, 'raw_mm', None),
        valid=getattr(reading, 'valid', False),
        phase=decision.phase,
        reason=decision.reason,
        cooldown_remaining_s=decision.cooldown_remaining_s,
        updated_at=getattr(reading, 'updated_at', 0.0),
    )


def _record_config(args):
    return {
        'source': str(args.source),
        'width': args.width,
        'height': args.height,
        'mirror': args.mirror,
        'model_complexity': args.model_complexity,
        'inference_fps': args.inference_fps,
        'record_interval': args.record_interval,
        'record_keypoints': args.record_keypoints,
        'min_visibility': args.min_visibility,
        'workout': {
            'program': args.workout_program,
            'squat_target': args.workout_squat_target,
            'lunge_target': args.workout_lunge_target,
            'burpee_target': args.workout_burpee_target,
        },
        'tracking': {
            'mode': args.tracking_mode,
            'desired_distance': _arg(args, 'desired_distance', 3.0),
            'desired_min_distance': _arg(args, 'desired_min_distance', 2.7),
            'desired_max_distance': _arg(args, 'desired_max_distance', 3.3),
        },
    }


def _process_frame(frame, pose, extractor, action_registry, workout_session, builder, recorder, args, driver, fps_meter):
    """Run one full vision/action/workout/tracking update."""
    import cv2

    started_at = time.time()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    results = pose.process(rgb)
    rgb.flags.writeable = True

    if not results.pose_landmarks:
        actions = action_registry.reset_stages()
        workout = workout_session.update(actions)
        tracking = _empty_tracking(builder, driver.pan_angle, driver.tilt_angle)
        analysis = PoseAnalysis(
            actions=actions,
            workout=workout,
            tracking=_tracking_status(args, tracking),
            inference_fps=fps_meter.tick(),
            latency_ms=(time.time() - started_at) * 1000.0,
            updated_at=time.time(),
        )
        return TrackingFrame(analysis=analysis, tracking=tracking, action_active=False, updated_at=time.time())

    landmarks = results.pose_landmarks.landmark
    features = extractor.extract(landmarks)
    posture = classify_posture(features)
    target = replace(features.target, posture=posture)
    features = replace(features, target=target)
    distance_features = extract_distance_features(landmarks, target, posture, args.min_visibility)
    actions = action_registry.update(features, posture)
    active = _action_active(actions)
    workout = workout_session.update(actions)
    recorder.record(posture, features, actions, landmarks)
    tracking = builder.from_features(
        detected=target.detected,
        area=target.area,
        center_x=target.center_x,
        center_y=target.center_y,
        confidence=distance_features['confidence'],
        visible_mode=distance_features['visible_mode'],
        shoulder_width=distance_features['shoulder_width'],
        torso_height=distance_features['torso_height'],
        tilt_angle=driver.tilt_angle,
        pan_angle=driver.pan_angle,
    )
    squat = actions.get('squat')
    analysis = PoseAnalysis(
        posture=posture,
        color=(80, 255, 80) if posture == 'Standing' else (230, 240, 245),
        squat_count=squat.count if squat else 0,
        squat_stage=squat.stage if squat else 'unknown',
        actions=actions,
        workout=workout,
        tracking=_tracking_status(args, tracking, frozen=active),
        pose_features=features,
        inference_fps=fps_meter.tick(),
        latency_ms=(time.time() - started_at) * 1000.0,
        target=target,
        landmarks=results.pose_landmarks if args.draw_landmarks else None,
        updated_at=time.time(),
    )
    return TrackingFrame(analysis=analysis, tracking=tracking, action_active=active, updated_at=analysis.updated_at)


def run_full_tracking_demo(args):
    """Run the package-level full tracking runtime used by posture_demo."""
    import cv2
    import mediapipe as mp

    args.tracking_mode = _arg(args, 'tracking_mode', 'full')
    args.live = not bool(_arg(args, 'dry_run_control', True))
    args.input_mode = 'camera'
    ensure_pose_model_available(args.model_complexity)
    source = int(args.source) if str(args.source).isdigit() else args.source
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

    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=args.model_complexity,
        smooth_landmarks=True,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )
    extractor = PoseFeatureExtractor(min_visibility=args.min_visibility)
    action_registry = build_action_registry(args)
    recorder = JsonlRecorder(
        args.record_path,
        args.record_interval,
        args.record_min_confidence,
        url=args.record_url,
        session_id=args.record_session_id,
        device_id=args.record_device_id,
        upload_batch_size=args.record_upload_batch_size,
        upload_interval=args.record_upload_interval,
        upload_queue_size=args.record_upload_queue_size,
        include_keypoints=args.record_keypoints,
    )
    recorder.start(config=_record_config(args))
    workout_session = WorkoutSession(build_hyrox_program(args), session_id=recorder.session_id)
    builder = TargetTrackingInputBuilder(_tracking_config(args))
    planner = DistancePlanner(args)
    logger = TrackingLogger(args)
    driver = TrackingRobotDriver(
        live=args.live,
        i2c_bus=_arg(args, 'i2c_bus', 1),
        print_motors=_arg(args, 'print_motors', False),
        print_servos=_arg(args, 'print_servos', False),
    )
    driver.configure_servos(args.pan_center, args.tilt_center)
    obstacle_enabled = bool(_arg(args, 'enable_obstacle_avoidance', False)) and args.tracking_mode != 'camera'
    ultrasonic = UltrasonicMonitor(
        bot=driver.bot,
        enabled=obstacle_enabled and args.live,
        poll_interval=_arg(args, 'ultrasonic_poll_interval', 0.05),
        buffer_size=_arg(args, 'ultrasonic_filter_size', 5),
    )
    avoider = ObstacleAvoidanceController(args, enabled=obstacle_enabled)
    ultrasonic.start()

    camera_fps = FpsMeter()
    inference_fps = FpsMeter()
    inference_interval = 0.0 if args.inference_fps <= 0.0 else 1.0 / float(args.inference_fps)
    next_inference_at = 0.0
    last_tracking_frame = None
    started_at = time.time()
    interval = max(0.02, float(_arg(args, 'control_interval', 0.05)))
    duration = float(_arg(args, 'duration', 0.0))

    print(
        f"{'LIVE' if args.live else 'DRY-RUN'} posture_demo tracking: "
        f"tracking_mode={args.tracking_mode} control_interval={interval:.2f}s"
    )

    try:
        while duration <= 0.0 or time.time() - started_at < duration:
            ok, frame = camera.read()
            now = time.time()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            if args.mirror:
                frame = cv2.flip(frame, 1)

            if last_tracking_frame is None or inference_interval == 0.0 or now >= next_inference_at:
                next_inference_at = now + inference_interval
                last_tracking_frame = _process_frame(
                    frame,
                    pose,
                    extractor,
                    action_registry,
                    workout_session,
                    builder,
                    recorder,
                    args,
                    driver,
                    inference_fps,
                )

            tracking_frame = last_tracking_frame
            tracking = tracking_frame.tracking
            ultrasonic_reading = ultrasonic.latest()
            obstacle_decision = avoider.update(ultrasonic_reading.distance_mm, now)
            obstacle_status = _obstacle_status(ultrasonic_reading, obstacle_decision, obstacle_enabled)

            tracking_yaw_decision = yaw_from_tracking(tracking, args, now, tracking_frame.action_active)
            yaw_decision = tracking_yaw_decision
            if obstacle_decision.active:
                yaw_decision = YawDecision(0.0, "obstacle avoidance")
            servo_update = driver.update_camera(tracking, args, now, yaw_speed=yaw_decision.speed)
            sample = distance_input_from_tracking(
                tracking,
                servo_idle_s=driver.servo_idle_s(now),
                posture=tracking_frame.posture,
                action_active=tracking_frame.action_active,
                updated_at=tracking_frame.updated_at,
            )
            if obstacle_decision.active:
                goal = obstacle_decision.goal
            elif args.tracking_mode == 'camera':
                goal = MotionGoal(active=False, reason='camera tracking only')
            else:
                goal = planner.update(sample, now)

            move_speed = 0.0
            direction = 90.0
            if goal.active and now < goal.expires_at:
                move_speed = goal.speed
                direction = goal.direction_degrees

            wheels = mix_translation_yaw(move_speed, direction, yaw_decision.speed, max_speed=args.max_wheel_speed)
            driver.set_wheel_speeds(wheels, reason=f"move={move_speed:.1f}@{direction:.1f} yaw={yaw_decision.speed:.1f}")
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
                obstacle_status,
            )

            frozen = tracking_frame.action_active or obstacle_decision.active
            analysis = replace(
                tracking_frame.analysis,
                tracking=_tracking_status(args, tracking, frozen=frozen),
                obstacle=obstacle_status,
            )
            if analysis.landmarks is not None:
                mp.solutions.drawing_utils.draw_landmarks(frame, analysis.landmarks, mp.solutions.pose.POSE_CONNECTIONS)
            if not args.no_target_box:
                draw_tracking_target(frame, analysis.target)
            draw_label(frame, analysis, camera_fps.tick())
            if preview_state:
                preview_state.publish(frame, analysis_payload(analysis, camera_fps.fps))
            if args.view_img:
                cv2.imshow('Raspbot posture tracking', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            time.sleep(interval)
    finally:
        ultrasonic.stop()
        driver.stop()
        recorder.close()
        logger.close()
        pose.close()
        camera.release()
        if preview_server:
            preview_server.shutdown()
        if args.view_img:
            cv2.destroyAllWindows()
