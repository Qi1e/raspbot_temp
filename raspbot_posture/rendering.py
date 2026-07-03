"""Drawing helpers for preview overlays."""

import cv2


def draw_tracking_target(frame, target):
    """Draw the lightweight human target box and center point."""
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


def draw_label(frame, analysis, camera_fps):
    """Draw posture, FPS, and squat count in the top-left overlay."""
    box_width = max(220, min(frame.shape[1] - 20, 470))
    cv2.rectangle(frame, (10, 10), (10 + box_width, 118), (16, 19, 22), -1)
    cv2.putText(
        frame,
        f'Posture: {analysis.posture}',
        (20, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        analysis.color,
        2,
    )
    cv2.putText(
        frame,
        f'Cam: {camera_fps:.1f} FPS  Infer: {analysis.inference_fps:.1f} FPS',
        (20, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (230, 240, 245),
        2,
    )
    cv2.putText(
        frame,
        f'Squats: {analysis.squat_count}  Stage: {analysis.squat_stage}',
        (20, 98),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (230, 240, 245),
        2,
    )

