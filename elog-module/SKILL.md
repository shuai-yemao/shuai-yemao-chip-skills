---
name: elog-module
version: "1.0.0"
description: "EasyLogger (elog) 轻量级嵌入式日志库指南。覆盖 elog 移植（elog_cfg.h/elog_port.c）、输出后端配置（RTT/UART/文件/Flash）、分级日志（assert/error/warn/info/debug/verbose）、彩色输出、格式模板配置（时间/标签/函数/文件/行号）、异步/缓冲模式、API 参考（init/start/输出宏）、与 SFUD/SEGGER RTT 配合、常见问题排查。当用户提到 EasyLogger、elog、日志库、嵌入式日志、ELOG、log_a、log_e、log_w、log_i、log_d、log_v、分级日志、彩色日志、elog_init、elog_start、elog_set_fmt、elog 移植、日志输出、日志后端、elog_port、EasyLogger RTT、EasyLogger Flash 时使用。"
---

# EasyLogger 嵌入式日志库指南

> **EasyLogger (elog)** — 轻量级、高性能的嵌入式日志库，支持分级日志、彩色输出、
> 灵活的后端（RTT/UART/文件/Flash）。
>
> 官方仓库：https://github.com/armink/EasyLogger（MIT 许可，2K+ Stars，v2.2.99）
>
> STM32 移植文档：`references/stm32-elog-porting-guide.md`
>
> 适用平台：ARM Cortex-M / ESP32 等，裸机或 FreeRTOS/RT-Thread 均可

## 场景

- **需要分级日志** — assert/error/warn/info/debug/verbose 分级管理
- **产品中需要开关日志** — 编译时通过宏开关完全移除日志代码
- **后端灵活切换** — 开发期用 RTT，部署后用 UART 或文件存储
- **彩色输出** — 终端上按级别显示不同颜色，提高可读性
- **遗留项目添加日志** — 不侵入原有 printf，通过 elog 后端重定向

## 输入

- MCU 平台（STM32/ESP32/AT32 等）
- 输出后端（RTT / UART / Flash 文件 / 自定义）
- 操作系统（裸机 / FreeRTOS / RT-Thread）
- 需要的日志级别和格式

## 依赖

- **输出后端**：SEGGER RTT（需 `segger-rtt-module`）或 UART printf
- **临界区**：裸机用关中断，FreeRTOS 用互斥锁
- **时间戳**（可选）：`elog_port_get_time()` 实现

## 步骤

### Step 1: 获取源码

```bash
git clone https://github.com/armink/EasyLogger.git
```

所需文件结构：

```
Middlewares/easylogger/
├── inc/
│   ├── elog.h              # 公共 API + 日志宏定义
│   └── elog_cfg.h          # 配置文件
├── port/
│   └── elog_port.c         # 平台移植层（需自行实现）
├── src/
│   ├── elog.c              # 核心引擎
│   ├── elog_async.c        # 异步输出（可选）
│   ├── elog_buf.c          # 缓冲输出（可选）
│   └── elog_utils.c        # 工具函数
├── plugins/
│   ├── file/               # 文件后端（可选）
│   └── flash/              # Flash 后端（可选）
```

### Step 2: 配置 elog_cfg.h

```c
#ifndef _ELOG_CFG_H_
#define _ELOG_CFG_H_

/* ========== 总开关 ========== */
/* 注释掉则所有日志宏展开为 ((void)0)，零开销 */
#define ELOG_OUTPUT_ENABLE

/* ========== 输出级别 ========== */
/* 编译时最高级别：assert(1) error(2) warn(3) info(4) debug(5) verbose(6) */
#define ELOG_OUTPUT_LVL          ELOG_LVL_VERBOSE

/* ========== 行缓冲区 ========== */
/* 单行日志最大长度。过长时行会被截断 */
#define ELOG_LINE_BUF_SIZE       1024

/* ========== 颜色输出 ========== */
#define ELOG_COLOR_ENABLE

/* ========== 格式模板 ========== */
#define ELOG_FMT_USING_LVL       /* 输出级别标签 [I]/[E]/[W] */
#define ELOG_FMT_USING_TAG       /* 日志标签 */
#define ELOG_FMT_USING_FUNC      /* 函数名 */
#define ELOG_FMT_USING_DIR       /* 文件路径 */
#define ELOG_FMT_USING_LINE      /* 行号 */

/* ========== 功能开关 ========== */
// #define ELOG_ASYNC_OUTPUT_ENABLE   /* 异步输出模式（需 RTOS 队列） */
// #define ELOG_BUF_OUTPUT_ENABLE     /* 缓冲输出模式 */

#endif /* _ELOG_CFG_H_ */
```

