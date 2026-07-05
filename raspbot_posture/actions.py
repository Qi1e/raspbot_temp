"""Action detectors implemented as reusable package state machines."""

import time

from .state import ActionStatus

def clamp01(value):
    """Clamp a float to a confidence-like 0-1 range."""
    return max(0.0, min(1.0, float(value)))


def floor_ratio(target):
    """Return target width divided by height, guarding empty boxes."""
    return target.width / target.height if target.height > 0 else 0.0


def is_standing(features, posture, up_angle=155.0):
    """Return whether the body looks upright enough for a recovery/up stage."""
    if posture in ('Standing', 'Arms up'):
        return True
    return (
        features.legs_visible
        and features.knee_angle >= up_angle
        and abs(features.torso_offset) < 0.34
    )


def is_squat_like(features, posture, down_angle=152.0):
    """Return whether both legs look like a compact squat."""
    if not features.legs_visible:
        return posture == 'Squat or sit'
    compact_stance = (
        features.knee_angle_gap <= 25.0
        and features.ankle_width_ratio <= 1.25
        and features.ankle_y_gap <= 0.08
        and features.hip_ankle_mid_x_gap <= 0.45
    )
    return features.knee_angle <= down_angle and compact_stance


def is_split_stance(features, min_angle_gap=18.0, min_stance_width=1.45, min_ankle_y_gap=0.05):
    """Return whether the leg skeleton looks more like a lunge than a squat."""
    if not features.legs_visible:
        return False
    strong_leg_angle_split = features.knee_angle_gap >= min_angle_gap
    vertical_split = features.ankle_y_gap >= min_ankle_y_gap and features.knee_y_gap >= min_ankle_y_gap * 0.7
    shifted_hip_base = features.hip_ankle_mid_x_gap >= 0.45
    strong_foot_spread = features.ankle_width_ratio >= min_stance_width
    moderate_foot_spread = features.ankle_width_ratio >= min_stance_width * 0.8
    return (
        strong_foot_spread and (strong_leg_angle_split or vertical_split or shifted_hip_base)
    ) or (
        moderate_foot_spread and shifted_hip_base and (strong_leg_angle_split or vertical_split)
    )


def is_lunge_candidate(features, down_angle=128.0, min_angle_gap=18.0, min_stance_width=1.45, min_ankle_y_gap=0.05):
    """Return whether the leg skeleton strongly favors lunge over squat."""
    if not features.legs_visible:
        return False
    min_knee = min(features.left_knee_angle, features.right_knee_angle)
    split_stance = is_split_stance(
        features,
        min_angle_gap=min_angle_gap,
        min_stance_width=min_stance_width,
        min_ankle_y_gap=min_ankle_y_gap,
    )
    structural_split = (
        features.ankle_width_ratio >= min_stance_width
        or (
            features.ankle_width_ratio >= min_stance_width * 0.8
            and features.hip_ankle_mid_x_gap >= 0.45
        )
    )
    asymmetry = (
        features.knee_angle_gap >= min_angle_gap
        or features.ankle_y_gap >= min_ankle_y_gap
        or features.hip_ankle_mid_x_gap >= 0.55
    )
    return min_knee <= down_angle + 18.0 and split_stance and structural_split and asymmetry


class ActionRegistry:
    """Run all HYROX action detectors."""

    def __init__(self, detectors):
        self.detectors = list(detectors)
        self.by_name = {detector.name: detector for detector in self.detectors}

    def statuses(self):
        """Return detector statuses without advancing state machines."""
        return {detector.name: detector.status() for detector in self.detectors}

    def reset_stages(self):
        """Clear in-progress stages while preserving completed counts."""
        for detector in self.detectors:
            detector.reset_stage()
        return self.statuses()

    def update(self, features, posture):
        """Run detectors with action arbitration to avoid duplicate counts."""
        statuses = {}
        squat_candidate = posture == 'Squat or sit' or is_squat_like(features, posture)
        lunge_candidate = is_lunge_candidate(features)

        burpee = self.by_name.get('burpee')
        if burpee is not None:
            statuses['burpee'] = burpee.update(features, posture)

        burpee_status = statuses.get('burpee')
        burpee_blocks = burpee_status is not None and (
            burpee_status.active
            or burpee_status.stage in ('pushup_down', 'pushup_up', 'stand_recovery', 'broad_jump')
        )

        lunge = self.by_name.get('lunge')
        if lunge is not None:
            lunge_in_progress = lunge.stage == 'down'
            statuses['lunge'] = lunge.update(
                features,
                posture,
                blocked=burpee_blocks or (squat_candidate and not (lunge_candidate or lunge_in_progress)),
            )

        lunge_status = statuses.get('lunge')
        lunge_blocks = lunge_status is not None and (
            lunge_status.active
            or lunge_status.stage == 'down'
            or lunge_candidate
        )
        if squat_candidate and not burpee_blocks and not lunge_candidate:
            lunge_blocks = False

        squat = self.by_name.get('squat')
        if squat is not None:
            statuses['squat'] = squat.update(features, posture, blocked=burpee_blocks or lunge_blocks)

        for detector in self.detectors:
            if detector.name not in statuses:
                status = detector.update(features, posture)
                statuses[status.name] = status
        return statuses


