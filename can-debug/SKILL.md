---
name: can-debug
description: 当需要调试 CAN 总线通信时使用，支持通过 USB-CAN 适配器监听、发送 CAN 帧和扫描节点。当用户提到 CAN 总线、CAN 调试、CAN 分析、USB-CAN、CAN 帧、CAN 数据、CAN 通信、CANopen 时使用。
version: "1.0.0"
---

# CAN 总线调试

## 适用场景

- 嵌入式设备实现了 CAN 通信，需要验证收发是否正常。
- 需要监听 CAN 总线上的所有帧或过滤特定 ID。
- 需要向 CAN 总线发送测试帧并等待响应。
- 需要扫描总线上的活跃节点。

## 必要输入

- CAN 接口类型（pcan、kvaser、slcan、socketcan、virtual 等）。
- 通道名（取决于接口类型，如 PCAN_USBBUS1、{SERIAL_PORT}、can0）。
- 波特率（默认 500000）。

## 依赖

- `python-can`（pip install python-can）
- 对应适配器的驱动（如 PCAN 需要 PCAN-Basic API）

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认操作参数。
2. 探测环境：
   ```bash
   python scripts/can_tool.py --detect
   ```
3. 根据需求执行操作：
   ```bash
   # 监听总线
   python scripts/can_tool.py --interface pcan --channel PCAN_USBBUS1 --listen --duration 10

   # 发送帧
   python scripts/can_tool.py --interface pcan --channel PCAN_USBBUS1 --send --id 0x123 --data 01,02,03

   # 扫描节点
   python scripts/can_tool.py --interface pcan --channel PCAN_USBBUS1 --scan --scan-range 0x001-0x0FF
   ```

## 失败分流

- `connection-failure`：适配器未连接或驱动未安装。
- `bus-error`：CAN 总线错误（如未接终端电阻）。
- `timeout`：发送后无响应。

## 输出约定

示例输出格式：

```
结果: ✅ 监听完成，收到 15 帧
  连接: pcan PCAN_USBBUS1 500000

  [14:30:01] 0x123  [8]  01 02 03 04 05 06 07 08
  [14:30:01] 0x456  [4]  AA BB CC DD
```

## 边界定义

### 不该激活
- 用户需要的是 CANopen / J1939 / DeviceNet 等上层协议调试（本 skill 仅支持 CAN 2.0 帧级调试）
- 用户没有 USB-CAN 适配器且不需要虚拟 CAN（virtual 模式仅用于测试）
- 用户只需要串口日志 → `serial-monitor`
- 用户需要在 MCU 固件侧实现 CAN 驱动而非调试 → `peripheral-driver`

### 不该做
- **禁止**在无适配器且非 virtual 模式时静默连接
- **禁止**向未知 CAN ID 发送数据（可能触发安全关键系统响应，如车辆 ECU）
- **禁止**修改 CAN 适配器的固件或配置（仅使用 python-can 驱动层）

### 不该碰
- **不触碰**非目标 CAN 通道的其他总线
- **不触碰**系统级 CAN 驱动安装
- **不触碰**目标设备 Flash/RAM

## 交接关系

- 从 `build-keil` / `build-platformio` 烧录固件后，用此 skill 验证 CAN 通信。
- 与 `serial-monitor` 互补：serial-monitor 查看串口调试输出，can-debug 进行 CAN 协议级调试。
