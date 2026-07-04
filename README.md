# raspbot_posture

Raspbot 姿态识别与姿态跟随控制工程。仓库的可维护功能代码只放在 `raspbot_posture/` 包体中；根目录入口文件只负责调用包内 CLI，不实现业务逻辑。

## 当前内容

```text
.
├── posture_demo.py                 # 姿态识别预览入口，只调用 raspbot_posture.cli
├── raspbot_posture/                # 唯一功能包体
└── dev_tests/                      # 后续开发、联调、测试脚本
```

`project_demo/` 和旧 `test_demo/` 不属于维护代码。需要参考旧资料时只能作为本地资料使用，不从这些目录复制运行逻辑到入口文件；可复用逻辑必须先整理进 `raspbot_posture/`。

## 运行入口

姿态识别预览：

```bash
python3 posture_demo.py
```

姿态跟随控制：

```bash
python3 posture_robot_control_demo.py --run-mode camera
python3 posture_robot_control_demo.py --run-mode steering
python3 posture_robot_control_demo.py --run-mode full
```

三种控制模式：

- `camera`：仅摄像头和网页预览，不启动 MediaPipe，不发送硬件指令。
- `steering`：姿态推理、人体目标跟踪、云台转向、车身原地转向。
- `full`：在 `steering` 基础上打开距离控制测试分支。

无硬件调试：

```bash
python3 posture_robot_control_demo.py --run-mode steering --dry-run-control --control-debug
```

默认网页预览地址：

```text
http://<raspberry-pi-ip>:8080/
```

## 包体结构

`raspbot_posture/` 是唯一功能包体：

```text
raspbot_posture/
├── cli.py              # 普通姿态 demo 参数
├── app.py              # 摄像头、推理、预览、可选控制线程的共享主循环
├── camera.py           # 摄像头打开和分辨率设置
├── preview.py          # HTTP/MJPEG 网页预览
├── model_paths.py      # MediaPipe 离线模型检查
├── state.py            # PoseAnalysis、HumanTarget、ActionStatus 等共享状态
├── geometry.py         # 关键点几何计算和人体目标框
├── vision.py           # 姿态特征提取和基础姿态分类
├── actions.py          # 深蹲计数和动作检测扩展点
├── inference.py        # MediaPipe 推理线程和分析结果组装
├── rendering.py        # 预览画面文字、人体框绘制
├── hardware.py         # Raspbot I2C 硬件最小适配
├── target_filter.py    # 人体目标平滑
├── robot_driver.py     # 舵机、电机、短脉冲封装
├── robot_controller.py # 云台跟随、车身转向、距离控制分支
├── robot_app.py        # 控制模式接入共享主循环
└── robot_cli.py        # 控制版参数
```

## HYROX 动作扩展

HYROX 扩展以旁路方式新增，不修改 `raspbot_posture/` 包体：

```text
hyrox_action_demo.py      # HYROX 动作识别和记录入口
hyrox_actions/
├── detectors.py          # 深蹲、箭步蹲、波比跳计数状态机
├── pose_features.py      # 关键关节角度和人体框特征
├── recorder.py           # JSONL/NDJSON 角度、动作记录和可选远端上传
└── overlay.py            # 预览叠字
```

运行示例：

```bash
python3 hyrox_action_demo.py --source 0 --record-path records/session.jsonl
```

如需把记录实时传到电脑后端，可先约定电脑端监听 `8765` 端口，并提供一个接收 `POST /ingest` 的 demo 服务。receiver 脚本可以放在仓库外，不需要提交到本仓库。树莓派端命令示例：

```bash
python3 hyrox_action_demo.py \
  --source 0 \
  --record-path records/local_backup.jsonl \
  --record-url http://<电脑IP>:8765/ingest \
  --record-device-id raspbot_01 \
  --record-keypoints
```

远端上传使用 `application/x-ndjson` 批量 HTTP POST，每行一个 JSON 事件；本地 `--record-path` 仍会保留完整备份。上传在后台线程中进行，后端断开不会阻塞动作识别和小车运动控制。当前版本不依赖额外 WebSocket 包，后续前端需要实时展示时，可以由电脑后端把收到的数据再转发给前端。

默认推理上限为 12 FPS，默认记录间隔为 0.1 秒。树莓派压力较大时可降回：

```bash
python3 hyrox_action_demo.py --source 0 --inference-fps 8 --record-interval 0.2
```

扩展中的深蹲和箭步蹲使用互斥仲裁，明显的 split-stance 骨架特征会优先 favour 箭步蹲，并阻止深蹲抢计数。深蹲默认 `--squat-down-angle` 为 152，并优先看对称腿部骨架与膝角，降低低机位下髋部下沉特征失真的影响；`--squat-min-down-time` 默认 0.4 秒，避免单帧抽搐造成深蹲误计。箭步蹲要求更明确的脚踝展开或髋脚偏移，减少正面深蹲被膝角抖动抢成箭步蹲。

