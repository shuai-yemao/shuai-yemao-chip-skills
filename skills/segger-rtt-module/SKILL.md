---
name: segger-rtt-module
description: SEGGER RTT (Real-Time Transfer) 完整指南——MCU 端集成（源码/配置/API）+ PC 端监控（JLinkRTTClient/OpenOCD/自动脚本）。覆盖 RTT 原理、工程集成（SEGGER_RTT.c/SEGGER_RTT_printf.c）、SEGGER_RTT_Conf.h 配置、API 速查、JLink RTT Viewer/Client 使用、OpenOCD RTT 模式、关键字过滤/ANSI 颜色/时间戳、与 EasyLogger 集成、环缓冲溢出检测。当用户提到 SEGGER RTT、RTT、Real-Time Transfer、SEGGER_RTT_printf、JLink RTT Viewer、RTT 日志、RTT 调试、打印到 RTT、RTT 初始化、SEGGER_RTT_Init、RTT 通道、J-Link RTT、不用串口看日志、实时日志时使用。
version: "1.0.0"
---

# SEGGER RTT 实时传输完整指南

> **SEGGER RTT** (Real-Time Transfer) — 通过 JLink 调试器与目标 MCU 之间进行高速双向通信的技术，
> 不占用额外硬件引脚（复用 SWD/SWO），速度远高于 UART。
>
> 官方仓库：https://github.com/SEGGERMicro/RTT（BSD 许可，SEGGER 原厂维护）
>
> 适用场景：有 JLink 调试器的任何 ARM Cortex-M 项目

---

## 上篇：MCU 端集成

### 场景

- **串口不够用** — MCU 的 UART 已被其他外设占用
- **需要高速日志** — RTT 带宽远高于 UART（可达 1MB/s+）
- **低资源消耗** — RTT 只需约 1KB RAM + 少量 Flash，不用中断
- **与 JLink 联合调试** — 直接用 JLink RTT Viewer / RTT Client 查看日志
- **量产调试** — 成品通过 SWD 接口即可输出日志，不需预留串口

### 输入

- MCU 类型（Cortex-M0/M3/M4/M7 — RTT 全系列支持）
- 调试器（JLink V9+ / ST-Link V2+）
- SEGGER RTT 源码（SEGGER 官网或 GitHub）

### 依赖

- **JLink 调试器** — RTT 需要 JLink 的 RTT 功能支持
- **JLink RTT Viewer** 或 **RTT Client** — PC 端读取 RTT 输出的工具

### 步骤

#### Step 1: 获取源码

```bash
# 方式 1：SEGGER 官网下载（含 RTT Viewer 上位机）
# https://www.segger.com/downloads/jlink/#J-LinkSoftwareAndDocumentationPack

# 方式 2：GitHub
git clone https://github.com/SEGGERMicro/RTT.git
```

需添加的源文件（仅 3 个文件即可工作）：

```
Middlewares/RTT/
├── Inc/
│   ├── SEGGER_RTT.h            # API 头文件
│   ├── SEGGER_RTT_Conf.h       # 配置文件
│   └── SEGGER_RTT_ASM_ARMv7M.S # 汇编优化写入（可选，加速用）
└── Src/
    ├── SEGGER_RTT.c            # 核心实现
    └── SEGGER_RTT_printf.c     # printf 风格格式化（可选）
```

#### Step 2: 配置 SEGGER_RTT_Conf.h

```c
#ifndef SEGGER_RTT_CONF_H
#define SEGGER_RTT_CONF_H

/* ========== 缓冲区数量 ========== */
/* 上行（目标→主机）：日志输出通道。3 个 = 通道0(RTT) + 通道1(SystemView) + 备用 */
#define SEGGER_RTT_MAX_NUM_UP_BUFFERS             (3)

/* 下行（主机→目标）：键盘输入等。3 个 = 同上对应 */
#define SEGGER_RTT_MAX_NUM_DOWN_BUFFERS           (3)

/* ========== 缓冲区大小 ========== */
#define BUFFER_SIZE_UP                            (1024)   // 上行缓冲区（日志）
#define BUFFER_SIZE_DOWN                          (16)     // 下行缓冲区（仅输入）

/* ========== 输出行为 ========== */
/* NO_BLOCK_SKIP: 缓冲区满时丢弃新数据（不阻塞目标）
 * NO_BLOCK_TRIM: 缓冲区满时丢弃最旧数据（保新弃旧）
 * BLOCK: 缓冲区满时等待（可能阻塞目标） */
#define SEGGER_RTT_MODE_DEFAULT                   SEGGER_RTT_MODE_NO_BLOCK_SKIP

/* ========== printf 格式化缓冲区 ========== */
#define SEGGER_RTT_PRINTF_BUFFER_SIZE             (64)

/* ========== 中断锁定 ========== */
/* BASEPRI 阈值：优先级高于此值的中断在 RTT 写入期间不受影响 */
#define SEGGER_RTT_MAX_INTERRUPT_PRIORITY         (0x20)

/* ========== memcpy 优化 ========== */
/* 0 = 标准 memcpy，1 = 字节循环（更小代码尺寸） */
#define SEGGER_RTT_MEMCPY_USE_BYTELOOP            (0)

#endif
```

