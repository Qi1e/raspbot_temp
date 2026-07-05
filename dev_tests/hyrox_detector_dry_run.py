#!/usr/bin/env python3
# coding: utf-8
"""Synthetic dry run for HYROX action detectors."""

from argparse import Namespace

from raspbot_posture import actions as detectors
from raspbot_posture.actions import build_action_registry
from raspbot_posture.pose_features import PoseFeatures
from raspbot_posture.state import HumanTarget


def default_args():
    """Return detector defaults without opening camera or MediaPipe."""
    return Namespace(
        squat_stable_frames=1,
        squat_down_frames=None,
        squat_up_frames=None,
        squat_down_angle=152.0,
        squat_up_angle=155.0,
        squat_max_angle_gap=25.0,
        squat_max_stance_width=1.25,
        squat_max_ankle_y_gap=0.08,
        squat_cooldown=0.0,
        squat_min_down_time=0.0,
        lunge_stable_frames=1,
        lunge_down_frames=None,
        lunge_up_frames=None,
        lunge_down_angle=128.0,
        lunge_up_angle=155.0,
        lunge_min_angle_gap=18.0,
        lunge_min_stance_width=1.45,
        lunge_min_ankle_y_gap=0.05,
        lunge_cooldown=0.0,
        burpee_stable_frames=1,
        burpee_floor_frames=None,
        burpee_up_frames=None,
        burpee_landing_frames=None,
        burpee_squat_angle=152.0,
        burpee_up_angle=155.0,
        burpee_floor_width_ratio=1.15,
        burpee_floor_height_max=0.55,
        burpee_floor_center_y_min=0.45,
        burpee_flat_floor_width_ratio=1.25,
        burpee_flat_floor_height_max=0.38,
        burpee_flat_floor_center_y_min=0.52,
        burpee_no_arm_floor_frames=None,
        burpee_pushup_down_elbow_angle=118.0,
        burpee_pushup_up_elbow_angle=148.0,
        burpee_pushup_min_knee_angle=135.0,
        burpee_broad_jump_min_dx=0.16,
        burpee_stage_timeout=7.0,
        burpee_cooldown=0.0,
    )


def target(width=0.25, height=0.7, center_x=0.5, center_y=0.55):
    """Synthetic confident target box."""
    return HumanTarget(
        detected=True,
        center_x=center_x,
        width=width,
        height=height,
        area=width * height,
        center_y=center_y,
        confidence=0.9,
    )


def standing(center_x=0.5):
    """Synthetic standing posture."""
    return PoseFeatures(
        full_body=True,
        legs_visible=True,
        knee_angle=170.0,
        left_knee_angle=170.0,
        right_knee_angle=170.0,
        target=target(center_x=center_x),
    )


def squat_down():
    """Synthetic squat-down posture."""
    return PoseFeatures(
        full_body=True,
        legs_visible=True,
        hips_low=True,
        knee_angle=112.0,
        left_knee_angle=112.0,
        right_knee_angle=112.0,
        target=target(),
    )


def floor_like_squat_down():
    """Synthetic low-camera squat whose target box looks floor-like."""
    return PoseFeatures(
        full_body=True,
        arms_visible=True,
        legs_visible=True,
        hips_low=True,
        torso_height=0.18,
        knee_angle=112.0,
        left_knee_angle=112.0,
        right_knee_angle=112.0,
        target=target(width=0.18, height=0.43, center_y=0.49),
    )


def lunge_down():
    """Synthetic split-stance lunge posture."""
    return PoseFeatures(
        full_body=True,
        legs_visible=True,
        hips_low=True,
        knee_angle=140.0,
        left_knee_angle=112.0,
        right_knee_angle=168.0,
        knee_angle_gap=56.0,
        ankle_width_ratio=2.20,
        hip_ankle_mid_x_gap=0.58,
        target=target(),
    )


def floor_like_lunge_no_arms():
    """Synthetic lunge-like frame that previously looked like a burpee floor entry."""
    return PoseFeatures(
        full_body=True,
        arms_visible=False,
        legs_visible=True,
        hips_low=True,
        torso_height=0.18,
        knee_angle=140.0,
        left_knee_angle=112.0,
        right_knee_angle=168.0,
        knee_angle_gap=56.0,
        ankle_width_ratio=2.20,
        ankle_y_gap=0.08,
        knee_y_gap=0.05,
        hip_ankle_mid_x_gap=0.58,
        target=target(width=0.72, height=0.35, center_y=0.62),
    )


def knee_jitter_squat_like():
    """Synthetic front squat frame with bad knee-angle jitter but no split stance."""
    return PoseFeatures(
        full_body=True,
        arms_visible=True,
        legs_visible=True,
        hips_low=True,
        knee_angle=82.0,
        left_knee_angle=128.0,
        right_knee_angle=36.0,
        knee_angle_gap=92.0,
        ankle_width_ratio=0.44,
        ankle_y_gap=0.01,
        knee_y_gap=0.01,
        hip_ankle_mid_x_gap=0.02,
        target=target(width=0.18, height=0.43, center_y=0.48),
    )


def burpee_floor():
    """Synthetic floor/plank posture."""
    return PoseFeatures(
        full_body=True,
        arms_visible=True,
        legs_visible=True,
        knee_angle=150.0,
        left_knee_angle=150.0,
        right_knee_angle=150.0,
        left_elbow_angle=100.0,
        right_elbow_angle=100.0,
        target=target(width=0.72, height=0.35, center_y=0.62),
    )


def burpee_pushup_up():
    """Synthetic floor posture after the pushup is pressed up."""
    return PoseFeatures(
        full_body=True,
        arms_visible=True,
        legs_visible=True,
        knee_angle=150.0,
        left_knee_angle=150.0,
        right_knee_angle=150.0,
        left_elbow_angle=160.0,
        right_elbow_angle=160.0,
        target=target(width=0.72, height=0.35, center_y=0.62),
    )


