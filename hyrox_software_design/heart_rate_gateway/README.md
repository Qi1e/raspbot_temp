# Heart Rate Gateway

用于连接支持标准 BLE Heart Rate Service 的手表或心率带，订阅实时心率并输出 JSON 数据。

已知 vivo WATCH GT2 在 nRF Connect 中能看到 `180D` Heart Rate Service 时，可以优先尝试本组件。

## 安装

```bash
cd heart_rate_gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 扫描设备

```bash
python heart_rate_gateway.py --scan
```

找到名称类似 `vivo WATCH GT2 230` 的设备后，可以直接用名称过滤连接：

```bash
python heart_rate_gateway.py --name "vivo WATCH"
```

也可以用扫描结果里的蓝牙地址连接：

```bash
python heart_rate_gateway.py --address "XX:XX:XX:XX:XX:XX"
```

## 输出格式

默认每次收到心率通知都会输出一行 JSON：

```json
{"type":"heart_rate_sample","device_name":"vivo WATCH GT2 230","timestamp_ms":1782980021300,"bpm":156,"source":"ble_2a37"}
```

## 常见问题

- 如果一直找不到设备，先在 nRF Connect 中确认手表处于可连接状态。
- 如果连接成功但没有数据，打开手表的心率测量或运动模式。
- 如果没有 `2A37 Heart Rate Measurement` 特征，说明手表可能没有开放标准实时心率，需要走 vivo 私有协议或换标准 BLE 心率带。
