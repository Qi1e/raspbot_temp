# HYROX Backend

HYROX 运动报告软件的电脑端后端。MVP 阶段后端运行在电脑上，同时接收：

```text
Raspbot 小车 -> Wi-Fi HTTP NDJSON -> FastAPI 后端
vivo WATCH GT2 -> 电脑 BLE -> FastAPI 后端
FastAPI 后端 -> WebSocket live_snapshot -> 前端
FastAPI 后端 -> Pushover -> iPhone -> vivo WATCH GT2 通知震动
```

## 已确认的 MVP 决策

1. `session_start` 到达后，后端自动创建 session，不要求前端或小车提前创建。
2. MVP 直接使用小车端 `session_id` 作为平台 `session_id`。
3. 数据库使用 SQLite，默认路径为 `./data/hyrox_backend.sqlite3`。
4. 小车数据入口为 `POST /api/v1/robot/ingest`，格式是 `application/x-ndjson`。
5. 小车事件支持 `ping`、`session_start`、`sample`、`rep_event`、`session_end`。
6. `rep_event` 是动作次数的权威来源，使用 `(session_id, device_id, action, count)` 幂等去重。
7. 前端只订阅聚合后的 `live_snapshot`，不直接拼接原始样本。
8. 心率设备只支持同时连接一个设备。
9. BLE 扫描默认 10 秒，支持扫描、连接、断开、状态查询。
10. 心率数据进入同一个 `live_snapshot`，前端不需要单独订阅心率 WebSocket。
11. Pushover 配置并启用后，训练开始和训练结束通知默认开启。
12. Pushover 动作完成通知默认关闭，但可通过 API 打开。
13. 心率过高不做手表通知，只在前端展示心率状态。
14. 前端 MVP 只做展示和必要按钮，不直接控制小车开始/停止。
15. 报告和分析统一使用电脑接收时间轴：小车原始时间保留，但不作为拟合心率的主时间。
16. 数据拟合、热量消耗、运动效果等放入独立 `analysis` 模块，不混入实时采集逻辑。

## 安装

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果只想先检查代码结构，可以暂时不安装依赖；运行服务前必须安装。

## 配置

复制配置模板：

```bash
cp .env.example .env
```

推荐配置：

```text
HYROX_DATABASE_PATH=./data/hyrox_backend.sqlite3
HYROX_LIVE_PUSH_INTERVAL_SECONDS=0.4

PUSHOVER_ENABLED=false
PUSHOVER_NOTIFY_REPS=false
PUSHOVER_APP_TOKEN=
PUSHOVER_USER_KEY=
PUSHOVER_DEFAULT_PRIORITY=0
PUSHOVER_REP_THROTTLE_SECONDS=1.0
PUSHOVER_WARNING_THROTTLE_SECONDS=15.0

HR_BLE_SCAN_TIMEOUT_SECONDS=10.0
HR_BLE_DEFAULT_NAME=
```

真实 `.env` 不要提交。根目录 `.gitignore` 已忽略 `.env` 和 `*.env`。需要 Pushover 通知时再把 `PUSHOVER_ENABLED` 改成 `true` 并填入自己的 token/key。

## 启动

推荐从项目根目录使用一键启动：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design
./hyrox_start.command
```

该脚本会自动安装依赖、构建前端、生成默认 `.env`、启动后端，并打开：

```text
http://127.0.0.1:8000
```

手动启动后端：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
source .venv/bin/activate
set -a
source .env
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

如果 `frontend/dist` 存在，FastAPI 会直接托管前端页面，不再必须单独运行 Vite 开发服务器。

## MVP 使用流程

### 1. 电脑端准备

一键启动会在 `backend/.env` 不存在时创建安全默认配置。已有 `.env` 不会被覆盖。默认关闭 Pushover，便于没有通知密钥的小伙伴先跑通数据链路：

```text
PUSHOVER_ENABLED=false
PUSHOVER_NOTIFY_REPS=false
HR_BLE_SCAN_TIMEOUT_SECONDS=10.0
```

需要手表通知时，再手动配置：

```text
PUSHOVER_ENABLED=true
PUSHOVER_APP_TOKEN=...
PUSHOVER_USER_KEY=...
```

启动电脑端：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design
./hyrox_start.command
```

### 2. 验证手表通知

在另一个终端运行：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/tools
set -a
source .env
set +a
python3 pushover_notify.py
```

预期 iPhone 收到“已开始运动”，vivo WATCH GT2 同步震动。

### 3. 扫描并连接心率

扫描：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/hr/ble/scan?timeout=10'
```

连接：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hr/ble/connect \
  -H 'Content-Type: application/json' \
  -d '{"name":"vivo WATCH"}'
