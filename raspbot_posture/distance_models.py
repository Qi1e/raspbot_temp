"""Calibrated distance models for body tracking."""

import math
import statistics
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class FeatureFit:
    scale: float
    offset: float
    weight: float
    sqrt_feature: bool = False

    def estimate(self, value):
        if value <= 0.0:
            return None
        base = math.sqrt(value) if self.sqrt_feature else value
        if base <= 0.0:
            return None
        return self.scale / base + self.offset


@dataclass(frozen=True)
class DistanceModel:
    name: str
    reference_tilt: float
    min_distance: float
    max_distance: float
    fits: Dict[str, FeatureFit]


FITTED_MODELS = (
    DistanceModel(
        name="close_tilt_60",
        reference_tilt=60.0,
        min_distance=0.8,
        max_distance=1.6,
        fits={
            "area": FeatureFit(0.6324404002, -0.2908273813, 0.05, sqrt_feature=True),
            "shoulder_width": FeatureFit(0.3240232680, -0.7086368972, 0.25),
            "torso_height": FeatureFit(0.9487164527, -1.7064665868, 0.70),
        },
    ),
    DistanceModel(
        name="near_tilt_50",
        reference_tilt=50.0,
        min_distance=1.2,
        max_distance=2.4,
        fits={
            "area": FeatureFit(0.9755193256, -0.5766804208, 0.20, sqrt_feature=True),
            "shoulder_width": FeatureFit(0.3380328685, -0.5190628119, 0.35),
            "torso_height": FeatureFit(0.7377236254, -0.7402426401, 0.45),
        },
    ),
    DistanceModel(
        name="far_tilt_35",
        reference_tilt=35.0,
        min_distance=2.4,
        max_distance=4.0,
        fits={
            "area": FeatureFit(0.9209381051, 0.0076184811, 0.12, sqrt_feature=True),
            "shoulder_width": FeatureFit(0.3239024916, -0.2656578322, 0.58),
            "torso_height": FeatureFit(0.6858445971, -0.4677233273, 0.30),
        },
    ),
)


def clip01(value):
    return max(0.0, min(1.0, float(value)))


def select_model(tilt_angle):
    return min(FITTED_MODELS, key=lambda model: abs(float(tilt_angle) - model.reference_tilt))


def weighted_distance(model, features):
    estimates = {}
    weighted = []
    for name, fit in model.fits.items():
        estimate = fit.estimate(features.get(name, 0.0))
        if estimate is None or not math.isfinite(estimate):
            continue
        estimates[name] = estimate
        weighted.append((estimate, fit.weight))

    if not weighted:
        return None, estimates

    total_weight = sum(weight for _, weight in weighted)
    distance_m = sum(value * weight for value, weight in weighted) / total_weight
    return distance_m, estimates


def agreement_confidence(values):
    if len(values) < 2:
        return 0.65 if values else 0.0
    mean_value = statistics.mean(values)
    if mean_value <= 0.0:
        return 0.0
    spread = statistics.stdev(values) / mean_value
    return clip01(1.0 - min(spread, 0.6))


def model_confidence(model, tilt_angle, distance_m):
    tilt_error = abs(float(tilt_angle) - model.reference_tilt)
    tilt_score = clip01(1.0 - tilt_error / 30.0)
    if distance_m is None:
        return 0.0

    if model.min_distance <= distance_m <= model.max_distance:
        range_score = 1.0
    else:
        nearest = model.min_distance if distance_m < model.min_distance else model.max_distance
        range_score = clip01(1.0 - abs(distance_m - nearest) / 1.0)
    return 0.5 * tilt_score + 0.5 * range_score