#### Step 3: 加入工程

**Keil MDK** 中需添加的文件：

| 文件 | 类型 |
|------|------|
| `Middlewares/RTT/Src/SEGGER_RTT.c` | C 源码 |
| `Middlewares/RTT/Src/SEGGER_RTT_printf.c` | C 源码（需要 printf 时） |
| `Middlewares/RTT/Inc/SEGGER_RTT_ASM_ARMv7M.S` | 汇编（可选，性能优化） |

头文件路径添加：
```
Middlewares/RTT/Inc
```

#### Step 4: 初始化与输出

```c
/* main.c — RTT 无需显式初始化！SEGGER_RTT.c 的 construct 函数自动调用
 * 调用任何 API 前自动完成。 */

#include "SEGGER_RTT.h"

int main(void)
{
    /* 方式 1：直接写字符串（推荐 — 避免格式化开销） */
    SEGGER_RTT_WriteString(0, "Hello RTT!\r\n");

    /* 方式 2：printf 风格格式化 */
    SEGGER_RTT_printf(0, "Value: %d, Hex: 0x%08X\r\n", 42, 0xDEAD);

    /* 方式 3：原始字节写入 */
    const uint8_t data[] = { 0x01, 0x02, 0x03 };
    SEGGER_RTT_Write(0, data, sizeof(data));

    /* 方式 4：代替 printf（将 stdout 重定向到 RTT） */
    // int fputc(int ch, FILE *f) {
    //     SEGGER_RTT_WriteChar(0, ch);
    //     return ch;
    // }

    while (1);
}
```

### API 速查

#### 写操作（目标→主机，最常用）

| API | 说明 | 主要用途 |
|-----|------|---------|
| `SEGGER_RTT_WriteString(0, str)` | 写字符串到通道 0 | 简单日志 |
| `SEGGER_RTT_Write(0, buf, len)` | 写原始字节到通道 0 | 二进制数据 |
| `SEGGER_RTT_printf(0, fmt, ...)` | printf 格式化输出到通道 0 | 格式化日志 |
| `SEGGER_RTT_WriteChar(0, ch)` | 写单个字符 | fputc 重定向 |
| `SEGGER_RTT_GetKey()` | 阻塞读按键（下行） | 交互式输入 |

#### 配置与状态

| API | 说明 |
|-----|------|
| `SEGGER_RTT_ConfigUpBuffer(0, "Name", NULL, 0, MODE)` | 重配置通道 0 |
| `SEGGER_RTT_SetFlagsUpBuffer(0, FLAG_ECHO)` | 设置回显标志 |
| `SEGGER_RTT_HasDataDown(0)` | 检查下行是否有数据 |

---

## 下篇：PC 端监控

### 触发条件
- 用户提到 RTT、SEGGER RTT、J-Link RTT
- 用户希望在不占用串口的情况下查看日志
- 固件中使用了 SEGGER_RTT_printf 或 elog 库

### 使用前提
- 已安装 SEGGER J-Link Software
- 固件已集成 SEGGER RTT 库并调用 SEGGER_RTT_Init()
- J-Link 探针已连接目标板

### 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `device` | 目标 MCU 型号 | 必填 |
| `interface` | SWD 或 JTAG | SWD |
| `speed` | 连接速度 (kHz) | 4000 |
| `rtt_addr` | RTT 控制块地址（可选） | 自动搜索 |
| `channel` | RTT 通道号 | 0 |
| `mode` | jlink / openocd | jlink |
| `filter` | 关键字过滤 | 无 |
| `color` | ANSI 颜色输出 | true |
| `timestamp` | 每行前缀时间戳 | true |
| `log_file` | 日志保存路径 | 无 |

### 自动化脚本

本 skill 提供自动化脚本 `scripts/rtt_capture.py`，通过 JLinkRTTClient 自动捕获：

```bash
# 烧录 + 捕获
python scripts/rtt_capture.py --device STM32F411CE --flash firmware.axf --timeout 8

# 仅捕获（已烧录过）
python scripts/rtt_capture.py --device STM32F411CE --timeout 8
```

> **限制**：单次故障输出的 RTT 数据生成极快（毫秒级），RTT Client 捕获窗口可能错过。
> 对于 HardFault 等一次性输出，推荐使用 **JLinkRTTViewer 图形界面** 获得完整输出。

### 手动执行流程