```

连接后，心率样本会自动进入最新 session 的 `live_snapshot.heart_rate`。

### 4. 小车端上传

在树莓派端运行当前统一入口 `posture_demo.py`：

```bash
python3 posture_demo.py \
  --source 0 \
  --record-path records/local_backup.jsonl \
  --record-url http://<电脑IP>:8000/api/v1/robot/ingest \
  --record-device-id raspbot_01 \
  --record-keypoints
```

后端收到 `session_start` 后自动创建 session。

需要自动结束时，建议给小车端加 `--duration`。例如记录 10 分钟：

```bash
python3 posture_demo.py \
  --source 0 \
  --duration 600 \
  --record-path records/local_backup.jsonl \
  --record-url http://<电脑IP>:8000/api/v1/robot/ingest \
  --record-device-id raspbot_01 \
  --record-keypoints
```

### 5. 前端或 API 查看

最新 session：

```bash
curl http://127.0.0.1:8000/api/v1/sessions/latest
```

实时快照：

```bash
curl http://127.0.0.1:8000/api/v1/live/<session_id>
```

WebSocket：

```text
ws://127.0.0.1:8000/ws/v1/live/<session_id>
```

### 6. 训练结束

小车上传 `session_end` 后，后端会用电脑接收时间计算训练时长、更新动作次数，并发送：

```text
训练结束，本次运动 xx分xx秒
```

正确的数据记录入口：

| 场景 | 入口 |
|---|---|
| 开始记录 | 小车端启动 `posture_demo.py --record-url http://<电脑IP>:8000/api/v1/robot/ingest`，后端收到 `session_start` 自动创建 session |
| 正常结束 | 小车端自然退出并执行 `recorder.close()`，发送 `session_end` |
| 定时结束 | 小车端使用 `--duration <秒数>` |
| 本地窗口调试结束 | 带 `--view-img` 时按 `q` 退出窗口 |
| 异常中断兜底 | 前端点“结束记录”，或调用下面的 API |

异常中断兜底 API：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/sessions/<session_id>/finish
```

直接在树莓派上 Ctrl+C 可能来不及完成远端上传队列 flush，导致后端没有收到 `session_end`，前端会停在最后一帧或一直显示记录中。这时使用“结束记录”兜底即可收口当前 session；它只结束后端记录，不会向小车发控制命令。

### 7. 无小车测试

用真实样本回放：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
python3 tools/replay_robot_jsonl.py /tmp/raspbot_receiver_records/receiver_test.jsonl
```

验收结果：

```text
20260703_130100: squat=2, lunge=2, burpee=1
```

## 小车数据接入

正式入口：

```text
POST /api/v1/robot/ingest
Content-Type: application/x-ndjson
```

每行一个 JSON 事件。后端会：

1. 逐行解析 NDJSON；
2. 按小车 `session_id` 自动创建 session；
3. 记录电脑接收时间；
4. 保存原始事件到 `raw_robot_events`；
5. 抽取 `sample` 到 `robot_samples`；
6. 抽取 `rep_event` 到 `action_events`；
7. 归一化 `timestamp_ms` 和 `elapsed_ms` 为电脑时间轴；
8. 保留 `robot_timestamp_ms` 和 `robot_elapsed_ms` 作为小车侧诊断信息；
9. 收到 `session_end` 后更新训练时长和动作次数；
10. 更新 `live_snapshot`；
11. 按配置触发 Pushover 通知。

### 统一时间轴

后续报告需要把心率曲线和动作阶段拟合到同一时间轴。树莓派系统时间可能不稳定，因此后端约定：

| 字段 | 含义 | 是否用于报告拟合 |
|---|---|---|
| `sessions.started_at_ms` | 电脑收到该 session 首个有效事件的时间 | 是 |
| `sessions.ended_at_ms` | 电脑收到 `session_end` 的时间 | 是 |
| `robot_samples.timestamp_ms` | 电脑收到该姿态样本的时间 | 是 |
| `robot_samples.elapsed_ms` | `timestamp_ms - sessions.started_at_ms` | 是 |
| `action_events.timestamp_ms` | 电脑收到动作完成事件的时间 | 是 |
| `action_events.elapsed_ms` | `timestamp_ms - sessions.started_at_ms` | 是 |
| `heart_rate_samples.timestamp_ms` | 电脑收到 BLE 心率 notify 的时间 | 是 |
| `raw_robot_events.timestamp_ms` | 小车事件原始 `timestamp` | 否 |
| `robot_samples.robot_timestamp_ms` | 小车事件原始 `timestamp` | 否，仅诊断 |
| `robot_samples.robot_elapsed_ms` | 小车事件原始 `elapsed_ms` | 否，仅诊断 |
| `action_events.robot_timestamp_ms` | 小车动作事件原始 `timestamp` | 否，仅诊断 |
| `action_events.robot_elapsed_ms` | 小车动作事件原始 `elapsed_ms` | 否，仅诊断 |

