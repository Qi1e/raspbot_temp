# Raspbot Source Map

Source location inspected:

- `/Users/guo/Desktop/程序源码汇总`
- Current writable workspace: `/Users/guo/College/Raspbot_project`

Important note: the writable workspace was empty when inspected. The actual source tree is on the Desktop. If code needs to be edited later, either copy the relevant project into this workspace or grant/edit the Desktop source directly.

## Top-Level Contents

- `课程程序源码/source_code 2/project_demo`: Python demos for the Raspbot courses.
- `课程程序源码/source_code 2/ros2_source_code`: ROS2 workspaces and packages.
- `python驱动库/py_install`: small packaged Python driver library.
- `库文件/底盘驱动库`: duplicate packaged chassis driver library.
- `库文件/Opencv分类器`: Haar cascade XML files.
- `库文件/KMachineLearning-master` and `MNIST_data数据集`: ML examples and datasets, mostly unrelated to chassis control.
- `附件`: speech/yolo zip assets.

The most useful source tree for normal non-ROS Python work is:

`/Users/guo/Desktop/程序源码汇总/课程程序源码/source_code 2/project_demo`

The most useful source tree for ROS2 work is:

`/Users/guo/Desktop/程序源码汇总/课程程序源码/source_code 2/ros2_source_code/yahboomcar_ws/src`

## Core Non-ROS Raspbot Directory

Path:

`/Users/guo/Desktop/程序源码汇总/课程程序源码/source_code 2/project_demo/raspbot`

Key files:

- `Raspbot_Lib.py`: low-level I2C hardware wrapper.
- `PID.py`: incremental, positional, and simple PID controllers.
- `HSV_Config.py`: color segmentation helper using HSV thresholding and contours.
- `face_tracking.py`: MediaPipe face detector wrapper.
- `gesture_action.py`: MediaPipe hand detector and gesture recognizer.
- `color_detection.py`: maps detected color names to WS2812 LED effects.
- `yb-discover.py`: UDP discovery server on `0.0.0.0:8000`; replies to `YAHBOOMRASPBOT_FIND` with `Raspbot_Pi_V2.0`.
- `raspbot_start.sh`: starts `/home/pi/project_demo/raspbot/raspbot.pyc` and `yb-discover.py`.
- `templates/index.html`, `templates/init.html`: Flask templates for video/control UI.
- `raspbot.pyc`: compiled main application. No matching `raspbot.py` source was present.

`raspbot.pyc` strings indicate the compiled app uses Flask, websocket-style handling, camera frames, `Raspbot`, OLED code, face/gesture/color helpers, servo camera functions, and `/video_feed` plus `/init` routes.

## Hardware Driver API

Class:

`Raspbot_Lib.Raspbot`

I2C address:

- `0x2B`
- bus `1`

Main methods:

- `Ctrl_Car(motor_id, motor_dir, motor_speed)`: direct motor control. `motor_dir` is `0` forward, `1` backward; speed clamped to `0..255`.
- `Ctrl_Muto(motor_id, motor_speed)`: signed motor control, `-255..255`; negative means backward.
- `Ctrl_Servo(id, angle)`: servo control, `0..180`, with servo `2` limited to `<=100` in this copy.
- `Ctrl_WQ2812_ALL(state, color)`: all LEDs on/off with color code.
- `Ctrl_WQ2812_Alone(number, state, color)`: one LED.
- `Ctrl_WQ2812_brightness_ALL(R, G, B)`: all LEDs by RGB brightness.
- `Ctrl_WQ2812_brightness_Alone(number, R, G, B)`: one LED by RGB brightness.
- `Ctrl_IR_Switch(state)`: IR receiver switch.
- `Ctrl_BEEP_Switch(state)`: buzzer switch.
- `Ctrl_Ulatist_Switch(state)`: ultrasonic switch.
- `read_data_array(reg, len)`: raw I2C reads.

Sensor register examples from comments and ROS2 driver:

- Line sensor: `read_data_array(0x0a, 1)`, then bits are split into four channels.
- Ultrasonic: high byte `0x1b`, low byte `0x1a`, combined as `diss_H << 8 | diss_L`.
- IR remote: `0x0c`.

`LightShow` in the same file implements LED effects:

- `river`
- `breathing`
- `gradient`
- `random_running`
- `starlight`

## Non-ROS Motion Helper

Path:

`/Users/guo/Desktop/程序源码汇总/课程程序源码/source_code 2/project_demo/lib/McLumk_Wheel_Sports.py`

It wraps mecanum/chassis movement over `Raspbot.Ctrl_Muto`:

- forward/backward/left/right
- diagonal movement
- rotate left/right
- drifting
- stop
- `set_deflection(speed, deflection)` converts speed plus movement angle into four motor speeds.

## Project Demo Groups

Under `project_demo`:

- `03.Basic_car_course`: basic LED tests.
- `04.Car_motion_control`: car motion examples.
- `05.Comprehensive_gameplay`: combined examples.
- `06.Open_source_cv_fundamentals_course`: OpenCV basics.
- `07.AI_Visual_Recognition`: color recognition, camera, TensorFlow object recognition, QR, face, license plate, MediaPipe.
- `08.AI_Visual_Interaction_Course`: color tracking/following, face tracking/following, line following, garbage recognition, sandbox autopilot, gesture follows.
- `raspbot`: compiled Flask/web control app plus reusable helpers.
- `lib`: shared motion helper.

