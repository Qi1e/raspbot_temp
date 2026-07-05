"""
避障状态机 — 纯决策，零硬件依赖
弧形绕行: 斜向左前绕过 → 等步数斜向右前回正 → 恢复直行
"""

# —— 阈值 (mm) ——
OBSTACLE_ENTER_MM = 280
OBSTACLE_TOO_CLOSE_MM = 250
OBSTACLE_EXIT_MM = 420
OBSTACLE_EXIT_STABLE_COUNT = 3

# —— 运动参数 ——
BYPASS_SPEED = 25
BYPASS_PULSE = 0.25
MAX_STEPS = 15
BACKWARD_SPEED = 20
BACKWARD_PULSE = 0.15

# —— 阶段 ——
PHASE_NORMAL = 'normal'
PHASE_BYPASS = 'bypass'
PHASE_RETURN = 'return'
PHASE_FAIL = 'fail'

AVOID_NORMAL = 'normal_follow'
AVOID_ACTIVE = 'obstacle_avoid'

obstacle_state = AVOID_NORMAL
exit_stable_count = 0

_bypass_dir = 'left'
_bypass_step = 0
_bypass_steps_taken = 0
_return_step = 0
_phase = PHASE_NORMAL


def update(distance_mm, forward_needed=True):
    """
    每帧调用一次，返回 (action, direction)。
    action: 'normal' | 'backward' | 'diagonal_left' | 'diagonal_right' | 'hold' | 'stop'
    """
    global obstacle_state, exit_stable_count
    global _bypass_dir, _bypass_step, _bypass_steps_taken, _return_step, _phase

    if distance_mm is None:
        return 'stop', None

    # —— NORMAL: 检测到障碍 → 进入绕行 ——
    if _phase == PHASE_NORMAL:
        if forward_needed and distance_mm < OBSTACLE_ENTER_MM:
            obstacle_state = AVOID_ACTIVE
            _bypass_dir = 'left'
            _bypass_step = 0
            _bypass_steps_taken = 0
            _return_step = 0
            _phase = PHASE_BYPASS
            return 'diagonal_left', None
        else:
            return 'normal', None

    # —— 安全兜底: 过近 → 后退 ——
    if distance_mm < OBSTACLE_TOO_CLOSE_MM:
        exit_stable_count = 0
        return 'backward', None

    # —— BYPASS: 斜向绕行中 ——
    if _phase == PHASE_BYPASS:
        _bypass_step += 1

        if distance_mm >= OBSTACLE_EXIT_MM:
            exit_stable_count += 1
            if exit_stable_count >= OBSTACLE_EXIT_STABLE_COUNT:
                _bypass_steps_taken = _bypass_step
                _return_step = 0
                _phase = PHASE_RETURN
                return ('diagonal_left', None) if _bypass_dir == 'left' else ('diagonal_right', None)
        else:
            exit_stable_count = 0

        if _bypass_step >= MAX_STEPS:
            if _bypass_dir == 'left':
                _bypass_dir = 'right'
                _bypass_step = 0
            else:
                _phase = PHASE_FAIL
                return 'backward', None

        return ('diagonal_left', None) if _bypass_dir == 'left' else ('diagonal_right', None)

    # —— RETURN: 斜向回正 ——
    if _phase == PHASE_RETURN:
        _return_step += 1
        return_dir = 'right' if _bypass_dir == 'left' else 'left'
        if _return_step >= _bypass_steps_taken:
            obstacle_state = AVOID_NORMAL
            exit_stable_count = 0
            _phase = PHASE_NORMAL
            return 'normal', None
        return ('diagonal_left', None) if return_dir == 'left' else ('diagonal_right', None)

    # —— FAIL: 后退退出 ——
    if _phase == PHASE_FAIL:
        if distance_mm >= OBSTACLE_EXIT_MM:
            obstacle_state = AVOID_NORMAL
            exit_stable_count = 0
            _phase = PHASE_NORMAL
            return 'normal', None
        return 'backward', None

    return 'hold', None


def reset():
    """重置状态机 (启动时调用)"""
    global obstacle_state, exit_stable_count
    global _bypass_dir, _bypass_step, _bypass_steps_taken, _return_step, _phase
    obstacle_state = AVOID_NORMAL
    exit_stable_count = 0
    _bypass_dir = 'left'
    _bypass_step = 0
    _bypass_steps_taken = 0
    _return_step = 0
    _phase = PHASE_NORMAL