class SquatCounter:
    """Squat counter matching the original knee-angle hysteresis idea."""

    name = 'squat'

    def __init__(
        self,
        stable_frames=1,
        down_angle=152.0,
        up_angle=155.0,
        max_angle_gap=25.0,
        max_stance_width=1.25,
        max_ankle_y_gap=0.08,
        cooldown=0.35,
        min_down_time=0.4,
        down_frames=None,
        up_frames=None,
    ):
        fallback_frames = max(1, int(stable_frames))
        self.down_frames_required = max(1, int(down_frames or fallback_frames))
        self.up_frames_required = max(1, int(up_frames or fallback_frames))
        self.down_angle = float(down_angle)
        self.up_angle = float(up_angle)
        self.max_angle_gap = float(max_angle_gap)
        self.max_stance_width = float(max_stance_width)
        self.max_ankle_y_gap = float(max_ankle_y_gap)
        self.cooldown = max(0.0, float(cooldown))
        self.min_down_time = max(0.0, float(min_down_time))
        self.count = 0
        self.stage = 'unknown'
        self.down_frames = 0
        self.up_frames = 0
        self.last_count_time = 0.0
        self.down_started_at = 0.0

    def reset_stage(self):
        """Clear transient squat state while preserving count."""
        self.stage = 'unknown'
        self.down_frames = 0
        self.up_frames = 0
        self.down_started_at = 0.0

    def status(self):
        """Return current squat status without updating."""
        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=self.stage == 'down',
            updated_at=time.time(),
        )

    def update(self, features, posture, blocked=False):
        """Update squat state and return ActionStatus."""
        now = time.time()
        is_down = False
        is_up = False
        confidence = 0.0

        if features.legs_visible:
            compact_stance = (
                features.knee_angle_gap <= self.max_angle_gap
                and features.ankle_width_ratio <= self.max_stance_width
                and features.ankle_y_gap <= self.max_ankle_y_gap
                and features.hip_ankle_mid_x_gap <= 0.45
            )
            is_down = features.knee_angle <= self.down_angle and compact_stance
            is_up = features.knee_angle >= self.up_angle and abs(features.torso_offset) < 0.28
            confidence = clamp01(features.target.confidence)

        if posture == 'Squat or sit' and not blocked:
            is_down = True
        elif posture == 'Standing':
            is_up = True

        if blocked:
            is_down = False
            self.down_frames = 0
            if self.stage == 'down':
                self.stage = 'blocked'
                self.down_started_at = 0.0

        self.down_frames = self.down_frames + 1 if is_down else 0
        self.up_frames = self.up_frames + 1 if is_up else 0
        down_elapsed = now - self.down_started_at if self.down_started_at else 0.0

        if self.down_frames >= self.down_frames_required:
            if self.stage != 'down':
                self.stage = 'down'
                self.down_started_at = now
                down_elapsed = 0.0

        if self.up_frames >= self.up_frames_required:
            if (
                self.stage == 'down'
                and down_elapsed >= self.min_down_time
                and now - self.last_count_time >= self.cooldown
            ):
                self.count += 1
                self.last_count_time = now
            self.stage = 'up'
            self.down_started_at = 0.0

        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=is_down,
            confidence=confidence,
            details={
                'blocked': blocked,
                'knee_angle': features.knee_angle,
                'knee_angle_gap': features.knee_angle_gap,
                'ankle_width_ratio': features.ankle_width_ratio,
                'ankle_y_gap': features.ankle_y_gap,
                'hip_ankle_mid_x_gap': features.hip_ankle_mid_x_gap,
                'hips_low': features.hips_low,
                'down_elapsed': down_elapsed,
                'min_down_time': self.min_down_time,
            },
            updated_at=now,
        )


