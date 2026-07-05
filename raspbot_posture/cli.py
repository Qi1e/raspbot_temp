"""Command-line entrypoint and argument defaults."""

import argparse


def add_posture_arguments(parser):
    """Add shared camera, preview, and posture-analysis arguments."""
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
    parser.add_argument('--squat-max-angle-gap', type=float, default=25.0, help='max left/right knee angle gap for squat detection')
    parser.add_argument('--squat-max-stance-width', type=float, default=1.25, help='max ankle span divided by shoulder width for squat detection')
    parser.add_argument('--squat-max-ankle-y-gap', type=float, default=0.08, help='max normalized ankle height gap for squat detection')
    parser.add_argument('--squat-cooldown', type=float, default=0.35, help='minimum seconds between two squat counts')
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
    parser.add_argument('--workout-program', default='HYROX', help='workout program name exposed to preview and frontend state')
    parser.add_argument('--workout-squat-target', type=int, default=20, help='squat target count for workout progress')
    parser.add_argument('--workout-lunge-target', type=int, default=20, help='lunge target count for workout progress')
    parser.add_argument('--workout-burpee-target', type=int, default=10, help='burpee target count for workout progress')
    parser.add_argument('--record-path', default='', help='optional JSONL path for action and joint-angle samples')
    parser.add_argument('--record-url', default='', help='optional HTTP/HTTPS endpoint for NDJSON batch upload')
    parser.add_argument('--record-session-id', default='', help='optional session id for local and remote records')
    parser.add_argument('--record-device-id', default='raspbot', help='device id included in local and remote records')
    parser.add_argument('--record-interval', type=float, default=0.1, help='minimum seconds between recorded samples')
    parser.add_argument('--record-min-confidence', type=float, default=0.55, help='minimum target confidence for recording')
    parser.add_argument('--record-upload-batch-size', type=int, default=10, help='samples per remote NDJSON upload batch')
    parser.add_argument('--record-upload-interval', type=float, default=1.0, help='maximum seconds between remote upload batches')
    parser.add_argument('--record-upload-queue-size', type=int, default=300, help='maximum queued remote record events')
    parser.add_argument('--record-keypoints', action='store_true', help='include selected joint coordinates in records')
    return parser


def build_parser():
    """Build the posture demo argument parser."""
    parser = argparse.ArgumentParser(description='Raspbot body posture demo with MediaPipe Pose')
    return add_posture_arguments(parser)


def parse_args():
    """Parse command-line arguments for Raspberry Pi low-load preview mode."""
    parser = build_parser()
    return parser.parse_args()


def main():
    """Run the posture demo using CLI arguments."""
    args = parse_args()
    from .app import run_posture_demo

    run_posture_demo(args)
