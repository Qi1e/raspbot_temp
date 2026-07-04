# raspbot_posture

Raspbot 姿态识别与姿态跟随控制工程。仓库的可维护功能代码只放在 `raspbot_posture/` 包体中；根目录入口文件只负责调用包内 CLI，不实现业务逻辑。

## 当前内容

```text
.
├── posture_demo.py                 # 统一入口，只调用 raspbot_posture.robot_cli
├── raspbot_posture/                # 唯一功能包体
└── dev_tests/                      # 后续开发、联调、测试脚本
```

`project_demo/` 和旧 `test_demo/` 不属于维护代码。需要参考旧资料时只能作为本地资料使用，不从这些目录复制运行逻辑到入口文件；可复用逻辑必须先整理进 `raspbot_posture/`。

## 运行入口

默认姿态识别预览：

```bash
python3 posture_demo.py
```

同一个入口切换运行模式：

```bash
python3 posture_demo.py --run-mode posture
python3 posture_demo.py --run-mode camera
python3 posture_demo.py --run-mode steering
python3 posture_demo.py --run-mode full
```

四种运行模式：

- `posture`：姿态识别、人体目标框、动作判断和网页预览，不发送硬件指令。默认模式。
- `camera`：仅摄像头和网页预览，不启动 MediaPipe，不发送硬件指令。
- `steering`：姿态推理、人体目标跟踪、云台转向、车身原地转向。
- `full`：在 `steering` 基础上打开距离控制测试分支。

无硬件调试：

```bash
python3 posture_demo.py --run-mode steering --dry-run-control --control-debug
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
├── robot_cli.py        # 控制版参数
├── distance_features.py # 人体估距特征提取
├── distance_models.py  # 标定后的距离模型
├── tracking_estimator.py # 目标距离、云台偏转、底盘方向估计
├── tracking_control.py # 距离规划、轮速混合、车身 yaw 决策
├── tracking_driver.py  # 同步追踪用连续舵机/电机驱动
└── tracking_log.py     # 同步追踪 CSV/参数日志
```

## 已实现功能

- 摄像头采集、镜像、本地窗口和网页 MJPEG 预览。
- MediaPipe Pose 异步推理，支持推理 FPS 限制。
- 基础姿态识别：站立、举手、T pose、蹲/坐、左倾、右倾。
- 人体目标输出：归一化中心点、面积、置信度、当前姿态。
- 深蹲计数动作检测。
- `posture` / `camera` / `steering` / `full` 四种运行模式。
- 云台舵机跟随人体目标。
- 云台偏转持续过大时，车身短脉冲原地转向。
- 目标丢失停车、退出停车、退出舵机复位。
- `--dry-run-control` 和 `--control-debug` 调试模式。
- 基于人体面积、肩宽、躯干高度的距离估计模型。
- 云台、车身 yaw、距离运动的同步追踪控制模块。
- 车身旋转时 pan 舵机反向补偿和方向冲突保护。
- 同步追踪运行参数和运动数据 CSV 日志。

## 待跟进功能

- 继续扩大远距离样本，特别是 4m 以上的人体估距模型和置信度策略。
- 完善距离控制安全策略：速度限制、最小安全距离、连续误检保护、动作过程冻结策略。
- 将同步追踪控制接入正式 `posture_demo.py --run-mode full` 前，继续用 `dev_tests/distance_control_demo.py` 做实车验证。
- 为关键控制逻辑补充可重复的开发测试脚本，所有脚本放在 `dev_tests/`。

## 开发和测试目录

`dev_tests/` 只放开发、调试、联调脚本。新增功能先在这里用 demo 验证；确认可用、接口稳定后，再整理进 `raspbot_posture/` 包体。已经进入包体的功能，后续测试脚本必须调用包内接口。

当前脚本：

```text
dev_tests/
├── camera_preview.py       # 仅摄像头预览烟测
├── steering_dry_run.py     # 转向控制 dry run
├── full_mode_dry_run.py    # full 模式 dry run
├── distance_control_demo.py # estimator 接入后的云台 + 车身同步追踪 demo
├── mixed_motion_demo.py    # 固定方向平移 + 转向混控实验 demo
└── target_distance_calibration_demo.py # 人体距离标定采样 demo
```

运行示例：

```bash
python3 -m dev_tests.camera_preview
python3 -m dev_tests.steering_dry_run
python3 -m dev_tests.full_mode_dry_run
```

采集人体目标面积、肩宽、躯干高度与真实距离的标定数据：

```bash
python3 -m dev_tests.target_distance_calibration_demo --distance 1.0 --tilt-angle 80 --confirm-time 15 --duration 10
```

