# Raspbot 小车开发知识库

本知识库基于当前仓库的 `project_demo/` 示例代码整理，目标是给后续开发提供一份“看得懂、能复制、能改”的工程手册。

重点来源：

- `project_demo/lib/McLumk_Wheel_Sports.py`：麦克纳姆轮运动封装，全向移动核心。
- `project_demo/08.AI_Visual_Interaction_Course/08.Autopilot_map_sandbox/Raspbot_Lib.py`：底层 I2C 硬件驱动。
- `project_demo/03.Basic_car_course/`：电机、舵机、超声波、巡线传感器等基础示例。
- `project_demo/04.Car_motion_control/`：前后、平移、斜向、旋转等运动示例。
- `project_demo/05.Comprehensive_gameplay/`：红外巡线、超声避障、超声跟随。
- `project_demo/07.AI_Visual_Recognition/`：摄像头、颜色识别、Haar 人脸、TensorFlow 目标识别等视觉基础。
- `project_demo/08.AI_Visual_Interaction_Course/`：颜色跟随、人脸跟随、视觉循线、手势跟随、YOLO/垃圾识别。
- `project_demo/09.AI_Big_Model/AI_CarAgent/`：动作 API 化、语音/大模型编排示例。

## 运行环境

树莓派端常见运行路径：

```python
import sys
sys.path.append('/home/pi/project_demo/lib')
from McLumk_Wheel_Sports import *
```

常见硬件/系统依赖：

- Python 3。
- `smbus`：I2C 通信，底层驱动 `Raspbot_Lib.py` 依赖它。
- `cv2` / OpenCV：摄像头采集、HSV、图像处理、显示。
- `numpy`：视觉处理和矩阵计算。
- `mediapipe`：人脸检测、手势识别。
- `ipywidgets` / `IPython.display`：原厂 notebook 预览用；SSH 脚本不建议依赖。
- `/home/pi/software/oled_yahboom/`：OLED 显示示例依赖。
- 摄像头默认用 `/dev/video0`，代码中一般写 `cv2.VideoCapture(0)`。
- CSI 摄像头示例使用 `picamera2` + `libcamera`，多数 notebook 里是注释模板。

当前小车 AP 模式固定 IP：

```text
192.168.1.11
```

SSH 普通脚本推荐结构：

```python
try:
    # init hardware
    while True:
        # read sensor / camera
        # control motors
        pass
except KeyboardInterrupt:
    stop_robot()
finally:
    stop_robot()
    # release camera / reset servo
```

注意：示例 notebook 很多是为 Jupyter 写的，直接 SSH 运行时常见问题是 `display()` 未定义、daemon 线程启动后主程序退出、`ipywidgets` 不可用。普通 SSH 程序应改成主线程循环或网页 MJPEG 预览。

## 硬件底层 API

底层类：

```python
from Raspbot_Lib import Raspbot
bot = Raspbot()
```

I2C：

- 地址：`0x2B`
- 总线：`1`

主要方法：

```python
bot.Ctrl_Car(motor_id, motor_dir, motor_speed)
bot.Ctrl_Muto(motor_id, motor_speed)
bot.Ctrl_Servo(id, angle)
bot.Ctrl_WQ2812_ALL(state, color)
bot.Ctrl_WQ2812_Alone(number, state, color)
bot.Ctrl_WQ2812_brightness_ALL(R, G, B)
bot.Ctrl_WQ2812_brightness_Alone(number, R, G, B)
bot.Ctrl_IR_Switch(state)
bot.Ctrl_BEEP_Switch(state)
bot.Ctrl_Ulatist_Switch(state)
bot.read_data_array(reg, length)
```

电机编号约定：

```text
0 = L1 左前
1 = L2 左后
2 = R1 右前
3 = R2 右后
```

电机控制方式：

- `Ctrl_Car(motor_id, motor_dir, motor_speed)`：方向和速度分开，`motor_dir=0` 前进，`motor_dir=1` 后退，速度 `0..255`。
- `Ctrl_Muto(motor_id, motor_speed)`：带符号速度，范围 `-255..255`；负数后退，正数前进。全向移动封装主要用它。