如果电脑端 receiver 在写 JSONL 或转发 HTTP 时附加 `received_at_ms`、`server_received_at_ms` 或 `receiver_received_at_ms`，后端会优先使用这些电脑时间字段。否则实时 HTTP 接收时使用后端收到该事件时的电脑时间。

注意：旧 JSONL 快速回放时，如果文件中没有电脑接收时间字段，后端只能使用回放请求到达时间，训练时长会被压缩。这种文件仍适合验证动作次数和数据结构；需要验证报告时间拟合时，应使用实时上传数据或让 receiver 写入电脑接收时间。

### 回放真实样本

项目已经有真实小车接收文件：

```text
/tmp/raspbot_receiver_records/receiver_test.jsonl
```

启动后端后回放：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
python3 tools/replay_robot_jsonl.py /tmp/raspbot_receiver_records/receiver_test.jsonl
```

验收目标：

```text
session_id=20260703_130100
squat=2
lunge=2
burpee=1
```

查询：

```bash
curl http://127.0.0.1:8000/api/v1/sessions
curl http://127.0.0.1:8000/api/v1/sessions/20260703_130100
curl http://127.0.0.1:8000/api/v1/sessions/20260703_130100/events
curl http://127.0.0.1:8000/api/v1/sessions/20260703_130100/samples?limit=20
```

## 心率 BLE 接入

BLE 由电脑执行扫描和连接，MVP 只支持一个当前心率设备。

扫描 10 秒：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/hr/ble/scan?timeout=10'
```

连接指定设备地址：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hr/ble/connect \
  -H 'Content-Type: application/json' \
  -d '{"address":"XX:XX:XX:XX:XX:XX"}'
```

或按名称过滤连接：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hr/ble/connect \
  -H 'Content-Type: application/json' \
  -d '{"name":"vivo WATCH"}'
```

查看连接状态：

```bash
curl http://127.0.0.1:8000/api/v1/hr/ble/status
```

状态含义：

| status | 含义 |
|---|---|
| `connecting` | 后端正在查找或连接设备 |
| `connected` | BLE 连接已建立，尚未确认收到心率 notify |
| `listening` | 已订阅 `2A37`，等待或正在接收心率样本 |
| `error` | 扫描、连接或订阅失败 |
| `disconnected` | 未连接 |

如果前端显示“已连接”但没有心率，优先看：

```bash
curl http://127.0.0.1:8000/api/v1/hr/ble/status
```

需要关注：

```json
{
  "status": "listening",
  "samples_received": 3,
  "latest_bpm": 98
}
```

如果 `samples_received` 一直是 `0`，通常说明手表没有推送实时心率。处理方式：

1. 在手表上打开实时心率测量或运动模式；
2. 确认手表没有被 vivo 健康或其他 App 占用连接；
3. 后端调用 `/api/v1/hr/ble/disconnect` 后重新连接；
4. 先用 `heart_rate_gateway/heart_rate_gateway.py --name "vivo WATCH"` 单独验证是否有 JSON 心率输出。

断开：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hr/ble/disconnect
```

后端订阅标准 BLE Heart Rate Measurement：

```text
Service: 0000180d-0000-1000-8000-00805f9b34fb
Characteristic: 00002a37-0000-1000-8000-00805f9b34fb
```

每个心率样本会保存到 `heart_rate_samples`，并写入最新 session 的 `live_snapshot.heart_rate`。

## 实时数据

前端可先调用：

```bash
curl http://127.0.0.1:8000/api/v1/sessions/latest
```

拿到最新 session 后订阅：

```text
ws://127.0.0.1:8000/ws/v1/live/{session_id}
```

也可以直接查询快照：

```bash
curl http://127.0.0.1:8000/api/v1/live/20260703_130100
```

`live_snapshot` 结构核心字段：

```json
{
  "type": "live_snapshot",
  "session_id": "20260703_130100",
  "status": "recording",
  "timer": {
    "duration_s": 75.8,
    "active_duration_s": 75.8
  },
  "current": {
    "action": "squat",
    "phase": "up",
    "posture": "Standing",
    "latest_score": null
  },
  "counts": {
    "squat": 2,
    "lunge": 2,
    "burpee": 1
  },
  "heart_rate": {
    "bpm": 156,
    "status": "live"
  },
  "robot": {
    "device_id": "raspbot_01",
    "last_sample_age_ms": 240,
    "target_confidence": 0.91,
    "pose_quality": "good",
    "connection_status": "live",
    "sample_count": 290,
    "latest_sample_id": 290,
    "elapsed_ms": 75800,
    "server_elapsed_ms": 75800,
    "robot_elapsed_ms": 75490,
    "received_at_ms": 1783054600000,
    "robot_timestamp_ms": 1783054599800,
    "angles": {
      "left_knee": 158.8,
      "right_knee": 159.4
    },
    "visibility": {
      "full_body": true,
      "arms_visible": false,
      "legs_visible": true
    }
  },
  "notifications": {
    "notify_reps": false
  },
  "events": []
}
```

## Analysis 模块

`analysis` 模块是后续报告生成、心率拟合、热量消耗和运动效果分析的入口。采集层只负责存储真实数据和实时快照；分析层负责把小车数据、动作事件、心率样本整合成报告可用的数据集。

当前已提供两个接口：

```bash
curl http://127.0.0.1:8000/api/v1/analysis/20260703_130100/summary

