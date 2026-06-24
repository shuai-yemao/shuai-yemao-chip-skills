---
name: arm-core-registers
description: ARM Cortex-M 内核架构寄存器速查与调试指南。涵盖核心寄存器（R0~R15/PSP/MSP）、特殊寄存器（PRIMASK/BASEPRI/FAULTMASK/CONTROL）、系统控制块 SCB（VTOR/AIRCR/CFSR/HFSR）、NVIC（ISER/ICER/IP）、SysTick、MPU、FPU、DWT 周期计数器、ITM/TPIU 跟踪、Bit-banding 位带、异常模型与故障分析。当用户提到寄存器、内核寄存器、ARM 寄存器、系统寄存器、Cortex-M 寄存器、SCB、NVIC 寄存器、SysTick 寄存器、DWT、ITM、MPU 寄存器、HardFault 分析、故障状态寄存器、位带操作、vector table、VTOR、AIRCR、PRIMASK、BASEPRI 时使用。
version: "1.0.0"
---

# ARM Cortex-M 内核架构寄存器指南

> 内核寄存器是 Cortex-M 处理器核心的底层控制接口，所有 STM32 MCU 共享同一套 ARM 内核寄存器架构。
> 与 stm32-hal-development 互补：HAL 封装了寄存器操作，而本 skill 让你直接读写寄存器本身。
> 主要参考：ARMv7-M Architecture Reference Manual (DDI 0403E) / ARMv8-M ARM。

## 适用场景

- 调试器 halt 后读取/修改内核寄存器（R0~R15、xPSR、MSP、PSP）
- 配置中断优先级分组（AIRCR.PRIGROUP）
- 向量表重定位（VTOR）—— 如 IAP/OTA 中跳转 APP
- SysTick 寄存器级配置（不使用 HAL 时）
- MPU 区域配置（特权级保护、内存属性）
- DWT 周期计数器（精确时序测量，不受编译器优化影响）
- ITM/TPIU 跟踪输出（printf via SWO）
- HardFault 现场分析（读取 CFSR、HFSR、BFAR、MMAR 定位故障）
- Bit-banding 原子位操作（F1/F4 可用）
- FPU 控制（启用/禁用、精度模式）
- 低功耗模式（SLEEPDEEP、WFI/WFE）
- 不使用 CMSIS 或 HAL 时的裸寄存器编程

## 必要输入

- Cortex-M 内核版本（M3/M4/M7/M0+ — 寄存器和特性有差异）
- 操作类型（读/写/配寄存器）
- 寄存器名称或地址

## 内核寄存器架构

### 程序员模型

```
低地址                             高地址
┌──────────┬──────────┬──────────────────────────┐
│  R0~R7   │  R8~R12  │  SP(MSP/PSP)  LR(R14)    │
│ (低寄存器)│ (高寄存器)│  PC(R15)  xPSR            │
└──────────┴──────────┴──────────────────────────┘

特殊寄存器:
  PRIMASK  (位 0: 1=禁止所有可屏蔽中断)
  FAULTMASK(位 0: 1=禁止所有中断 + HardFault 也屏蔽)
  BASEPRI  (位[7:4]: 屏蔽优先级 ≥ 该值的中断)
  CONTROL  (位 0: 0=特权级 1=非特权; 位 1: 0=MSP 1=PSP)
```

### 寄存器访问（C 代码）

```c
#include <stdint.h>

// CMSIS 内联函数（推荐）
uint32_t primask = __get_PRIMASK();
__set_PRIMASK(1);       // 关中断
__set_PRIMASK(0);       // 开中断

uint32_t baspri = __get_BASEPRI();
__set_BASEPRI(0x80);    // 屏蔽优先级 ≥ 0x80 的中断（数值越小优先级越高）

uint32_t control = __get_CONTROL();
__set_CONTROL(0x02);    // 切换到 PSP（FreeRTOS 任务栈）

// 内联汇编（等效）
__asm volatile("MRS %0, PRIMASK" : "=r"(primask));
__asm volatile("MSR PRIMASK, %0" : : "r"(1));
```

