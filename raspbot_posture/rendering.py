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
    """Draw posture, workout, action, and tracking state in the overlay."""
    box_width = max(360, min(frame.shape[1] - 20, 760))
    cv2.rectangle(frame, (10, 10), (10 + box_width, 202), (16, 19, 22), -1)
    cv2.putText(
        frame,
        f'Posture: {analysis.posture}',
        (20, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        analysis.color,
        2,
    )
    workout = analysis.workout
    station = 'Complete' if workout.completed else f'{workout.station_index}/{workout.total_stations} {workout.current_station}'
    progress = f'{workout.current_count}/{workout.target_count}' if workout.target_count else '-'
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
        f'Workout: {workout.program_name or "-"}  Station: {station}  Progress: {progress}',
        (20, 98),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (230, 240, 245),
        2,
    )
    counts = []
    for name, label in (('squat', 'Squat'), ('lunge', 'Lunge'), ('burpee', 'Burpee')):
        status = analysis.actions.get(name)
        if status is not None:
            counts.append(f'{label} {status.count}:{status.stage}')
    cv2.putText(
        frame,
        '  '.join(counts) if counts else 'Actions: -',
        (20, 126),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (230, 240, 245),
        2,
    )
    tracking = analysis.tracking
    if tracking.enabled:
        tracking_text = (
            f'Tracking: {tracking.mode} {tracking.distance_state} '
            f'move={tracking.chassis_motion_direction} frozen={int(tracking.frozen)}'
        )
    else:
        tracking_text = 'Tracking: disabled'
    cv2.putText(
        frame,
        tracking_text[:96],
        (20, 154),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (230, 240, 245),
        2,
    )
    obstacle = analysis.obstacle
    if obstacle.enabled:
        distance = '-' if obstacle.distance_mm is None else f'{obstacle.distance_mm:.0f}mm'
        obstacle_text = (
            f'Obstacle: {obstacle.phase} active={int(obstacle.active)} '
            f'dist={distance} {obstacle.reason}'
        )
    else:
        obstacle_text = 'Obstacle: disabled'
    cv2.putText(
        frame,
        obstacle_text[:96],
        (20, 182),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.56,
        (230, 240, 245),
        2,
    )
