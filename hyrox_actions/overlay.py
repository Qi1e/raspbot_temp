"""OpenCV overlay helpers for the HYROX demo."""

import cv2


ACTION_LABELS = {
    'squat': 'Squats',
    'lunge': 'Lunges',
    'burpee': 'Burpees',
}


def draw_target_box(frame, target):
    """Draw the visible-body box used by the detectors."""
    if not target.detected:
        return

    height, width = frame.shape[:2]
    x1 = int(max(0, (target.center_x - target.width / 2.0) * width))
    y1 = int(max(0, (target.center_y - target.height / 2.0) * height))
    x2 = int(min(width - 1, (target.center_x + target.width / 2.0) * width))
    y2 = int(min(height - 1, (target.center_y + target.height / 2.0) * height))
    center = (int(target.center_x * width), int(target.center_y * height))
    cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 200, 255), 2)
    cv2.circle(frame, center, 4, (80, 200, 255), -1)


def draw_hyrox_label(frame, posture, actions, camera_fps, inference_fps, record_enabled=False):
    """Draw posture, FPS, action counts, and recording status."""
    box_width = max(250, min(frame.shape[1] - 20, 520))
    box_height = 188
    cv2.rectangle(frame, (10, 10), (10 + box_width, 10 + box_height), (16, 19, 22), -1)

    cv2.putText(
        frame,
        f'Posture: {posture}',
        (20, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (80, 255, 160),
        2,
    )
    cv2.putText(
        frame,
        f'Cam: {camera_fps:.1f} FPS  Infer: {inference_fps:.1f} FPS',
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (230, 240, 245),
        2,
    )

    y = 98
    for name in ('squat', 'lunge', 'burpee'):
        status = actions.get(name)
        count = status.count if status else 0
        stage = status.stage if status else 'unknown'
        cv2.putText(
            frame,
            f'{ACTION_LABELS[name]}: {count}  Stage: {stage}',
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (230, 240, 245),
            2,
        )
        y += 28

    record_text = 'Recording: on' if record_enabled else 'Recording: off'
    cv2.putText(
        frame,
        record_text,
        (20, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (80, 220, 255) if record_enabled else (180, 190, 200),
        2,
    )