舵机：

- `Ctrl_Servo(1, angle)`：水平舵机，常用中位 `90`。
- `Ctrl_Servo(2, angle)`：垂直舵机，示例里常用 `25`、`40`、`80`，底层会限制上限。

传感器寄存器：

```python
# 巡线传感器，1 字节，拆 4 位
track = bot.read_data_array(0x0a, 1)[0]
x1 = (track >> 3) & 0x01
x2 = (track >> 2) & 0x01
x3 = (track >> 1) & 0x01
x4 = track & 0x01

# 超声波，单位 mm
bot.Ctrl_Ulatist_Switch(1)
diss_H = bot.read_data_array(0x1b, 1)[0]
diss_L = bot.read_data_array(0x1a, 1)[0]
distance_mm = diss_H << 8 | diss_L
bot.Ctrl_Ulatist_Switch(0)

# 红外遥控
bot.Ctrl_IR_Switch(1)
ir_value = bot.read_data_array(0x0c, 1)
bot.Ctrl_IR_Switch(0)
```

## 移动操作总览

推荐优先使用：

```python
from McLumk_Wheel_Sports import *
```

常用动作：

```python
move_forward(speed)
move_backward(speed)
move_left(speed)
move_right(speed)
move_diagonal_left_front(speed)
move_diagonal_left_back(speed)
move_diagonal_right_front(speed)
move_diagonal_right_back(speed)
rotate_left(speed)
rotate_right(speed)
drifting(speed, deflection, rate)
move_param_forward(speed, param)
stop_robot()
stop()
```

速度范围：

- 高层封装最终会限制在 `0..255` 或 `-255..255`。
- 示例中普通运动常用 `speed=100`。
- 视觉闭环运动建议更低，比如 `15..50`，否则识别和控制延迟会导致抖动。

最小示例：

```python
import sys
import time
sys.path.append('/home/pi/project_demo/lib')
from McLumk_Wheel_Sports import *

try:
    move_forward(80)
    time.sleep(1)
    move_left(80)
    time.sleep(1)
finally:
    stop_robot()
```

## 全向移动核心

小车使用麦克纳姆轮，可以把“希望底盘往哪个方向平移”转换成四个轮子的速度。

在 `McLumk_Wheel_Sports.py` 中，方向角定义为：

```text
        90 前进
180 左移  |  0 右移
        270 后退
```

核心函数：

```python
def set_deflection(speed, deflection):
    if speed > 255:
        speed = 255
    if speed < 0:
        speed = 0
    rad2deg = math.pi / 180
    vx = speed * math.cos(deflection * rad2deg)
    vy = speed * math.sin(deflection * rad2deg)
    l1 = int(vy + vx)
    l2 = int(vy - vx)
    r1 = int(vy - vx)
    r2 = int(vy + vx)
    return l1, l2, r1, r2
```

含义：

- `vx`：左右方向速度分量，右为正。
- `vy`：前后方向速度分量，前为正。
- `L1/R2` 同组，`L2/R1` 同组。
- `Ctrl_Muto()` 负责把负速度转成反转方向。

典型结果：

```text
前进 90:  L1=+S L2=+S R1=+S R2=+S
后退 270: L1=-S L2=-S R1=-S R2=-S
右移 0:   L1=+S L2=-S R1=-S R2=+S
左移 180: L1=-S L2=+S R1=+S R2=-S
右前 45:  L1=+S L2=0  R1=0  R2=+S
左前 135: L1=0  L2=+S R1=+S R2=0
```

平移封装本质：

```python
def move_right(speed):
    l1, l2, r1, r2 = set_deflection(speed, 0)
    bot.Ctrl_Muto(0, l1)
    bot.Ctrl_Muto(1, l2)
    bot.Ctrl_Muto(2, r1)
    bot.Ctrl_Muto(3, r2)
```

原地旋转不是单纯调用 `set_deflection`，而是在左右轮组上额外翻符号：