波比跳按“俯卧撑起身 + 相对摄像头左右方向立定跳远”计数，需经历俯卧撑下降、俯卧撑推起、起身、横向位移、落地阶段，默认 `--burpee-stage-timeout` 为 7.0 秒。`floor_entry` 只作为内部弱候选，不再作为正式显示或阻挡状态；俯卧撑入口优先要求地面姿态、肘角和伸腿证据共同成立。如果低机位导致手臂关键点不可见，只有非常扁平且贴近地面的目标框才允许用 `--burpee-flat-floor-*` 严格入口进入 `pushup_down`，避免深蹲或箭步蹲低位误进波比跳。

记录文件为 JSONL/NDJSON，每行包含 `type`、`session_id`、时间戳、当前动作阶段、关键关节角度、人体框、可见性和计数状态；开启 `--record-keypoints` 时还会记录肩、肘、腕、髋、膝、踝等关键点坐标，供后端动作完成度计算使用。记录事件包括 `session_start`、`sample`、`rep_event` 和 `session_end`。部署到树莓派时，把 `hyrox_action_demo.py` 和 `hyrox_actions/` 放到 Pi 项目目录中，与 `raspbot_posture/` 同级即可。

## 已实现功能

- 摄像头采集、镜像、本地窗口和网页 MJPEG 预览。
- MediaPipe Pose 异步推理，支持推理 FPS 限制。
- 基础姿态识别：站立、举手、T pose、蹲/坐、左倾、右倾。
- 人体目标输出：归一化中心点、面积、置信度、当前姿态。
- 深蹲计数动作检测。
- `camera` / `steering` / `full` 三种控制测试模式。
- 云台舵机跟随人体目标。
- 云台偏转持续过大时，车身短脉冲原地转向。
- 目标丢失停车、退出停车、退出舵机复位。
- `--dry-run-control` 和 `--control-debug` 调试模式。

## 待跟进功能

- 距离控制，也就是舵机转向、车身转向之外的前进/后退运动部分，还需要实车标定。
- 标定人体目标面积与真实距离的关系，确定 `--target-area-min` 和 `--target-area-max`。
- 完善距离控制安全策略：速度限制、最小安全距离、连续误检保护、动作过程冻结策略。
- 为关键控制逻辑补充可重复的开发测试脚本，所有脚本放在 `dev_tests/`。

## 开发和测试目录

`dev_tests/` 只放开发、调试、联调脚本。这里的脚本必须调用 `raspbot_posture` 包中已有函数，不实现新的产品逻辑。

当前脚本：

```text
dev_tests/
├── camera_preview.py       # 仅摄像头预览烟测
├── steering_dry_run.py     # 转向控制 dry run
├── full_mode_dry_run.py    # full 模式 dry run
└── hyrox_detector_dry_run.py # HYROX 动作计数器合成数据 dry run
```

运行示例：

```bash
python3 dev_tests/camera_preview.py
python3 dev_tests/steering_dry_run.py
python3 dev_tests/full_mode_dry_run.py
python3 -m dev_tests.hyrox_detector_dry_run
```

## 维护原则

1. 功能代码只进入 `raspbot_posture/`。
2. 根目录入口文件只能解析或转发到包内 CLI，不写摄像头、推理、控制、硬件逻辑。
3. 开发和测试脚本只放 `dev_tests/`，并且只能调用包内已有接口。
4. 新功能先设计包内模块和接口，再写入口参数或测试脚本。
5. 不依赖环境变量、绝对路径或外部 `sys.path` 注入寻找工程代码。
6. 不把旧 demo、notebook、供应商示例直接混入维护路径。
7. 任何新增模式或参数都要同步更新 README。

## 维护流程

1. 在 `raspbot_posture/` 中实现或调整功能模块。
2. 在 `raspbot_posture/*_cli.py` 中暴露必要参数。
3. 在 `dev_tests/` 中增加最小测试脚本，调用包内函数验证行为。
4. 执行静态检查：

```bash
python3 -m py_compile posture_demo.py posture_robot_control_demo.py raspbot_posture/*.py dev_tests/*.py
python3 posture_demo.py --help
python3 posture_robot_control_demo.py --help
```

5. 检查是否出现禁止路径依赖：

```bash
rg -n "RASPBOT_POSTURE_PATH|project_demo|Raspbot_Base|/home/pi|sys\\.path|os\\.environ|os\\.getenv" \
  posture_demo.py posture_robot_control_demo.py raspbot_posture dev_tests
```

6. 更新 README 的“已实现功能”和“待跟进功能”。

## 依赖说明

普通姿态识别和预览需要：

- Python 3
- OpenCV (`cv2`)
- MediaPipe

实车控制还需要树莓派上的 I2C/smbus 支持。非树莓派环境请使用 `--dry-run-control` 先验证控制输出。
