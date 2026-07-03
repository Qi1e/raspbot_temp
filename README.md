# raspbot_posture

Raspbot 姿态识别与姿态跟随控制工程。仓库的可维护功能代码只放在 `raspbot_posture/` 包体中；根目录入口文件只负责调用包内 CLI，不实现业务逻辑。

## 当前内容

```text
.
├── posture_demo.py                 # 姿态识别预览入口，只调用 raspbot_posture.cli
├── posture_robot_control_demo.py   # 姿态跟随控制入口，只调用 raspbot_posture.robot_cli
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
└── full_mode_dry_run.py    # full 模式 dry run
```

运行示例：

```bash
python3 dev_tests/camera_preview.py
python3 dev_tests/steering_dry_run.py
python3 dev_tests/full_mode_dry_run.py
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