```python
def rotate_left(speed):
    l1, l2, r1, r2 = set_deflection(speed, 180)
    bot.Ctrl_Muto(0, l1)
    bot.Ctrl_Muto(1, -l2)
    bot.Ctrl_Muto(2, r1)
    bot.Ctrl_Muto(3, abs(r2))

def rotate_right(speed):
    l1, l2, r1, r2 = set_deflection(speed, 0)
    bot.Ctrl_Muto(0, l1)
    bot.Ctrl_Muto(1, abs(l2))
    bot.Ctrl_Muto(2, r1)
    bot.Ctrl_Muto(3, -r2)
```

带角速度的全向移动：

```python
def set_deflection_rate(speed, deflection, rate):
    vx = speed * math.cos(deflection * math.pi / 180)
    vy = speed * math.sin(deflection * math.pi / 180)
    vp = -rate * (117 + 132) / 2
    l1 = int(vy + vx - vp)
    l2 = int(vy - vx + vp)
    r1 = int(vy - vx - vp)
    r2 = int(vy + vx + vp)
    return l1, l2, r1, r2
```

`drifting(speed, deflection, rate)` 就是把上面的四轮速度直接写入电机。它适合“边平移边旋转”的动作。

如果要写自己的全向控制，推荐封装成：

```python
def omni_move(speed, angle_deg, rotate_rate=0):
    if rotate_rate:
        l1, l2, r1, r2 = set_deflection_rate(speed, angle_deg, rotate_rate)
    else:
        l1, l2, r1, r2 = set_deflection(speed, angle_deg)
    bot.Ctrl_Muto(0, l1)
    bot.Ctrl_Muto(1, l2)
    bot.Ctrl_Muto(2, r1)
    bot.Ctrl_Muto(3, r2)
```

## 视觉跟随里的移动控制

很多视觉跟随并不直接使用完整全向角度，而是用“前后速度 + 左右修正量”控制：

```python
speed_L1 = speed_fb + speed_lr
speed_L2 = speed_fb + speed_lr
speed_R1 = speed_fb - speed_lr
speed_R2 = speed_fb - speed_lr
```

这更像差速修正：目标偏左/偏右时改变左右轮组速度，让车朝目标方向修正。示例位置：

- `09.AI_Big_Model/AI_CarAgent/Track_color_Follow_api.py`
- `10.Basic_voice_control/4.Speech_Car_line_patrol/Track_color_line_api.py`

手势跟随中还使用：

```python
move_param_forward(speed, target_valuex)
```

它先按前进计算四轮速度，再根据 `param` 增加左/右侧轮速，用于边前进边转向。

## PID 使用方式

PID 文件在多个目录有副本，例如：

- `project_demo/08.AI_Visual_Interaction_Course/05.Face_follow/PID.py`
- `project_demo/09.AI_Big_Model/AI_CarAgent/PID.py`

常用的是位置式 PID：

```python
pid = PID.PositionalPID(P, I, D)
pid.SystemOutput = current_value
pid.SetStepSignal(target_value)
pid.SetInertiaTime(inertia_time, sample_time)
output = pid.SystemOutput
```

示例参数：

- 人脸水平转向：`PID.PositionalPID(0.8, 0, 0.2)`
- 人脸垂直舵机：`PID.PositionalPID(0.8, 0.2, 0.01)`
- 人脸距离速度：`PID.PositionalPID(1.1, 0, 0.2)`
- 视觉循线：`PID.PositionalPID(0.5, 0, 1)` 或颜色线 API 中的 `0.5, 0.001, 0.0001`

经验：

- `SystemOutput` 放当前测量值，比如目标中心 x、目标半径、线中心偏差。
- `SetStepSignal()` 放目标值，比如图像中心 `160/320`、目标半径 `80`。
- 输出要限幅，避免过猛。

## 摄像头与预览

USB 摄像头模板：

```python
import cv2

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)

ret, frame = cap.read()
```

示例里也常写成：

```python
image = cv2.VideoCapture(0)
image.set(3, 320)
image.set(4, 240)
image.set(5, 30)
```

CSI 摄像头模板：