def burpee_flat_no_arms(center_x=0.5):
    """Synthetic very flat floor frame where arms are occluded by the low camera."""
    return PoseFeatures(
        full_body=True,
        arms_visible=False,
        legs_visible=False,
        torso_height=0.12,
        target=target(width=0.56, height=0.22, center_x=center_x, center_y=0.58),
    )


def burpee_rising_no_arms(center_x=0.5):
    """Synthetic post-floor recovery frame without enough arm landmarks."""
    return PoseFeatures(
        full_body=True,
        arms_visible=False,
        legs_visible=False,
        torso_height=0.30,
        target=target(width=0.28, height=0.68, center_x=center_x, center_y=0.42),
    )


def main():
    """Run a deterministic detector sequence and print final counts."""
    registry = build_action_registry(default_args())
    statuses = {}
    for features, posture in (
        (standing(), 'Standing'),
        (squat_down(), 'Squat or sit'),
        (standing(), 'Standing'),
        (lunge_down(), 'Body detected'),
        (standing(), 'Standing'),
        (squat_down(), 'Squat or sit'),
        (burpee_floor(), 'Body detected'),
        (burpee_pushup_up(), 'Body detected'),
        (standing(center_x=0.50), 'Standing'),
        (standing(center_x=0.72), 'Standing'),
    ):
        statuses = registry.update(features, posture)

    print(
        'counts: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}"
    )

    regression = build_action_registry(default_args())
    for features, posture in (
        (standing(), 'Standing'),
        (floor_like_squat_down(), 'Squat or sit'),
        (standing(), 'Standing'),
    ):
        statuses = regression.update(features, posture)
    print(
        'floor-like squat: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}, "
        f"burpee_stage={statuses['burpee'].stage}"
    )

    lunge_regression = build_action_registry(default_args())
    for features, posture in (
        (standing(), 'Standing'),
        (lunge_down(), 'Squat or sit'),
        (standing(), 'Standing'),
    ):
        statuses = lunge_regression.update(features, posture)
    if statuses['lunge'].count != 1 or statuses['squat'].count != 0:
        raise AssertionError(
            'lunge-over-squat regression failed: '
            f"squat={statuses['squat'].count}, lunge={statuses['lunge'].count}"
        )
    print(
        'lunge-over-squat: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}"
    )

    burpee_guard = build_action_registry(default_args())
    sequence = [(standing(), 'Standing')]
    sequence.extend((floor_like_lunge_no_arms(), 'Leaning left') for _ in range(5))
    sequence.append((standing(), 'Standing'))
    for features, posture in sequence:
        statuses = burpee_guard.update(features, posture)
    if statuses['burpee'].count != 0 or statuses['burpee'].stage in ('pushup_down', 'pushup_up'):
        raise AssertionError(
            'burpee no-arm floor fallback regression failed: '
            f"burpee={statuses['burpee'].count}, stage={statuses['burpee'].stage}"
        )
    print(
        'no-arm lunge burpee guard: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}, "
        f"burpee_stage={statuses['burpee'].stage}"
    )

    jitter_regression = build_action_registry(default_args())
    for features, posture in (
        (standing(), 'Standing'),
        (knee_jitter_squat_like(), 'Squat or sit'),
        (standing(), 'Standing'),
    ):
        statuses = jitter_regression.update(features, posture)
    if statuses['lunge'].count != 0:
        raise AssertionError(
            'knee-jitter lunge regression failed: '
            f"lunge={statuses['lunge'].count}, stage={statuses['lunge'].stage}"
        )
    print(
        'knee-jitter squat guard: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}"
    )

    old_time = detectors.time.time
    clock = [1000.0]
    detectors.time.time = lambda: clock[0]
    try:
        timed_args = default_args()
        timed_args.squat_min_down_time = 0.4
        timed_regression = build_action_registry(timed_args)
        for current_time, features, posture in (
            (1000.00, standing(), 'Standing'),
            (1001.00, squat_down(), 'Squat or sit'),
            (1001.13, standing(), 'Standing'),
            (1002.00, squat_down(), 'Squat or sit'),
            (1002.70, standing(), 'Standing'),
        ):
            clock[0] = current_time
            statuses = timed_regression.update(features, posture)
    finally:
        detectors.time.time = old_time
    if statuses['squat'].count != 1:
        raise AssertionError(
            'squat min-down-time regression failed: '
            f"squat={statuses['squat'].count}, stage={statuses['squat'].stage}"
        )
    print(
        'squat min-down-time guard: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}"
    )

    no_arm_burpee = build_action_registry(default_args())
    for features, posture in (
        (standing(center_x=0.40), 'Standing'),
        (burpee_flat_no_arms(center_x=0.40), 'Leaning right'),
        (burpee_flat_no_arms(center_x=0.40), 'Leaning right'),
        (burpee_flat_no_arms(center_x=0.40), 'Leaning right'),
        (burpee_rising_no_arms(center_x=0.40), 'Body detected'),
        (standing(center_x=0.40), 'Standing'),
        (standing(center_x=0.66), 'Standing'),
    ):
        statuses = no_arm_burpee.update(features, posture)
    if statuses['burpee'].count != 1:
        raise AssertionError(
            'no-arm strict-flat burpee regression failed: '
            f"burpee={statuses['burpee'].count}, stage={statuses['burpee'].stage}"
        )
    print(
        'no-arm flat burpee: '
        f"squat={statuses['squat'].count}, "
        f"lunge={statuses['lunge'].count}, "
        f"burpee={statuses['burpee'].count}"
    )


if __name__ == '__main__':
    main()