运行后用浏览器打开 `http://<raspberry-pi-ip>:8080/` 查看 socket/MJPEG 预览画面。脚本会默认把 pan 舵机固定到正前方 90 度，把 tilt 舵机移动到 `--tilt-angle`，并把这两个角度写入 CSV。`--confirm-time` 阶段只用于确认测试者是否被拍到，不写入 CSV；之后进入 warmup 和正式采集。按 0.6m、0.8m、1.0m、1.2m、1.5m 等已测距离分别运行一次；脚本会追加写入 `dev_tests/target_distance_samples.csv`，并根据已有样本输出面积、肩宽、躯干高度的简化距离模型，以及推荐的 `--target-area-min` / `--target-area-max`。

回放 CSV 检查当前测试版估距函数：

```bash
python3 -m dev_tests.target_pose_estimator_check
```

估距和追踪输入实现已经进入 `raspbot_posture.tracking_estimator`；`dev_tests/target_pose_estimator.py` 只保留兼容导入。核心入口是 `TargetTrackingInputBuilder`。它会输出摄像头 pan/tilt 偏转方向、车身转向方向、距离误差、小车前进/后退方向和底盘平移角度。

测试小车能否一边转向一边向固定方向前进。这个实验逻辑只写在 demo 内，不属于 `raspbot_posture/` 包体功能：

```bash
python3 -m dev_tests.mixed_motion_demo
```

默认是 dry-run，只打印四个电机速度，不发送硬件指令。确认轮速后再上实车：

```bash
python3 -m dev_tests.mixed_motion_demo --live
```

常用参数：

```bash
--direction forward    # 车体坐标方向：forward/backward/left/right
--speed 30             # 平移速度
--turn left            # 转向方向：left/right
--turn-speed 8         # 叠加转向速度
--duration 2           # 运行秒数，结束自动停车
```

注意：这个 demo 测试的是车体坐标系下的固定方向平移并叠加自转；如果要保持地面坐标系的绝对固定方向，需要后续加入 IMU/航向反馈。

测试 estimator 接入后的云台 + 车身同步追踪：

```bash
python3 -m dev_tests.distance_control_demo
```

默认使用模拟目标特征，只 dry-run 打印舵机和四轮速度，不发送硬件指令。接入真实摄像头但仍不发送硬件指令：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --duration 60 --view-img
```

只测试云台摄像头追踪，不开启车身转向和前进/后退：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --tracking-mode camera --duration 60 --view-img
```

真实摄像头模式会直接调用 `raspbot_posture.camera.open_camera`、MediaPipe 模型检查、姿态分类、人体目标框、动作检测和预览绘制等包内接口，然后把实时画面中的人体目标转换成 `TargetTrackingInputBuilder` 的输入。默认同时启动网页预览，地址仍是 `http://<raspberry-pi-ip>:8080/`；如果只看本地窗口或端口被占用，可以加 `--no-preview`。

确认画面、目标框、姿态、距离状态和 dry-run 轮速合理后，再上实车：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --live --duration 60
```

如果实车阶段也只想让云台跟踪、底盘完全不参与：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --tracking-mode camera --live --duration 60
```

车身转向时，demo 会默认给 pan 舵机叠加一个弱反向前馈，减少“车身已经转动、视觉还没来得及纠偏”导致的转向过度。车身 yaw 还会检查当前画面偏转方向：如果画面里的目标方向和云台历史偏角要求的车身转向方向冲突，demo 会先暂停车身 yaw，让云台把目标拉回，避免人物从画面边缘进入时反向转。初次实车建议先用较小转向速度和默认参数观察；如果补偿方向反了，改 `--yaw-servo-compensation-sign 1`。

| 参数 | 默认值 | 作用 | 调参建议 |
| --- | --- | --- | --- |
| `--max-reasonable-distance` | `10.0` | 丢弃超过该上限的估距，超过后记为 `unknown` 且不允许距离运动 | 场景不会超过 10m 时保持默认；设为 `0` 或负数可关闭过滤 |
| `--body-yaw-deadband-degrees` | `4.0` | pan 舵机偏离中心超过该角度后才允许车身转向 | 低于 `4.0` 容易放大过度转向 |
| `--body-yaw-gain` | `0.12` | pan 偏角转换成车身 yaw 速度的比例 | 车身反应太弱再小幅增加 |
| `--body-yaw-screen-gate-degrees` | `3.0` | 画面偏转超过该值且方向与 pan 偏角冲突时，暂停车身 yaw | 设为 `0` 或负数可关闭该保护 |
| `--max-yaw-speed` | `3.5` | 限制车身原地转向速度 | 先保持较低，确认不过冲后再提高 |
| `--yaw-servo-compensation-gain` | `0.5` | 用车身 yaw 命令估算 pan 反向补偿强度，单位近似为 `deg / yaw_speed / s` | 过度偏向一侧就逐步增大；舵机明显抢跑或抖动就减小；设为 `0` 可关闭 |
| `--yaw-servo-compensation-max-step` | `0.6` | 每次舵机更新最多叠加多少度补偿；补偿会累计到足够形成实际舵机命令 | 不要调得太大，先用 `0.6~0.8` 验证 |
| `--yaw-servo-compensation-deadband` | `0.5` | yaw 命令绝对值小于该值时不补偿 | 小车轻微抖动时误补偿就调大 |
| `--yaw-servo-compensation-sign` | `-1` | 补偿方向，`-1` 表示 pan 与正 yaw 命令反向 | 如果车身转动时画面偏移更严重，改成 `1` |
| `--camera-servo-step` | `1.0` | pan/tilt 单次最大舵机步长，视觉修正和 yaw 补偿叠加后仍受它限制 | 过冲就减小，跟踪太慢再增大 |
| `--camera-servo-gain` | `0.16` | 画面偏转角转换成舵机步长的比例 | 低性能设备上优先保持保守 |
| `--servo-interval` | `0.15` | 舵机更新间隔 | 低性能设备保持 `0.15~0.25`，避免指令太密 |