class LungeCounter:
    """Lunge counter using split-stance cues and down/up hysteresis."""

    name = 'lunge'

    def __init__(
        self,
        stable_frames=2,
        down_angle=128.0,
        up_angle=155.0,
        min_angle_gap=18.0,
        min_stance_width=1.15,
        min_ankle_y_gap=0.05,
        cooldown=0.45,
        down_frames=None,
        up_frames=None,
    ):
        fallback_frames = max(1, int(stable_frames))
        self.down_frames_required = max(1, int(down_frames or fallback_frames))
        self.up_frames_required = max(1, int(up_frames or fallback_frames))
        self.down_angle = float(down_angle)
        self.up_angle = float(up_angle)
        self.min_angle_gap = float(min_angle_gap)
        self.min_stance_width = float(min_stance_width)
        self.min_ankle_y_gap = float(min_ankle_y_gap)
        self.cooldown = max(0.0, float(cooldown))
        self.count = 0
        self.stage = 'unknown'
        self.down_frames = 0
        self.up_frames = 0
        self.last_count_time = 0.0

    def reset_stage(self):
        """Clear transient lunge state while preserving count."""
        self.stage = 'unknown'
        self.down_frames = 0
        self.up_frames = 0

    def status(self):
        """Return current lunge status without updating."""
        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=self.stage == 'down',
            updated_at=time.time(),
        )

    def update(self, features, posture, blocked=False):
        """Update lunge state and return ActionStatus."""
        now = time.time()
        is_down = False
        is_up = False
        active_leg = 'unknown'
        confidence = 0.0

        if features.legs_visible:
            min_knee = min(features.left_knee_angle, features.right_knee_angle)
            max_knee = max(features.left_knee_angle, features.right_knee_angle)
            active_leg = 'left' if features.left_knee_angle <= features.right_knee_angle else 'right'
            split_stance = is_split_stance(
                features,
                min_angle_gap=self.min_angle_gap,
                min_stance_width=self.min_stance_width,
                min_ankle_y_gap=self.min_ankle_y_gap,
            )
            even_squat_like = (
                features.left_knee_angle <= self.down_angle + 8.0
                and features.right_knee_angle <= self.down_angle + 8.0
                and features.knee_angle_gap < self.min_angle_gap
                and features.ankle_width_ratio < self.min_stance_width
            )
            is_down = min_knee <= self.down_angle and features.hips_low and split_stance and not even_squat_like
            is_up = min_knee >= self.up_angle and max_knee >= self.up_angle and abs(features.torso_offset) < 0.32
            confidence = clamp01(features.target.confidence)

        if blocked:
            is_down = False
            self.down_frames = 0
            if self.stage == 'down':
                self.stage = 'blocked'

        self.down_frames = self.down_frames + 1 if is_down else 0
        self.up_frames = self.up_frames + 1 if is_up else 0

        if self.down_frames >= self.down_frames_required:
            self.stage = 'down'

        if self.up_frames >= self.up_frames_required:
            if self.stage == 'down' and now - self.last_count_time >= self.cooldown:
                self.count += 1
                self.last_count_time = now
            self.stage = 'up'

        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=is_down,
            confidence=confidence,
            details={
                'blocked': blocked,
                'active_leg': active_leg,
                'left_knee_angle': features.left_knee_angle,
                'right_knee_angle': features.right_knee_angle,
                'knee_angle_gap': features.knee_angle_gap,
                'ankle_width_ratio': features.ankle_width_ratio,
                'ankle_y_gap': features.ankle_y_gap,
                'hip_ankle_mid_x_gap': features.hip_ankle_mid_x_gap,
            },
            updated_at=now,
        )