```python
from picamera2 import Picamera2
import libcamera

picam2 = Picamera2()
camera_config = picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (320, 240)}
)
camera_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(camera_config)
picam2.start()
frame = picam2.capture_array()
```

Notebook 预览方式：

```python
import ipywidgets.widgets as widgets
image_widget = widgets.Image(format='jpeg', width=640, height=480)
image_widget.value = bytes(cv2.imencode('.jpg', frame)[1])
```

SSH 运行建议：

- 不用 `display()` 和 `ipywidgets`。
- 使用我们在 `detect1.py` / `follow.py` 里加的 MJPEG HTTP 预览。
- AP 模式电脑端访问 `http://192.168.1.11:8080/`。

## 颜色识别与颜色跟随

HSV 检测基本流程：

```python
frame_ = cv2.GaussianBlur(frame, (5, 5), 0)
hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
mask = cv2.inRange(hsv, color_lower, color_upper)
mask = cv2.erode(mask, None, iterations=2)
mask = cv2.dilate(mask, None, iterations=2)
mask = cv2.GaussianBlur(mask, (3, 3), 0)
cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
```

取目标中心和半径：

```python
cnt = max(cnts, key=cv2.contourArea)
(color_x, color_y), color_radius = cv2.minEnclosingCircle(cnt)
```

常见阈值：

```python
red    = ([0, 43, 89],   [7, 255, 255])
green  = ([54, 104, 64], [78, 255, 255])
blue   = ([92, 100, 62], [121, 255, 255])
yellow = ([26, 100, 91], [32, 255, 255])
orange = ([11, 43, 46],  [25, 255, 255])
```

颜色跟随控制：

- x 方向：目标中心 `color_x` 对齐图像中心 `160`。
- y 方向：目标中心 `color_y` 控制云台垂直舵机。
- 距离：目标半径 `color_radius` 控制前进/后退速度。
- 运动：`control_motor_speed(speed_fb, speed_lr)` 调整左右轮组速度。

## 人脸识别、追踪、跟随

两类实现：

- Haar cascade：`07.AI_Visual_Recognition/06.Face_recognition/06_Face_recognition.ipynb`
- MediaPipe FaceDetection：`08.AI_Visual_Interaction_Course/04.Face_tracking/` 和 `05.Face_follow/`

MediaPipe 人脸检测核心：

```python
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(min_detection_confidence=0.75)

img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
results = face_detection.process(img_rgb)
```

检测框转像素坐标：

```python
bbox_c = detection.location_data.relative_bounding_box
ih, iw, _ = frame.shape
x = int(bbox_c.xmin * iw)
y = int(bbox_c.ymin * ih)
w = int(bbox_c.width * iw)
h = int(bbox_c.height * ih)
center_x = x + w // 2
```

人脸跟随控制逻辑：

- `center_x` 用于水平转向 PID。
- `y + h / 2` 用于垂直舵机 PID。
- `h / 2` 近似作为目标距离指标。
- `h / 2` 在 `75..100`：认为距离合适，停车。
- `h / 2 > 60`：人脸太近，居中时后退。
- `20 < h / 2 < 55`：人脸较远，居中时前进。
- `target_valuex > 50`：左转修正。
- `target_valuex < -50`：右转修正。

## 视觉循线

来源：

- `08.AI_Visual_Interaction_Course/06.Vision_Based_Auto_LineFollowing/`
- `10.Basic_voice_control/4.Speech_Car_line_patrol/Track_color_line_api.py`

黑线循线流程：

1. 摄像头采集，resize 到 `320x240`。
2. 透视变换，把前方路面拉成俯视图。
3. 灰度化 + 二值化 + 腐蚀。
4. 对下半部分图像按列求和，得到 histogram。
5. 找左右边界：`leftx_base`、`rightx_base`。
6. 计算线中心：`lane_center = (leftx_base + rightx_base) / 2`。
7. 计算偏差：`Bias = 159 - lane_center`。
8. PID 限幅后控制 `move_left`、`move_right`、`move_forward`、`rotate_left/right`。
9. 超声波距离 `<200mm` 时停车并蜂鸣。

关键透视变换：

