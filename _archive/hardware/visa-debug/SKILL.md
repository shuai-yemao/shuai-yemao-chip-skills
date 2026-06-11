---
name: visa-debug
description: 当需要调试 GPIB/USB/TCP/Serial VISA 仪器通信时使用，支持 SCPI 命令收发、波形捕获、截图和持续监控。当用户提到 VISA、SCPI、GPIB、仪器控制、示波器通信、信号源、万用表、程控仪器时使用。
version: "1.0.0"
---

# VISA 仪器调试

## 适用场景

- 需要识别和探测连接的 VISA 仪器（示波器、万用表、信号源等）。
- 需要发送 SCPI 命令查询或控制仪器。
- 需要从示波器捕获波形数据并保存为 CSV。
- 需要捕获仪器屏幕截图。
- 需要持续监控某个测量值的变化。

## 必要输入

- VISA 资源字符串（如 `TCPIP::192.168.1.100::INSTR`、`USB0::0x1AB1::0x04CE::DS1ZA1234::INSTR`）。
- SCPI 命令（查询/写入/监控模式需要）。

## 依赖

- `pyvisa`（pip install pyvisa）
- `pyvisa-py`（纯 Python 后端，pip install pyvisa-py）或 NI-VISA 驱动

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认操作参数。
2. 探测环境：
   ```bash
   python scripts/visa_tool.py --detect
   ```
3. 根据需求执行操作：
   ```bash
   # 查询仪器标识
   python scripts/visa_tool.py --resource "TCPIP::192.168.1.100::INSTR" --idn

   # 发送 SCPI 查询
   python scripts/visa_tool.py --resource "TCPIP::192.168.1.100::INSTR" --query ":MEAS:VOLT?"

   # 捕获波形
   python scripts/visa_tool.py --resource "TCPIP::192.168.1.100::INSTR" --waveform --output wave.csv
   ```

## 失败分流

- `connection-failure`：VISA 资源未找到或无法打开连接。
- `timeout`：仪器未响应。
- `command-error`：SCPI 命令被仪器拒绝。
- `data-error`：波形或截图数据传输失败。

## 输出约定

示例输出格式：

```
结果: ✅ Rigol Technologies,DS1054Z,DS1ZA1234,00.04.04.SP4
  资源: TCPIP::192.168.1.100::INSTR
```

## 边界定义

### 不该激活
- 用户没有 VISA 仪器（示波器、万用表、信号源等），只是用串口调试 MCU → `serial-monitor`
- 用户需要在 MCU 资源受限环境中实现 SCPI 解析 → `peripheral-driver`
- 用户需要的是 GPIB 控制而非 SCPI 命令 → GPIB 协议不同，需专门工具
- 用户的仪器不支持 SCPI（老旧仪器可能使用专有命令集）

### 不该做
- **禁止**向仪器发送可能修改校准数据的 SCPI 命令（如 `:CALibration:` 前缀）
- **禁止**向仪器发送可能导致输出短路或过载的配置命令
- **禁止**在仪器正在采集关键数据时执行耗时命令（如截图、长波形捕获）

### 不该碰
- **不触碰**仪器的校准数据和 EEPROM 配置区
- **不触碰**非目标仪器的其他 VISA 资源
- **不触碰** NI-VISA 或 pyvisa-py 驱动配置

## 交接关系

- 从 `build-keil` / `build-platformio` 烧录固件后，用此 skill 验证硬件输出信号。
- 与 `serial-monitor` 互补：serial-monitor 查看串口调试输出，visa-debug 进行仪器级测量验证。
- 与 `modbus-debug` / `can-debug` 互补：协议调试配合仪器测量。