class BurpeeCounter:
    """Burpee broad jump counter using pushup and lateral-jump phases."""

    name = 'burpee'

    def __init__(
        self,
        stable_frames=1,
        squat_angle=152.0,
        up_angle=155.0,
        floor_width_ratio=1.15,
        floor_height_max=0.55,
        floor_center_y_min=0.45,
        flat_floor_width_ratio=1.25,
        flat_floor_height_max=0.38,
        flat_floor_center_y_min=0.52,
        no_arm_floor_frames=None,
        pushup_down_elbow_angle=118.0,
        pushup_up_elbow_angle=148.0,
        pushup_min_knee_angle=135.0,
        broad_jump_min_dx=0.16,
        stage_timeout=7.0,
        cooldown=0.8,
        floor_frames=None,
        up_frames=None,
        landing_frames=None,
    ):
        fallback_frames = max(1, int(stable_frames))
        self.floor_frames_required = max(1, int(floor_frames or fallback_frames))
        self.up_frames_required = max(1, int(up_frames or fallback_frames))
        self.landing_frames_required = max(1, int(landing_frames or fallback_frames))
        self.squat_angle = float(squat_angle)
        self.up_angle = float(up_angle)
        self.floor_width_ratio = float(floor_width_ratio)
        self.floor_height_max = float(floor_height_max)
        self.floor_center_y_min = float(floor_center_y_min)
        self.flat_floor_width_ratio = float(flat_floor_width_ratio)
        self.flat_floor_height_max = float(flat_floor_height_max)
        self.flat_floor_center_y_min = float(flat_floor_center_y_min)
        self.no_arm_floor_frames_required = max(
            1,
            int(no_arm_floor_frames or self.floor_frames_required + 1),
        )
        self.pushup_down_elbow_angle = float(pushup_down_elbow_angle)
        self.pushup_up_elbow_angle = float(pushup_up_elbow_angle)
        self.pushup_min_knee_angle = float(pushup_min_knee_angle)
        self.broad_jump_min_dx = float(broad_jump_min_dx)
        self.stage_timeout = max(0.5, float(stage_timeout))
        self.cooldown = max(0.0, float(cooldown))
        self.count = 0
        self.stage = 'unknown'
        self.stage_started_at = 0.0
        self.floor_start_x = None
        self.stand_x = None
        self.max_jump_dx = 0.0
        self.floor_frames = 0
        self.up_frames = 0
        self.landing_frames = 0
        self.last_count_time = 0.0

    def reset_stage(self):
        """Clear transient burpee state while preserving count."""
        self.stage = 'unknown'
        self.stage_started_at = 0.0
        self.floor_start_x = None
        self.stand_x = None
        self.max_jump_dx = 0.0
        self.floor_frames = 0
        self.up_frames = 0
        self.landing_frames = 0

    def status(self):
        """Return current burpee status without updating."""
        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=self.stage in ('pushup_down', 'pushup_up', 'stand_recovery', 'broad_jump'),
            updated_at=time.time(),
        )

    def set_stage(self, stage, now, target=None):
        """Move to a new stage and capture useful reference positions."""
        if self.stage == stage:
            return
        self.stage = stage
        self.stage_started_at = now
        if stage == 'pushup_down' and target is not None and self.floor_start_x is None:
            self.floor_start_x = target.center_x
            self.max_jump_dx = 0.0
        if stage == 'stand_recovery' and target is not None:
            self.stand_x = target.center_x

    def timed_out(self, now):
        """Return whether the current in-progress stage has gone stale."""
        return self.stage not in ('unknown', 'up') and now - self.stage_started_at > self.stage_timeout

    def update(self, features, posture):
        """Update burpee sequence state and return ActionStatus."""
        now = time.time()
        target = features.target
        confidence = clamp01(target.confidence)
        if self.timed_out(now):
            self.set_stage('unknown', now)
            self.floor_start_x = None
            self.stand_x = None
            self.max_jump_dx = 0.0

        squat_entry = False
        compact_squat_entry = False
        lunge_entry = False
        is_floor = False
        is_up = False
        pushup_down = False
        pushup_up = False
        raw_floor_like = False
        box_floor_like = False
        strict_flat_floor = False
        no_arm_floor_entry = False
        legs_extended = False
        broad_jump = False
        landing = False
        jump_dx = 0.0

        if features.legs_visible:
            compact_squat_entry = is_squat_like(features, posture, down_angle=self.squat_angle)
            squat_entry = compact_squat_entry
            lunge_entry = is_lunge_candidate(features)
            is_up = is_standing(features, posture, up_angle=self.up_angle)

        if posture == 'Squat or sit':
            squat_entry = True

        ratio = floor_ratio(target)
        if target.detected:
            box_floor_like = (
                ratio >= self.floor_width_ratio
                and target.height <= self.floor_height_max
                and target.center_y >= self.floor_center_y_min
            )
            raw_floor_like = box_floor_like
            if features.full_body:
                skeleton_low = features.target.height <= self.floor_height_max + 0.12
                hip_shoulder_close = features.torso_height <= 0.22
                raw_floor_like = raw_floor_like or (skeleton_low and hip_shoulder_close and target.center_y >= 0.42)
            strict_flat_floor = (
                ratio >= self.flat_floor_width_ratio
                and target.height <= self.flat_floor_height_max
                and target.center_y >= self.flat_floor_center_y_min
            )

        legs_extended = not features.legs_visible or features.knee_angle >= self.pushup_min_knee_angle
        is_floor = raw_floor_like and (
            legs_extended
            or self.stage in ('pushup_down', 'pushup_up', 'stand_recovery', 'broad_jump')
        )
        no_arm_floor_entry = (
            not features.arms_visible
            and strict_flat_floor
            and not lunge_entry
            and self.floor_frames >= self.no_arm_floor_frames_required - 1
        )

        if features.arms_visible:
            elbow_angle = min(features.left_elbow_angle, features.right_elbow_angle)
            pushup_down = (
                box_floor_like
                and legs_extended
                and not lunge_entry
                and elbow_angle <= self.pushup_down_elbow_angle
            )
            pushup_up = (
                self.stage == 'pushup_down'
                and is_floor
                and legs_extended
                and not lunge_entry
                and max(features.left_elbow_angle, features.right_elbow_angle) >= self.pushup_up_elbow_angle
            )
        else:
            pushup_down = no_arm_floor_entry
            pushup_up = (
                self.stage == 'pushup_down'
                and not is_floor
                and not is_up
                and not squat_entry
                and not lunge_entry
            )

        self.floor_frames = self.floor_frames + 1 if is_floor else 0
        self.up_frames = self.up_frames + 1 if is_up else 0

        if self.stage in ('unknown', 'up') and pushup_down:
            self.set_stage('pushup_down', now, target)

        if self.stage == 'floor_entry' and (is_up or squat_entry):
            self.set_stage('up', now, target)

        if self.stage == 'floor_entry' and self.floor_frames >= self.floor_frames_required:
            if pushup_down:
                self.set_stage('pushup_down', now, target)

        if self.stage == 'pushup_down' and pushup_up:
            self.set_stage('pushup_up', now, target)

        if self.stage == 'pushup_up' and self.up_frames >= self.up_frames_required:
            self.set_stage('stand_recovery', now, target)

        if self.stage in ('pushup_up', 'stand_recovery', 'broad_jump') and target.detected:
            references = [value for value in (self.floor_start_x, self.stand_x) if value is not None]
            if references:
                jump_dx = max(abs(target.center_x - value) for value in references)
                self.max_jump_dx = max(self.max_jump_dx, jump_dx)

        if self.stage == 'stand_recovery' and target.detected:
            broad_jump = self.max_jump_dx >= self.broad_jump_min_dx
            if broad_jump:
                self.set_stage('broad_jump', now, target)

        if self.stage == 'broad_jump':
            landing = is_up or squat_entry
            self.landing_frames = self.landing_frames + 1 if landing else 0
            if self.landing_frames >= self.landing_frames_required and now - self.last_count_time >= self.cooldown:
                self.count += 1
                self.last_count_time = now
                self.set_stage('up', now, target)
                self.floor_start_x = None
                self.stand_x = None
                self.max_jump_dx = 0.0
                self.landing_frames = 0
        else:
            self.landing_frames = 0

        return ActionStatus(
            name=self.name,
            count=self.count,
            stage=self.stage,
            active=(
                self.stage in ('pushup_down', 'pushup_up', 'stand_recovery', 'broad_jump')
                or (strict_flat_floor and not lunge_entry)
            ),
            confidence=confidence,
            details={
                'squat_entry': squat_entry,
                'compact_squat_entry': compact_squat_entry,
                'lunge_entry': lunge_entry,
                'raw_floor_like': raw_floor_like,
                'box_floor_like': box_floor_like,
                'strict_flat_floor': strict_flat_floor,
                'no_arm_floor_entry': no_arm_floor_entry,
                'is_floor': is_floor,
                'legs_extended': legs_extended,
                'arms_visible': features.arms_visible,
                'pushup_down': pushup_down,
                'pushup_up': pushup_up,
                'broad_jump': broad_jump,
                'landing': landing,
                'stand_x': self.stand_x,
                'floor_start_x': self.floor_start_x,
                'current_x': target.center_x,
                'jump_dx': jump_dx,
                'max_jump_dx': self.max_jump_dx,
                'target_width': target.width,
                'target_height': target.height,
                'target_center_y': target.center_y,
                'floor_width_ratio': ratio,
                'flat_floor_width_ratio': self.flat_floor_width_ratio,
                'flat_floor_height_max': self.flat_floor_height_max,
                'flat_floor_center_y_min': self.flat_floor_center_y_min,
                'no_arm_floor_frames_required': self.no_arm_floor_frames_required,
                'knee_angle': features.knee_angle,
                'pushup_min_knee_angle': self.pushup_min_knee_angle,
                'left_elbow_angle': features.left_elbow_angle,
                'right_elbow_angle': features.right_elbow_angle,
            },
            updated_at=now,
        )