```python
matSrc = np.float32([[0, 149], [320, 149], [281, 72], [43, 72]])
matDst = np.float32([[0, 240], [320, 240], [320, 0], [0, 0]])
matAffine = cv2.getPerspectiveTransform(matSrc, matDst)
dst = cv2.warpPerspective(frame, matAffine, (320, 240))
```

彩色线循线使用 HSV 分割，逻辑更简单：

- 找指定颜色目标。
- 取 `color_x`。
- PID 让 `color_x` 靠近图像中心 `160`。
- `control_motor_speed(line_speed, -x_line_real_value)` 控制前进和左右修正。

## 超声波避障与跟随

避障示例阈值：

```python
NEAR_DISTANCE = 200
FAR_DISTANCE = 425
```

逻辑：

- `<200mm`：后退。
- `200..425mm`：停车后左转。
- `>425mm`：前进。

跟随示例阈值：

```python
NEAR_DISTANCE = 150
MID_DISTANCE = 300
FAR_DISTANCE = 500
```

逻辑：

- `<150mm`：后退。
- `150..300mm`：停车。
- `300..500mm`：前进。
- `>=500mm`：停车，目标太远或无目标。

## 手势跟随

来源：

- `08.AI_Visual_Interaction_Course/09.Gesture_follows/`

核心：

- MediaPipe 手势识别。
- 取第 9 号关键点作为手部中心。
- x 方向 PID 控制小车朝手部修正。
- y 方向 PID 控制垂直舵机。
- 手势 `"Zero"` 控制停车，其他手势执行跟随。

运动调用：

```python
if finger_number == "Zero":
    stop_robot()
else:
    if -40 < target_valuex < 40:
        target_valuex = 0
    move_param_forward(speed, target_valuex)
```

## 身体姿态判断

本仓库新增 demo：

- `posture_demo.py`

它使用 `mediapipe.solutions.pose.Pose` 做人体关键点检测，默认只输出姿态判断和远程预览，不控制小车移动。

树莓派 AP 模式完全离线时，必须提前放好 MediaPipe 模型。当前脚本默认使用 lite 模型：

```text
/home/pi/.local/lib/python3.11/site-packages/mediapipe/modules/pose_landmark/pose_landmark_lite.tflite
```

运行：

```bash
python3 posture_demo.py
```

浏览器访问：

```text
http://192.168.1.11:8080/
```

可判断的基础姿态：

- `Standing`：双腿较直，肩胯中心基本对齐。
- `Arms up`：双手腕高于肩部。
- `T pose`：双手接近肩部高度且向左右展开。
- `Squat or sit`：膝关节弯曲明显。
- `Leaning left` / `Leaning right`：肩部中心相对胯部中心有明显水平偏移。
- 深蹲计数：检测到稳定的 `Standing -> Squat or sit -> Standing` 后计 1 次。

判断依据主要来自肩、肘、腕、胯、膝、踝关键点：

```python
left_knee_angle = angle(left_hip, left_knee, left_ankle)
right_knee_angle = angle(right_hip, right_knee, right_ankle)
torso_offset = (shoulder_mid_x - hip_mid_x) / shoulder_width
```

姿态判断是启发式规则，不是训练模型；实际效果受摄像头角度、人体是否完整入镜、光照、遮挡影响。若画面左右相反，运行时加：

```bash
python3 posture_demo.py --mirror
```

深蹲计数使用简单状态机和帧数防抖：

```python
if posture == 'Standing' and stage == 'down':
    count += 1
    stage = 'up'
elif posture == 'Squat or sit' and stage in ('up', 'unknown'):
    stage = 'down'
```

如果计数受抖动影响，可以提高稳定帧数：

```bash
python3 posture_demo.py --squat-stable-frames 5
```

## 动作 API 化

来源：

- `09.AI_Big_Model/AI_CarAgent/Car_base_control.py`
- `09.AI_Big_Model/AI_CarAgent/Car_execute_api.py`

基础动作封装示例：

