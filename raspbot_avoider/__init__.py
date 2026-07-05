"""
raspbot_avoider — 纯超声波弧形避障模块

外部只需:
    import raspbot_avoider
    raspbot_avoider.start()      # 启动后台避障
    raspbot_avoider.is_active()  # 查询是否避障中
    raspbot_avoider.stop()       # 安全停止

依赖:
    Raspbot_Lib (硬件驱动, I2C: 0x2B)
    McLumk_Wheel_Sports (麦克纳姆轮运动)
"""

from .avoider import start, stop, is_active

__all__ = ['start', 'stop', 'is_active']
