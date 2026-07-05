# HYROX Tools

## Pushover 手表通知验证

这个样例用于验证链路：

```text
电脑脚本 -> Pushover -> iPhone 通知 -> vivo WATCH GT2 同步通知并震动
```

当前结论：

- 该链路已经在 iPhone 15 Pro + vivo WATCH GT2 上验证成功；
- 电脑端调用 Pushover API 后，iPhone 可以收到通知；
- vivo WATCH GT2 可以同步 iPhone 通知并产生震动；
- 因此 MVP 阶段不需要自研 iOS App，也不需要直接控制 vivo 手表蓝牙协议。

推荐定位：

```text
Raspbot 小车 -> 电脑后端 -> Pushover API -> iPhone -> vivo WATCH GT2
```

其中小车只需要继续上传训练事件，手表通知由电脑端后端负责。

准备：

1. 在 iPhone 安装并登录 Pushover。
2. 在 Pushover 网页端创建一个应用，获得 `APP_TOKEN`。
3. 在 Pushover 首页复制你的 `USER_KEY`。
4. 确认 iPhone 设置中允许 Pushover 通知。
5. 确认 vivo WATCH GT2 会同步 iPhone 上 Pushover 的通知。

运行：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/tools
cp pushover.env.example .env
```

编辑 `.env` 填入真实密钥后运行：

```bash
set -a
source .env
set +a
python3 pushover_notify.py
```

默认会发送：

```text
HYROX
已开始运动
```

也可以自定义消息：

```bash
python3 pushover_notify.py --message "深蹲 +1"
```

测试训练结束通知：

```bash
python3 pushover_notify.py --event finished --duration-seconds 755
```

示例内容：

```text
HYROX
训练结束，本次运动 12分35秒
```

## 后端接入设计

后续后端收到小车事件后，可以在这些训练节点推送通知：

| 场景 | 触发事件 | 示例消息 | 优先级 |
|---|---|---|---|
| 训练开始 | `session_start` 或前端开始按钮 | 已开始运动 | normal |
| 动作完成 | `rep_event` | 深蹲 +1 | normal，可配置，默认关闭 |
| 训练暂停 | 前端暂停或后端状态变化 | 训练已暂停 | normal |
| 训练结束 | `session_end` 或前端结束按钮 | 训练结束，本次运动 12分35秒 | normal |
| 风险告警 | 目标丢失等 warning | 目标丢失，请检查小车视野 | high |

后端建议封装为：

```text
backend/app/services/notification_service.py
```

对外提供类似接口：

```python
notify_session_started(session_id)
notify_rep_completed(session_id, action, count)
notify_session_finished(session_id, duration_seconds, summary)
notify_warning(session_id, warning_type, message)
```

结束通知必须包含本次运动时间。后端优先使用平台 session 的 `active_duration_s`；如果还没有有效运动时长，则退回到 `duration_s` 或小车 `session_end.elapsed_ms`。

## 保护机制

### 1. 节流

动作完成事件可能连续出现，后端必须避免通知刷屏。建议规则：

```text
同一 session 内普通动作通知至少间隔 1 秒；
同一种 warning 至少间隔 15 秒；
训练开始和训练结束不受普通动作节流影响；
```

如果 1 秒内出现多个动作完成事件，可以合并为：

```text
已完成 3 次动作
```

或者只推送最后一条，同时在前端保留完整事件日志。

### 2. 消息分级

建议分为三类：

| 等级 | 用途 | Pushover priority |
|---|---|---|
| silent/log | 只记录，不震动 | -2 |
| normal | 开始、结束、动作完成 | 0 |
| high | 心率过高、目标丢失、异常中断 | 1 |

不建议 MVP 阶段使用 `priority=2` emergency，因为它需要 `retry` 和 `expire` 参数，并且会反复提醒，容易干扰训练。

### 3. 开关配置

后端应允许在配置中开关通知：

```text
PUSHOVER_ENABLED=true
PUSHOVER_NOTIFY_REPS=false
PUSHOVER_APP_TOKEN=...
PUSHOVER_USER_KEY=...
PUSHOVER_DEFAULT_PRIORITY=0
PUSHOVER_REP_THROTTLE_SECONDS=1.0
PUSHOVER_WARNING_THROTTLE_SECONDS=15.0
```

说明：

- 训练开始和训练结束通知默认开启；
- 动作完成通知默认关闭，可在前端或配置中打开；
- MVP 不做心率过高通知，只在前端展示心率状态。

真实密钥只放本地 `.env`，不要提交到仓库。

## 下一步

1. 在后端实现 `notification_service.py`；
2. 将 `pushover_notify.py` 中的发送逻辑复用到服务层；
3. 在 `session_start`、`rep_event`、`session_end` 处理器里调用通知服务；
4. 添加节流测试，确保连续 `rep_event` 不会刷屏。