#### 方法 1: JLink RTT Viewer（图形界面）
打开 JLink RTT Viewer → File → Connect → 选择 MCU → OK

连接成功后自动显示 RTT 通道 0 的输出。

#### 方法 2: JLinkRTTClient（命令行）
```bash
JLinkRTTClient.exe
# 自动连接并显示 RTT 输出，Ctrl+C 退出
```

#### 方法 3: OpenOCD RTT 模式
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "init" -c "rtt setup 0x20000000 65536 SEGGER_RTT" \
  -c "rtt start" -c "rtt polling_interval 10"
# 通过 telnet :4444 读取 RTT 输出
```

### elog (EasyLogger) 集成

当固件通过 RTT 后端输出 elog 日志时，日志格式为：

```
[颜色码]E/tag (file.c:line) message      ← ERROR 级别
[颜色码]W/tag (file.c:line) message      ← WARN  级别
[颜色码]I/tag (file.c:line) message      ← INFO  级别
[颜色码]D/tag (file.c:line) message      ← DEBUG 级别
[颜色码]V/tag (file.c:line) message      ← VERBOSE 级别
[颜色码]A/tag (file.c:line) message      ← ASSERT 级别
```

elog 级别前缀: `A/`(ASSERT) `E/`(ERROR) `W/`(WARN) `I/`(INFO) `D/`(DEBUG) `V/`(VERBOSE)

#### elog 专属操作
- **按 tag 过滤**: 仅显示指定 tag 的日志（如 `boot`, `flash`, `ymodem`）
- **自动提取**: 自动识别 elog 格式并统计各 tag 出现次数
- **颜色剥离**: 自动去除 ANSI 颜色码，保留纯文本

#### 固件集成 elog + RTT

```c
// elog_port.c
#include "SEGGER_RTT.h"
void elog_port_output(const char *log, size_t size) {
    SEGGER_RTT_Write(0, log, size);  // 写裸字符串（不用 printf，避免 % 冲突）
}

// 用户代码
#include <elog.h>
#define LOG_TAG "boot"
elog_i(LOG_TAG, "System clock: %uMHz", HAL_RCC_GetSysClockFreq() / 1000000);
elog_w(LOG_TAG, "Flash write retry %d/3", retry);
```

### 错误处理

| 错误 | 解决方案 |
|------|---------|
| RTT Control Block not found | 检查固件是否调用 SEGGER_RTT_Init()，或手动指定 rtt_addr |
| Connection failed | 检查 J-Link 连接，确认 device 型号 |
| No output | 检查 RTT channel 号，确认固件有输出 |
| Lost connection | J-Link 断连，自动重连 3 次后停止 |
| Buffer overflow | RTT 环形缓冲区满，建议增大 BUFFER_SIZE_UP |
| RTT 输出卡死目标 | 缓冲区满了且模式设为 BLOCK | 改为 `SEGGER_RTT_MODE_NO_BLOCK_SKIP` |
| printf 风格日志出现异常字符 | log 中包含 % 字符 | 用 `SEGGER_RTT_Write` 代替 `SEGGER_RTT_printf` |
| ST-Link 无法使用 RTT | ST-Link 不完全支持 RTT | 换用 JLink |

### 边界

- **仅限 JLink / 兼容调试器** — ST-Link 不完全支持 RTT，功能受限
- **不覆盖 EasyLogger 上层封装** — 那是 `elog-module` 的范畴
- **不覆盖 UART 输出** — RTT 和 UART 是互补方案，非替代
- 与 `elog-module` 配合：RTT 作为 elog 的输出后端
- 用户只需要普通串口日志查看 → 使用 `serial-monitor`
- 用户没有 J-Link 探针且没有 OpenOCD 环境 → RTT 无法建立连接
- 用户提到 "RTT" 但指的是网络 RTT（Round-Trip Time）而非 SEGGER RTT

### 交接

- **RTT 不工作** → 用 JLink Commander 确认 `_SEGGER_RTT` 符号地址是否正确
- **需要 JLink 调试技巧** → 使用 `flash-jlink` / `debug-gdb-openocd` skill
- **需要日志分级管理** → 使用 `elog-module` skill 对接 RTT 后端
- **RTT 日志发现异常后深入分析** → `rtos-debug` / `cmbacktrace-debug`
- **编译报 SEGGER_RTT_Conf.h 未找到** → 确认头文件路径已添加 Inc/ 目录

### 参考资料

- **SEGGER RTT 官网**: https://www.segger.com/products/debug-probes/j-link/technology/about-real-time-transfer/
- **GitHub**: https://github.com/SEGGERMicro/RTT
- **JLink RTT Viewer 使用教程**: https://wiki.segger.com/RTT_Viewer
- **与 EasyLogger 集成**: https://github.com/armink/EasyLogger