### Step 3: 实现 elog_port.c

这是移植 elog 最核心的文件，连接 log 引擎和输出后端：

```c
/* elog_port.c — STM32F4 + SEGGER RTT 后端示例 */
#include "elog.h"
#include "SEGGER_RTT.h"

/* 初始化 */
void elog_port_init(void)
{
    SEGGER_RTT_Init();           // 初始化 RTT（后端）
}

/* 输出 — 每行日志最终调用此函数 */
void elog_port_output(const char *log, size_t size)
{
    /* ✅ 正确做法：写裸字符串，避免格式化开销和 % 冲突 */
    SEGGER_RTT_Write(0, log, size);

    /* ❌ 错误做法：log 不是格式字符串，第三个参数不用传 size
     *    SEGGER_RTT_printf(0, log, size);  // 如果 log 含 % 会崩溃 */
}

/* 终结 — 极少使用 */
void elog_port_deinit(void)
{
}

/* 输出锁定 — 多线程环境防止日志交错 */
void elog_port_output_lock(void)
{
    /* 裸机：关中断 */
    __disable_irq();
    /* FreeRTOS：取互斥锁 */
    // xSemaphoreTake(g_elog_mutex, portMAX_DELAY);
}

void elog_port_output_unlock(void)
{
    __enable_irq();
    // xSemaphoreGive(g_elog_mutex);
}

/* 时间戳（可选，返回 NULL 则时间戳不输出） */
const char *elog_port_get_time(void)
{
    return NULL;    // 暂不实现时间戳
}

/* 进程/线程信息（可选） */
const char *elog_port_get_p_info(void) { return NULL; }
const char *elog_port_get_t_info(void) { return NULL; }
```

### Step 4: 初始化与使用

```c
/* main.c */
#include "elog.h"

/* 设置默认日志标签（在所有 log_* 宏生效前定义） */
#define LOG_TAG              "main"
#define LOG_LVL              ELOG_LVL_VERBOSE
#include "elog.h"

int main(void)
{
    /* 初始化日志库 */
    elog_init();

    /* 配置格式：各级别使用不同格式 */
    elog_set_text_color_enabled(true);
    elog_set_fmt(ELOG_LVL_ASSERT,  ELOG_FMT_ALL);
    elog_set_fmt(ELOG_LVL_ERROR,   ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_WARN,    ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_INFO,    ELOG_FMT_LVL | ELOG_FMT_TAG);
    elog_set_fmt(ELOG_LVL_DEBUG,   ELOG_FMT_ALL & ~ELOG_FMT_TIME);
    elog_set_fmt(ELOG_LVL_VERBOSE, ELOG_FMT_ALL);

    /* 启动日志 */
    elog_start();

    /* ========== 使用分级日志 ========== */
    log_a("Assert: this should never happen");          // 断言
    log_e("Error: SPI communication failed, code=%d", -1); // 错误
    log_w("Warning: battery low");                       // 警告
    log_i("Info: system initialized");                   // 信息
    log_d("Debug: sensor value = %d", 42);               // 调试
    log_v("Verbose: loop iteration %d", 100);            // 详细

    while (1);
}
```

输出示例（RTT Viewer）：
```
[15200] [I] [main] system_init: System initialized
[15201] [E] [main] configure_spi: Error: SPI communication failed, code=-1
```

### Step 5: UART 后端（替代 RTT）

如果不用 RTT，elog_port_output 中直接输出到 UART：

```c
/* elog_port.c — UART 后端实现 */
#include "elog.h"

extern UART_HandleTypeDef huart1;

void elog_port_output(const char *log, size_t size)
{
    /* 使用寄存器直接发送（HardFault 上下文也安全） */
    for (size_t i = 0; i < size; i++) {
        while (!(USART1->SR & USART_SR_TXE));
        USART1->DR = (uint8_t)log[i];
    }
}
```

### Step 6: 编译时零开销

`elog_cfg.h` 中注释掉 `ELOG_OUTPUT_ENABLE` 后，所有 `log_*` 宏变为空操作：

```c
// #define ELOG_OUTPUT_ENABLE   // 注释掉 → 日志代码完全从二进制中移除
```