### 调试器读取（J-Link Commander）

```
// J-Link halt 后读取内核寄存器（通过调试器，非目标代码）
mem32 0xE000EDF0, 1    // SCB->CPUID: 读取 Cortex-M 版本
mem32 0xE000ED00, 1    // SCB->VTOR:  当前向量表地址
mem32 0xE000ED2C, 4    // SCB->CFSR/BFAR/MMAR/AIRCR 一带读取

// 或通过 GDB (debug-gdb-openocd)
// info registers
// p/x $r0
// x/1xw 0xE000ED00
```

## 系统控制块 (SCB)

SCB 基地址：`0xE000ED00`

| 寄存器 | 偏移 | 用途 | 关键位 |
|-------|------|------|--------|
| CPUID | 0x00 | CPU ID | Revision[3:0], PartNo[15:4] |
| ICSR | 0x04 | 中断控制状态 | NMIPENDSET, PENDSVSET, VECTACTIVE |
| VTOR | 0x08 | 向量表偏移寄存器 | **TBLBASE, TBLOFF[31:7]** |
| AIRCR | 0x0C | 应用中断与复位控制 | **VECTKEY[31:16]=0x05FA, PRIGROUP[10:8], SYSRESETREQ[2]** |
| SCR | 0x10 | 系统控制 | SLEEPONEXIT[1], SLEEPDEEP[2], SEVONPEND[4] |
| CCR | 0x14 | 配置与控制 | NONBASETHRDENA[18], USERSETMPENDENA[1], UNALIGN_TRP[3] |
| SHPR1~3 | 0x18~0x20 | 系统异常优先级 | 可配置优先级：MemManage/BusFault/UsageFault/SVCall/Debug/SysTick/PendSV |
| SHCSR | 0x24 | 系统异常处理控制 | MemFault/BusFault/UsageFault 全局使能位 |
| CFSR | 0x28 | **可配置故障状态寄存器** | **UFSR[15:0], BFSR[7:0], MMFSR[7:0]** |
| HFSR | 0x2C | 硬故障状态寄存器 | FORCED[30], VECTTBL[1] |
| MMAR | 0x34 | MemManage 故障地址 | 访问违规的目标地址 |
| BFAR | 0x38 | BusFault 地址 | BusFault 的目标地址 |

### VTOR — 向量表重定位

```c
// 将向量表定位到 Flash 0x08010000（IAP 跳转 APP 前设置）
// 需注意：向量表对齐到 512 字节边界
SCB->VTOR = 0x08010000;
```

**IAP 跳转陷阱**：跳转到 APP 前必须将向量表指向 APP 的偏移地址（`SCB->VTOR = APP_ADDRESS`），否则中断无法正常响应。

### AIRCR — 优先级分组

```c
// PRIGROUP = 4: 4 位抢占优先级, 0 位子优先级（16 级抢占）
// PRIGROUP = 3: 3 位抢占, 1 位子优先级（8 级抢占, 2 级子）
HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);  // HAL 封装
// 等效寄存器操作
SCB->AIRCR = 0x05FA0000 | (4 << 8);  // VECTKEY=0x05FA, PRIGROUP=4
```

### CFSR — 故障分析（HardFault 后必须读）

```c
// 读取故障状态（在 HardFault_Handler 中或调试器 halt 后）
uint32_t cfsr = SCB->CFSR;

// MMFSR: MemManage 故障（低 8 位）
if (cfsr & (1 << 7)) printf("MemManage: MMAR valid\n");
if (cfsr & (1 << 4)) printf("MemManage: Data access violation\n");
if (cfsr & (1 << 1)) printf("MemManage: Instruction access violation\n");

// BFSR: BusFault（次低 8 位）
if (cfsr & (1 << 15)) printf("BusFault: BFAR valid\n");
if (cfsr & (1 << 12)) printf("BusFault: Precise data bus error\n");
if (cfsr & (1 << 8))  printf("BusFault: Instruction bus error\n");

// UFSR: UsageFault（高 16 位）
if (cfsr & (1 << 25)) printf("UsageFault: Divide by zero\n");
if (cfsr & (1 << 24)) printf("UsageFault: Unaligned access\n");
if (cfsr & (1 << 18)) printf("UsageFault: Undefined instruction\n");
if (cfsr & (1 << 17)) printf("UsageFault: Invalid EXC_RETURN\n");
if (cfsr & (1 << 16)) printf("UsageFault: Invalid state (load from !thumb addr)\n");

// HFSR: HardFault 状态
uint32_t hfsr = SCB->HFSR;
if (hfsr & (1 << 30)) printf("HardFault: Forced (another exception can't activate)\n");
if (hfsr & (1 << 1))  printf("HardFault: Vector table read error\n");
```