## ROS2 Workspace

Main workspace:

`/Users/guo/Desktop/程序源码汇总/课程程序源码/source_code 2/ros2_source_code/yahboomcar_ws/src`

Packages:

- `yahboomcar_bringup`: main chassis driver.
- `yahboomcar_ctrl`: keyboard control.
- `yahboomcar_msgs`: custom messages.
- `yahboomcar_astra`: camera/color line following.
- `yahboomcar_apriltag`: AprilTag identify/tracking/follow.
- `yahboomcar_mediapipe`: hand/pose/face demos and controls.
- `yahboomcar_visual`: image, AR, laser/image utilities.
- `yahboomcar_description`: robot description/URDF launch files.
- `yahboomcar_point`: point-related package.

### Main ROS2 Driver

Path:

`yahboomcar_bringup/yahboomcar_bringup/Mcnamu_driver.py`

Node:

- name: `driver_node`
- console script: `Mcnamu_driver`
- launch: `yahboomcar_bringup/launch/bringup.launch.py`

Subscriptions:

- `cmd_vel` (`geometry_msgs/Twist`): mecanum drive control.
- `rgblight` (`std_msgs/Int32MultiArray`): RGB light brightness `[R, G, B]`.
- `buzzer` (`std_msgs/Bool`): buzzer on/off.
- `servo` (`yahboomcar_msgs/ServoControl`): servo angles.

Publications:

- `line_sensor` (`std_msgs/Int32MultiArray`): four line sensor bits.
- `ultrasonic` (`std_msgs/Float32`): distance in centimeters (`raw mm / 10`).

Motion mapping:

- `vx = msg.linear.x`
- `vy = msg.linear.y`
- `vz = msg.angular.z`
- scales linear components by `255`
- spin term uses `(117 + 132) / 8`
- sends four wheel values through `Ctrl_Muto(0..3, value)`.

### ROS2 Keyboard

Path:

`yahboomcar_ctrl/yahboomcar_ctrl/yahboom_keyboard.py`

Console script:

- `yahboom_keyboard`

Publishes:

- `cmd_vel`

Keys follow the standard teleop pattern:

- `i`, `,`: forward/back
- `j`, `l`: lateral
- `u`, `o`, `m`, `.`: diagonals
- speed adjustment: `q/z`, `w/x`, `e/c`
- space or `k`: stop

### ROS2 Messages

Path:

`yahboomcar_msgs/msg`

Messages:

- `ServoControl.msg`: `int32 servo_s1`, `int32 servo_s2`
- `Position.msg`: `float32 anglex`, `float32 angley`, `float32 distance`
- `PointArray.msg`: `geometry_msgs/Point[] points`

### ROS2 Line Following

Path:

`yahboomcar_astra/yahboomcar_astra/follow_line.py`

Behavior:

- opens camera with `cv.VideoCapture(0)`
- uses HSV ROI learning or saved HSV file
- computes line center from contour
- publishes `/cmd_vel`
- publishes `servo`
- uses PID to steer toward image center

Helper:

`yahboomcar_astra/yahboomcar_astra/follow_common.py`

Important helpers:

- `write_HSV`
- `read_HSV`
- `ManyImgs`
- `color_follow.line_follow`
- `color_follow.Roi_hsv`
- `simplePID`

### ROS2 Console Scripts

Notable entries found:

- `Mcnamu_driver`
- `yahboom_keyboard`
- `follow_line`
- `apriltag_identify`
- `apriltag_tracking`
- `apriltag_follow`
- `simple_AR`
- `laser_to_image`
- `pub_image`
- `astra_rgb_image`
- `astra_depth_image`
- `astra_image_flip`
- `astra_color_point`
- MediaPipe demos: `01_HandDetector`, `02_PoseDetector`, `03_Holistic`, `04_FaceMesh`, `05_FaceEyeDetection`, `HandCtrl`, `RobotCtrl`, `control_shape`, `FingerCtrl`, `test_msg`

## Likely Dependencies

Python modules used throughout:

- `smbus`
- `rclpy`
- `geometry_msgs`
- `std_msgs`
- `sensor_msgs`
- `cv2`
- `numpy`
- `mediapipe`
- `flask`
- `PIL`
- `tensorflow` / TensorFlow object detection code in older examples
- `apriltag` or related AprilTag dependency

Hardware-specific code will not run correctly on a normal Mac without Raspberry Pi I2C, camera, and ROS2 environment.

## Coding Guidance For Later

- For direct hardware scripts, import and reuse `Raspbot_Lib.Raspbot`; avoid duplicating raw I2C writes.
- For direct movement helpers, reuse `McLumk_Wheel_Sports.py` or the ROS2 `cmd_vel` mapping.
- For ROS2 behavior, add a new package/node or extend an existing package under `yahboomcar_ws/src`; publish `Twist`, `ServoControl`, `Bool`, or `Int32MultiArray` instead of calling I2C directly when the driver node is running.
- For vision demos, keep camera capture and image processing separate from chassis commands when possible. Existing code often mixes them, but separating makes testing safer.
- Be careful with duplicate driver copies. There are several `Raspbot_Lib.py` files. The active import depends on runtime path and current package.
- The Desktop source is read-only from this workspace. Copy the subset to `/Users/guo/College/Raspbot_project` before making edits here.