编译后可节省约 2.5KB Flash + 1.2KB RAM（含 RTT 缓冲区）。  
适合量产版本保留日志源码但不产生日志输出。

## API 速查

### 初始化

| API | 说明 |
|-----|------|
| `elog_init()` | 初始化日志引擎（需先实现 elog_port_init） |
| `elog_start()` | 启动日志输出 |
| `elog_set_fmt(level, fmt_mask)` | 设置指定级别的格式模板 |
| `elog_set_text_color_enabled(bool)` | 启用/禁用彩色输出 |
| `elog_set_filter(level, tag)` | 设置运行时过滤（低于 level 或 tag 不匹配的日志不输出） |

### 日志宏（在定义 LOG_TAG 后使用）

| 宏 | 级别 | 使用场景 |
|----|------|---------|
| `log_a(...)` | ASSERT (1) | 不可恢复的错误 |
| `log_e(...)` | ERROR (2) | 功能失败但可恢复 |
| `log_w(...)` | WARN (3) | 非预期但可容忍 |
| `log_i(...)` | INFO (4) | 关键状态信息 |
| `log_d(...)` | DEBUG (5) | 调试阶段信息 |
| `log_v(...)` | VERBOSE (6) | 详细的调试输出 |

## 错误

| 错误现象 | 根因 | 解决 |
|---------|------|------|
| 日志不输出 | `ELOG_OUTPUT_ENABLE` 被注释 | 取消注释宏定义 |
| 彩色日志显示为乱码 | 终端不支持 ANSI 颜色码 | 关闭 `ELOG_COLOR_ENABLE` |
| 日志格式显示 "??:?" | `elog_port_get_*` 返回 NULL | 实现这些函数或移除非必要的格式选项 |
| RTT 输出出现奇怪字符 | `elog_port_output` 用 `SEGGER_RTT_printf` 传错参数 | 改用 `SEGGER_RTT_Write(0, log, size)` |
| FreeRTOS 下日志交错 | 未实现 `output_lock/unlock` | 用互斥锁保护输出 |
| 日志行被截断 | `ELOG_LINE_BUF_SIZE` 太小 | 增大到 2048 |
| 编译后体积没有减小 | 未注释 `ELOG_OUTPUT_ENABLE` | 确认量产版本中已注释该宏 |

## 输出

EasyLogger 典型输出格式（取决于 `elog_set_fmt` 配置）：

```
[I] [main] system_init() at main.c:88 -- System initialized
 ERROR: configure_spi() at spi.c:45 -- SPI communication failed, code=-1
```

各部分由 `ELOG_FMT_*` 宏控制：
- `ELOG_FMT_LVL` — `[I]` / `[E]` 级别标签
- `ELOG_FMT_TAG` — `[main]` 标签名
- `ELOG_FMT_FUNC` — `function_name()`
- `ELOG_FMT_DIR` — `file/path/`
- `ELOG_FMT_LINE` — `:行号`
- `ELOG_FMT_TIME` — 时间戳（需实现 `elog_port_get_time`）

## 边界

- **不覆盖 SEGGER RTT 直接使用** — RTT 作为 elog 后端时，推荐通过 elog API 使用
- **不覆盖文件系统写入** — 文件后端需要文件系统支持（`fatfs-module`）
- **不覆盖 Flash 存储日志** — Flash 后端需要 `sfud-module` 或 `flash-module`
- **不覆盖 CmBacktrace** — elog 是常规日志，故障转储由 `cmbacktrace-debug` 处理
- 与 `cmbacktrace-debug` 互补：elog 输出常规运行日志，CmBacktrace 输出故障诊断
- 与 `segger-rtt-module` 配合：elog 通过 RTT 输出

## 交接

- **RTT 后端不工作** → 使用 `segger-rtt-module` skill 单独测试 RTT
- **需要文件写入** → 使用 `fatfs-module` + `sfud-module` 对接文件后端插件
- **需要故障自动追踪** → 使用 `cmbacktrace-debug` skill
- **日志内容格式调整** → 调用 `elog_set_fmt()` 修改格式化掩码

## 参考资料

- **官方仓库**: https://github.com/armink/EasyLogger
- **API 文档**: https://github.com/armink/EasyLogger#readme
- **elog_cfg.h 配置说明**: 见仓库根目录 README
- **作者**: armink（与 CmBacktrace/SFUD/EasyFlash 同作者）
