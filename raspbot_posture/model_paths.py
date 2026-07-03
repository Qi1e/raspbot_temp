"""Offline MediaPipe model path helpers."""

from pathlib import Path

import mediapipe as mp


def mediapipe_package_dir():
    """Return the installed mediapipe package directory."""
    return Path(mp.__file__).resolve().parent


def pose_model_path(model_complexity):
    """Return the expected local Pose model path for model_complexity."""
    filenames = {
        0: 'pose_landmark_lite.tflite',
        1: 'pose_landmark_full.tflite',
        2: 'pose_landmark_heavy.tflite',
    }
    return mediapipe_package_dir() / 'modules' / 'pose_landmark' / filenames[model_complexity]


def ensure_pose_model_available(model_complexity):
    """Fail early if the offline Raspberry Pi lacks the selected Pose model."""
    model_path = pose_model_path(model_complexity)
    if model_path.exists():
        return

    raise FileNotFoundError(
        'MediaPipe pose model is missing and this Raspberry Pi is offline.\n'
        f'Missing file: {model_path}\n'
        'Copy the required .tflite model to the path above before running this demo.\n'
        'For the default lite model, the file name is pose_landmark_lite.tflite.'
    )

