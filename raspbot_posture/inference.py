"""MediaPipe inference worker and analysis assembly."""

import threading
import time

import cv2
import mediapipe as mp

from .actions import build_action_registry
from .constants import NO_PERSON_COLOR
from .geometry import PoseMetrics, build_human_target
from .state import ActionStatus, FpsMeter, HumanTarget, PoseAnalysis
from .vision import PostureClassifier


def analyze_pose(frame, pose, classifier, action_registry, args, fps_meter):
    """Run one Pose inference and build a PoseAnalysis snapshot."""
    started_at = time.time()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    results = pose.process(rgb)
    rgb.flags.writeable = True

    posture = 'No person'
    color = NO_PERSON_COLOR
    target = HumanTarget(updated_at=time.time())
    landmarks = None
    metrics = PoseMetrics()

    if results.pose_landmarks:
        landmark_list = results.pose_landmarks.landmark
        metrics = classifier.measure(landmark_list)
        posture, color = classifier.classify(metrics)
        target = build_human_target(landmark_list, posture, args.min_visibility)
        if args.draw_landmarks:
            landmarks = results.pose_landmarks

    actions = action_registry.update(metrics, posture, target)
    squat = actions.get('squat', ActionStatus(name='squat'))
    latency_ms = (time.time() - started_at) * 1000.0

    return PoseAnalysis(
        posture=posture,
        color=color,
        squat_count=squat.count,
        squat_stage=squat.stage,
        actions=actions,
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
    classifier = PostureClassifier(min_visibility=args.min_visibility)
    action_registry = build_action_registry(args)
    fps_meter = FpsMeter()
    last_frame_id = -1

    try:
        while not stop_event.is_set():
            frame, last_frame_id = mailbox.wait_latest(last_frame_id, timeout=0.5)
            if frame is None:
                continue
            analysis_state.update(analyze_pose(frame, pose, classifier, action_registry, args, fps_meter))
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

