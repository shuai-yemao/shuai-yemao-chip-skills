---
name: modbus-debug
description: 当需要调试 Modbus RTU（串口）或 Modbus TCP（网络）设备通信时使用，支持寄存器读写、从站扫描和持续监控。当用户提到 Modbus、Modbus RTU、Modbus TCP、寄存器读写、从站扫描、485 调试、Modbus 调试时使用。
version: "1.0.0"
---

# Modbus 调试

## 适用场景

- 嵌入式设备实现了 Modbus RTU/TCP 从站，需要验证通信是否正常。
- 需要读写保持寄存器、输入寄存器、线圈或离散输入。
- 需要扫描总线上的从站地址，确认设备是否在线。
- 需要持续监控寄存器值的变化。

## 必要输入

- RTU 模式：串口号（如 {SERIAL_PORT}）、波特率、从站地址。
- TCP 模式：主机 IP 和端口、从站地址。
- 操作类型：读/写/扫描/监控。

## 依赖

- `pymodbus`（pip install pymodbus）
- `pyserial`（RTU 模式需要）

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认操作参数。
2. 探测环境：
   ```bash
   python scripts/modbus_tool.py --detect
   ```
3. 根据需求执行对应操作：
   ```bash
   # 读保持寄存器
   python scripts/modbus_tool.py --port {SERIAL_PORT} --slave 1 --read --address 0 --count 10

   # 写寄存器
   python scripts/modbus_tool.py --port {SERIAL_PORT} --slave 1 --write --address 0 --values 100,200

   # 扫描从站
   python scripts/modbus_tool.py --port {SERIAL_PORT} --scan --scan-range 1-10

   # TCP 读取
   python scripts/modbus_tool.py --tcp --host 192.168.1.100 --slave 1 --read --address 0 --count 10
   ```

## 失败分流

- `connection-failure`：串口无法打开、网络不通。
- `slave-no-response`：从站地址无响应。
- `illegal-function`：设备不支持该功能码。
- `illegal-address`：寄存器地址越界。

## 输出约定

示例输出格式：

```
结果: ✅ 读取 10 个寄存器
  连接: RTU {SERIAL_PORT} 9600 8N1
  从站: 1

    地址 |  十进制 |  十六进制 |             二进制
  ------+---------+----------+--------------------
       0 |     100 | 0x0064   | 0000000001100100
       1 |     200 | 0x00c8   | 0000000011001000
```

## 边界定义

### 不该激活
- 用户需要的是纯串口日志查看（无 Modbus 协议）→ `serial-monitor`
- 用户需要调试的是 Modbus ASCII 模式（本 skill 仅支持 RTU/TCP）
- 用户需要在 MCU 固件侧实现 Modbus 从站/主站 → `peripheral-driver`
- 用户提到的 "Modbus" 实际上是 Modbus Plus（MB+）或其他专有变体

### 不该做
- **禁止**向从站写入功能码 05/06/15/16（写操作）前不提示用户确认
- **禁止**在生产环境的从站上执行扫描操作（大量请求可能干扰正常运行）
- **禁止**在没有明确从站地址的情况下广播式扫描整个地址范围

### 不该碰
- **不触碰**非目标从站地址的其他 Modbus 设备
- **不触碰**串口设备的系统驱动配置
- **不触碰**工业控制系统（DCS/SCADA）的实时控制回路

## 交接关系

- 从 `build-keil` / `build-platformio` 烧录固件后，用此 skill 验证 Modbus 通信。
- 与 `serial-monitor` 互补：serial-monitor 查看串口原始输出，modbus-debug 进行协议级调试。