## NVIC 寄存器

NVIC 基地址：`0xE000E100`

| 寄存器 | 偏移 | 位宽 | 功能 |
|-------|------|------|------|
| ISER[0~7] | 0x100 | 32bit | 中断使能设置（写 1 使能） |
| ICER[0~7] | 0x180 | 32bit | 中断清除（写 1 清除） |
| ISPR[0~7] | 0x200 | 32bit | 中断挂起设置 |
| ICPR[0~7] | 0x280 | 32bit | 中断挂起清除 |
| IABR[0~7] | 0x300 | 32bit | 中断活跃位（只读） |
| IP[0~239] | 0x400 | 8bit | 中断优先级（高 4 位有效） |

```c
// NVIC 寄存器级操作（绕过 HAL）
NVIC_EnableIRQ(USART1_IRQn);       // ISER → 使能中断
NVIC_DisableIRQ(USART1_IRQn);      // ICER → 禁止
NVIC_SetPendingIRQ(USART1_IRQn);    // ISPR → 软件触发
NVIC_ClearPendingIRQ(USART1_IRQn); // ICPR → 清除挂起
NVIC_GetActive(USART1_IRQn);       // IABR → 检查是否正在处理

// 优先级寄存器（IP）
// 优先级值 = NVIC_EncodePriority(s_preempt, s_sub, preempt, sub)
// 共 8 位，但只有高 N 位有效（取决于 PRIGROUP）
NVIC_SetPriority(USART1_IRQn, 5);  // 写入 IP[IRQn]
```

**中断号 vs 异常号**：
```
IRQn 从 0 开始     → NVIC 中断
异常号从 16 开始   → vector table 索引

Handler = vector_table[IRQn + 16]
```

## SysTick 寄存器

SysTick 基地址：`0xE000E010`

| 寄存器 | 偏移 | 用途 |
|-------|------|------|
| CSR (CTRL) | 0x00 | 控制与状态：ENABLE[0], TICKINT[1], CLKSOURCE[2], COUNTFLAG[16] |
| RVR (LOAD) | 0x04 | 重装载值 |
| CVR (VAL) | 0x08 | 当前计数值 |
| CALIB | 0x0C | 校准值（只读，含 10ms 参考值） |

```c
// SysTick 寄存器级配置（1ms 中断）
SysTick->LOAD  = (SystemCoreClock / 1000) - 1;   // 1ms 周期
SysTick->VAL   = 0;                                // 清计数器
SysTick->CTRL  = SysTick_CTRL_ENABLE_Msk          // 使能
               | SysTick_CTRL_TICKINT_Msk          // 使能中断
               | SysTick_CTRL_CLKSOURCE_Msk;       // 系统时钟源

// 读取校准值（10ms 参考间隔）
uint32_t calib = SysTick->CALIB;
uint32_t ten_ms_ticks = calib & 0x00FFFFFF;  // 10ms == SystemCoreClock/100
uint8_t  skew = (calib >> 30) & 1;             // 1=校准值不精确
```

## DWT 周期计数器

DWT 基地址：`0xE0001000`

```c
// 精确时序测量（不受编译器优化影响）
void DWT_Init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;  // 使能跟踪
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;              // 使能周期计数器
    DWT->CYCCNT = 0;                                   // 清零
}

uint32_t DWT_GetCycles(void)
{
    return DWT->CYCCNT;
}

uint32_t DWT_DelayCycles(uint32_t cycles)
{
    uint32_t start = DWT_GetCycles();
    while ((DWT_GetCycles() - start) < cycles);
}
```

