---
name: cmbacktrace-debug
version: "1.0.0"
description: "CmBacktrace (Cortex Microcontroller Backtrace) — ARM Cortex-M 系列 MCU 错误自动追踪与故障诊断库。覆盖 CmBacktrace 移植、配置、API 使用、addr2line 函数调用栈解析、HardFault/MemManage/BusFault/UsageFault 自动诊断、裸机/FreeRTOS/RT-Thread/UCOS 集成、RTT+elog 输出通道、常见移植踩坑与解决。当用户提到 CmBacktrace、HardFault 定位、故障追踪、backtrace、函数调用栈、addr2line、错误自动诊断、Cortex-M 异常、故障寄存器自动分析、cm_backtrace_fault、cm_backtrace_assert、HardFault_Handler 定位、死机定位、除零异常、HardFault 诊断 时使用。"
---

# CmBacktrace 故障诊断与调试指南

> **CmBacktrace**（Cortex Microcontroller Backtrace）—— 针对 ARM Cortex-M 系列 MCU 的错误代码自动追踪、定位，错误原因自动分析的开源库。
>
> 官方仓库：https://github.com/armink/CmBacktrace（MIT 许可，2K+ Stars）
>
> 最新 Release：**v1.4.1**（2022-08-12），master 分支持续更新
>
> STM32 移植文档：`references/stm32-cmbacktrace-porting-guide.md`

## 场景

在 ARM Cortex-M 嵌入式开发中遇到以下问题时使用：

- **HardFault 死机** — 产品跑着跑着就死了，没有串口输出，仿真器一断开就抓不到
- **断言触发** — assert 触发后只知道在哪行断言，不知道为什么断言失败
- **Bug 极难复现** — 真机调试必须断开仿真器，问题一两个月出现一次
- **新人调试困难** — 不知道故障寄存器（CFSR/HFSR/BFSR/MMFSR）怎么读
- **需要函数调用栈** — 出问题后需要还原调用关系，不只是知道死在哪个地址

## 输入

使用本 skill 前需要确认以下信息：

- MCU 内核（Cortex-M0/M3/M4/M7）
- 编译器（Keil MDK / IAR / GCC）
- 操作系统（裸机 / FreeRTOS / RT-Thread / UCOS）
- 串口输出方式（UART printf / RTT / SWO）
- 工程可执行文件路径（.axf / .out / .elf — addr2line 用）

## 依赖

- **arm-gcc 工具链中的 addr2line.exe** — 用于将函数调用栈地址反解析为函数名+行号
  - GCC 工具链自带：`arm-none-eabi-addr2line`
  - 或从 https://github.com/armink/CmBacktrace/tree/master/tools 下载独立 addr2line.exe
- C99 模式（Keil 需在 Target 选项勾选 C99 Mode）
- CmBacktrace 源码（添加到工程即可，无需额外库依赖）

## 移植验证实战踩坑（STM32F411CE + FreeRTOS + Keil MDK + HC-05）

以下为真实移植过程中遇到的关键问题，按排查顺序排列：

### 1. printf 重定向 — CubeMX 不生成，必须手动添加

CubeMX 生成的 usart.c 中没有 `fputc`，`printf` 默认走半主机模式输出到调试器。
**根因**：`cmb_println(...)` 定义为 `printf(__VA_ARGS__)`，但 printf 没有输出目标。

```c
/* usart.c — 必须添加，放在 USER CODE BEGIN 1 区域 */
#pragma import(__use_no_semihosting)
struct __FILE { int handle; };
FILE __stdout;
void _sys_exit(int x) { while(1); }
int fputc(int ch, FILE *f)
{
    while (!(USART1->SR & USART_SR_TXE));
    USART1->DR = (ch & 0xFF);
    return ch;
}
```

> 若使用 `HAL_UART_Transmit` 实现 fputc，需确保 HAL 时基（TIM/SysTick）在调用 printf 时已正常工作。

### 2. DIV_0_TRP — Cortex-M4 默认不捕获除零

`volatile uint32_t c = a / b;` 不会触发 HardFault，除非使能 CCR.DIV_0_TRP。

```c
/* 在故障测试前调用 */
SCB->CCR |= SCB_CCR_DIV_0_TRP_Msk;
__DSB();
```

### 3. 语言文件必须下载

`cm_backtrace.c` 中 `#include "Languages/en-US/cmb_en_US.h"` 等语言文件必须存在。
从 GitHub 下载对应语言目录放到 `cm_backtrace/Languages/` 下，否则编译报 `cannot open source input file`。

### 4. CMB_ASSERT(!on_fault) 在 Keil ARMCC 下触发通病

