"""Application runtime for the posture demo."""

import threading
import time

import cv2

from .camera import open_camera
from .output import analysis_payload
from .preview import start_preview_server
from .rendering import draw_label, draw_tracking_target
from .state import AnalysisState, FpsMeter, FrameMailbox


def run_posture_demo(
    args,
    control_factory=None,
    start_label='Posture demo started.',
    window_title='Raspbot posture demo',
    summary_printer=None,
):
    """Run camera capture, optional inference, overlay drawing, preview, and control."""
    args.inference_fps = max(0.0, float(args.inference_fps))
    camera_only = bool(getattr(args, 'camera_only', False))
    source = int(args.source) if str(args.source).isdigit() else args.source
    if not camera_only:
        from .model_paths import ensure_pose_model_available

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
    inference_worker = None
    if not camera_only:
        from .inference import start_inference_worker

        inference_worker = start_inference_worker(args, mailbox, analysis_state, stop_event)
    control_worker = None
    camera_fps_meter = FpsMeter()

    drawing = None
    drawing_styles = None
    if args.draw_landmarks and not camera_only:
        import mediapipe as mp

        drawing = mp.solutions.drawing_utils
        drawing_styles = mp.solutions.drawing_styles

    inference_interval = 0.0
    if args.inference_fps > 0:
        inference_interval = 1.0 / float(args.inference_fps)
    next_inference_at = 0.0

    inference_status = 'Inference disabled.' if camera_only else f'Inference cap: {args.inference_fps:.1f} FPS.'
    print(f'{start_label} {inference_status} Press Ctrl+C to stop.')
    if summary_printer:
        summary_printer(args)

    try:
        if control_factory is not None:
            control_worker = control_factory(args, analysis_state, stop_event).start()

        while True:
            ret, frame = camera.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            if args.mirror:
                frame = cv2.flip(frame, 1)

            now = time.time()
            if not camera_only and (inference_interval == 0.0 or now >= next_inference_at):
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
                preview_state.publish(frame, analysis_payload(analysis, camera_fps_meter.fps))

            if args.view_img:
                cv2.imshow(window_title, frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        stop_event.set()
        mailbox.close()
        if inference_worker:
            inference_worker.join(timeout=2.0)
        if control_worker:
            control_worker.join(timeout=2.0)
        camera.release()
        if preview_server:
            preview_server.shutdown()
        if args.view_img:
            cv2.destroyAllWindows()