**优势**：DWT 是硬件计数器，不受中断和任务切换影响。在 FreeRTOS 环境下比 `HAL_GetTick()` 精度高得多。

## MPU 寄存器

MPU 基地址：`0xE000ED90`（SCB 区域）

| 寄存器 | 偏移 | 用途 |
|-------|------|------|
| TYPE | 0x00 | MPU 类型：DREGION[15:8] = 区域数 |
| CTRL | 0x04 | PRIVDEFENA[2], HFNMIENA[1], ENABLE[0] |
| RNR | 0x08 | 区域号选择（0~DREGION-1） |
| RBAR | 0x0C | 区域基地址 + ADDR[31:N], VALID[4], REGION[3:0] |
| RLAR | 0x10 | 区域上限地址（ARMv8-M） |
| RASR | 0x10 | 区域属性和大小（ARMv7-M）：SIZE[5:1], AP[26:24], TEX[12:11], C/B/S |

```c
// MPU 配置示例（保护关键内存区域，防止野指针破坏）
void MPU_Config(void)
{
    // 禁用 MPU
    MPU->CTRL = 0;

    // 区域 0: Flash (0x08000000, 1MB) — 只读(XN), 特权可读写
    MPU->RNR  = 0;
    MPU->RBAR = 0x08000000 | MPU_RBAR_VALID_Msk;
    MPU->RASR = (0 << MPU_RASR_AP_Pos)        // 特权读写, 用户不可读
               | MPU_RASR_CACHEABLE_Msk
               | MPU_RASR_BUFFERABLE_Msk
               | (19 << MPU_RASR_SIZE_Pos);    // 2^19 = 512KB

    // 使能 MPU + 默认映射（特权模式下可访问未映射区域）
    MPU->CTRL = MPU_CTRL_ENABLE_Msk | MPU_CTRL_PRIVDEFENA_Msk;
    __DSB();
    __ISB();
}
```

## ITM / TPIU（SWO 跟踪）

ITM 基地址：`0xE0000000`, TPIU 基地址：`0xE0040000`

```c
// ITM 发送单个字符（用于 SWO printf）
void ITM_SendChar(char ch)
{
    // 等待 ITM 通道 0 就绪
    while (!(ITM->STIM[0] & ITM_STIM_FIFOREADY_Msk));
    ITM->STIM[0] = ch;
}

// 与 Syscall printf 挂钩：
int _write(int file, char *ptr, int len)
{
    for (int i = 0; i < len; i++) {
        ITM_SendChar(ptr[i]);
    }
    return len;
}

// 前提：
// 1. 调试器持续读取 TPIU (SWO 引脚)
// 2. CoreDebug->DEMCR |= TRCENA
// 3. ITM->TER |= (1 << 0)    // 使能 stimulus port 0
// 4. TPIU 配置: SWO 时钟 = CPU_CLK / (prescaler + 1)
```

## Bit-banding（位带操作）

Cortex-M3/M4/M7 支持位带：将 1MB 别名区映射到 32MB 位带区，实现原子位操作。

```c
// GPIO ODR 位 5 的位带地址
// 位带别名地址 = 0x42000000 + (A - 0x40000000) * 32 + n * 4
// A = 外设寄存器地址, n = 位号

#define BITBAND_PERI(addr, bit)  (*(volatile uint32_t *)(0x42000000 + ((uint32_t)(addr) - 0x40000000) * 32 + (bit) * 4))

// 原子置位/复位（不破坏其他位）
BITBAND_PERI(&GPIOA->ODR, 5) = 1;   // PA5 = 1
BITBAND_PERI(&GPIOA->ODR, 5) = 0;   // PA5 = 0
```

**限制**：
- 仅 SRAM (0x20000000~0x200FFFFF) 和外设 (0x40000000~0x400FFFFF) 支持
- H7 不支持位带（Cortex-M7 早期版本支持，H7 内核移除了位带）