`cm_backtrace_fault` 内部有 `CMB_ASSERT(!on_fault)`，其中 `on_fault` 是 `static bool = false`。
在 Keil ARMCC v5 下（**未勾选 Use MicroLIB** 时），标准 C 库的 BSS 初始化时机与
CmBacktrace 的 `on_fault` 静态变量存在竞态，导致首次调用时 `on_fault` 误判为 true。

**解决**：

方案 A（推荐）：在 `cmb_def.h` 中将 CMB_ASSERT 定义为空：
```c
#define CMB_ASSERT(EXPR)  ((void)(EXPR))
```
功能完全不受影响，只是跳过了这个保护性断言。

方案 B（尝试）：Project → Target → **勾选 Use MicroLIB**，MicroLIB 的 BSS 初始化
流程更简单，可能避免此问题。但需注意 MicroLIB 的 printf 浮点支持和某些 libc 函数受限。

### 5. FreeRTOS tasks.c 追加三个函数

必须在 tasks.c **文件末尾**（所有 `#endif` 之后）追加：

```c
uint32_t *vTaskStackAddr(void) { return (uint32_t *)pxCurrentTCB->pxStack; }
uint32_t vTaskStackSize(void)  { (void)pxCurrentTCB; return 256; }
char *vTaskName(void)          { return (char *)pxCurrentTCB->pcTaskName; }
```

> **注意**：FreeRTOS V10.3.1 的 TCB 中 **没有 `uxStackDepth` 字段**，`vTaskStackSize` 必须返回固定值或通过 `(pxEndOfStack - pxStack) / sizeof(StackType_t)` 计算。

### 6. 蓝牙模块串口 — 先监听再复位

通过蓝牙串口（HC-05 等）接收时，必须先打开 PC 端串口监听 **再复位板子**，
否则板子启动后发完数据但蓝牙连接尚未就绪，导致数据丢失。

```bash
# Python 串口监听流程
ser = serial.Serial('{SERIAL_PORT}', 115200, timeout=2)
# ... 然后复位/上电板子 ...
ser.read(4096)
```

### 7. JLink 烧录后需断电重上电

JLink 在调试模式下会影响 HC-05 蓝牙模块的状态。烧录完成后：
1. 拔掉 JLink 排线
2. 板子完全断电再重上电
3. 蓝牙连接会自动恢复

### 8. RTT 输出替代 UART

CmBacktrace 的诊断输出也可以通过 **SEGGER RTT** 发送，无需 UART 引脚：

```c
/* cmb_cfg.h 中使用 snprintf + RTT 的组合 */
#include "SEGGER_RTT.h"
#define cmb_println(...)        do { \
    char buf[256]; \
    int len = snprintf(buf, sizeof(buf), __VA_ARGS__); \
    if (len > 0) SEGGER_RTT_Write(0, buf, len); \
    SEGGER_RTT_Write(0, "\r\n", 2); \
} while(0)
```

> **注意**：256 字节的栈缓冲区在 HardFault 上下文中可能触发主栈溢出。
> 如果看到 `Error: Main stack was overflow`，需增大启动文件中的 `Stack_Size`：
> ```asm
> Stack_Size      EQU     0x800    ; 从 0x400(1KB) 改为 2KB
> ```

通过 elog + RTT 则更适合应用层日志，但 HardFault 上下文中建议直接用 `SEGGER_RTT_Write`。

### 9. 故障测试应在 FreeRTOS 任务中触发（非 main 函数）

如果将故障测试放在 `main()` 中（调度器启动前），CmBacktrace 会输出：
```
Fault on interrupt or bare metal(no OS) environment
```
这**不是错误**——因为 FreeRTOS 调度器还未运行，所以诊断正确。

如果想看到 **"Fault on thread: TaskName"**（验证 RTOS 集成），故障需在 FreeRTOS 任务中触发：

```c
void StartTestTask(void *argument)
{
    /* 使能除零捕获 */
    SCB->CCR |= SCB_CCR_DIV_0_TRP_Msk;
    __DSB();

    fault_test_by_div0();  /* 在任务上下文触发 → 显示 Fault on thread */
}
```

### 10. 编译选项：addr2line 需要 Debug Information

Keil 工程必须确认：
- Project → Options → Target → **勾选 C99 Mode**
- Project → Options → Output → **勾选 Debug Information**

否则 addr2line 输出 `??:?`。

## 步骤

### Step 1: 获取源码并加入工程

从 https://github.com/armink/CmBacktrace 获取源码，组织到工程中：