curl 'http://127.0.0.1:8000/api/v1/analysis/20260703_130100/aligned?sample_limit=2000&nearest_hr_window_ms=5000'
```

`/aligned` 返回：

1. `time_axis`：电脑接收时间轴说明；
2. `summary`：训练时长、姿态样本数、返回样本数、动作事件数、心率样本数、平均心率、最高心率；
3. `streams.robot_samples`：姿态样本流，含 `t_ms`、关节角度、动作状态；
4. `streams.action_events`：动作完成事件流；
5. `streams.heart_rate_samples`：心率样本流；
6. `streams.action_events_with_heart_rate`：每个动作完成事件匹配最近心率样本；
7. `analysis_modules`：当前分析能力状态。

目前 `alignment=ready`；`calories` 和 `training_effect` 先标记为待实现。后续实现热量消耗时，需要补充用户体重、年龄、性别、最大心率估计或实测值；运动效果分析则需要确定评分模型，例如动作完成率、节奏稳定性、姿态质量、心率恢复速度等。

## Pushover 通知

已验证链路：

```text
电脑后端 -> Pushover API -> iPhone 15 Pro -> vivo WATCH GT2 同步通知并震动
```

通知策略：

| 场景 | 默认 | 消息 |
|---|---|---|
| 训练开始 | 开启 | 已开始运动 |
| 动作完成 | 关闭 | 深蹲 +1，第 1 次 |
| 训练结束 | 开启 | 训练结束，本次运动 12分35秒 |
| 心率过高 | 关闭 | 不推送，只前端展示 |

动作完成通知运行时开关：

```bash
curl http://127.0.0.1:8000/api/v1/settings/notifications

curl -X PUT http://127.0.0.1:8000/api/v1/settings/notifications \
  -H 'Content-Type: application/json' \
  -d '{"notify_reps":true}'
```

该开关 MVP 阶段只保存在后端内存里，服务重启后回到 `.env` 的默认值。

## 数据库表

| 表 | 用途 |
|---|---|
| `sessions` | 训练会话，MVP 使用小车 `session_id` 作为主键 |
| `raw_robot_events` | 原始小车事件，便于重放和调试 |
| `robot_samples` | 从 `sample` 抽取的姿态、角度、动作状态，主时间为电脑接收时间 |
| `action_events` | 从 `rep_event` 抽取的动作完成事件，主时间为电脑接收时间 |
| `heart_rate_samples` | BLE 心率样本，时间为电脑收到 BLE notify 的时间 |

直接查询 SQLite：

```bash
sqlite3 data/hyrox_backend.sqlite3
```

常用 SQL：

```sql
SELECT id, status, duration_s, counts_json
FROM sessions
ORDER BY started_at_ms DESC;

SELECT action, count, stage, elapsed_ms, robot_elapsed_ms
FROM action_events
WHERE session_id='20260703_130100'
ORDER BY timestamp_ms;

SELECT bpm, timestamp_ms
FROM heart_rate_samples
WHERE session_id='20260703_130100'
ORDER BY timestamp_ms;
```

## 前端 MVP 要求

前端第一版只需要展示和必要控制：

1. 当前训练状态；
2. 本次运动时间；
3. 当前动作、阶段；
4. 深蹲、箭步蹲、波比跳次数；
5. 最近动作事件；
6. 姿态质量和目标置信度；
7. 当前心率和心率连接状态；
8. BLE 心率设备扫描结果；
9. 连接/断开心率设备按钮；
10. Pushover 动作完成通知开关；
11. 清空或停止当前展示数据的按钮。

前端不直接控制小车开始/停止。小车仍按当前代码采集和上传数据，后端负责适配。

## 后续扩展

1. 生成训练报告；
2. 在 `analysis` 模块中实现心率区间、能量消耗和运动效果统计；
3. 前端运动记录页面；
4. 将通知设置持久化到数据库；
5. 手机端 BLE 迁移；
6. 小车蓝牙串口或 BLE 数据链路实验。
