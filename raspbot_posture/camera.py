"""Camera helpers."""

import cv2


def open_camera(source, width, height):
    """Open a camera/video source and request the target resolution."""
    camera = cv2.VideoCapture(source)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not camera.isOpened():
        raise RuntimeError(f'camera source {source} could not be opened')
    return camera

