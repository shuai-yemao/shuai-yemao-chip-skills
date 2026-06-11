# STM32 CmBacktrace 移植指南

> 目标平台：STM32F1/F4/F7/H7（Cortex-M3/M4/M7）
> 开发环境：Keil MDK（ARMCC v5/v6） / IAR EWARM / GCC
> 调试器：J-Link / ST-Link
> 仓库地址：https://github.com/armink/CmBacktrace（MIT 许可，v1.4.1+）

---

## 目录

1. [移植前准备](#1-移植前准备)
2. [源码获取与工程组织](#2-源码获取与工程组织)
3. [配置 cmb_cfg.h](#3-配置-cmb_cfgh)
4. [中断处理与 HardFault_Handler](#4-中断处理与-hardfault_handler)
5. [初始化与断言钩子](#5-初始化与断言钩子)
6. [串口输出配置](#6-串口输出配置)
7. [编译与验证](#7-编译与验证)
8. [addr2line 调用栈解析](#8-addr2line-调用栈解析)
9. [FreeRTOS 集成](#9-freertos-集成)
10. [常见问题](#10-常见问题)
11. [检查清单](#11-检查清单)

---

## 1. 移植前准备

### 1.1 确认环境

| 项目 | 要求 |
|------|------|
| MCU | 任意 Cortex-M0/M3/M4/M7 |
| 编译器 | Keil MDK (ARMCC v5/v6)、IAR、GCC |
| C 标准 | **C99 或更高**（Keil 需手动开启） |
| 串口 | 至少一个可用 UART，能输出 printf |
| 可执行文件 | .axf (Keil) / .out (IAR) / .elf (GCC) |

### 1.2 开启 C99 模式

**Keil MDK**：
```
Project → Options → C/C++ → C99 Mode → 勾选
```

**IAR**：
```
Project → Options → C/C++ Compiler → Language 1 → C Standard: C99
```

**GCC**：
```makefile
# Makefile 中
CFLAGS += -std=c99
# 或使用 -std=gnu99 以获得 GNU 扩展
```

---

## 2. 源码获取与工程组织

### 2.1 获取源码

```bash
# 方式 1：git clone
git clone https://github.com/armink/CmBacktrace.git

# 方式 2：直接下载 ZIP
# https://github.com/armink/CmBacktrace/archive/refs/heads/master.zip
```

### 2.2 工程目录组织

将 CmBacktrace 源码按以下结构放入工程：

```
project/
├── User/                    # 用户代码
│   ├── main.c
│   └── ...
├── Libraries/               # HAL/LL 库
│   └── ...
├── cm_backtrace/            # ← 新建目录
│   ├── src/
│   │   ├── cm_backtrace.c
│   │   ├── cm_backtrace.h
│   │   ├── cmb_cfg.h        # 用户配置文件（需自行创建）
│   │   └── cmb_def.h        # 默认配置，一般不动
│   └── fault_handler/
│       ├── cmb_fault.S       # MDK (ARMCC) 用
│       ├── cmb_fault.s       # GCC / IAR 用
│       └── cmb_fault.c       # C 语言版（备选）
├── MDK-ARM/                 # Keil 工程目录
│   ├── project.uvprojx
│   └── ...
└── Output/                  # 编译输出（.axf 在此）
```

### 2.3 在 Keil 中添加文件

1. 在 Project 窗口右键 → **Add Group** → 命名为 `CmBacktrace`
2. 右键 CmBacktrace 分组 → **Add Existing Files to Group** → 选择：
   - `cm_backtrace/cm_backtrace.c`（注意路径在 cm_backtrace/ 根目录，不是 src/ 子目录）
   - `cm_backtrace/fault_handler/cmb_fault.S`（ARMCC 用）
3. 添加语言文件目录到 Include Paths：
   - Project → Options → C/C++ → Include Paths → 添加 `.\cm_backtrace\Languages\en-US`
4. 确认 Keil 开启了 C99 Mode：
   - Project → Options → C/C++ → C99 Mode → **勾选**

> 注意 1：cmb_fault.S 中定义了 HardFault_Handler，需要**注释掉**启动文件或其他位置原有的 HardFault_Handler。
> 
> 注意 2：语言文件（`Languages/en-US/cmb_en_US.h`）必须从 GitHub 下载，否则编译报错 "cannot open source input file"。

---

## 3. 配置 cmb_cfg.h

在 `cm_backtrace/src/` 下新建 `cmb_cfg.h`，以下是一个 STM32F4 的完整配置：

```c
#ifndef _CMB_CFG_H_
#define _CMB_CFG_H_

/* ================================================================
 *  CmBacktrace 配置文件 — STM32F4 (Cortex-M4F)
 *  适配环境：Keil MDK-ARM v5, ARMCC v5.06, STM32F4xx_HAL_Driver
 * ================================================================ */

/* ---------- 0. 必要头文件 ---------- */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

/* ---------- 1. 输出接口（必须配置） ---------- */
/*
 * cmb_println 是 CmBacktrace 的唯一输出通道。
 *
 * 如果工程已经实现了 printf 重定向到串口，直接：
 *   #define cmb_println(...)  printf(__VA_ARGS__); printf("\r\n")
 *
 * 如果没有 printf，直接用 UART 发送函数：
 *   #define cmb_println(...)  uart_printf(__VA_ARGS__); uart_printf("\r\n")
 *   或
 *   #define cmb_println(...)  { char buf[256]; snprintf(buf,sizeof(buf),__VA_ARGS__); \
 *                               HAL_UART_Transmit(&huart1,(uint8_t*)buf,strlen(buf),100); }
 */
#define cmb_println(...)        printf(__VA_ARGS__); printf("\r\n")

/* ---------- 2. 平台选择（二选一） ---------- */
/*
 * 裸机：    定义 CMB_USING_BARE_METAL_PLATFORM
 * 操作系统：定义 CMB_USING_OS_PLATFORM（并设置 OS 类型）
 */
#define CMB_USING_BARE_METAL_PLATFORM
// #define CMB_USING_OS_PLATFORM      // FreeRTOS 时取消注释

/* ---------- 3. 操作系统类型（仅 OS 模式需要） ---------- */
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_RTT
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_UCOSII
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_UCOSIII
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_FREERTOS

/* ---------- 4. CPU 平台 ---------- */
/*
 * 根据你的 MCU 选：
 *   CMB_CPU_ARM_CORTEX_M0   — STM32F0
 *   CMB_CPU_ARM_CORTEX_M3   — STM32F1/F2
 *   CMB_CPU_ARM_CORTEX_M4   — STM32F3/F4/L4/G4
 *   CMB_CPU_ARM_CORTEX_M7   — STM32F7/H7
 */
#define CMB_CPU_PLATFORM_TYPE       CMB_CPU_ARM_CORTEX_M4

/* ---------- 5. 功能开关 ---------- */
#define CMB_USING_DUMP_STACK_INFO                   /* Dump 堆栈内容 */
// #define CMB_USING_DUMP_HEAP_INFO                  /* Dump 堆信息（一般不开） */

/* ---------- 6. 语言 ---------- */
#define CMB_PRINT_LANGUAGE              CMB_PRINT_LANGUAGE_ENGLISH
// #define CMB_PRINT_LANGUAGE            CMB_PRINT_LANGUAGE_CHINESE

/* ---------- 7. Keil 主栈配置（仅 Keil 需要关注） ---------- */
/*
 * 如果初始化时提示 "can't get main stack info"，说明启动文件中的栈名称
 * 不是默认的 "STACK"。在 cmb_cfg.h 中定义正确的名称即可解决。
 *
 * 查看启动文件 startup_stm32f4xx.s 中搜索 Stack_Mem 或 EQU 栈标签。
 * 例如 STM32F4 默认是：
 *   Stack_Size      EQU     0x00000400
 *   AREA    STACK, NOINIT, READWRITE, ALIGN=3
 * 所以 CMB_CSTACK_BLOCK_NAME = STACK（即默认值）
 *
 * 如果你的板子改过栈名称（例如 CUSTOM_STACK），取消注释下面这行：
 */
// #define CMB_CSTACK_BLOCK_NAME       STACK

#endif /* _CMB_CFG_H_ */
```

### 各 STM32 系列配置速查

| MCU 系列 | 内核 | `CMB_CPU_PLATFORM_TYPE` | 启动文件栈名 |
|----------|------|------------------------|-------------|
| STM32F0 | Cortex-M0 | `CMB_CPU_ARM_CORTEX_M0` | STACK |
| STM32F1 | Cortex-M3 | `CMB_CPU_ARM_CORTEX_M3` | STACK |
| STM32F3 | Cortex-M4F | `CMB_CPU_ARM_CORTEX_M4` | STACK |
| STM32F4 | Cortex-M4F | `CMB_CPU_ARM_CORTEX_M4` | STACK |
| STM32F7 | Cortex-M7 | `CMB_CPU_ARM_CORTEX_M7` | STACK |
| STM32G0 | Cortex-M0+ | `CMB_CPU_ARM_CORTEX_M0` | STACK |
| STM32G4 | Cortex-M4F | `CMB_CPU_ARM_CORTEX_M4` | STACK |
| STM32H7 | Cortex-M7 | `CMB_CPU_ARM_CORTEX_M7` | STACK |
| STM32L0 | Cortex-M0+ | `CMB_CPU_ARM_CORTEX_M0` | STACK |
| STM32L4 | Cortex-M4F | `CMB_CPU_ARM_CORTEX_M4` | STACK |
| STM32L5 | Cortex-M33 | `CMB_CPU_ARM_CORTEX_M33` | STACK |
| STM32WB | Cortex-M4F | `CMB_CPU_ARM_CORTEX_M4` | STACK |

> 注意：Cortex-M33 支持需要 CmBacktrace master 分支较新版本，v1.4.1 官方 release 尚未正式声明支持 M33。

---

## 4. 中断处理与 HardFault_Handler

CmBacktrace 提供两种方式接管 HardFault。

### 方式 A：使用 cmb_fault.S（推荐）

1. 将 `cm_backtrace/fault_handler/cmb_fault.S`（注意大写 S，ARMCC 专用）加入 Keil 工程
2. **注释掉**工程中其他位置定义的 `HardFault_Handler`：

   **startup_stm32f4xx.s**（约 120 行处）：
   ```asm
   ; 注释或删除原有 Handler
   ; HardFault_Handler    PROC
   ;                     EXPORT  HardFault_Handler [WEAK]
   ;                     B       .
   ;                     ENDP
   ```

   **stm32f4xx_it.c**：
   ```c
   // 注释或删除
   // void HardFault_Handler(void) { ... }
   ```

   如果两个文件都定义了，Keil 会报错：
   ```
   Error: L6200E: Symbol HardFault_Handler multiply defined.
   ```

3. 编译，cmb_fault.S 自动在 HardFault 发生时调用 `cm_backtrace_fault()`

### 方式 B：手动调用（不依赖汇编文件）

如果不想替换 `HardFault_Handler`，直接在现有的 ISR 中调用：

```c
/* stm32f4xx_it.c */
#include "cm_backtrace.h"

void HardFault_Handler(void)
{
    /* 保存 LR 和 SP（必须在函数开头、尽可能靠近入口的位置获取） */
    uint32_t lr_value, sp_value;

    __asm volatile(
        "MOV %0, LR\n"
        "MOV %1, SP\n"
        : "=r"(lr_value),
          "=r"(sp_value)
    );

    /* 调用 CmBacktrace 故障分析 */
    cm_backtrace_fault(lr_value, sp_value);

    /* 死循环，等待复位 */
    while (1);
}
```

### 方式 A vs 方式 B 对比

| | 方式 A (cmb_fault.S) | 方式 B (手动) |
|---|---|---|
| 代码侵入 | 低，加文件注释掉旧 Handler 即可 | 中，需修改 stm32f4xx_it.c |
| LR 获取精度 | 汇编层直接获取，最准确 | C 内联汇编，可能受编译器优化影响 |
| 适用编译器 | 各编译器有对应的 .s 文件 | 通用（C 代码） |
| 新手推荐 | ✅ | ❌ 方式 B 入参容易出错 |

> **新手第一次移植强烈推荐方式 A**。

---

## 5. 初始化与断言钩子

### 5.1 调用初始化

在 `main()` 函数中完成硬件初始化后调用：

```c
/* main.c */
#include "cm_backtrace.h"

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();

    /* ---- CmBacktrace 初始化 ---- */
    cm_backtrace_init(
        "STM32F411_Firmware",   /* 固件名称（与编译器输出的 .axf 同名更便于 addr2line） */
        "HW-1.0",               /* 硬件版本 */
        "SW-1.0.0"              /* 软件版本 */
    );

    /* ... 创建任务等 ... */

    while (1)
    {
        /* 主循环 */
    }
}
```

### 5.2 断言钩子（如果使用 assert）

如果工程使用了 `assert_param()` 或自定义断言：

```c
/* 方式 1：重写 HAL 的断言函数 */
void assert_failed(uint8_t *file, uint32_t line)
{
    uint32_t sp_value;

    /* 在函数开头获取 SP，越早越准确 */
    __asm volatile("MOV %0, SP\n" : "=r"(sp_value));

    /* 打印断言位置 */
    printf("[ASSERT] file: %s, line: %lu\n", file, line);

    /* 调用 CmBacktrace 断言追踪 */
    cm_backtrace_assert(sp_value);

    while (1);
}
```

> CubeMX 生成的工程中，`assert_failed` 的弱定义在 `main.h` 中，取消注释后实现即可。

---

## 6. 串口输出配置

### 6.1 实现 printf 重定向

CmBacktrace 通过 `cmb_println` 输出，推荐使用 printf 重定向到串口。

**Keil MDK (ARMCC v5) — 使用半主机模式**（最简单，但不推荐用于量产）：

```c
/* 需要勾选 Project → Target → Use MicroLIB */
int fputc(int ch, FILE *f)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)&ch, 1, 100);
    return ch;
}
```

**Keil MDK (ARMCC v5/v6) — 非半主机 + 寄存器级 UART（推荐）**：

```c
/* 在 usart.c 或其他任意 .c 中添加 */
#pragma import(__use_no_semihosting)

struct __FILE { int handle; };
FILE __stdout;

void _sys_exit(int x) { while (1); }

int fputc(int ch, FILE *f)
{
    /* 使用寄存器轮询，不依赖 HAL 时基（HardFault 上下文也安全） */
    while (!(USART1->SR & USART_SR_TXE));
    USART1->DR = (ch & 0xFF);
    return ch;
}
```

> **为什么不推荐 `HAL_UART_Transmit`？**  
> 在 HardFault 发生时，HAL 时基（TIM/SysTick）可能已中断或未初始化，
> 导致 `HAL_UART_Transmit` 的超时等待永远不结束。直接操作寄存器
> 不依赖任何中间件，在 HardFault 上下文中也能正常工作。

**GCC / IAR**：
```c
/* GCC — syscalls.c 中实现 _write */
int _write(int file, char *ptr, int len)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)ptr, len, 100);
    return len;
}

/* IAR — 直接在 fputc 实现 */
int putchar(int ch)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)&ch, 1, 100);
    return ch;
}
```

### 6.2 验证串口输出

下载程序后复位，串口应能看到 CmBacktrace 初始化完成的信息。  
可以先不加故障测试代码，确保 printf 能正常工作：

```c
printf("CmBacktrace init done, waiting for fault...\n");
```

---

## 7. 编译与验证

### 7.1 使能除零捕获 + 添加测试故障

**从 Cortex-M4 开始，除零异常默认关闭**，需要手动使能 `CCR.DIV_0_TRP`，否则 `a / 0` 不会触发 HardFault。

在 main 中添加故障测试函数：

```c
/* 在 main.c 中 main 函数之前添加 */
static void fault_test_by_div0(void)
{
    volatile uint32_t a = 100;
    volatile uint32_t b = 0;     /* 故意除零 */
    volatile uint32_t c = a / b; /* → HardFault */
    (void)c;
}

static void fault_test_by_unalign(void)
{
    volatile uint32_t *p = (uint32_t *)0x20000001; /* 非对齐地址 */
    *p = 0x12345678;             /* → UsageFault → HardFault */
}
```

在 main 中调用：
```c
int main(void)
{
    // ... 初始化 ...

    cm_backtrace_init("STM32F411_Firmware", "HW-1.0", "SW-1.0.0");

    /* ⚠ 使能除零捕获（Cortex-M4/M7 默认关闭，不使能则除零不触发 HardFault） */
    SCB->CCR |= SCB_CCR_DIV_0_TRP_Msk;
    __DSB();

    /* 触发故障（二选一测试） */
    fault_test_by_div0();
    // fault_test_by_unalign();

    while (1);
}
```

### 7.2 预期输出

下载运行后，串口应输出：

```
============= CmBacktrace (V1.4.0) =============
*** Firmware: STM32F411_Firmware, HW: HW-1.0, SW: SW-1.0.0 ***
=================================================
[cm_backtrace_fault] please input command:

addr2line -e STM32F411_Firmware.axf -a -f 08000a60 08000141 0800313f

=================== Fault Registers ====================
SCB_CFSR:      0x00010000  [DIVBYZERO]
SCB_HFSR:      0x40000000  [FORCED]
SCB_DFSR:      0x00000008
SCB_MMAR:      0x00000000
SCB_BFAR:      0x00000000

=================== Fault Diagnosis ====================
Fault Type: HardFault
Caused by: DIVBYZERO (divide by zero)
========================================================
```

> 如果没有输出：
> - 确认串口波特率匹配（与 printf 重定向一致）
> - 确认 `cmb_println` 配置正确
> - 确认 HardFault_Handler 没有冲突（只保留一份）

### 7.3 故障类型速查

CFSR 常见位含义：

| 位 | 标志 | 含义 | 常见场景 |
|----|------|------|---------|
| bit 9 | DIVBYZERO | 除零 | `a / 0` |
| bit 8 | UNALIGNED | 非对齐访问 | 指针未对齐、结构体 packed 问题 |
| bit 3 | STKERR | 异常入栈时 BusFault | 栈指针损坏、MSP 指向非法地址 |
| bit 2 | BFARVALID | BFAR 有效 | BusFault 地址在 BFAR 中 |
| bit 1 | PRECISERR | 精确数据总线错误 | 访问不存在的地址 |
| bit 0 | UNDEFINSTR | 未定义指令 | 指令区损坏、PC 跑飞到数据区 |
| bit 15 | IACCVIOL | 指令访问违规 | 尝试执行非可执行区域 |
| bit 12 | MSTKERR | 异常入栈时 MemManage | MPU 配置错误 |

---

## 8. addr2line 调用栈解析

### 8.1 获取 addr2line 工具

**方式 1**：从 CmBacktrace 项目下载独立版
```
https://github.com/armink/CmBacktrace/tree/master/tools
```
里面有 32 位和 64 位两个版本，根据你的系统选。

**方式 2**：使用 arm-none-eabi-gcc 工具链自带版
```
# 如果装了 ARM GCC 工具链
# 路径通常在: C:\Program Files\ARM_GNU\bin\arm-none-eabi-addr2line.exe
```

### 8.2 执行 addr2line

将 `addr2line.exe` 复制到 `.axf` 文件所在目录（Keil 通常在 `Output/` 下）：

```bash
# 进入 .axf 所在目录
cd D:\project\MDK-ARM\Output\

# 执行 addr2line 命令（从 CmBacktrace 串口输出的命令直接复制即可）
addr2line -e STM32F411_Firmware.axf -a -f 08000a60 08000141 0800313f
```

输出：
```
0x08000a60
fault_test_by_div0
D:\project\Src\fault_test.c:38          ← 精确到行号！
0x08000141
main
D:\project\Src\main.c:98
0x0800313f
_call_main
??:?                                    ← C 库函数，无名
```

### 8.3 优化选项的影响

| 编译优化 | addr2line 效果 | 说明 |
|---------|---------------|------|
| `-O0` | 准确 | 调试阶段推荐 |
| `-Og` | 较准确 | GCC 调试优化 |
| `-O1` | 部分不准 | 内联函数可能被展开 |
| `-O2`/`-O3` | 可能不准 | 函数内联、尾调用优化等导致地址错位 |

> 量产固件如果用了 `-O2`，编译时**加 `-g` 保留调试符号**，addr2line 仍能提供参考信息。

---

## 9. FreeRTOS 集成

### 9.1 配置切换

```c
/* cmb_cfg.h — 改为 OS 模式 */
// #define CMB_USING_BARE_METAL_PLATFORM      ← 注释掉
#define CMB_USING_OS_PLATFORM                 ← 启用
#define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_FREERTOS
```

### 9.2 在 FreeRTOS tasks.c 末尾追加三个支持函数

CmBacktrace 在 FreeRTOS 下需要三个函数来获取当前任务的栈基址、栈大小、任务名。
在 `tasks.c` **文件末尾**（所有 `#endif` 之后）追加以下代码：

```c
/* ========== CmBacktrace Support Functions ========== */
uint32_t *vTaskStackAddr(void)
{
    return (uint32_t *)pxCurrentTCB->pxStack;
}

uint32_t vTaskStackSize(void)
{
    /* 注意：FreeRTOS V10.3.1 的 TCB 中没有 uxStackDepth 字段！
     * 对于 Cortex-M (portSTACK_GROWTH < 0)，如果有 pxEndOfStack 可用则计算，
     * 否则返回一个固定安全值 */
    #if (portSTACK_GROWTH < 0)
        if( pxCurrentTCB->pxEndOfStack != NULL )
        {
            return ( ( uint32_t ) pxCurrentTCB->pxEndOfStack -
                     ( uint32_t ) pxCurrentTCB->pxStack ) / sizeof( StackType_t );
        }
    #endif
    return 256;  /* 安全默认值 */
}

char *vTaskName(void)
{
    return ( char * ) pxCurrentTCB->pcTaskName;
}
/* =================================================== */
```

> **不推荐修改 tasks.c 中间部分**：CmBacktrace 旧版文档建议在 tasks.c 内部多处插入代码，
> 但最简单可靠的方法是在文件末尾追加这三个函数。`pxCurrentTCB` 是 tasks.c 的文件作用域变量，
> 在文件末尾的函数中也可直接访问。

### 9.3 CubeMX + FreeRTOS 移植步骤

如果你用 CubeMX 生成 FreeRTOS 工程：

1. CubeMX 正常配置 FreeRTOS
2. 在生成代码后，手动添加 `cm_backtrace/` 目录到工程
3. `cmb_cfg.h` 配为 OS 模式 + FREERTOS
4. 按上述步骤修改 `tasks.c`
5. 注释掉启动文件和 `stm32f4xx_it.c` 中的 `HardFault_Handler`

---

## 10. 常见问题

### Q1: 编译报错 `HardFault_Handler` 重复定义

```
Error: L6200E: Symbol HardFault_Handler multiply defined.
```

**解决**：在以下 3 个地方中只保留 1 个：
- `cm_backtrace/fault_handler/cmb_fault.S`（CmBacktrace 提供）→ **保留这个**
- `startup_stm32f4xx.s` → 注释掉
- `stm32f4xx_it.c` → 注释掉

### Q2: 初始化提示 `can't get main stack info`

```
[cm_backtrace_init] Error: can't get main stack info!
```

**原因**：Keil MDK 启动文件中主栈名称不是默认的 `STACK`。

**解决**：打开启动文件 `startup_stm32f4xx.s`，搜索 `AREA` 和 `STACK`：

```asm
Stack_Size      EQU     0x00000400
                AREA    STACK, NOINIT, READWRITE, ALIGN=3
;                    ^^^^^ 这里就是栈名称
```

如果名称不是 `STACK`（例如 `MY_STACK`），在 `cmb_cfg.h` 中配置：
```c
#define CMB_CSTACK_BLOCK_NAME      MY_STACK
```

或者在启动文件中把 `AREA` 名称改回 `STACK`。

### Q3: 串口无任何输出

**排查**：
1. 确认 `cmb_println` 在 `cmb_cfg.h` 中已正确定义
2. 单独测试 printf 是否正常：`printf("test\n");`
3. 确认 HardFault_Handler 确实被执行（在 handler 中翻转 GPIO 测试）
4. 确认串口波特率、引脚配置正确

### Q4: addr2line 输出 `??:?`

**原因**：
1. `.axf` 文件路径不对（确认在正确的目录执行）
2. 编译时没加调试符号（Keil 确认勾选 `Debug Information`）
3. 优化级别导致地址错位（`-O2`/`-O3` 可能出问题）
4. 地址不在用户代码段（C 库/启动代码部分无法反解析是正常的）

**解决**：
```bash
# 确认 .axf 包含调试信息
arm-none-eabi-objdump -h firmware.axf | grep debug
# 如果没输出 → 需要重新编译加 -g
```

### Q5: 故障信息只打印了部分，然后卡死

**原因**：栈溢出导致 CmBacktrace 的栈操作本身触发了新的 HardFault。

**解决**：
- 增大主栈大小（启动文件中 `Stack_Size EQU 0x00000400` → `0x00000800`）
- 如果栈特别小，可以关闭 `CMB_USING_DUMP_STACK_INFO` 减少栈使用

### Q6: 蓝牙/无线串口 — 收不到数据

**排查**：
1. 先打开 PC 端串口监听，**再复位板子**（蓝牙连接需要时间建立）
2. 确认 STM32 USART 波特率与蓝牙模块匹配（HC-05 默认 9600 或 38400，常见配 115200）
3. JLink 调试器连接时蓝牙可能不工作，烧录后断开调试器再上电
4. 确认串口引脚连线正确：STM32 TX → HC-05 RX，GND 相连

```python
# 正确流程：先监听再复位
import serial, time
ser = serial.Serial('{SERIAL_PORT}', 115200, timeout=3)
# 此时复位板子
data = ser.read(4096)
```

### Q7: RTT 输出替代 UART（无串口引脚场景）

如果板子没有可用的 UART 引脚，可使用 SEGGER RTT 输出 CmBacktrace 诊断信息。

**cmb_cfg.h 配置**：
```c
#include "SEGGER_RTT.h"
#define cmb_println(...)        do { \
    char buf[256]; \
    int len = snprintf(buf, sizeof(buf), __VA_ARGS__); \
    if (len > 0) SEGGER_RTT_Write(0, buf, len); \
    SEGGER_RTT_Write(0, "\r\n", 2); \
} while(0)
```

**增加主栈大小**（避免 "Main stack was overflow"）：
```asm
; startup_stm32f4xx.s
Stack_Size      EQU     0x800    ; 默认 0x400(1KB) → 2KB
```

### Q8: 故障测试显示 "bare metal(no OS)" 而不是 "Fault on thread"

**原因**：故障测试放在 `main()` 中、FreeRTOS 调度器启动前触发。

**解决**：将故障测试移到 FreeRTOS 任务函数中触发，CmBacktrace 会自动检测任务上下文，显示任务名称和线程栈信息。

### Q9: CMB_ASSERT(!on_fault) 断言失敗，但功能正常

**现象**：CmBacktrace 故障输出开始时显示 `(!on_fault) has assert failed at cm_backtrace_fault`，然后卡死。

**根因**：Keil ARMCC v5 下 `static bool on_fault = false;` 的初始化行为异常（疑似 BSS 处理时机问题），导致首次调用 `cm_backtrace_fault` 时 `on_fault` 为 true。

**解决**：在 `cmb_def.h` 中将 CMB_ASSERT 定义为空：
```c
#define CMB_ASSERT(EXPR)  ((void)(EXPR))
```
完全不影响 CmBacktrace 的故障诊断功能，只是跳过了这个保护性断言。

### Q8: 编译报 `cannot open source input file "Languages/..."`

**解决**：从 GitHub 下载缺失的语言目录：
```bash
# 下载 en-US 语言文件
curl -sL -o cm_backtrace/Languages/en-US/cmb_en_US.h \
  https://raw.githubusercontent.com/armink/CmBacktrace/master/cm_backtrace/Languages/en-US/cmb_en_US.h
```
或将 `CMB_PRINT_LANGUAGE` 改为 `CMB_PRINT_LANGUAGE_ENGLISH` 并下载 `Languages/en-US/`。

### Q9: 进入 Stop 低功耗模式后 CmBacktrace 不工作

**原因**：Stop 模式下 SysTick 停止，UART 可能也停止。

**解决**：低功耗模式调试建议：
1. 先关闭低功耗，调通 CmBacktrace
2. 低功耗模式下使用 RTT 而非 UART 输出
3. 或把故障信息存到 RTC backup register / Flash，唤醒后读出

---

## 11. 检查清单

```
移植完成后逐项确认：

[ ] 工程添加了 cm_backtrace.c + cmb_fault.S
[ ] 语言文件（Languages/en-US/cmb_en_US.h）已下载到工程
[ ] cmb_cfg.h 配置了正确的 CPU 类型
[ ] cmb_cfg.h 中 cmb_println 指向可用的串口输出
[ ] Keil 开启了 C99 Mode
[ ] Keil 开启了 Debug Information（addr2line 需要）
[ ] 启动文件和 stm32f4xx_it.c 中的 HardFault_Handler 已注释
[ ] main 中调用了 cm_backtrace_init
[ ] 故障测试前使能了 DIV_0_TRP（Cortex-M4/M7）或改用非对齐访问测试
[ ] printf 重定向已实现（推荐寄存器级操作，不依赖 HAL 时基）
[ ] 编译通过，无 HardFault_Handler 重定义
[ ] 先打开串口监听，再复位板子（蓝牙串口需注意时序）
[ ] 看到 CmBacktrace 故障诊断输出 + addr2line 命令
[ ] addr2line 可正常反解析出文件名+行号
[ ] FreeRTOS 下 tasks.c 末尾追加三个支持函数（如适用）
[ ] FreeRTOS 下 cmb_cfg.h 设为 OS 模式 + FREERTOS（如适用）
[ ] CMB_ASSERT 若触发则设为空宏（Keil ARMCC 已知问题）
```

---

## 参考链接

- **CmBacktrace 官方仓库**: https://github.com/armink/CmBacktrace
- **中文 README**: https://github.com/armink/CmBacktrace/blob/master/README_ZH.md
- **Demo 工程**:
  - 裸机 STM32F1: `demos/non_os/stm32f10x/`
  - FreeRTOS STM32F1: `demos/os/freertos/stm32f10x/`
  - RT-Thread STM32F4: `demos/os/rtthread/stm32f4xx/`
  - UCOSII STM32F1: `demos/os/ucosii/stm32f10x/`
- **addr2line 独立版**: https://github.com/armink/CmBacktrace/tree/master/tools
- **B站视频教程**:
  - [CmBacktrace 使用教程（上）](https://www.bilibili.com/video/BV1LB4y1Q78a)
  - [CmBacktrace 使用教程（中）](https://www.bilibili.com/video/BV1uF411i7Ka)
  - [CmBacktrace 使用教程（下）](https://www.bilibili.com/video/BV1rb4y1474Y)
- **armink 其他开源项目**: https://github.com/armink (EasyFlash/FlashDB/Letter Shell)

---

> 更新：2026-06-01
> 作者：Chip @ CherryClaw
