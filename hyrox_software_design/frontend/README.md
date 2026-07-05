# HYROX Frontend

电脑端 HYROX 实时训练控制台。第一版只展示和调整后端状态，不向小车下发开始、停止等反向命令。

## 功能范围

当前页面包含：

1. 最新 session 和实时训练状态；
2. 本次运动时间、当前动作、心率、姿态质量；
3. 深蹲、箭步蹲、波比跳次数；
4. 小车连接状态、运动数据个数、最新样本号、电脑运动时间、小车原始耗时；
5. 最新关节角度，包括膝、髋、肘、肩；
6. 可选摄像头预览，默认使用小车 8080 预览地址；
7. 最近 `session_start`、`rep_event`、`session_end` 事件；
8. BLE 心率设备扫描、连接、断开；
9. Pushover 动作完成通知开关；
10. `live_snapshot` WebSocket 实时更新；
11. 后端 session 兜底结束按钮；
12. 无小车时可配合后端 JSONL 回放查看。

## 启动

普通演示优先使用一键启动：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design
./hyrox_start.command
```

一键启动会自动安装依赖、执行 `npm run build`，然后由 FastAPI 托管前端。浏览器打开：

```text
http://127.0.0.1:8000
```

前端开发时才需要单独启动 Vite：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/frontend
npm install
npm run dev
```

Vite 开发页面为 `http://127.0.0.1:5173`，接口代理到 `http://127.0.0.1:8000`。

## 测试数据

无小车时，在后端目录回放真实数据：

```bash
cd /Users/guo/College/Raspbot_project/Raspbot_Base/raspbot_temp/hyrox_software_design/backend
source .venv/bin/activate
python3 tools/replay_robot_jsonl.py /tmp/raspbot_receiver_records/receiver_test.jsonl
```

前端应显示：

```text
20260703_130100
深蹲 2
箭步蹲 2
波比跳 1
运动数据个数 290
```

旧 JSONL 快速回放如果没有电脑端 `received_at_ms` 字段，后端会使用回放请求到达时间，因此“电脑运动时间”可能明显短于真实运动时间。真实训练上传或带电脑接收时间的 JSONL 才适合验证后续报告拟合。

## 摄像头预览

小车端如果启动了网页预览，默认端口通常是：

```text
http://192.168.1.11:8080/
```

前端页面中的“摄像头预览”地址填写该 URL 后，打开“预览”即可嵌入显示。

关闭前端预览只会停止浏览器继续拉取画面。若要真正减少小车端推流和编码消耗，需要小车端运行时关闭预览，例如使用 `--no-preview`。

## 结束记录

正常结束应由小车端发送 `session_end`。推荐方式：

```bash
python3 posture_demo.py --duration 600 --record-url http://<电脑IP>:8000/api/v1/robot/ingest
```

如果小车端 Ctrl+C 或异常退出后前端停在“记录中”，点击“结束记录”可以让后端用电脑时间收口当前 session。这个按钮只结束后端记录，不会控制小车运动。

## 心率不显示排查

前端显示“已连接”只表示 BLE 连接建立，不一定代表手表已经推送心率。

打开：

```bash
curl http://127.0.0.1:8000/api/v1/hr/ble/status
```

理想状态应包含：

```json
{
  "status": "listening",
  "samples_received": 1,
  "latest_bpm": 96
}
```

如果 `samples_received` 一直是 `0`：

1. 在 vivo WATCH GT2 上打开心率测量或运动模式；
2. 断开后重连心率设备；
3. 确认没有其他 App 占用手表蓝牙心率连接；
4. 使用独立心率网关脚本验证手表是否输出 `heart_rate_sample`。

## 接口来源

Vite 开发服务器已经代理：

```text
/api -> http://127.0.0.1:8000
/ws  -> ws://127.0.0.1:8000
```

因此前端代码中可以直接请求 `/api/v1/...` 和 `/ws/v1/...`。
