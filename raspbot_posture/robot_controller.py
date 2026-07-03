"""Posture target controller for pan/tilt and chassis steering."""

import threading
import time

from .robot_driver import RobotDriver
from .target_filter import TargetFilter


class PostureRobotController:
    """Conservative controller using HumanTarget snapshots."""

    ACTION_POSTURES = {"Squat or sit", "Arms up", "T pose", "Leaning left", "Leaning right"}

    def __init__(self, args, analysis_state, stop_event):
        self.args = args
        self.analysis_state = analysis_state
        self.stop_event = stop_event
        self.driver = RobotDriver(args)
        self.filter = TargetFilter(args.target_smoothing, args.target_min_confidence)
        self.last_servo_update = 0.0
        self.last_body_pulse = 0.0
        self.last_log = 0.0
        self.pan_offset_started_at = None
        self.standing_started_at = None
        self.action_freeze_until = 0.0

    def start(self):
        """Start the background control loop."""
        worker = threading.Thread(target=self.loop, name="posture-robot-control")
        worker.daemon = True
        worker.start()
        return worker

    def loop(self):
        print("Robot control loop started.")
        try:
            while not self.stop_event.is_set():
                self.step()
                time.sleep(max(0.02, self.args.control_interval))
        finally:
            self.driver.stop()
            if self.args.reset_servo_on_exit:
                self.driver.reset_servos()

    def step(self):
        now = time.time()
        analysis = self.analysis_state.get()
        target = analysis.target
        smoothed = self.filter.update(target)

        if self.target_is_stale(target, now):
            self.driver.stop()
            if self.args.return_center_on_lost:
                self.return_servos_to_center(now)
            self.debug_status(now, "target stale/lost", smoothed, analysis)
            return

        self.update_action_freeze(now, analysis, target)
        self.update_pan_tilt(now, smoothed)
        self.update_body_turn(now)
        self.update_distance(now, smoothed)
        self.debug_status(now, "tracking", smoothed, analysis)

    def target_is_stale(self, target, now):
        if not target.detected:
            return True
        if target.confidence < self.args.target_min_confidence:
            return True
        return now - target.updated_at > self.args.target_timeout

    def update_action_freeze(self, now, analysis, target):
        squat = analysis.actions.get("squat") if analysis.actions else None
        action_active = target.posture in self.ACTION_POSTURES
        action_active = action_active or (squat is not None and (squat.active or squat.stage == "down"))

        if action_active and self.args.freeze_during_action:
            self.action_freeze_until = now + self.args.action_freeze_time

        if target.posture == "Standing":
            if self.standing_started_at is None:
                self.standing_started_at = now
        else:
            self.standing_started_at = None

    def update_pan_tilt(self, now, target):
        if now - self.last_servo_update < self.args.servo_interval:
            return

        moved = False
        err_x = target.x - 0.5
        err_y = target.y - 0.5

        if abs(err_x) > self.args.pan_deadzone:
            direction = -1 if err_x > 0 else 1
            if self.args.invert_pan:
                direction *= -1
            step = min(self.args.servo_step, abs(err_x) * self.args.servo_gain)
            self.driver.set_servo(1, self.driver.pan_angle + direction * step, reason="pan tracking")
            moved = True

        if abs(err_y) > self.args.tilt_deadzone:
            direction = -1 if err_y > 0 else 1
            if self.args.invert_tilt:
                direction *= -1
            step = min(self.args.servo_step, abs(err_y) * self.args.servo_gain)
            self.driver.set_servo(2, self.driver.tilt_angle + direction * step, reason="tilt tracking")
            moved = True

        if moved:
            self.last_servo_update = now

    def update_body_turn(self, now):
        pan_offset = self.driver.pan_angle - self.args.pan_center
        if abs(pan_offset) < self.args.pan_body_threshold:
            self.pan_offset_started_at = None
            return

        if self.pan_offset_started_at is None:
            self.pan_offset_started_at = now
            return

        if now - self.pan_offset_started_at < self.args.pan_body_hold:
            return
        if now - self.last_body_pulse < self.args.body_cooldown:
            return

        direction = "left" if pan_offset > 0 else "right"
        self.driver.pulse_turn(direction, self.args.body_turn_speed, self.args.body_pulse)
        self.last_body_pulse = time.time()
        self.pan_offset_started_at = self.last_body_pulse

    def update_distance(self, now, target):
        if not self.args.distance_control:
            return
        if self.args.freeze_during_action and now < self.action_freeze_until:
            return
        if self.standing_started_at is None:
            return
        if now - self.standing_started_at < self.args.distance_stable_time:
            return
        if now - self.last_body_pulse < self.args.body_cooldown:
            return
        if abs(target.x - 0.5) > self.args.distance_x_deadzone:
            return

        if target.area < self.args.target_area_min:
            self.driver.pulse_forward(self.args.body_forward_speed, self.args.body_pulse)
            self.last_body_pulse = time.time()
        elif target.area > self.args.target_area_max:
            self.driver.pulse_backward(self.args.body_backward_speed, self.args.body_pulse)
            self.last_body_pulse = time.time()

    def return_servos_to_center(self, now):
        if now - self.last_servo_update < self.args.servo_interval:
            return

        moved = False
        if abs(self.driver.pan_angle - self.args.pan_center) > 0.5:
            delta = self.args.servo_step if self.driver.pan_angle < self.args.pan_center else -self.args.servo_step
            self.driver.set_servo(1, self.driver.pan_angle + delta, reason="lost target center pan")
            moved = True
        if abs(self.driver.tilt_angle - self.args.tilt_center) > 0.5:
            delta = self.args.servo_step if self.driver.tilt_angle < self.args.tilt_center else -self.args.servo_step
            self.driver.set_servo(2, self.driver.tilt_angle + delta, reason="lost target center tilt")
            moved = True
        if moved:
            self.last_servo_update = now

    def debug_status(self, now, label, target, analysis):
        if not self.args.control_debug:
            return
        if now - self.last_log < self.args.control_log_interval:
            return
        self.last_log = now
        print(
            f"{label}: x={target.x:.3f} y={target.y:.3f} area={target.area:.3f} "
            f"conf={target.confidence:.2f} posture={analysis.posture} "
            f"pan={self.driver.pan_angle:.1f} tilt={self.driver.tilt_angle:.1f}"
        )
