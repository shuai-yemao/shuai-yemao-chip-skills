---
name: rtt-monitor
description: 通过 SEGGER RTT 实时抓取嵌入式目标板日志，支持 J-Link 和 OpenOCD 两种模式。全速运行下零延迟抓取，支持关键字过滤、ANSI 颜色、时间戳、自动重连、多通道监控、环缓冲溢出检测。支持 elog (EasyLogger) 日志格式解析与 tag 过滤。当用户提到 RTT、SEGGER RTT、不用串口看日志、实时日志、J-Link RTT、RTT 监控、elog、EasyLogger 时使用。
version: "1.0.0"
---

# rtt-monitor

通过 SEGGER RTT (Real-Time Transfer) 实时抓取嵌入式目标板的日志输出。
相比串口方式无需占用 UART 引脚，延迟更低，支持目标板全速运行时抓取。

## 触发条件
- 用户提到 RTT、SEGGER RTT、J-Link RTT
- 用户希望在不占用串口的情况下查看日志
- 固件中使用了 SEGGER_RTT_printf 或 elog 库
- 用户说"查看调试日志"、"实时日志"、"不用串口看日志"
- 用户提到 elog、EasyLogger

## 使用前提
- 已安装 SEGGER J-Link Software
- 固件已集成 SEGGER RTT 库并调用 SEGGER_RTT_Init()
- J-Link 探针已连接目标板

## 参数收集
- device: 目标 MCU 型号（如 STM32F407VG）
- interface: SWD 或 JTAG（默认 SWD）
- speed: kHz（默认 4000）
- rtt_addr: RTT 控制块地址（可选，不填则自动搜索）
- channel: RTT 通道号（默认 0）
- log_file: 日志保存路径（可选）
- mode: jlink（默认）/ openocd（通过 OpenOCD telnet 读取 RTT）
- filter: 关键字过滤，只显示含指定字符串的行
- color: 是否启用颜色输出（ERROR 红色、WARN 黄色、INFO 绿色，默认 true）
- timestamp: 是否在每行前加时间戳（默认 true）

## 执行流程

### Step 1 验证工具
```bash
JLinkExe -version
```

### Step 2 启动 RTT 日志器（JLink 模式）
```bash
JLinkRTTLogger -device STM32F407VG -if SWD -speed 4000 -RTTChannel 0 output.log
```

### Step 2（OpenOCD 模式）
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "init" -c "rtt setup 0x20000000 65536 SEGGER_RTT" \
  -c "rtt start" -c "rtt polling_interval 10"
# 通过 telnet :4444 读取 RTT 输出
```

### Step 3 实时输出
持续打印 RTT 输出，Ctrl+C 停止，保存日志文件。

## 固件集成 RTT 快速指南

```c
// 1. 将 SEGGER_RTT.c / SEGGER_RTT.h 加入工程
// 2. 调用初始化（可选，首次调用自动初始化）
SEGGER_RTT_Init();
// 3. 输出日志
SEGGER_RTT_printf(0, "Hello RTT! tick=%u\n", HAL_GetTick());
// 4. 多通道（Channel 1 用于二进制数据）
SEGGER_RTT_Write(1, sensor_data, sizeof(sensor_data));
```

## elog (EasyLogger) 集成

当固件通过 RTT 后端输出 elog 日志时，日志格式为：

```
[颜色码]E/tag (file.c:line) message      ← ERROR 级别
[颜色码]W/tag (file.c:line) message      ← WARN  级别
[颜色码]I/tag (file.c:line) message      ← INFO  级别
[颜色码]D/tag (file.c:line) message      ← DEBUG 级别
[颜色码]V/tag (file.c:line) message      ← VERBOSE 级别（DEBUG 处理）
[颜色码]A/tag (file.c:line) message      ← ASSERT 级别（ERROR 处理）
```

elog 级别前缀: `A/`(ASSERT) `E/`(ERROR) `W/`(WARN) `I/`(INFO) `D/`(DEBUG) `V/`(VERBOSE)

### elog 专属操作
- **按 tag 过滤**: `keil_rtt_analyze filter_tags=["boot","flash","ymodem"]`
- **自动提取**: 自动识别 elog 格式并统计各 tag 出现次数
- **颜色剥离**: 自动去除 ANSI 颜色码，保留纯文本

### 固件集成 elog + RTT 快速指南

```c
// 1. port 层对接 RTT
// elog_port.c
#include "SEGGER_RTT.h"
void elog_port_output(const char *log, size_t size) {
    SEGGER_RTT_printf(0, log, size);
}

// 2. 用户代码按 tag 输出
#include <elog.h>
#define LOG_TAG "boot"

elog_i(LOG_TAG, "System clock: %uMHz", HAL_RCC_GetSysClockFreq() / 1000000);
elog_w(LOG_TAG, "Flash write retry %d/3", retry);
elog_e(LOG_TAG, "YMODEM CRC mismatch, expected=0x%04X", expected);
```

## 边界定义

### 不该激活
- 用户只需要**普通串口**日志查看（不使用 RTT 协议）→ 使用 `serial-monitor`
- 用户没有 J-Link 探针且没有 OpenOCD 环境 → RTT 无法建立连接
- 用户的固件未集成 SEGGER RTT 库
- 用户提到 "RTT" 但指的是网络 RTT（Round-Trip Time）而非 SEGGER RTT

### 不该做
- **禁止**在固件未集成 RTT 库时猜测 RTT 控制块地址
- **禁止**在 J-Link 模式下自动修改目标板的 RAM 内容
- **禁止**将 RTT 日志写入系统临时目录后不经用户确认删除

### 不该碰
- **不触碰**目标板的 Flash：RTT 仅读取 RAM 中的环形缓冲区
- **不触碰**目标板的 CPU 寄存器（除连接探测外）
- **不触碰**非 RTT 通道的 RAM 区域
- **不触碰** J-Link 或 OpenOCD 的全局配置

## 错误处理
| 错误 | 解决方案 |
|------|---------|
| RTT block not found | 检查固件是否调用 SEGGER_RTT_Init()，或手动指定 rtt_addr |
| Connection failed | 检查 J-Link 连接，确认 device 型号 |
| No output | 检查 RTT channel 号，确认固件有输出 |
| Cannot find RTT buffer | 目标板 RAM 搜索范围不正确，手动指定 `--rtt-addr` |
| Lost connection | J-Link 断连，自动重连 3 次后停止 |
| Buffer overflow | RTT 环形缓冲区满，建议增大 BUFFER_SIZE_UP |

## 输出约定
实时显示 RTT 日志流，汇报：
- 连接状态
- RTT 控制块地址
- 实时日志内容（含时间戳）
- 累计接收字节数

## 交接关系

- 上游：`build-keil` / `build-cmake` / `flash-jlink`（编译烧录后查看实时日志）
- 替代：`serial-monitor`（当没有 RTT 支持时回退到串口日志）
- 调试时：`rtos-debug`（RTT 日志发现 RTOS 异常后深入分析）
