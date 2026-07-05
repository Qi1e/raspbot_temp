"""
避障主循环 (后台线程) + 启停接口
依赖: ultrasonic, state_machine, McLumk_Wheel_Sports
"""

import time
import threading

from McLumk_Wheel_Sports import (
    move_forward, move_backward, move_left, move_right,
    move_diagonal_left_front as move_diagonal_left,
    move_diagonal_right_front as move_diagonal_right,
    stop_robot,
)

from . import ultrasonic
from . import state_machine

_running = False
_thread = None
SPEED = 25  # 正常前进速度


def _execute(action, direction=None):
    """执行单次避障动作 (脉冲式)"""
    if action == 'normal':
        move_forward(SPEED)

    elif action == 'backward':
        move_backward(state_machine.BACKWARD_SPEED)
        time.sleep(state_machine.BACKWARD_PULSE)
        stop_robot()

    elif action == 'diagonal_left':
        move_diagonal_left(state_machine.BYPASS_SPEED)
        time.sleep(state_machine.BYPASS_PULSE)
        stop_robot()

    elif action == 'diagonal_right':
        move_diagonal_right(state_machine.BYPASS_SPEED)
        time.sleep(state_machine.BYPASS_PULSE)
        stop_robot()

    elif action == 'strafe':
        if direction == 'left':
            move_left(state_machine.BYPASS_SPEED)
        else:
            move_right(state_machine.BYPASS_SPEED)
        time.sleep(state_machine.BYPASS_PULSE)
        stop_robot()

    elif action in ('hold', 'stop'):
        stop_robot()


def _loop():
    """主循环 (运行在后台线程)"""
    global _running

    state_machine.reset()
    ultrasonic.clear_buffer()
    ultrasonic.on()

    prev_print = time.time()

    while _running:
        t0 = time.time()

        distance = ultrasonic.read_filtered()
        action, direction = state_machine.update(distance)
        _execute(action, direction)

        if time.time() - prev_print >= 1.0:
            prev_print = time.time()
            print(f'[避障] 距离={distance}mm | 动作={action} | 阶段={state_machine._phase}')

        elapsed = time.time() - t0
        if elapsed < 0.05:
            time.sleep(0.05 - elapsed)

    stop_robot()
    ultrasonic.off()


def start():
    """启动避障 (后台线程)"""
    global _running, _thread

    if _running:
        return

    _running = True
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop():
    """停止避障"""
    global _running
    _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=1.0)
    stop_robot()
    ultrasonic.off()


def is_active():
    """是否正在避障中"""
    return state_machine._phase != state_machine.PHASE_NORMAL
