# 开发和测试脚本

这个目录用于后续开发、烟测和硬件联调。

规则：

- 不在这里实现正式产品逻辑。
- 调用 `raspbot_posture` 包内已有函数。
- 脚本保持小而聚焦，只验证一个明确目标。
- 如果逻辑会被多个脚本依赖，先整理进 `raspbot_posture/` 再调用。

从仓库根目录运行 demo：

```bash
python3 -m dev_tests.<name>
```

人体距离标定：

```bash
python3 -m dev_tests.target_distance_calibration_demo --distance 1.0 --tilt-angle 80 --confirm-time 15 --duration 10
```

运行后用浏览器打开预览地址：

```text
http://<raspberry-pi-ip>:8080/
```

脚本会默认把 1 号 pan 舵机固定到正前方 90 度，把 2 号 tilt 舵机移动到 `--tilt-angle`，并把这两个角度写入 CSV。`--confirm-time` 是确认阶段，只推送摄像头画面和识别框，不写入 CSV；确认测试者已经出现在画面中后，脚本会进入 warmup，然后正式采集。把人移动到已测量距离，例如 0.6m、0.8m、1.0m、1.2m、1.5m，然后每个距离运行一次命令。脚本会把样本追加写入 `dev_tests/target_distance_samples.csv`，并输出基于人体面积、肩宽、躯干高度的简化距离模型，以及推荐的 `--target-area-min` 和 `--target-area-max`。

回放 CSV 检查当前测试版估距函数：

```bash
python3 -m dev_tests.target_pose_estimator_check
```

估距和追踪输入工具类暂时保留在 `dev_tests/target_pose_estimator.py`，测试通过后再整理进 `raspbot_posture/` 包体。核心入口是 `TargetTrackingInputBuilder`，输出包含摄像头 pan/tilt 偏转方向、车身转向方向、距离误差、小车前进/后退方向和底盘平移角度。

同步追踪可行性 Demo：

```bash
python3 -m dev_tests.distance_control_demo
```

默认是模拟目标 + dry-run。接真实摄像头但不发送硬件指令：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --duration 60 --view-img
```

只开云台摄像头追踪、关闭车身追踪：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --tracking-mode camera --duration 60 --view-img
```

确认画面、人体框、姿态、距离状态和轮速输出后，再实车运行：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --live --duration 60
```

实车只动云台、不动底盘：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --tracking-mode camera --live --duration 60
```

车身转向时，demo 默认给 pan 舵机叠加弱反向补偿，减少车身旋转造成的画面偏移。车身 yaw 会检查当前画面偏转方向；如果它和云台历史偏角要求的车身转向方向冲突，会先暂停车身 yaw，让云台重新拉回目标：

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `--max-reasonable-distance` | `10.0` | 超过该上限的估距记为 `unknown`，不触发距离运动 |
| `--body-yaw-deadband-degrees` | `4.0` | pan 舵机偏离中心超过该角度后才允许车身转向 |
| `--body-yaw-gain` | `0.12` | pan 偏角转换成车身 yaw 速度的比例 |
| `--body-yaw-screen-gate-degrees` | `3.0` | 画面偏转超过该值且方向与 pan 偏角冲突时暂停车身 yaw，设为 `0` 或负数可关闭 |
| `--max-yaw-speed` | `3.5` | 限制车身原地转向速度 |
| `--yaw-servo-compensation-gain` | `0.5` | 补偿强度，设为 `0` 可关闭 |
| `--yaw-servo-compensation-max-step` | `0.6` | 每次舵机更新最多叠加多少度；小于 1 度的补偿会累计到足够形成实际舵机命令 |
| `--yaw-servo-compensation-deadband` | `0.5` | 小 yaw 命令不补偿 |
| `--yaw-servo-compensation-sign` | `-1` | 补偿方向，方向反了改成 `1` |
| `--camera-servo-step` | `1.0` | 视觉修正和补偿叠加后的总限幅 |
| `--camera-servo-gain` | `0.16` | 画面偏转角转换成舵机步长的比例 |
| `--servo-interval` | `0.15` | 舵机更新间隔 |

记录本次参数和运动数据：

```bash
python3 -m dev_tests.distance_control_demo --input-mode camera --live --log-dir dev_tests/logs --duration 60
```

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `--log-dir` | 空 | 非空时启用日志，生成 CSV 和 args JSON |
| `--log-prefix` | `tracking` | 日志文件名前缀 |
| `--log-interval` | `0.05` | CSV 最小记录间隔，单位秒 |
| `--print-motors` | 关闭 | 打印每轮四电机速度，默认关闭以减少控制台刷屏 |

真实摄像头模式直接调用 `raspbot_posture` 包内摄像头、姿态识别、人体目标和预览接口；跟踪估距仍保留在 demo 侧验证。
