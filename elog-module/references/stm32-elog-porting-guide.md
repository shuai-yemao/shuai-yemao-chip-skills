# STM32 EasyLogger 日志库移植指南

> 目标平台：STM32F4（Cortex-M4F） + SEGGER RTT 后端
> 开发环境：Keil MDK（ARMCC v5）
> 库版本：EasyLogger v2.2.99（armink/MIT）
> 仓库地址：https://github.com/armink/EasyLogger

---

## 目录

1. [移植前准备](#1-移植前准备)
2. [源码获取与工程组织](#2-源码获取与工程组织)
3. [配置 elog_cfg.h](#3-配置-elog_cfgh)
4. [实现 elog_port.c（核心移植）](#4-实现-elog_portc核心移植)
5. [初始化与测试](#5-初始化与测试)
6. [格式模板配置](#6-格式模板配置)
7. [RTT 后端 vs UART 后端](#7-rtt-后端-vs-uart-后端)
8. [编译时零开销开关](#8-编译时零开销开关)
9. [常见问题](#9-常见问题)
10. [检查清单](#10-检查清单)

---

## 1. 移植前准备

### 1.1 确认环境

| 项目 | 要求 |
|------|------|
| MCU | 任意（不依赖硬件外设） |
| 操作系统 | 裸机 / FreeRTOS / RT-Thread |
| 输出后端 | SEGGER RTT（需 JLink）或 UART |
| 编译器 | Keil MDK / IAR / GCC（需 C99） |

### 1.2 选择后端

| 后端 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **SEGGER RTT** | 高速、无需额外引脚 | 需 JLink 调试器 | 开发调试 |
| **UART** | 独立运行、无需调试器 | 需占用 TX/RX 引脚 | 生产/现场调试 |
| **Flash** | 掉电保存日志 | 需 SPI Flash + 文件系统 | 事后分析 |
| **文件** | 大容量存储 | 需文件系统 | 复杂产品 |

本指南以 **SEGGER RTT 后端** 为例（最常用），RTT 移植详见 `segger-rtt-module` 移植指南。

---

## 2. 源码获取与工程组织

### 2.1 获取源码

```bash
git clone https://github.com/armink/EasyLogger.git
```

### 2.2 工程目录组织

```
project/
├── Core/Src/                        # 用户代码
├── Middlewares/easylogger/          # ← 新建目录
│   ├── inc/
│   │   ├── elog.h                  # 公共 API + 日志宏
│   │   └── elog_cfg.h              # 用户配置（需创建）
│   ├── port/
│   │   └── elog_port.c             # 平台移植层（需创建）
│   └── src/
│       ├── elog.c                  # 核心引擎（必需）
│       ├── elog_async.c            # 异步模式（可选）
│       ├── elog_buf.c              # 缓冲模式（可选）
│       └── elog_utils.c            # 工具函数（必需）
├── MDK-ARM/
│   └── project.uvprojx
```

### 2.3 在 Keil 中添加文件

**必需文件**（最小集）：

| 文件 | 说明 |
|------|------|
| `src/elog.c` | 核心日志引擎 |
| `src/elog_utils.c` | 字符串辅助函数 |
| `port/elog_port.c` | 平台移植（需自行编写） |

**可选文件**：

| 文件 | 功能 | 何时需要 |
|------|------|---------|
| `src/elog_async.c` | 异步输出模式 | RTOS 环境下避免日志阻塞任务 |
| `src/elog_buf.c` | 缓冲输出模式 | 希望日志批量刷新时 |

**头文件路径**：
```
Project → Options → C/C++ → Include Paths → 添加 `Middlewares/easylogger/inc`
```

---

## 3. 配置 elog_cfg.h

在 `Middlewares/easylogger/inc/` 下创建 `elog_cfg.h`：

```c
#ifndef _ELOG_CFG_H_
#define _ELOG_CFG_H_

/* ========== 总开关 ========== *
 * 注释掉此宏 → 所有 log_* 宏展开为 ((void)0)，零 Flash/RAM 开销
 * 取消注释 → 启用日志输出 */
#define ELOG_OUTPUT_ENABLE

/* ========== 输出级别 ========== *
 * 编译时最高输出级别。运行时也可通过 elog_set_filter 过滤。
 *   ELOG_LVL_ASSERT  (1) — 不可恢复错误
 *   ELOG_LVL_ERROR   (2) — 功能失败
 *   ELOG_LVL_WARN    (3) — 非预期但可容忍
 *   ELOG_LVL_INFO    (4) — 关键状态
 *   ELOG_LVL_DEBUG   (5) — 调试信息
 *   ELOG_LVL_VERBOSE (6) — 冗余调试 */
#define ELOG_OUTPUT_LVL              ELOG_LVL_VERBOSE

/* ========== 行缓冲区 ========== */
/* 单行日志最大长度（超过后截断）。含格式前缀 + 正文 */
#define ELOG_LINE_BUF_SIZE           (256)

/* ========== 颜色输出 ========== */
/* 终端支持 ANSI 颜色码时启用 */
#define ELOG_COLOR_ENABLE

/* ========== 格式模板 ========== *
 * 选择每行日志包含哪些前缀信息 */
#define ELOG_FMT_USING_LVL           /* 级别标签 [I]/[E]/[W] */
#define ELOG_FMT_USING_TAG           /* 标签名 [main]/[spi] */
#define ELOG_FMT_USING_FUNC          /* 函数名 */
#define ELOG_FMT_USING_DIR           /* 文件路径 */
#define ELOG_FMT_USING_LINE          /* 行号 */
// #define ELOG_FMT_USING_TIME        /* 时间戳（需实现 elog_port_get_time） */

/* ========== 功能开关 ========== */
// #define ELOG_ASYNC_OUTPUT_ENABLE   /* 异步模式 */
// #define ELOG_BUF_OUTPUT_ENABLE     /* 缓冲模式 */

#endif /* _ELOG_CFG_H_ */
```

### 配置项速查

| 配置项 | 推荐值 | 说明 |
|--------|--------|------|
| `ELOG_OUTPUT_ENABLE` | 定义 | 取消注释后日志才生效。量产版注释掉→零开销 |
| `ELOG_OUTPUT_LVL` | `ELOG_LVL_VERBOSE` | 编译时最高级别。量产可改为 `ELOG_LVL_WARN` |
| `ELOG_LINE_BUF_SIZE` | 256 | 每行最大长度。太大浪费 RAM，太小日志被截断 |
| `ELOG_COLOR_ENABLE` | 定义 | 终端支持 ANSI 颜色时启用 |

---

## 4. 实现 elog_port.c（核心移植）

这是移植最重要的一步，连接 elog 引擎和底层输出通道：

### RTT 后端版本（推荐）

```c
/* elog_port.c — SEGGER RTT 后端 */
#include "elog.h"
#include "SEGGER_RTT.h"

/* 初始化：放在 elog_init() 之前调用 */
void elog_port_init(void)
{
    SEGGER_RTT_Init();
}

/* 输出一行日志：每行日志最终调用此函数 */
void elog_port_output(const char *log, size_t size)
{
    /* ✅ 正确：写裸字符串，高效且不会误解析格式字符 */
    SEGGER_RTT_Write(0, log, size);

    /* ❌ 错误：不要用 SEGGER_RTT_printf(0, log, size)
     *   因为 log 是完整日志行（含格式前缀），不是格式字符串。
     *   若 log 中包含 % 字符，printf 会错误解析导致输出异常 */
}

/* 终结（极少使用） */
void elog_port_deinit(void)
{
}

/* 输出锁定：防止多任务日志交错 */
void elog_port_output_lock(void)
{
    /* 裸机 */
    __disable_irq();
    /* FreeRTOS 下应改为：
     *   extern SemaphoreHandle_t g_elog_mutex;
     *   xSemaphoreTake(g_elog_mutex, portMAX_DELAY); */
}

void elog_port_output_unlock(void)
{
    __enable_irq();
    // xSemaphoreGive(g_elog_mutex);
}

/* 时间戳（如需 ELOG_FMT_TIME 则必须实现） */
const char *elog_port_get_time(void)
{
    /* 返回格式固定的时间字符串，如 "15200"（ms 级 tick） */
    static char time_buf[16];
    snprintf(time_buf, sizeof(time_buf), "%lu", HAL_GetTick());
    return time_buf;
}

/* 进程信息（在 OS 环境下实现） */
const char *elog_port_get_p_info(void) { return NULL; }

/* 线程信息（在 OS 环境下实现） */
const char *elog_port_get_t_info(void) { return NULL; }
```

### UART 后端版本（独立运行不需要 JLink）

```c
/* elog_port.c — UART 后端 */
#include "elog.h"

/* 使用寄存器级 UART 输出（不依赖 HAL 时基） */
void elog_port_output(const char *log, size_t size)
{
    for (size_t i = 0; i < size; i++) {
        while (!(USART1->SR & USART_SR_TXE));
        USART1->DR = (uint8_t)log[i];
    }
}
```

---

## 5. 初始化与测试

### 5.1 完整初始化

```c
/* debug.c */
#include "elog.h"

#define LOG_TAG              "app"
#define LOG_LVL              ELOG_LVL_VERBOSE
#include "elog.h"

void app_elog_init(void)
{
    /* 顺序：init → set 配置 → start */
    elog_init();
    elog_set_text_color_enabled(true);

    /* 配置各级别的格式模板 */
    elog_set_fmt(ELOG_LVL_ASSERT,  ELOG_FMT_ALL);
    elog_set_fmt(ELOG_LVL_ERROR,   ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_WARN,    ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_INFO,    ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_DEBUG,   ELOG_FMT_ALL & ~(ELOG_FMT_TIME | ELOG_FMT_P_INFO | ELOG_FMT_T_INFO));
    elog_set_fmt(ELOG_LVL_VERBOSE, ELOG_FMT_ALL);

    elog_start();
}
```

### 5.2 使用日志

```c
/* main.c */
#define LOG_TAG              "main"
#define LOG_LVL              ELOG_LVL_VERBOSE
#include "elog.h"

int main(void)
{
    /* ... 硬件初始化 ... */

    /* 初始化日志 */
    app_elog_init();

    /* 使用分级日志 */
    log_i("System booting...");
    log_d("SPI1 initialized, freq = %d kHz", 328);

    int sensor_val = 42;
    if (sensor_val < 0) {
        log_e("Sensor read failed: %d", sensor_val);
    } else {
        log_i("Sensor OK: %d", sensor_val);
    }

    log_w("Battery low: %d%%", 15);

    while (1) {
        log_v("Loop iteration");
        HAL_Delay(1000);
    }
}
```

### 5.3 预期输出

通过 JLink RTT Viewer 看到：

```
[I] [main] System booting...
[D] [main] SPI1 initialized, freq = 328 kHz
[I] [main] Sensor OK: 42
[W] [main] Battery low: 15%
```

启用颜色后，不同级别显示不同颜色（在支持 ANSI 颜色的终端中）：

| 级别 | 颜色 |
|------|------|
| ASSERT | 红色背景 |
| ERROR | 红色 |
| WARN | 黄色 |
| INFO | 默认（无色） |
| DEBUG | 蓝色 |
| VERBOSE | 灰色 |

---

## 6. 格式模板配置

`elog_set_fmt(level, mask)` 控制每行日志的前缀格式：

```c
/* 格式掩码组合 */
ELOG_FMT_LVL     // [I] / [E] / [W] 等级别标签
ELOG_FMT_TAG     // [main] / [spi] 等标签名
ELOG_FMT_FUNC    // 函数名()
ELOG_FMT_DIR     // 文件路径
ELOG_FMT_LINE    // :行号
ELOG_FMT_TIME    // 时间戳（需实现 elog_port_get_time）
ELOG_FMT_P_INFO  // 进程信息（OS 下）
ELOG_FMT_T_INFO  // 线程信息（OS 下）
ELOG_FMT_ALL     // 所有选项
```

示例组合效果：

| 掩码 | 输出示例 |
|------|---------|
| `ELOG_FMT_LVL | ELOG_FMT_TAG` | `[I] [main] msg` |
| `ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_FUNC` | `[I] [main] main() msg` |
| `ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_DIR | ELOG_FMT_LINE` | `[I] [main] main.c:88 msg` |
| `ELOG_FMT_LVL | ELOG_FMT_TAG | ELOG_FMT_FUNC | ELOG_FMT_LINE` | `[I] [main] main:88 msg` |

---

## 7. RTT 后端 vs UART 后端

| | RTT 后端 | UART 后端 |
|--|---------|----------|
| 速度 | **~1MB/s** | 115200bps ≈ 11KB/s |
| 硬件依赖 | JLink 调试器 | USART 引脚 TX/RX |
| 独立运行 | ❌ 需要调试器 | ✅ 独立工作 |
| 中断上下文安全 | ✅（NO_BLOCK_SKIP） | ✅（寄存器级） |
| HardFault 上下文安全 | ❌（需调试器连接） | ✅ |
| elog_port_output 实现 | `SEGGER_RTT_Write(0, log, size)` | 寄存器轮询写入 USART1->DR |

**推荐方案**：开发期用 RTT + 生产版用 UART，两个后端通过 `#ifdef` 切换。

```c
void elog_port_output(const char *log, size_t size)
{
#ifdef ELOG_OUTPUT_RTT
    SEGGER_RTT_Write(0, log, size);
#else
    for (size_t i = 0; i < size; i++) {
        while (!(USART1->SR & USART_SR_TXE));
        USART1->DR = log[i];
    }
#endif
}
```

---

## 8. 编译时零开销开关

只需注释 `elog_cfg.h` 中的 `ELOG_OUTPUT_ENABLE`：

```c
// #define ELOG_OUTPUT_ENABLE    ← 注释掉
```

效果：
- 所有 `log_*` 宏变成 `((void)0)`，编译器完全优化掉
- 不消耗 Flash 和 RAM
- 日志源码可保留在工程中，量产版本自动移除

```c
/* 但注意：LOG_TAG 和 LOG_LVL 定义也应保护，否则会有 unused variable 警告 */
#ifdef ELOG_OUTPUT_ENABLE
#define LOG_TAG              "main"
#define LOG_LVL              ELOG_LVL_VERBOSE
#include "elog.h"
#else
/* 空宏，让 log_* 全部被优化掉 */
#define log_a(...)           ((void)0)
#define log_e(...)           ((void)0)
/* ... 实际 elog.h 中已处理，只需确保 ELOG_OUTPUT_ENABLE 未定义 */
#endif
```

---

## 9. 常见问题

### Q1: 所有日志都看不到

**排查**：
1. `elog_cfg.h` 中 `ELOG_OUTPUT_ENABLE` **是否已取消注释**
2. `app_elog_init()` 是否已被调用（`elog_init()` + `elog_start()`）
3. `elog_port_output` 是否正确实现了（检查 RTT 或 UART）

### Q2: RTT 输出出现乱码或奇怪字符

**根因**：`elog_port_output` 中使用 `SEGGER_RTT_printf(0, log, size)`，
将 `log` 作为格式字符串传入，而 `log` 中可能包含 `%` 字符。

**解决**：改用 `SEGGER_RTT_Write(0, log, size)`，不经过 printf 格式化。

### Q3: FreeRTOS 下日志交错

**根因**：多个任务同时调 `log_*`，输出未保护，数据交错。

**解决**：实现 `elog_port_output_lock/unlock`，用 FreeRTOS 互斥锁保护：

```c
void elog_port_output_lock(void)
{
    xSemaphoreTake(g_elog_mutex, portMAX_DELAY);
}

void elog_port_output_unlock(void)
{
    xSemaphoreGive(g_elog_mutex);
}
```

### Q4: 日志行被截断

**根因**：`ELOG_LINE_BUF_SIZE`（默认 256）太小，单行日志超过此长度。

**解决**：增大到 512 或 1024。注意每增大一倍多消耗对应 RAM。

### Q5: 启用 `ELOG_ASYNC_OUTPUT_ENABLE` 后无输出

**根因**：异步模式需要 RTOS 队列支持，未正确初始化异步输出线程。

**解决**：如非必要不要开启异步模式。同步模式已足够大部分场景使用。

### Q6: 时间戳输出 "??:?"

**根因**：在格式模板中启用了 `ELOG_FMT_TIME`，但 `elog_port_get_time` 返回 `NULL`。

**解决**：实现 `elog_port_get_time` 返回有效时间字符串，或在格式模板中移除 `ELOG_FMT_TIME`。

---

## 10. 检查清单

```
[ ] 工程添加了 elog.c + elog_utils.c + elog_port.c
[ ] elog_cfg.h 配置了正确的输出级别和格式
[ ] elog_cfg.h 中 ELOG_OUTPUT_ENABLE 未注释（测试阶段）
[ ] elog_port.c 正确实现了 init/output/lock/unlock
[ ] RTT 后端使用 SEGGER_RTT_Write 非 SEGGER_RTT_printf
[ ] 头文件路径包含 inc/
[ ] 编译通过
[ ] 串口/RTT Viewer 能看到分级日志输出
[ ] 格式模板按需配置（开发期信息全，量产期精简）
[ ] 量产版本注释掉 ELOG_OUTPUT_ENABLE 实现零开销
```

---

## 参考链接

- **EasyLogger 官方仓库**: https://github.com/armink/EasyLogger
- **elog_cfg.h 配置说明**: https://github.com/armink/EasyLogger#readme
- **SEGGER RTT 移植**: 见 `segger-rtt-module` 移植指南
- **SFUD Flash 驱动**: 见 `sfud-module` 移植指南
- **作者 armink 关联项目**: CmBacktrace, SFUD, EasyFlash, FlashDB
