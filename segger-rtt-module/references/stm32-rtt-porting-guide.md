# STM32 SEGGER RTT 移植指南

> 目标平台：STM32F4（Cortex-M4F） + JLink
> 开发环境：Keil MDK（ARMCC v5）
> RTT 版本：v8.12c（SEGGER）
> 官方仓库：https://github.com/SEGGERMicro/RTT

---

## 目录

1. [移植前准备](#1-移植前准备)
2. [源码获取与工程组织](#2-源码获取与工程组织)
3. [配置 SEGGER_RTT_Conf.h](#3-配置-segger_rtt_confh)
4. [添加到 Keil 工程](#4-添加到-keil-工程)
5. [初始化与测试](#5-初始化与测试)
6. [printf 重定向到 RTT（可选）](#6-printf-重定向到-rtt可选)
7. [与 EasyLogger 集成](#7-与-easylogger-集成)
8. [RTT Viewer 使用方法](#8-rtt-viewer-使用方法)
9. [常见问题](#9-常见问题)
10. [检查清单](#10-检查清单)

---

## 1. 移植前准备

### 1.1 确认环境

| 项目 | 要求 |
|------|------|
| MCU | 任意 ARM Cortex-M（RTT 全系列支持） |
| 调试器 | **JLink V9+**（ST-Link 不完全支持 RTT） |
| JLink 软件 | V6.20+（含 RTT Viewer / RTT Client） |
| 编译器 | Keil MDK / IAR / GCC皆可 |

### 1.2 RTT vs UART 对比

| 特性 | RTT | UART |
|------|-----|------|
| 额外引脚 | 无（复用 SWD） | 需 TX/RX 两个引脚 |
| 速度 | ~1 MB/s+ | 受波特率限制（115200 ≈ 11KB/s） |
| RAM 开销 | 约 1KB（上行缓冲区） | 0 |
| Flash 开销 | ~500B（核心代码） | UART 驱动大小 |
| 调试器依赖 | 需要 JLink | 无 |
| 不可逆操作安全 | 高（RTT 缓冲区满可丢弃） | 取决于实现 |

---

## 2. 源码获取与工程组织

### 2.1 获取源码

从 SEGGER 官方 GitHub 获取：

```bash
git clone https://github.com/SEGGERMicro/RTT.git
```

最小需要的文件（仅 3 个源文件 + 1 个头文件）：

```
Middlewares/RTT/
├── Inc/
│   ├── SEGGER_RTT.h              # API 头文件
│   ├── SEGGER_RTT_Conf.h         # 配置文件
│   └── SEGGER_RTT_ASM_ARMv7M.S   # 汇编优化写入（Cortex-M3/M4/M7 推荐）
└── Src/
    ├── SEGGER_RTT.c              # 核心实现（必需）
    └── SEGGER_RTT_printf.c       # printf 风格格式化（可选）
```

### 2.2 工程目录放置

```
project/
├── Core/Src/                    # 用户代码
├── Middlewares/RTT/              # ← 新建目录
│   ├── Inc/
│   │   ├── SEGGER_RTT.h
│   │   ├── SEGGER_RTT_Conf.h    # 需修改配置
│   │   └── SEGGER_RTT_ASM_ARMv7M.S
│   └── Src/
│       ├── SEGGER_RTT.c
│       └── SEGGER_RTT_printf.c
├── MDK-ARM/
│   └── project.uvprojx
```

---

## 3. 配置 SEGGER_RTT_Conf.h

在 `Middlewares/RTT/Inc/SEGGER_RTT_Conf.h` 中关键配置：

```c
#ifndef SEGGER_RTT_CONF_H
#define SEGGER_RTT_CONF_H

/* ========== 缓冲区数量 ========== */
/* 通道 0：RTT 输出；通道 1：SystemView 调试；通道 2：备用 */
#define SEGGER_RTT_MAX_NUM_UP_BUFFERS             (3)
#define SEGGER_RTT_MAX_NUM_DOWN_BUFFERS           (3)

/* ========== 上行缓冲区大小（目标→主机） ========== */
/* 影响可缓冲的日志量。1024 适合大多数场景，日志量大可改为 2048 或 4096 */
#define BUFFER_SIZE_UP                            (1024)

/* ========== 下行缓冲区大小（主机→目标） ========== */
/* 仅用于键盘输入或小数据下发，16 字节足够 */
#define BUFFER_SIZE_DOWN                          (16)

/* ========== 输出模式 ========== */
/* 缓冲区满时：
 *   NO_BLOCK_SKIP − 丢弃新数据，不阻塞目标（推荐）
 *   NO_BLOCK_TRIM − 丢弃最旧数据，保留最新
 *   BLOCK         − 等待缓冲区有空间（可能卡死目标） */
#define SEGGER_RTT_MODE_DEFAULT                   SEGGER_RTT_MODE_NO_BLOCK_SKIP

/* ========== printf 内部缓冲区 ========== */
/* SEGGER_RTT_printf 格式化时的临时缓冲区 */
#define SEGGER_RTT_PRINTF_BUFFER_SIZE             (64)

/* ========== 中断锁定优先级 ========== */
/* RTT 写入期间，优先级 >= 此值的中断不受影响 */
#define SEGGER_RTT_MAX_INTERRUPT_PRIORITY         (0x20)

/* ========== memcpy 优化 ========== */
/* 0 = 标准 memcpy（推荐）；1 = 字节循环（代码更小但更慢） */
#define SEGGER_RTT_MEMCPY_USE_BYTELOOP            (0)

#endif
```

### 配置项详解

| 配置 | 推荐值 | 说明 |
|------|--------|------|
| `BUFFER_SIZE_UP` | 1024 | 每 KB 可存约 200 行日志（5 字节/行），过小会丢日志 |
| `SEGGER_RTT_MODE_DEFAULT` | `NO_BLOCK_SKIP` | 日志量 > 缓冲区时静默丢弃，不阻塞应用程序 |
| `SEGGER_RTT_MAX_INTERRUPT_PRIORITY` | `0x20` | BASEPRI 值，ARM 标准：数值越大优先级越低 |
| `SEGGER_RTT_PRINTF_BUFFER_SIZE` | 64 | 如果调用 `SEGGER_RTT_printf` 格式化长字符串时需增大 |

---

## 4. 添加到 Keil 工程

### 4.1 添加文件

| 文件 | 是否必需 | 说明 |
|------|---------|------|
| `SEGGER_RTT.c` | ✅ 必需 | 核心环形缓冲区管理 |
| `SEGGER_RTT_printf.c` | ⬜ 可选 | 需要格式化输出时添加 |
| `SEGGER_RTT_ASM_ARMv7M.S` | ⬜ 可选 | ARMv7-M 汇编优化，推荐添加 |

### 4.2 头文件路径

```
Project → Options → C/C++ → Include Paths → 添加 `Middlewares/RTT/Inc`
```

### 4.3 确认编译选项

- C99 Mode 已勾选（对 RTT 不是必须的，但工程建议开启）
- 无需额外库依赖

---

## 5. 初始化与测试

### 5.1 RTT 无需手动初始化

SEGGER RTT 使用 `__attribute__((constructor))` 机制，在 `main()` 执行前自动完成初始化。  
调用任何 RTT API 时，控制块已经就绪。

### 5.2 简单测试

```c
/* main.c */
#include "SEGGER_RTT.h"

int main(void)
{
    /* RTT 自动初始化，无需额外调用 */

    /* 方式 1：直接写字符串（最高效） */
    SEGGER_RTT_WriteString(0, "Hello RTT!\r\n");

    /* 方式 2：printf 风格格式化 */
    SEGGER_RTT_printf(0, "System tick: %u ms, temp: %d C\r\n",
                      HAL_GetTick(), 25);

    int count = 0;
    while (1) {
        SEGGER_RTT_WriteString(0, "RTT is working!\r\n");
        /* 大数据量测试：量大会不会卡死？取决于 NO_BLOCK_SKIP 模式 */
        HAL_Delay(1000);
    }
}
```

### 5.3 预期结果

打开 **JLink RTT Viewer**：
```
File → Connect → 选择 MCU (STM32F411CE) → OK

// 输出：
Hello RTT!
System tick: 500 ms, temp: 25 C
RTT is working!
RTT is working!
...
```

---

## 6. printf 重定向到 RTT（可选）

如果想把 `printf()` 输出全部重定向到 RTT 而非 UART：

```c
/* 在任意 .c 中添加 */
#include "SEGGER_RTT.h"

int fputc(int ch, FILE *f)
{
    SEGGER_RTT_WriteChar(0, ch);
    return ch;
}
```

Keil 下需配合 `__use_no_semihosting`：

```c
#pragma import(__use_no_semihosting)
struct __FILE { int handle; };
FILE __stdout;
void _sys_exit(int x) { while (1); }

int fputc(int ch, FILE *f)
{
    SEGGER_RTT_WriteChar(0, ch);
    return ch;
}
```

> 此方案在 HardFault 上下文中不可用（RTT 写入需要调试器连接）。

---

## 7. 与 EasyLogger 集成

推荐通过 EasyLogger 使用 RTT，获得分级日志和格式控制：

```c
/* elog_port.c — RTT 后端实现 */
#include "elog.h"
#include "SEGGER_RTT.h"

void elog_port_init(void)
{
    SEGGER_RTT_Init();                    /* RTT 初始化 */
}

void elog_port_output(const char *log, size_t size)
{
    /* 注意：必须使用 SEGGER_RTT_Write 而不是
     * SEGGER_RTT_printf(0, log, size) — 因 log 不是格式化字符串，
     * 如果含有 % 字符会导致输出错误 */
    SEGGER_RTT_Write(0, log, size);
}

void elog_port_output_lock(void)
{
    __disable_irq();
}

void elog_port_output_unlock(void)
{
    __enable_irq();
}
```

---

## 8. RTT Viewer 使用方法

### 8.1 图形界面（JLinkRTTViewer.exe）

```
1. 打开 JLink RTT Viewer
2. File → Connect
3. 选择：Device = STM32F411CE, Interface = SWD, Speed = 4000 kHz
4. 确认目标板运行（不要 halt）
5. OK → 自动检测 RTT Control Block
```

### 8.2 命令行（JLinkRTTClient.exe）

```bash
JLinkRTTClient.exe
# 自动连接并显示 RTT 通道 0 数据
# 输入 Ctrl+C 退出
```

### 8.3 如果显示 "RTT Control Block not found"

手动指定控制块地址：

```
在 RTT Viewer 的 Advanced 标签页：
1. 取消勾选 "Auto Detection"
2. 输入 _SEGGER_RTT 符号地址

查看 .map 文件获取地址：
> grep _SEGGER_RTT project.map
  _SEGGER_RTT       0x20000004   Data   4  segger_rtt.o(RTT)
```

---

## 9. 常见问题

### Q1: RTT Viewer 显示 "RTT Control Block not found"

**原因**：目标未运行、控制块地址未识别、或 `.map` 文件中 `_SEGGER_RTT` 被优化掉。

**解决**：
1. 确认 `SEGGER_RTT.c` 已加入工程编译
2. 在 RTT Viewer 手动输入控制块地址
3. 确认目标正在运行（JLink 发了 `g`）

### Q2: RTT 输出卡死目标

**原因**：`SEGGER_RTT_MODE_DEFAULT` 为 `BLOCK` 且缓冲区满了，目标等待 RTT 读出数据。

**解决**：改为 `SEGGER_RTT_MODE_NO_BLOCK_SKIP`（缓冲区满时丢弃新数据）。

### Q3: 日志输出被截断

**原因**：
1. `BUFFER_SIZE_UP` 太小
2. RTT Viewer 采集速度跟不上目标输出速度

**解决**：
- 增大 `BUFFER_SIZE_UP`（试 2048 或 4096）
- RTT Viewer 中减小 "Buffer down load" 采样间隔

### Q4: RTT 输出中出现奇怪字符

**原因**：在 `elog_port_output` 中调用了 `SEGGER_RTT_printf(0, log, size)`，
而 `log` 中包含 `%` 字符导致格式化异常。

**解决**：改用 `SEGGER_RTT_Write(0, log, size)`，不经过 printf 格式化。

### Q5: 调试时 RTT 工作，独立运行不工作

**原因**：调试器保持连接时，RTT 控制块通过调试器界面正常读取。
断开后没有 RTT Viewer 主动读取，缓冲区满后丢弃数据。

**解决**：这是正常行为。RTT 是调试工具，不适用于量产产品日志。
量产可用 UART 或 Flash 存储日志。

---

## 10. 检查清单

```
[ ] 工程添加了 SEGGER_RTT.c + SEGGER_RTT_printf.c（可选）
[ ] SEGGER_RTT_Conf.h 配置了合适的缓冲区大小和模式
[ ] 头文件路径包含 Inc/
[ ] 汇编优化文件 SEGGER_RTT_ASM_ARMv7M.S 已添加（可选）
[ ] 编译通过
[ ] JLink RTT Viewer 连接成功后能看到输出
[ ] 如果需要 printf 重定向，实现了 fputc 调用 RTT
[ ] 如果需要 elog 集成，实现了 elog_port_output（用 Write 非 printf）
```

---

## 参考链接

- **SEGGER RTT 官网**: https://www.segger.com/products/debug-probes/j-link/technology/about-real-time-transfer/
- **SEGGER RTT GitHub**: https://github.com/SEGGERMicro/RTT
- **RTT Viewer 使用说明**: https://wiki.segger.com/RTT_Viewer
- **JLink 软件包下载**: https://www.segger.com/downloads/jlink/