def _arg(args, name, default):
    return getattr(args, name, default)


def build_action_registry(args):
    """Build the package action-detector registry from CLI arguments."""
    return ActionRegistry(
        [
            SquatCounter(
                stable_frames=_arg(args, 'squat_stable_frames', 1),
                down_angle=_arg(args, 'squat_down_angle', 152.0),
                up_angle=_arg(args, 'squat_up_angle', 155.0),
                max_angle_gap=_arg(args, 'squat_max_angle_gap', 25.0),
                max_stance_width=_arg(args, 'squat_max_stance_width', 1.25),
                max_ankle_y_gap=_arg(args, 'squat_max_ankle_y_gap', 0.08),
                cooldown=_arg(args, 'squat_cooldown', 0.35),
                min_down_time=_arg(args, 'squat_min_down_time', 0.4),
                down_frames=_arg(args, 'squat_down_frames', None),
                up_frames=_arg(args, 'squat_up_frames', None),
            ),
            LungeCounter(
                stable_frames=_arg(args, 'lunge_stable_frames', 2),
                down_angle=_arg(args, 'lunge_down_angle', 128.0),
                up_angle=_arg(args, 'lunge_up_angle', 155.0),
                min_angle_gap=_arg(args, 'lunge_min_angle_gap', 18.0),
                min_stance_width=_arg(args, 'lunge_min_stance_width', 1.45),
                min_ankle_y_gap=_arg(args, 'lunge_min_ankle_y_gap', 0.05),
                cooldown=_arg(args, 'lunge_cooldown', 0.45),
                down_frames=_arg(args, 'lunge_down_frames', None),
                up_frames=_arg(args, 'lunge_up_frames', None),
            ),
            BurpeeCounter(
                stable_frames=_arg(args, 'burpee_stable_frames', 1),
                squat_angle=_arg(args, 'burpee_squat_angle', 152.0),
                up_angle=_arg(args, 'burpee_up_angle', 155.0),
                floor_width_ratio=_arg(args, 'burpee_floor_width_ratio', 1.15),
                floor_height_max=_arg(args, 'burpee_floor_height_max', 0.55),
                floor_center_y_min=_arg(args, 'burpee_floor_center_y_min', 0.45),
                flat_floor_width_ratio=_arg(args, 'burpee_flat_floor_width_ratio', 1.25),
                flat_floor_height_max=_arg(args, 'burpee_flat_floor_height_max', 0.38),
                flat_floor_center_y_min=_arg(args, 'burpee_flat_floor_center_y_min', 0.52),
                no_arm_floor_frames=_arg(args, 'burpee_no_arm_floor_frames', None),
                pushup_down_elbow_angle=_arg(args, 'burpee_pushup_down_elbow_angle', 118.0),
                pushup_up_elbow_angle=_arg(args, 'burpee_pushup_up_elbow_angle', 148.0),
                pushup_min_knee_angle=_arg(args, 'burpee_pushup_min_knee_angle', 135.0),
                broad_jump_min_dx=_arg(args, 'burpee_broad_jump_min_dx', 0.16),
                stage_timeout=_arg(args, 'burpee_stage_timeout', 7.0),
                cooldown=_arg(args, 'burpee_cooldown', 0.8),
                floor_frames=_arg(args, 'burpee_floor_frames', None),
                up_frames=_arg(args, 'burpee_up_frames', None),
                landing_frames=_arg(args, 'burpee_landing_frames', None),
            ),
        ]
    )