## 平台差异速查

| 特性 | M0+ | M3 | M4 | M7 |
|------|-----|----|----|----|
| 内核版本 | ARMv6-M | ARMv7-M | ARMv7-M | ARMv7E-M |
| 位带 | ❌ | ✅ | ✅ | ❌（H7 移除） |
| MPU | ✅（8 区域） | ❌（F103 无 MPU） | ✅（8 区域） | ✅（8/16 区域） |
| FPU | ❌ | ❌ | ✅ (SP) | ✅ (DP) |
| DWT | 有限 | ✅ | ✅ | ✅ |
| ITM/TPIU | ❌ | ✅ | ✅ | ✅ |
| 中断数 | 32 | 240 | 240 | 240 |
| BASEPRI | ❌ | ✅ | ✅ | ✅ |

## 调试方法

### J-Link Commander 快速寄存器读取
```
// halt 目标
halt

// 读取内核寄存器
reg          // 列出所有内核寄存器 (R0-R15, xPSR, MSP, PSP)
mem32 0xE000ED00, 8   // SCB 寄存器组 (VTOR, AIRCR, SCR, CCR, SHPR, SHCSR, CFSR, HFSR)

// 故障分析
mem32 0xE000ED28, 1   // CFSR
mem32 0xE000ED2C, 1   // HFSR
mem32 0xE000ED34, 1   // MMAR
mem32 0xE000ED38, 1   // BFAR

// SysTick
mem32 0xE000E010, 4   // CSR, RVR, CVR, CALIB

// NVIC (中断 0~31 使能)
mem32 0xE000E100, 1   // ISER[0]
mem32 0xE000E180, 1   // ICER[0]

// 向量表
mem32 0x00000000, 16  // 向量表前 16 项（系统异常）
mem32 0x08000000, 16  // Flash 起始向量表
```

### HardFault 诊断流程

```
1. halt 后读 CFSR  → 确定故障类型
   ├─ MMFSR ≠ 0 → MemManage (MPU)
   ├─ BFSR  ≠ 0 → BusFault (内存访问)
   └─ UFSR  ≠ 0 → UsageFault (非法指令/不对齐)

2. 读 MMAR / BFAR → 获取故障地址

3. 读 stacked PC → 定位故障指令
   └─ 根据 EXC_RETURN 确定使用的栈 (MSP vs PSP)
   └─ 在故障前手动记录的 R14(LR)=EXC_RETURN

4. 读 stack frame 中的 xPSR → 获取更多上下文
```

## 边界定义

### 不该激活
- 用户需要的是 HAL 层的 API 调用 → 使用 `stm32-hal-development`
- 用户需要的是外设级寄存器（GPIO/USART/TIM 等）→ 使用 `mcu-peripheral-registers`
- 用户需要的是调试器/烧录器配置 → 使用 `flash-jlink` / `flash-openocd` / `debug-gdb-openocd`

### 不该做
- **禁止**在运行中随意修改 SCB->AIRCR 的 PRIGROUP（必须在系统启动初期设置，且一次设置后不可改）
- **禁止**在 ISR 中修改 MPU 配置（可能导致权限瞬间变化）
- **禁止**在非特权级下执行需要特权级的 MRS/MSR 操作（会产生 UsageFault）

### 不该碰
- **不触碰** STM32 外设寄存器（属于另一个 skill）
- **不触碰** 系统内存映射中的保留区域

## 交接关系

- 同层：`mcu-peripheral-registers`（外设寄存器，互补）
- 上游：`stm32-hal-development`（HAL API 封装）
- 调试时：`debug-gdb-openocd`（GDB 读取内核寄存器）、`flash-jlink`（JLink Commander 读取）

## 参考资料

- ARMv7-M Architecture Reference Manual (DDI 0403E) — 官方《ARM Architecture Reference Manual》
- ARM Cortex-M3/M4/M7 技术参考手册 (TRM) — 各内核的 TRM
- STM32 各系列编程手册（PM）— 如 PM0214 (F3/F4), PM0253 (F7)
