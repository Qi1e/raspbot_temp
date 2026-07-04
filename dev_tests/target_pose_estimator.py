#!/usr/bin/env python3
# coding: utf-8
"""Compatibility imports for the package tracking estimator."""

from raspbot_posture.distance_models import FITTED_MODELS, DistanceModel, FeatureFit
from raspbot_posture.tracking_estimator import (
    MotionTrackingInput,
    TargetPoseConfig,
    TargetPoseEstimate,
    TargetTrackingInputBuilder,
    estimate_target_pose,
)

__all__ = [
    "DistanceModel",
    "FeatureFit",
    "FITTED_MODELS",
    "MotionTrackingInput",
    "TargetPoseConfig",
    "TargetPoseEstimate",
    "TargetTrackingInputBuilder",
    "estimate_target_pose",
]
