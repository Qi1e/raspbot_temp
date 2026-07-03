"""Command-line entrypoint and argument defaults."""

import argparse

from .app import run_posture_demo


def parse_args():
    """Parse command-line arguments for Raspberry Pi low-load preview mode."""
    parser = argparse.ArgumentParser(description='Raspbot body posture demo with MediaPipe Pose')
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
    parser.add_argument('--inference-fps', type=float, default=8.0, help='pose inference FPS cap; 0 runs on every captured frame')
    parser.add_argument('--draw-landmarks', action='store_true', help='draw MediaPipe landmarks for debugging')
    parser.add_argument('--no-target-box', action='store_true', help='hide the lightweight target box')
    parser.add_argument('--min-detection-confidence', type=float, default=0.5, help='pose detection confidence')
    parser.add_argument('--min-tracking-confidence', type=float, default=0.5, help='pose tracking confidence')
    parser.add_argument('--min-visibility', type=float, default=0.55, help='landmark visibility threshold')
    parser.add_argument('--squat-stable-frames', type=int, default=1, help='legacy shorthand for squat down/up confirmation frames')
    parser.add_argument('--squat-down-frames', type=int, default=None, help='down samples required before entering squat down stage')
    parser.add_argument('--squat-up-frames', type=int, default=None, help='up samples required before counting one squat')
    parser.add_argument('--squat-down-angle', type=float, default=145.0, help='knee angle threshold for squat down')
    parser.add_argument('--squat-up-angle', type=float, default=155.0, help='knee angle threshold for standing up')
    parser.add_argument('--squat-cooldown', type=float, default=0.35, help='minimum seconds between two squat counts')
    return parser.parse_args()


def main():
    """Run the posture demo using CLI arguments."""
    run_posture_demo(parse_args())