记录本次参数和每轮运动数据，便于后续调参分析：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --live --log-dir dev_tests/logs --duration 60
```

日志会生成两类文件：

```text
dev_tests/logs/tracking_<时间>.csv
dev_tests/logs/tracking_<时间>_args.json
```

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `--log-dir` | 空 | 非空时启用日志，写入该目录 |
| `--log-prefix` | `tracking` | 日志文件名前缀 |
| `--log-interval` | `0.05` | CSV 最小记录间隔，单位秒 |
| `--print-motors` | 关闭 | 打印每轮四电机速度，默认关闭以减少控制台刷屏 |

CSV 会记录目标位置、预测距离、pan/tilt 误差、视觉 pan 增量、yaw 补偿增量、yaw 补偿残差、最终舵机增量、车身 yaw、yaw 决策原因、前进方向、四轮速度、规划原因等字段；`args.json` 会记录本次启动参数。

demo 已接入 `raspbot_posture.tracking_estimator.TargetTrackingInputBuilder`、`raspbot_posture.tracking_control` 和 `raspbot_posture.tracking_driver`，控制链路是：

```text
目标特征 -> MotionTrackingInput
  ├── camera pan/tilt error -> 云台舵机
  ├── body_yaw_error        -> 车身转向
  ├── distance_error        -> 低频距离运动目标
  └── action_active         -> 深蹲/动作时阻断车身运动
```

距离规划默认每 `1.5s` 更新一次运动目标，新的目标会覆盖旧目标；总控仍按 `0.05s` 高频刷新轮速。云台优先，舵机刚动时距离规划会返回 `servo moving`。

模拟深蹲等动作阻断车身运动：

```bash
python3 -m dev_tests.distance_control_demo --action-active --posture "Squat or sit"
```

## 维护原则

1. 稳定功能代码只进入 `raspbot_posture/`。
2. 根目录入口文件只能解析或转发到包内 CLI，不写摄像头、推理、控制、硬件逻辑。
3. 新功能先在 `dev_tests/` 中用 demo 实现和实车验证，确认后再进入包体。
4. 已经进入包体的功能，开发和测试脚本只能调用包内已有接口，不重复实现产品逻辑。
5. 不依赖环境变量、绝对路径或外部 `sys.path` 注入寻找工程代码。
6. 不把旧 demo、notebook、供应商示例直接混入维护路径。
7. 任何新增模式、demo 或参数都要同步更新 README。

## 维护流程

1. 先在 `dev_tests/` 中写最小 demo，完成 dry-run 和实车验证。
2. demo 行为确认后，再把稳定、可复用的逻辑整理进 `raspbot_posture/`。
3. 在 `raspbot_posture/*_cli.py` 中暴露必要参数。
4. 保留或更新 `dev_tests/` 中的测试脚本，让它调用包内函数验证行为。
5. 执行静态检查：

```bash
python3 -m py_compile posture_demo.py raspbot_posture/*.py dev_tests/*.py
python3 posture_demo.py --help
```

6. 检查是否出现禁止路径依赖：

```bash
rg -n "RASPBOT_POSTURE_PATH|project_demo|Raspbot_Base|/home/pi|sys\\.path|os\\.environ|os\\.getenv" \
  posture_demo.py raspbot_posture dev_tests
```

7. 更新 README 的“已实现功能”“待跟进功能”和相关 demo 说明。

## 依赖说明

普通姿态识别和预览需要：

- Python 3
- OpenCV (`cv2`)
- MediaPipe

实车控制还需要树莓派上的 I2C/smbus 支持。非树莓派环境请使用 `--dry-run-control` 先验证控制输出。
