# raspbot_temp

短学期暂存仓库

## 开发知识库

小车开发方式、树莓派环境、底层硬件 API、全向移动、传感器和视觉实现整理在：

[CODEBASE_NOTES.md](CODEBASE_NOTES.md)

## YOLO 预览

树莓派小车处于 AP 模式时，电脑先连接小车 Wi-Fi，然后 SSH 到树莓派：

```bash
ssh pi@192.168.1.11
```

在树莓派上运行检测并开启网页预览：

```bash
python3 detect1.py --source 0 --weights weights/v5lite-c.pt --preview --nosave
```

这台电脑浏览器访问：

```text
http://192.168.1.11:8080/
```

常用参数：

```bash
--preview-port 8080      # 修改预览端口
--preview-width 640      # 限制预览宽度，降低 AP 网络压力
--preview-fps 10         # 限制预览帧率
--preview-quality 70     # JPEG 压缩质量
```

## 人脸跟随预览

SSH 到树莓派后运行：

```bash
python3 follow.py
```

这台电脑浏览器访问：

```text
http://192.168.1.11:8080/
```

停止时在 SSH 终端按 `Ctrl+C`，程序会停车、释放摄像头并复位舵机。

如果 8080 端口已经被 YOLO 预览占用，可以换端口：

```bash
python3 follow.py --preview-port 8081
```

## 身体姿态判断预览

SSH 到树莓派后运行：

```bash
python3 posture_demo.py
```

这台电脑浏览器访问：

```text
http://192.168.1.11:8080/
```

可识别的基础姿态包括站立、举手、T 字姿势、蹲/坐、左倾和右倾。画面上会显示简单深蹲计数，完成一次“站立 -> 蹲下 -> 重新站立”计 1 次。

姿态 demo 默认使用异步流程：摄像头持续取帧，MediaPipe Pose 按较低频率推理，网页预览复用最新一次识别结果。因此预览画面不会被单次推理明显卡住。

低负载默认参数：

```bash
--inference-fps 8       # 姿态推理频率，越高越不容易漏掉快速动作
--preview-fps 8         # 网页预览推送帧率
--preview-width 480     # 预览压缩宽度
--preview-quality 65    # JPEG 质量
```

如果树莓派仍然吃力，可以继续降推理频率：

```bash
python3 posture_demo.py --inference-fps 3
```

深蹲计数使用膝盖角度滞回状态机，默认更适合快速动作。如果误计数偏多，可以增加确认样本或冷却时间：

```bash
python3 posture_demo.py --squat-down-frames 2 --squat-up-frames 2 --squat-cooldown 0.6
```

骨架点绘制默认关闭，只保留轻量人体框和文字状态。需要调试关键点时再打开：

```bash
python3 posture_demo.py --draw-landmarks
```

后续做人体识别跟踪时，可以复用代码中的 `AnalysisState.get_tracking_target()`。它返回归一化的人体目标状态，包括 `center_x`、`center_y`、`area`、`confidence` 和当前姿态，适合直接接小车运动控制。后续新增其他动作时，按 `ActionDetectorRegistry` 的形式注册新的动作检测器即可，结果会进入 `PoseAnalysis.actions`，也可以通过 `AnalysisState.get_action_status(name)` 读取。

如果摄像头画面左右和预期相反，可以加镜像参数：

```bash
python3 posture_demo.py --mirror
```

旧参数 `--squat-stable-frames` 仍然保留，会同时设置下蹲和起身确认样本数：

```bash
python3 posture_demo.py --squat-stable-frames 2
```

树莓派完全离线时，需要提前把 lite 模型放到 MediaPipe 的模型目录。脚本默认使用 lite 模型：

```bash
python3 posture_demo.py --model-complexity 0
```

模型文件路径：

```text
/home/pi/.local/lib/python3.11/site-packages/mediapipe/modules/pose_landmark/pose_landmark_lite.tflite
```

### 姿态 Demo 工程结构

`posture_demo.py` 现在只作为兼容入口，核心代码拆分在 `raspbot_posture/`：

```text
raspbot_posture/
  cli.py          # 命令行参数和 main()
  app.py          # 主循环：摄像头、推理线程、预览发布
  camera.py       # 摄像头打开和分辨率设置
  preview.py      # raw socket HTTP/MJPEG 网页预览
  model_paths.py  # MediaPipe 离线模型路径检查
  state.py        # 线程共享状态、人体目标、动作状态
  geometry.py     # 关键点几何计算和人体目标框
  vision.py       # 姿态特征提取和基础姿态分类
  actions.py      # 深蹲计数和后续动作检测扩展点
  inference.py    # MediaPipe 推理线程和分析结果组装
  rendering.py    # 预览画面文字、人体框绘制
```

后续新增动作优先放到 `actions.py`，新增姿态特征优先放到 `geometry.py` / `vision.py`，不要再把逻辑堆回 `posture_demo.py`。
