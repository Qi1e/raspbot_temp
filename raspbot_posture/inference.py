"""MediaPipe inference worker and analysis assembly."""

import threading
import time
from dataclasses import replace

import cv2
import mediapipe as mp

from .actions import build_action_registry
from .constants import NO_PERSON_COLOR
from .pose_features import PoseFeatureExtractor, classify_posture
from .state import ActionStatus, FpsMeter, HumanTarget, PoseAnalysis
from .workout import WorkoutSession, build_hyrox_program


POSTURE_COLORS = {
    'Arms up': (0, 220, 255),
    'T pose': (255, 180, 0),
    'Squat or sit': (0, 165, 255),
    'Standing': (80, 255, 80),
    'Leaning left': (255, 120, 120),
    'Leaning right': (255, 120, 120),
    'Body detected': (180, 255, 180),
}


def analyze_pose(frame, pose, classifier, action_registry, workout_session, args, fps_meter):
    """Run one Pose inference and build a PoseAnalysis snapshot."""
    started_at = time.time()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    results = pose.process(rgb)
    rgb.flags.writeable = True

    target = HumanTarget(updated_at=time.time())
    landmarks = None
    features = None
    posture = 'No person'
    color = NO_PERSON_COLOR

    if results.pose_landmarks:
        landmark_list = results.pose_landmarks.landmark
        features = classifier.extract(landmark_list)
        posture = classify_posture(features)
        color = POSTURE_COLORS.get(posture, NO_PERSON_COLOR)
        target = replace(features.target, posture=posture)
        features = replace(features, target=target)
        if args.draw_landmarks:
            landmarks = results.pose_landmarks

    actions = action_registry.update(features, posture) if features is not None else action_registry.reset_stages()
    workout = workout_session.update(actions)
    squat = actions.get('squat', ActionStatus(name='squat'))
    latency_ms = (time.time() - started_at) * 1000.0

    return PoseAnalysis(
        posture=posture,
        color=color,
        squat_count=squat.count,
        squat_stage=squat.stage,
        actions=actions,
        workout=workout,
        pose_features=features,
        inference_fps=fps_meter.tick(),
        latency_ms=latency_ms,
        target=target,
        landmarks=landmarks,
        updated_at=time.time(),
    )


def inference_loop(args, mailbox, analysis_state, stop_event):
    """Worker loop that consumes latest camera frames and updates AnalysisState."""
    pose = mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=args.model_complexity,
        smooth_landmarks=True,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
    )
    classifier = PoseFeatureExtractor(min_visibility=args.min_visibility)
    action_registry = build_action_registry(args)
    workout_session = WorkoutSession(build_hyrox_program(args), session_id=getattr(args, 'record_session_id', ''))
    fps_meter = FpsMeter()
    last_frame_id = -1

    try:
        while not stop_event.is_set():
            frame, last_frame_id = mailbox.wait_latest(last_frame_id, timeout=0.5)
            if frame is None:
                continue
            analysis_state.update(analyze_pose(frame, pose, classifier, action_registry, workout_session, args, fps_meter))
    finally:
        pose.close()


def start_inference_worker(args, mailbox, analysis_state, stop_event):
    """Start the background Pose inference worker thread."""
    worker = threading.Thread(
        target=inference_loop,
        args=(args, mailbox, analysis_state, stop_event),
        name='pose-inference',
    )
    worker.daemon = True
    worker.start()
    return worker
