"""Non-blocking ultrasonic obstacle avoidance decisions."""

from dataclasses import dataclass, field

from .tracking_control import MotionGoal


PHASE_NORMAL = "normal"
PHASE_BYPASS = "bypass"
PHASE_RETURN = "return"
PHASE_FAIL = "fail"


@dataclass(frozen=True)
class AvoidanceDecision:
    enabled: bool = False
    active: bool = False
    distance_mm: object = None
    phase: str = PHASE_NORMAL
    reason: str = "disabled"
    goal: MotionGoal = field(default_factory=lambda: MotionGoal(active=False, reason="obstacle avoidance disabled"))
    cooldown_remaining_s: float = 0.0


class ObstacleAvoidanceController:
    """Convert filtered ultrasonic distance into a high-priority motion goal."""

    def __init__(self, args, enabled=True):
        self.args = args
        self.enabled = bool(enabled)
        self.phase = PHASE_NORMAL
        self.bypass_dir = "left"
        self.bypass_step = 0
        self.bypass_steps_taken = 0
        self.return_step = 0
        self.enter_count = 0
        self.exit_count = 0
        self.cooldown_until = 0.0
        self.started_at = 0.0
        self.next_step_at = 0.0
        self.fail_started_at = 0.0
        self.fail_backup_until = 0.0
        self.fail_retry_at = 0.0

    def update(self, distance_mm, now):
        if not self.enabled:
            return AvoidanceDecision(enabled=False)

        cooldown = max(0.0, self.cooldown_until - now)
        if distance_mm is None:
            if self.phase == PHASE_NORMAL:
                return self._decision(False, distance_mm, "no ultrasonic sample", cooldown)
            return self._decision(True, distance_mm, "ultrasonic unavailable", cooldown, 0.0, 90.0)

        if self.phase not in (PHASE_NORMAL, PHASE_FAIL) and now - self.started_at > self.args.obstacle_max_active_time:
            self._enter_fail(now)

        if self.phase == PHASE_NORMAL:
            return self._update_normal(distance_mm, now, cooldown)

        if self.phase != PHASE_FAIL and distance_mm < self.args.obstacle_too_close_mm:
            self.exit_count = 0
            return self._decision(
                True,
                distance_mm,
                "obstacle too close",
                cooldown,
                self.args.obstacle_backward_speed,
                self.args.obstacle_backward_direction_degrees,
            )

        if self.phase == PHASE_BYPASS:
            return self._update_bypass(distance_mm, now, cooldown)
        if self.phase == PHASE_RETURN:
            return self._update_return(distance_mm, now, cooldown)
        if self.phase == PHASE_FAIL:
            return self._update_fail(distance_mm, now, cooldown)

        self.phase = PHASE_NORMAL
        return self._decision(False, distance_mm, "unknown obstacle phase reset", cooldown)

    def _update_normal(self, distance_mm, now, cooldown):
        emergency = distance_mm < self.args.obstacle_too_close_mm
        in_enter_zone = distance_mm < self.args.obstacle_enter_mm
        if in_enter_zone:
            self.enter_count += 1
        else:
            self.enter_count = 0

        if not emergency and cooldown > 0.0:
            return self._decision(False, distance_mm, "obstacle cooldown", cooldown)

        if emergency:
            self._start_bypass(now, "left")
            return self._decision(
                True,
                distance_mm,
                "obstacle emergency enter",
                cooldown,
                self.args.obstacle_backward_speed,
                self.args.obstacle_backward_direction_degrees,
            )

        if self.enter_count >= self.args.obstacle_enter_stable_count:
            self._start_bypass(now, "left")
            return self._bypass_decision(distance_mm, cooldown, "obstacle confirmed")

        return self._decision(False, distance_mm, "path clear", cooldown)

    def _update_bypass(self, distance_mm, now, cooldown):
        self._advance_step(now)
        if distance_mm >= self.args.obstacle_exit_mm:
            self.exit_count += 1
            if self.exit_count >= self.args.obstacle_exit_stable_count:
                self.phase = PHASE_RETURN
                self.return_step = 0
                self.bypass_steps_taken = max(1, self.bypass_step)
                self.next_step_at = now + self.args.obstacle_pulse
                return self._return_decision(distance_mm, cooldown, "obstacle cleared")
        else:
            self.exit_count = 0

        if self.bypass_step >= self.args.obstacle_max_steps:
            if self.bypass_dir == "left":
                self.bypass_dir = "right"
                self.bypass_step = 0
                self.exit_count = 0
                self.next_step_at = now + self.args.obstacle_pulse
            else:
                self._enter_fail(now)
                return self._decision(
                    True,
                    distance_mm,
                    "obstacle bypass failed",
                    cooldown,
                    self.args.obstacle_backward_speed,
                    self.args.obstacle_backward_direction_degrees,
                )

        return self._bypass_decision(distance_mm, cooldown, f"bypass {self.bypass_dir}")

    def _update_return(self, distance_mm, now, cooldown):
        self._advance_step(now, returning=True)
        if self.return_step >= self.bypass_steps_taken:
            self._finish(now)
            return self._decision(False, distance_mm, "obstacle avoidance complete", self.args.obstacle_cooldown)
        return self._return_decision(distance_mm, cooldown, "return to path")

    def _update_fail(self, distance_mm, now, cooldown):
        if distance_mm >= self.args.obstacle_exit_mm:
            self.exit_count += 1
            if self.exit_count >= self.args.obstacle_exit_stable_count:
                self._finish(now)
                return self._decision(False, distance_mm, "obstacle fail recovered", self.args.obstacle_cooldown)
        else:
            self.exit_count = 0

        if now >= self.fail_retry_at:
            if distance_mm < self.args.obstacle_too_close_mm:
                self.fail_backup_until = now + self.args.obstacle_fail_backup_time
                self.fail_retry_at = self.fail_backup_until + self.args.obstacle_fail_stop_time
                return self._decision(
                    True,
                    distance_mm,
                    "obstacle fail retry backup",
                    cooldown,
                    self.args.obstacle_backward_speed,
                    self.args.obstacle_backward_direction_degrees,
                )
            retry_dir = "left" if self.bypass_dir == "right" else "right"
            self._start_bypass(now, retry_dir)
            return self._bypass_decision(distance_mm, cooldown, f"obstacle fail retry {retry_dir}")

        if now >= self.fail_backup_until:
            return self._decision(True, distance_mm, "obstacle fail stopped", cooldown, 0.0, 90.0)

        return self._decision(
            True,
            distance_mm,
            "obstacle fail backup",
            cooldown,
            self.args.obstacle_backward_speed,
            self.args.obstacle_backward_direction_degrees,
        )

    def _start_bypass(self, now, direction):
        self.phase = PHASE_BYPASS
        self.bypass_dir = direction
        self.bypass_step = 0
        self.bypass_steps_taken = 0
        self.return_step = 0
        self.exit_count = 0
        self.started_at = now
        self.next_step_at = now + self.args.obstacle_pulse

    def _enter_fail(self, now):
        if self.phase == PHASE_FAIL:
            return
        self.phase = PHASE_FAIL
        self.exit_count = 0
        self.fail_started_at = now
        self.fail_backup_until = now + self.args.obstacle_fail_backup_time
        self.fail_retry_at = self.fail_backup_until + self.args.obstacle_fail_stop_time

    def _finish(self, now):
        self.phase = PHASE_NORMAL
        self.enter_count = 0
        self.exit_count = 0
        self.bypass_step = 0
        self.return_step = 0
        self.fail_started_at = 0.0
        self.fail_backup_until = 0.0
        self.fail_retry_at = 0.0
        self.cooldown_until = now + self.args.obstacle_cooldown

    def _advance_step(self, now, returning=False):
        if now < self.next_step_at:
            return
        steps = max(1, int((now - self.next_step_at) // self.args.obstacle_pulse) + 1)
        if returning:
            self.return_step += steps
        else:
            self.bypass_step += steps
        self.next_step_at += steps * self.args.obstacle_pulse

    def _bypass_decision(self, distance_mm, cooldown, reason):
        direction = (
            self.args.obstacle_left_direction_degrees
            if self.bypass_dir == "left"
            else self.args.obstacle_right_direction_degrees
        )
        return self._decision(True, distance_mm, reason, cooldown, self.args.obstacle_speed, direction)

    def _return_decision(self, distance_mm, cooldown, reason):
        return_dir = "right" if self.bypass_dir == "left" else "left"
        direction = (
            self.args.obstacle_left_direction_degrees
            if return_dir == "left"
            else self.args.obstacle_right_direction_degrees
        )
        return self._decision(True, distance_mm, reason, cooldown, self.args.obstacle_return_speed, direction)

    def _decision(self, active, distance_mm, reason, cooldown, speed=0.0, direction=90.0):
        goal = MotionGoal(
            active=bool(active and speed > 0.0),
            direction_degrees=float(direction),
            speed=float(speed),
            expires_at=1e30 if active and speed > 0.0 else 0.0,
            reason=reason,
        )
        return AvoidanceDecision(
            enabled=True,
            active=bool(active),
            distance_mm=distance_mm,
            phase=self.phase,
            reason=reason,
            goal=goal,
            cooldown_remaining_s=max(0.0, cooldown),
        )
