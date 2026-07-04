#!/usr/bin/env python3
# coding: utf-8

"""Standalone HYROX action demo without modifying raspbot_posture internals."""

import argparse
import time

from hyrox_actions.detectors import build_action_registry
from hyrox_actions.pose_features import PoseFeatureExtractor, classify_posture
from hyrox_actions.recorder import JsonlRecorder
from raspbot_posture.state import FpsMeter


def add_arguments(parser):
    """Add camera, detector, preview, and recorder arguments."""
    parser.add_argument('--source', default='0', help='camera source, usually 0')
    parser.add_argument('--width', type=int, default=640, help='camera width')
    parser.add_argument('--height', type=int, default=480, help='camera height')
    parser.add_argument('--mirror', action='store_true', help='mirror camera image horizontally')
    parser.add_argument('--view-img', action='store_true', help='show local OpenCV window')
    parser.add_argument('--no-preview', action='store_true', help='disable web preview')
    parser.add_argument('--preview-host', default='0.0.0.0', help='preview server bind host')
    parser.add_argument('--preview-port', type=int, default=8080, help='preview server port')
    parser.add_argument('--preview-quality', type=int, default=65, help='preview JPEG quality 1-100')
    parser.add_argument('--preview-width', type=int, default=480, help='preview max width, 0 keeps original size')
    parser.add_argument('--preview-fps', type=float, default=8, help='preview max FPS, 0 disables throttling')
    parser.add_argument(
        '--model-complexity',
        type=int,
        default=0,
        choices=[0, 1, 2],
        help='MediaPipe Pose model complexity; 0 uses the lite model',
    )
    parser.add_argument('--inference-fps', type=float, default=12.0, help='pose inference FPS cap; 0 runs on every frame')
    parser.add_argument('--draw-landmarks', action='store_true', help='draw MediaPipe landmarks for debugging')
    parser.add_argument('--no-target-box', action='store_true', help='hide target box')
    parser.add_argument('--min-detection-confidence', type=float, default=0.5, help='pose detection confidence')
    parser.add_argument('--min-tracking-confidence', type=float, default=0.5, help='pose tracking confidence')
    parser.add_argument('--min-visibility', type=float, default=0.55, help='landmark visibility threshold')

    parser.add_argument('--squat-stable-frames', type=int, default=1, help='squat down/up confirmation frames')
    parser.add_argument('--squat-down-frames', type=int, default=None, help='down samples required for squat down stage')
    parser.add_argument('--squat-up-frames', type=int, default=None, help='up samples required before counting one squat')
    parser.add_argument('--squat-down-angle', type=float, default=152.0, help='knee angle threshold for squat down')
    parser.add_argument('--squat-up-angle', type=float, default=155.0, help='knee angle threshold for standing up')
    parser.add_argument('--squat-max-angle-gap', type=float, default=25.0, help='max left/right knee angle gap for squat detection')
    parser.add_argument('--squat-max-stance-width', type=float, default=1.25, help='max ankle span divided by shoulder width for squat detection')
    parser.add_argument('--squat-max-ankle-y-gap', type=float, default=0.08, help='max normalized ankle height gap for squat detection')
    parser.add_argument('--squat-cooldown', type=float, default=0.35, help='minimum seconds between squat counts')
    parser.add_argument('--squat-min-down-time', type=float, default=0.4, help='minimum seconds in squat down stage before counting')

    parser.add_argument('--lunge-stable-frames', type=int, default=2, help='lunge down/up confirmation frames')
    parser.add_argument('--lunge-down-frames', type=int, default=None, help='down samples required for lunge down stage')
    parser.add_argument('--lunge-up-frames', type=int, default=None, help='up samples required before counting one lunge')
    parser.add_argument('--lunge-down-angle', type=float, default=128.0, help='bent-knee threshold for lunge down')
    parser.add_argument('--lunge-up-angle', type=float, default=155.0, help='both-knees threshold for lunge standing up')
    parser.add_argument('--lunge-min-angle-gap', type=float, default=18.0, help='left/right knee angle gap for lunge detection')
    parser.add_argument('--lunge-min-stance-width', type=float, default=1.45, help='ankle span divided by shoulder width')
    parser.add_argument('--lunge-min-ankle-y-gap', type=float, default=0.05, help='normalized ankle height gap')
    parser.add_argument('--lunge-cooldown', type=float, default=0.45, help='minimum seconds between lunge counts')

    parser.add_argument('--burpee-stable-frames', type=int, default=1, help='burpee floor/up confirmation frames')
    parser.add_argument('--burpee-floor-frames', type=int, default=None, help='floor samples required for burpee floor stage')
    parser.add_argument('--burpee-up-frames', type=int, default=None, help='up samples required before counting one burpee')
    parser.add_argument('--burpee-landing-frames', type=int, default=None, help='landing samples required before counting one burpee broad jump')
    parser.add_argument('--burpee-squat-angle', type=float, default=152.0, help='knee angle threshold for protecting squats from burpee entry')
    parser.add_argument('--burpee-up-angle', type=float, default=155.0, help='knee angle threshold for burpee standing phase')
    parser.add_argument('--burpee-floor-width-ratio', type=float, default=1.15, help='target width/height ratio for floor phase')
    parser.add_argument('--burpee-floor-height-max', type=float, default=0.55, help='maximum target height for floor phase')
    parser.add_argument('--burpee-floor-center-y-min', type=float, default=0.45, help='minimum target center y for floor phase')
    parser.add_argument('--burpee-flat-floor-width-ratio', type=float, default=1.25, help='strict width/height ratio for no-arm floor entry')
    parser.add_argument('--burpee-flat-floor-height-max', type=float, default=0.38, help='strict max target height for no-arm floor entry')
    parser.add_argument('--burpee-flat-floor-center-y-min', type=float, default=0.52, help='strict min target center y for no-arm floor entry')
    parser.add_argument('--burpee-no-arm-floor-frames', type=int, default=None, help='strict floor samples required before no-arm pushup entry')
    parser.add_argument('--burpee-pushup-down-elbow-angle', type=float, default=118.0, help='elbow angle threshold for pushup-down phase')
    parser.add_argument('--burpee-pushup-up-elbow-angle', type=float, default=148.0, help='elbow angle threshold for pushup-up phase')
    parser.add_argument('--burpee-pushup-min-knee-angle', type=float, default=135.0, help='minimum knee angle for treating a floor pose as pushup instead of squat')
    parser.add_argument('--burpee-broad-jump-min-dx', type=float, default=0.16, help='minimum lateral center-x movement for broad jump')
    parser.add_argument('--burpee-stage-timeout', type=float, default=7.0, help='seconds before an incomplete burpee sequence resets')
    parser.add_argument('--burpee-cooldown', type=float, default=0.8, help='minimum seconds between burpee counts')

    parser.add_argument('--record-path', default='', help='optional JSONL path for action and joint-angle samples')
    parser.add_argument('--record-interval', type=float, default=0.1, help='minimum seconds between recorded samples')
    parser.add_argument('--record-min-confidence', type=float, default=0.55, help='minimum target confidence for recording')
    return parser