```
project/
├── cm_backtrace/
│   ├── src/
│   │   ├── cm_backtrace.c          # 核心源码
│   │   ├── cm_backtrace.h          # 头文件
│   │   ├── cmb_cfg.h               # 用户配置文件（需自行创建）
│   │   └── cmb_def.h               # 默认配置定义
│   ├── fault_handler/
│   │   ├── cmb_fault.S             # ARM 汇编 — MDK (ARMCC)
│   │   ├── cmb_fault.s             # ARM 汇编 — GCC / IAR
│   │   └── cmb_fault.c             # C 语言版本
│   └── Languages/
│       └── ...
├── demos/                          # 参考 Demo
│   ├── non_os/stm32f10x/
│   ├── os/rtthread/stm32f4xx/
│   ├── os/ucosii/stm32f10x/
│   └── os/freertos/stm32f10x/
```

将 `cm_backtrace/src/` 下所有文件加入工程。

### Step 2: 创建 cmb_cfg.h

```c
#ifndef _CMB_CFG_H_
#define _CMB_CFG_H_

/* ========== 1. 输出接口（必须配置） ========== */
/* 使用 printf 输出，或替换为你的串口输出函数 */
#include <stdio.h>
#define cmb_println(...)            printf(__VA_ARGS__); printf("\r\n")

/* ========== 2. 平台选择（二选一） ========== */
// 裸机平台：
#define CMB_USING_BARE_METAL_PLATFORM
// 或操作系统平台（注释掉上面，取消注释下面）：
// #define CMB_USING_OS_PLATFORM

/* ========== 3. 操作系统类型（仅 OS 模式需要） ========== */
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_RTT     // RT-Thread
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_UCOSII  // UCOSII
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_UCOSIII // UCOSIII
// #define CMB_OS_PLATFORM_TYPE       CMB_OS_PLATFORM_FREERTOS // FreeRTOS

/* ========== 4. CPU 平台 ========== */
#define CMB_CPU_PLATFORM_TYPE       CMB_CPU_ARM_CORTEX_M4   // M0/M3/M4/M7

/* ========== 5. 功能开关 ========== */
#define CMB_USING_DUMP_STACK_INFO                        // Dump 堆栈功能

/* ========== 6. 语言 ========== */
#define CMB_PRINT_LANGUAGE              CMB_PRINT_LANGUAGE_ENGLISH  // 或 CHINESE

#endif /* _CMB_CFG_H_ */
```

### Step 3: 添加故障处理汇编文件

**方式 A（推荐）**：使用 CmBacktrace 自带的 cmb_fault.s

- 将 `cm_backtrace/fault_handler/` 下对应编译器的汇编文件加入工程
- **注释掉** 项目中原有的 `HardFault_Handler` 定义
  - Keil: `startup_stm32fxx.s` 中的 `HardFault_Handler` PROC
  - HAL: `stm32fxx_it.c` 中的 `HardFault_Handler` 函数

**方式 B（自定义）**：在你的 HardFault_Handler 中手动调用

```c
void HardFault_Handler(void)
{
    /* 获取 LR 和 SP */
    uint32_t lr_value;
    uint32_t sp_value;

    __asm volatile(
        "MOV %0, LR\n"
        "MOV %1, SP\n"
        : "=r"(lr_value), "=r"(sp_value)
    );

    cm_backtrace_fault(lr_value, sp_value);

    while (1);  //  halt
}
```

### Step 4: 调用初始化 + 断言钩子

```c
int main(void)
{
    // ... 硬件初始化 ...

    /* 初始化 CmBacktrace */
    cm_backtrace_init("firmware_v1.0", "HW-1.0", "SW-1.0.0");

    // ... 创建任务等 ...
}

/* 断言钩子（如果使用 assert） */
void assert_failed(uint8_t *file, uint32_t line)
{
    /* 获取 SP（尽量在函数开头获取） */
    uint32_t sp_value;
    __asm volatile("MOV %0, SP\n" : "=r"(sp_value));

    cm_backtrace_assert(sp_value);

    while (1);
}
```

### Step 5: 触发故障测试

在任意位置添加测试函数验证移植是否正确：

```c
/* 除零异常测试 */
void fault_test_by_div0(void)
{
    volatile uint32_t *p = NULL;
    uint32_t a = 100;
    uint32_t b = 0;
    p[0] = a / b;  /* 除零 → HardFault */
}

/* 非对齐访问测试 */
void fault_test_by_unalign(void)
{
    volatile uint32_t *p = (uint32_t *)0x20000001;  /* 非对齐地址 */
    *p = 0x12345678;  /* UsageFault → HardFault */
}
```

编译烧录后运行，串口应看到类似输出：

```
============= CmBacktrace (V1.4.0) =============
*** Firmware: firmware_v1.0, HW: HW-1.0, SW: SW-1.0.0 ***
=================================================
[cm_backtrace_fault] please input command:

addr2line -e firmware.axf -a -f 08000a60 08000141 0800313f

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

### Step 6: 使用 addr2line 定位代码位置

将 Step 5 输出的 `addr2line` 命令在工程可执行文件目录执行：

```bash
# 进入 .axf/.out/.elf 所在目录（Keil 在 Output/ 下）
cd path/to/project/Output/

