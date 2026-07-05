# HYROX Software Design

本目录承载 HYROX 运动报告软件的电脑端后端、前端、心率网关和工具脚本。

## 一键启动版

推荐优先使用根目录的一键启动脚本：

```text
hyrox_software_design/hyrox_start.command
```

macOS 上可以直接双击该文件；也可以在终端运行：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design
./hyrox_start.command
```

只想提前安装依赖和构建前端、不启动服务时：

```bash
./hyrox_start.command --setup-only
```

脚本会自动完成：

1. 创建后端 Python 虚拟环境；
2. 安装后端依赖；
3. 安装前端 Node 依赖；
4. 构建前端；
5. 在 `.env` 不存在时生成安全默认配置；
6. 启动 FastAPI 后端；
7. 由后端托管前端页面；
8. 自动打开 `http://127.0.0.1:8000`；
9. 在终端打印小车端应使用的 `record-url`。

首次运行需要电脑已有：

```text
Python 3.9+
Node.js/npm
```

如果没有 Node.js，先安装 Node.js LTS。脚本不会自动安装系统级软件，也不会自动写入 Pushover 密钥。

首次运行生成的 `backend/.env` 默认关闭 Pushover。已有 `.env` 不会被覆盖：

```text
PUSHOVER_ENABLED=false
```

这样小伙伴即使没有 Pushover 账号，也能先完成小车数据接收、前端展示、BLE 心率扫描连接。需要手表通知时，再手动把 `backend/.env` 改成：

```text
PUSHOVER_ENABLED=true
PUSHOVER_APP_TOKEN=自己的 token
PUSHOVER_USER_KEY=自己的 user key
```

### 小车端地址

一键启动后，终端会打印类似：

```text
Raspbot record-url candidates:
  http://192.168.1.23:8000/api/v1/robot/ingest
```

小车端启动识别时，把这个地址填入 `--record-url`：

```bash
python3 posture_demo.py \
  --record-url http://192.168.1.23:8000/api/v1/robot/ingest
```

本阶段不修改小车端代码；小车仍然通过现有 `--record-url` 参数上传 NDJSON。

### 一键启动仍需人工处理的事

| 项目 | 是否自动 | 说明 |
|---|---|---|
| 后端依赖安装 | 自动 | 首次运行或依赖变化时执行 |
| 前端依赖安装 | 自动 | 首次运行或依赖变化时执行 |
| 前端构建 | 自动 | 构建后由后端托管 |
| SQLite 初始化 | 自动 | 后端启动时自动创建 |
| Pushover token/key | 手动 | 不能提交到仓库，也不能自动生成 |
| macOS 蓝牙权限 | 手动授权 | 第一次 BLE 扫描时系统弹窗 |
| 小车端 record-url | 手动填入 | 当前不改小车代码 |
| 小车 Wi-Fi 无外网 | 无法自动解决 | 会影响 Pushover 云通知，不影响本地数据 |

## 当前组成

```text
hyrox_software_design/
  backend/             # FastAPI 后端，负责小车数据、心率、实时快照、通知
  frontend/            # Vue 前端控制台
  heart_rate_gateway/  # 独立 BLE 心率网关实验脚本
  scripts/             # 一键启动和本地辅助脚本
  tools/               # Pushover 等独立验证工具
  docs/                # 软件侧补充文档预留目录
  hyrox_start.command   # macOS 一键启动入口
```

## MVP 信息流

```text
Raspbot 小车
  -> Wi-Fi HTTP NDJSON
  -> 电脑 FastAPI 后端
  -> SQLite / live_snapshot / Pushover

vivo WATCH GT2
  -> 电脑 BLE 心率读取
  -> 电脑 FastAPI 后端
  -> live_snapshot

电脑 FastAPI 后端
  -> Pushover
  -> iPhone
  -> vivo WATCH GT2 同步通知并震动
```

## 手动演示流程

一般不需要手动执行下面流程，优先使用 `hyrox_start.command`。当你需要调试后端或前端源码时，可以手动启动。

### 1. 启动后端单服务

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
source .venv/bin/activate
set -a
source .env
set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

检查：

```bash
curl http://127.0.0.1:8000/health
```

如果已经执行过前端构建，后端会同时托管前端页面：

```text
http://127.0.0.1:8000
```

### 2. 测试 Pushover 手表通知

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/tools
set -a
source .env
set +a
python3 pushover_notify.py
python3 pushover_notify.py --event finished --duration-seconds 755
```

预期：

```text
iPhone 收到通知
vivo WATCH GT2 同步震动
```

### 3. 扫描并连接心率设备

扫描 10 秒：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/hr/ble/scan?timeout=10'
```

连接心率手表：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/hr/ble/connect \
  -H 'Content-Type: application/json' \
  -d '{"name":"vivo WATCH"}'
```

查看状态：

```bash
curl http://127.0.0.1:8000/api/v1/hr/ble/status
```

### 4. 启动小车 HYROX 识别并上传

在树莓派小车端运行类似命令：

```bash
python3 posture_demo.py \
  --source 0 \
  --record-path records/local_backup.jsonl \
  --record-url http://<电脑IP>:8000/api/v1/robot/ingest
```

后端收到 `session_start` 后会自动创建 session，不需要前端或小车提前创建。

### 5. 查看训练状态

最新 session：

```bash
curl http://127.0.0.1:8000/api/v1/sessions/latest
```

训练列表：

```bash
curl http://127.0.0.1:8000/api/v1/sessions
```

实时快照：

```bash
curl http://127.0.0.1:8000/api/v1/live/<session_id>
```

WebSocket：

```text
ws://127.0.0.1:8000/ws/v1/live/<session_id>
```

前端会展示：

```text
小车连接状态
运动数据个数
电脑运动时间
小车原始耗时
最新关节角度
8080 摄像头预览
```

摄像头预览地址通常是：

```text
http://192.168.1.11:8080/
```

前端关闭预览只会停止浏览器拉流；如果要减少小车算力消耗，需要小车端运行时关闭预览。

### 6. 训练结束

小车上传 `session_end` 后，后端会：

1. 把 session 标记为 `finished_pending_report`；
2. 写入本次运动时间；
3. 更新动作次数；
4. 发送 Pushover 结束通知：

```text
训练结束，本次运动 xx分xx秒
```

## 无小车开发测试流程

没有连接小车时，可以用真实样本回放：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
source .venv/bin/activate
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
curl http://127.0.0.1:8000/api/v1/sessions/20260703_130100
curl http://127.0.0.1:8000/api/v1/sessions/20260703_130100/events
```

## 当前默认策略

| 功能 | 默认策略 |
|---|---|
| session 创建 | 小车 `session_start` 自动创建 |
| session_id | 直接使用小车 `session_id` |
| 数据库 | SQLite |
| 心率设备 | 同时只连接一个 |
| BLE 扫描 | 默认 10 秒 |
| 心率推送 | 写入同一个 `live_snapshot` |
| 训练开始通知 | Pushover 配置并启用后默认开启 |
| 动作完成通知 | 默认关闭，可 API 打开 |
| 训练结束通知 | Pushover 配置并启用后默认开启，必须包含本次运动时间 |
| 心率过高通知 | 不推送，只前端展示 |

## 重要文档

- 后端使用与 API：[backend/README.md](/Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend/README.md)
- Pushover 通知验证：[tools/README.md](/Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/tools/README.md)
- 独立心率网关：[heart_rate_gateway/README.md](/Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/heart_rate_gateway/README.md)
