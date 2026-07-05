"""
超声波传感器接口
依赖: Raspbot_Lib.Raspbot (I2C: 0x2B, 寄存器 0x1A/0x1B)
"""

import time
from collections import deque
from Raspbot_Lib import Raspbot

bot = Raspbot()
_filter_buf = deque(maxlen=5)


def read_ultrasonic():
    """读取原始距离 (mm), 失败返回 9999"""
    try:
        h = bot.read_data_array(0x1b, 1)[0]
        l = bot.read_data_array(0x1a, 1)[0]
        dis = (h << 8) | l
        if 0 < dis < 9999:
            _filter_buf.append(dis)
        return dis
    except:
        return 9999


def read_filtered():
    """中位数滤波距离 (mm), 无有效数据时返回 None"""
    read_ultrasonic()
    if len(_filter_buf) == 0:
        return None
    s = sorted(_filter_buf)
    return s[len(s) // 2]


def on():
    bot.Ctrl_Ulatist_Switch(1)
    time.sleep(0.1)


def off():
    bot.Ctrl_Ulatist_Switch(0)


def clear_buffer():
    _filter_buf.clear()