```python
def Car_Forword(speed=40, mytime=1):
    move_forward(speed)
    time.sleep(mytime)
    stop_robot()
    time.sleep(0.2)

def Car_left_translation(speed=45, mytime=1):
    move_left(speed)
    time.sleep(mytime)
    stop_robot()
    time.sleep(0.2)
```

这种封装适合给语音、大模型或 Web API 调用。建议后续所有高层任务都包装成“动作函数”，内部自己负责停车和异常清理。

复位动作建议：

```python
def Car_Reset():
    bot.Ctrl_WQ2812_ALL(0, 7)
    bot.Ctrl_Ulatist_Switch(0)
    bot.Ctrl_Servo(1, 90)
    bot.Ctrl_Servo(2, 25)
    stop_robot()
```

## 推荐开发模板

普通硬件脚本：

```python
import sys
import time
sys.path.append('/home/pi/project_demo/lib')
from McLumk_Wheel_Sports import *

def main():
    try:
        # init
        while True:
            # read sensor
            # decide action
            time.sleep(0.02)
    except KeyboardInterrupt:
        print('Stopping...')
    finally:
        stop_robot()
        bot.Ctrl_Servo(1, 90)
        bot.Ctrl_Servo(2, 25)

if __name__ == '__main__':
    main()
```

视觉脚本：

```python
cap = cv2.VideoCapture(0)
cap.set(3, 320)
cap.set(4, 240)

try:
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            stop_robot()
            time.sleep(0.05)
            continue
        # vision process
        # publish preview
        # motion control
finally:
    stop_robot()
    cap.release()
```

## 常见坑

- `project_demo` 里有多个 `Raspbot_Lib.py`、`PID.py`、`McLumk_Wheel_Sports.py` 副本。运行时到底 import 哪个，取决于当前目录和 `sys.path`。
- notebook 代码常依赖 `ipywidgets`，SSH 运行要改成普通循环或 HTTP 预览。
- 视觉代码里很多地方没有检查 `ret`，摄像头断帧会导致 `cv2.cvtColor(None, ...)` 崩溃。
- 示例有裸 `except:`，会吞掉硬件/I2C/摄像头错误。调试版应打印异常。
- 退出时必须 `stop_robot()`，并释放摄像头。
- 超声波使用前要 `Ctrl_Ulatist_Switch(1)`，不用时关闭。
- 舵机 2 的角度上限在不同驱动副本里可能不同，常用安全范围 `0..100/110`。
- `05.Comprehensive_gameplay/1.infrared_patrol_line.ipynb` 里有疑似笔误 `speed =3o#30`，应改为 `speed = 30`。
- `socketserver/http.server` 在目标树莓派环境可能不可用；本仓库的 `detect1.py` 和 `follow.py` 已改成只用 `socket + threading` 的预览服务。

## 快速索引

| 目标 | 优先看 |
| --- | --- |
| 全向移动公式 | `project_demo/lib/McLumk_Wheel_Sports.py` |
| 直接控制电机/舵机/传感器 | `project_demo/08.AI_Visual_Interaction_Course/08.Autopilot_map_sandbox/Raspbot_Lib.py` |
| 前后左右/斜向/旋转演示 | `project_demo/04.Car_motion_control/` |
| 超声波避障/跟随 | `project_demo/05.Comprehensive_gameplay/2.ultrasonic_obstacle_avoidance.ipynb`, `3.ultrasonic_followup.ipynb` |
| 摄像头基础 | `project_demo/07.AI_Visual_Recognition/01.Camera_Driving/` |
| HSV 颜色识别 | `project_demo/07.AI_Visual_Recognition/02.Color_Recog/` |
| 人脸检测/跟随 | `project_demo/08.AI_Visual_Interaction_Course/04.Face_tracking/`, `05.Face_follow/` |
| 视觉循线 | `project_demo/08.AI_Visual_Interaction_Course/06.Vision_Based_Auto_LineFollowing/` |
| 手势跟随 | `project_demo/08.AI_Visual_Interaction_Course/09.Gesture_follows/` |
| 身体姿态判断 | `posture_demo.py` |
| 动作 API 化 | `project_demo/09.AI_Big_Model/AI_CarAgent/Car_base_control.py` |