def build_parser():
    """Build the HYROX demo argument parser."""
    parser = argparse.ArgumentParser(description='Raspbot HYROX action demo')
    return add_arguments(parser)


def run(args):
    """Run camera capture, MediaPipe inference, HYROX detection, preview, and recording."""
    import cv2
    import mediapipe as mp

    from hyrox_actions.overlay import draw_hyrox_label, draw_target_box
    from raspbot_posture.camera import open_camera
    from raspbot_posture.model_paths import ensure_pose_model_available
    from raspbot_posture.preview import start_preview_server

    args.inference_fps = max(0.0, float(args.inference_fps))
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
    registry = build_action_registry(args)
    recorder = JsonlRecorder(args.record_path, args.record_interval, args.record_min_confidence)
    camera_fps_meter = FpsMeter()
    inference_fps_meter = FpsMeter()
    inference_interval = 0.0 if args.inference_fps <= 0 else 1.0 / args.inference_fps
    next_inference_at = 0.0
    posture = 'No person'
    features = None
    actions = registry.statuses()
    landmarks = None

    drawing = None
    drawing_styles = None
    if args.draw_landmarks:
        drawing = mp.solutions.drawing_utils
        drawing_styles = mp.solutions.drawing_styles

    print(
        'HYROX action demo started. '
        f'Inference cap: {args.inference_fps:.1f} FPS. '
        'Press Ctrl+C to stop.'
    )
    if recorder.enabled:
        print(f'Recording JSONL samples to: {recorder.path}')

    try:
        while True:
            ok, frame = camera.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            if args.mirror:
                frame = cv2.flip(frame, 1)

            now = time.time()
            if inference_interval == 0.0 or now >= next_inference_at:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = pose.process(rgb)
                rgb.flags.writeable = True
                next_inference_at = now + inference_interval

                if results.pose_landmarks:
                    landmarks = results.pose_landmarks
                    features = extractor.extract(results.pose_landmarks.landmark)
                    posture = classify_posture(features)
                    actions = registry.update(features, posture)
                    recorder.record(posture, features, actions)
                else:
                    landmarks = None
                    features = None
                    posture = 'No person'
                    actions = registry.reset_stages()
                inference_fps_meter.tick()

            if args.draw_landmarks and landmarks:
                drawing.draw_landmarks(
                    frame,
                    landmarks,
                    mp.solutions.pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=drawing_styles.get_default_pose_landmarks_style(),
                )

            if features is not None and not args.no_target_box:
                draw_target_box(frame, features.target)

            draw_hyrox_label(
                frame,
                posture,
                actions,
                camera_fps_meter.tick(),
                inference_fps_meter.fps,
                record_enabled=recorder.enabled,
            )

            if preview_state:
                preview_state.publish(frame)

            if args.view_img:
                cv2.imshow('Raspbot HYROX action demo', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        pose.close()
        camera.release()
        if preview_server:
            preview_server.shutdown()
        if args.view_img:
            cv2.destroyAllWindows()


def main():
    """Parse CLI args and run the HYROX demo."""
    run(build_parser().parse_args())


if __name__ == '__main__':
    main()