# 执行 addr2line（arm-none-eabi-addr2line 或独立版）
arm-none-eabi-addr2line -e firmware.axf -a -f 08000a60 08000141 0800313f
```

输出示例：

```
0x08000a60
fault_test_by_div0
D:/project/fault_test.c:38
0x08000141
main
D:/project/app.c:20
0x0800313f
_call_main
??:?
```

> 提示：Keil AC5 的 .axf 文件调试信息在工程属性 → Output → Select Folder for Objects 中设置；IAR 在 Exe 目录下。

## 错误

| 错误现象 | 根因 | 解决 |
|---------|------|------|
| 编译报错 C99 语法 | Keil 默认 C90，不支持 `//` 注释等 | Project → Target → C99 Mode 勾选 |
| HardFault_Handler 重复定义 | cmb_fault.s 和启动文件/ it.c 都定义了 | 删除/注释掉启动文件或 it.c 中的 HardFault_Handler |
| 初始化提示无法获取主栈 | 启动文件中主栈名称不是 `STACK`（Keil） | 在 cmb_cfg.h 中定义 `CMB_CSTACK_BLOCK_NAME` 或改启动文件 |
| 串口无输出 | cmb_println 未正确配置 | 确认 cmb_cfg.h 中 cmb_println 指向实际串口输出函数 |
| addr2line 提示 "File format not recognized" | addr2line 架构不匹配 | 使用 arm-none-eabi-addr2line 而非 x86 版 |
| addr2line 输出 "??:?" | 调试信息未包含或优化过度 | 检查 -O0/-Og 编译选项，确认 .axf 含 debug 符号 |
| FreeRTOS 下输出不准 | tasks.c 未按 CmBacktrace 要求修改 | 在 tasks.c 中搜索 `Support For CmBacktrace` 注释位置 |
| 部分地址无法反解析 | 地址不在代码区（可能在中断向量表区） | 忽略 C 库/启动代码部分的地址，关注应用代码地址 |

## 输出

CmBacktrace 正常运行后会输出以下信息（通过 cmb_println 配置的接口）：

1. **固件信息** — `cm_backtrace_init` 传入的名称、硬件版本、软件版本
2. **addr2line 命令** — 可直接复制到命令行执行的 addr2line 命令
3. **故障寄存器** — CFSR / HFSR / DFSR / MMAR / BFAR 原始值
4. **故障诊断** — 自动分析故障类型和原因（DIVBYZERO/UNALIGNED/IMPRECISERR 等）
5. **函数调用栈** — 一系列 PC 地址（需 addr2line 反解析）
6. **堆栈 Dump** — 故障时的堆栈原始数据（可选，由 CMB_USING_DUMP_STACK_INFO 控制）

## 边界

- **不覆盖 ARM Cortex-A/R 系列** — CmBacktrace 仅支持 Cortex-M 系列（M0/M0+/M3/M4/M7/M33）
- **不覆盖 RISC-V 架构** — 仅 ARM Cortex-M
- **不覆盖调试器的实时追踪**（ETM/ITM/SWO）— 那是 `arm-core-registers` / `embedded-debugger-framework` 的范畴
- **不替代仿真器单步调试** — CmBacktrace 用于无法连接仿真器时的故障定位
- 与 `rtos-debug` 互补：CmBacktrace 定位故障原因；rtos-debug 分析任务级运行态问题
- 与 `arm-core-registers` 互补：CmBacktrace 自动解码故障寄存器；arm-core-registers 提供寄存器手动查询

## 交接

- **addr2line 不可用或路径错误** → 检查是否安装了 arm-none-eabi-gcc 工具链，或从 CmBacktrace tools/ 目录下载独立版
- **故障类型无法解析** → 使用 `arm-core-registers` skill 手动解码 CFSR/HFSR 寄存器
- **FreeRTOS 集成问题** → 使用 `freertos-module` skill 检查任务栈配置
- **需要更深入的低级调试** → 使用 `embedded-debugger-framework` skill 的五层诊断模型
- **HardFault 反复出现但无规律** → 使用 `embedded-reviewer` skill 做代码安全审查（ISR/竞态/栈溢出）

## 参考资料

- **官方 GitHub**: https://github.com/armink/CmBacktrace
- **中文文档**: https://github.com/armink/CmBacktrace/blob/master/README_ZH.md
- **Demo 工程**: https://github.com/armink/CmBacktrace/tree/master/demos
- **B站视频教程**:
  - https://www.bilibili.com/video/BV1LB4y1Q78a
  - https://www.bilibili.com/video/BV1uF411i7Ka
  - https://www.bilibili.com/video/BV1rb4y1474Y
- **armink 其他工具**: https://github.com/armink （EasyFlash/FlashDB 等）
