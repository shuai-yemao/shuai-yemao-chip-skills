---
name: arm-interrupt-exception
description: ARM Cortex-M 中断与异常系统完整指南——异常架构（类型/优先级/咬尾/晚到/抢占/悬起）、NVIC 编程（ISER/ICER/ISPR/ICPR/IP/优先级分组）、EXTI 配置（线选择/触发类型/中断/事件模式/软件触发/Hardware Interrupt Map）、中断优先级设计模式（抢占优先/子优先级/临界区）、向量表管理（VTOR 重定位/IAP 跳转/动态表）、故障处理与异常升级（HardFault/NMI/BusFault）、中断安全与 ISR 设计模式、中断延迟分析与优化、零延迟中断设计、临界区优化（BASEPRI/PRIMASK/调度器锁）、中断负载均衡、ISR 执行时间优化。当用户提到中断、异常、NVIC、EXTI、ISER、ICER、IP 寄存器、中断优先级、抢占优先级、子优先级、优先级分组、PRIGROUP、向量表、VTOR、中断使能、中断禁止、中断挂起、中断清除、EXTI 配置、EXTI 中断、EXTI 事件、外部中断、PA0 中断、EXTI 线、HardFault、NMI、SysTick 中断、PendSV、SVC、中断嵌套、咬尾中断、晚到中断、悬起、临界区、中断安全、可重入、中断延迟、零延迟中断、中断向量表重映射、IAP 中断、动态向量表、中断优化、BASEPRI、咬尾优化、ISR 执行时间、优先级反转时使用。
version: "1.0.0"
---

# ARM Cortex-M 中断与异常系统指南

> 与 `arm-core-registers`（内核寄存器级）和 `mcu-peripheral-registers`（外设寄存器级）互补——本 skill 关注**中断与异常系统的架构设计、配置策略和调试**。

## 适用场景

- 异常类型判断与优先级规划（系统异常 vs 外部中断）
- NVIC 中断使能/禁能/挂起/优先级配置
- EXTI 外部中断配置与线选择
- 中断优先级分组策略设计（抢占 vs 子优先级）
- 向量表重定位（IAP/OTA Bootloader 跳转）
- 临界区设计与中断安全编程
- HardFault 分析（CFSR/HFSR/MMAR/BFAR 解码）
- 中断延迟分析与优化
- 中断嵌套/咬尾/晚到等硬件行为理解

## 必要输入

- Cortex-M 内核版本（M0+/M3/M4/M7/M33 — 异常模型相同，NVIC 中断数不同）
- STM32 系列与型号（决定 EXTI 线和 NVIC IRQ 通道号）
- 具体场景：中断配置/故障分析/向量表管理

---

## 1. 异常架构

### 异常类型

Cortex-M 的异常按优先级分为 3 个层级（从高到低）：

| 优先级层级 | 异常 | 编号 | 说明 |
|-----------|------|------|------|
| **固定最高** | Reset | 1 | 上电复位，最高优先级 -3 |
| | NMI | 2 | 非屏蔽中断，优先级 -2 |
| | HardFault | 3 | 硬故障，优先级 -1 |
| **可配置** | MemManage | 4 | MPU 违例 (M3/M4/M7/M33) |
| | BusFault | 5 | 总线错误 (M3/M4/M7/M33) |
| | UsageFault | 6 | 用法错误 (M3/M4/M7/M33) |
| | SecureFault | 7 | 安全故障 (M33 only) |
| | **SVCall** | 11 | SVC 指令调用 |
| | **DebugMonitor** | 12 | 调试监视器 |
| | **PendSV** | 14 | 可悬起的系统调用 |
| | **SysTick** | 15 | 系统滴答定时器 |
| **用户中断** | IRQ0~IRQn | 16+ | 外设中断（NVIC 管理） |

> M0/M0+ 只有 Reset/NMI/HardFault/SVCall/PendSV/SysTick + 外部中断。MemManage/BusFault/UsageFault 仅 M3+。

### 优先级架构

```
  ┌─ 固定优先级 ──────────────────────┐
  │  Reset   (-3)                      │  最高
  │  NMI     (-2)                      │  ↑
  │  HardFault(-1)                     │  │
  └────────────────────────────────────┘  │
  ┌─ PRIGROUP 配置区 ─────────────────┐  │
  │  MemManage (可配置)                 │  │
  │  BusFault                          │  │
  │  UsageFault                        │  │
  │  SVCall                            │  │
  │  PendSV                            │  │
  │  SysTick                           │  │
  │  IRQ0 ~ IRQn (外部中断)            │  最低
  └────────────────────────────────────┘
```

**关键规则**:
- 固定优先级异常始终高于可配置异常
- 可配置异常之间、可配置异常与 IRQ 之间**按优先级数值比较**（数值越小优先级越高）
- 相同优先级的异常：编号越小优先级越高（硬件仲裁）
- NMI 和 HardFault 不能被任何其他异常抢占
- MemManage/BusFault/UsageFault 可被 NMI/HardFault 抢占

### 异常处理流程

```
CPU 正在执行主程序
      │
      │ 中断/异常到来
      ▼
┌─────────────────────────────────────────┐
│ 1. 入栈 (Stacking)                       │
│    xPSR, PC, LR, R12, R3~R0 自动入栈    │
│    → 使用当前 SP (MSP 或 PSP)            │
│    耗时: M4=12 cycles, M7=~5 cycles     │
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│ 2. 取向量 (Vector Fetch)                 │
│    从向量表读取 ISR 地址                 │
│    向量表基址 = SCB->VTOR                │
│    ISR 地址 = VTOR + 异常编号 × 4        │
│    耗时: M4=4~7 cycles (含 I-Cache 命中)  │
└────────────────┬────────────────────────┘
                 ▼
┌─────────────────────────────────────────┐
│ 3. 更新寄存器                           │
│    LR = EXC_RETURN (0xFFFFFFFx)         │
│    PC = ISR 地址                        │
│    xPSR.ISR = 异常编号                  │
└────────────────┬────────────────────────┘
                 ▼
       ISR 开始执行
                 │
                 │ 执行完毕，执行 BX LR
                 ▼
┌─────────────────────────────────────────┐
│ 4. 出栈 (Unstacking)                     │
│    根据 EXC_RETURN 判断 MSP/PSP         │
│    恢复 R0~R3, R12, LR, PC, xPSR       │
│    耗时: M4=14 cycles                   │
└─────────────────────────────────────────┘
```

### 硬件优化机制

| 机制 | 说明 | 时序影响 |
|------|------|---------|
| **咬尾 (Tail-Chaining)** | 退出 ISR 时不执行出栈+入栈，直接进入下一个 pending 的中断 | 节省 ~12+12 cycles |
| **晚到 (Late-Arrival)** | 入栈过程中更高优先级中断到达，CPU 完成入栈后直接服务更高优先级 | 额外 0 cycle (free) |
| **悬起 (Pending)** | 中断被触发但优先级不足，自动标记为待处理 | PRS 置位 |
| **抢占 (Preemption)** | 高优先级中断打断低优先级 ISR | 完全入栈+出栈 |
| **咬尾+晚到混合** | 出栈时晚到 → 无视咬尾，直接取新向量 | ~8 cycles |

```c
// 时序对比（M4, 无 I-Cache 命中, Flash 零等待）
// 中断到来 → ISR 第一条指令: 22 cycles (栈操作 + 取向量)
// ISR 返回 → 主程序: 14 cycles (出栈)
// 咬尾: 中断1 → 中断2: 10 cycles (取向量，无栈操作)
// 晚到: 不增加额外 cycle
```

---

## 2. NVIC 编程

### NVIC 寄存器集

| 寄存器 | 偏移 | 宽度 | 操作 | 说明 |
|--------|------|------|------|------|
| **ISER[0..n]** | 0x000 | 32 | WO | 中断使能置位 |
| **ICER[0..n]** | 0x080 | 32 | WO | 中断使能清除 |
| **ISPR[0..n]** | 0x100 | 32 | WO | 中断挂起置位（软件触发） |
| **ICPR[0..n]** | 0x180 | 32 | WO | 中断挂起清除 |
| **IABR[0..n]** | 0x200 | 32 | RO | 中断活跃状态 |
| **IP[0..n]** | 0x300 | 8 | RW | 中断优先级（每 IRQ 1 字节） |
| **STIR** | 0xE00 | 32 | WO | 软件触发中断寄存器（M4/M7） |

> n = (最大 IRQ 数 + 31) / 32。STM32F411 有 82 个 IRQ → n=3。

### NVIC 编程 API

```c
// ── CMSIS 原生 API（推荐）──

// 中断使能/禁能
NVIC_EnableIRQ(IRQn_Type irq);      // 写 ISER
NVIC_DisableIRQ(IRQn_Type irq);     // 写 ICER

// 中断挂起控制
NVIC_SetPendingIRQ(IRQn);            // 写 ISPR（软件触发中断）
NVIC_ClearPendingIRQ(IRQn);          // 写 ICPR

// 获取挂起/活跃状态
uint32_t NVIC_GetPendingIRQ(IRQn);   // 读 ISPR
uint32_t NVIC_GetActive(IRQn);       // 读 IABR

// 优先级设置
NVIC_SetPriority(IRQn, priority);    // 写 IP[n]（只使用高位，根据 PRIGROUP）
NVIC_GetPriority(IRQn);              // 读 IP[n]

// 系统异常优先级
NVIC_SetPriority(MemoryManagement_IRQn, prio);
NVIC_SetPriority(BusFault_IRQn, prio);
NVIC_SetPriority(UsageFault_IRQn, prio);
NVIC_SetPriority(SVCall_IRQn, prio);
NVIC_SetPriority(PendSV_IRQn, prio);
NVIC_SetPriority(SysTick_IRQn, prio);
```

```c
// ── 寄存器级直接操作 ──
// 使能 USART1 中断 (IRQ 37)
NVIC->ISER[1] = (1 << (37 - 32));    // ISER1 位 5

// 禁能 USART1
NVIC->ICER[1] = (1 << (37 - 32));    // ICER1 位 5

// 软件触发 SPI1 中断 (IRQ 35)
NVIC->ISPR[1] = (1 << (35 - 32));    // 调试用

// 批量操作：原子地使能一段连续 IRQ
NVIC->ISER[0] = 0xFFFF0000;          // 一次性使能 IRQ16~IRQ31
```

### 优先级分组（PRIGROUP）

```c
// PRIGROUP 位于 SCB->AIRCR 的位[10:8]
// 设置方式（推荐使用 CMSIS）:
#define NVIC_PriorityGroup_0  0x00000007  // 0 位抢占, 4 位子优先级 (M0+/M3 特殊)
#define NVIC_PriorityGroup_1  0x00000006  // 1 位抢占, 3 位子优先级
#define NVIC_PriorityGroup_2  0x00000005  // 2 位抢占, 2 位子优先级
#define NVIC_PriorityGroup_3  0x00000004  // 3 位抢占, 1 位子优先级
#define NVIC_PriorityGroup_4  0x00000003  // 4 位抢占, 0 位子优先级 (默认)

// 标准设置方式
HAL_NVIC_SetPriorityGrouping(NVIC_PriorityGroup_2);
// 或寄存器级:
SCB->AIRCR = (0x5FA << 16) | (NVIC_PriorityGroup_2 << 8);
DSB();
ISB();
```

**优先级分组速查表**（M3/M4/M7 使用高 4 位，M0+ 使用高 2 位）：

```
M3/M4/M7 (8 位优先级寄存器，只使用高 4 位):

PRIGROUP | 抢占位数 | 子优先级位数 | 优先级组合数 | 应用场景
─────────┼─────────┼────────────┼────────────┼────────────────
Group 0  | 0       | 4          | 1×16=16    | 所有中断同级，按编号仲裁
Group 1  | 1       | 3          | 2×8=16     | 高/低两档抢占
Group 2  | 2       | 2          | 4×4=16     | 4 级嵌套（推荐 RTOS）
Group 3  | 3       | 1          | 8×2=16     | 8 级抢占 + 2 级子优先级
Group 4  | 4       | 0          | 16×1=16    | 完全嵌套（默认，最常用）

汇总: 无论分组方式，总共有 16 个离散优先级值。
```

**分组选择建议**：

| 场景 | 推荐分组 | 理由 |
|------|---------|------|
| 裸机简单应用 | Group 4 (4 bits preempt) | 清清爽爽 16 级嵌套，无需子优先级 |
| FreeRTOS | Group 2 (2+2) | configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY 常用 5 |
| 多级中断 + 相同优先级细分 | Group 3 (3+1) | 8 级嵌套，同嵌套级内部可设子优先级 |
| 所有中断平权 | Group 0 (0+4) | 无抢占，按硬件编号裁决 |

### FreeRTOS 特殊优先级约定

```c
// FreeRTOS 要求最低 4 位优先级分配给它的临界区机制
// 常用配置:
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY    5
// 含义: 优先级在 0~4 的中断不会被 FreeRTOS 的临界区关闭
//       优先级 ≥5 的中断会在临界区内被屏蔽

// 中断优先级设置与 FreeRTOS 兼容:
// 时序关键中断（如 1ms 系统时钟）: 优先级 0~4 （高于 MAX_SYSCALL）
// 普通外设中断（调用 FreeRTOS API 的）: 优先级 5~15
// PendSV: 优先级 15 （最低，最后执行）
// SysTick: 优先级 15 （与 PendSV 同优先级，咬尾优化）

// 重要: FreeRTOS 的临界区通过 BASEPRI 实现
// taskENTER_CRITICAL() 设置 BASEPRI = configMAX_SYSCALL_INTERRUPT_PRIORITY
// 因此优先级高于这个值的中断永远不会被延迟！
```

---

## 3. EXTI 外部中断

### EXTI 架构

```
                         NVIC
                          ↑
                     ┌────┴────┐
                     │  EXTI   │
                     │  PR/IMR │
                     └────┬────┘
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
  ┌───▼───┐         ┌────▼────┐         ┌────▼────┐
  │ GPIO A │         │ GPIO B  │  ...    │ GPIO H  │
  │PA0~PA15│         │PB0~PB15│         │PH0~PH1  │
  └────────┘         └─────────┘         └─────────┘
      ↑                   ↑                   ↑
  SYSCFG_EXTICR1     SYSCFG_EXTICR2     SYSCFG_EXTICR4
```

### EXTI 关键寄存器

| 寄存器 | 说明 |
|--------|------|
| **IMR** | 中断屏蔽寄存器（1=使能中断） |
| **EMR** | 事件屏蔽寄存器（1=使能事件，事件不产生中断） |
| **RTSR** | 上升沿触发选择（1=上升沿触发） |
| **FTSR** | 下降沿触发选择（1=下降沿触发） |
| **SWIER** | 软件中断事件寄存器（写 1 软件触发，前提 IMR 使能） |
| **PR** | 挂起寄存器（硬件置 1，写 1 清除） |

### EXTI 线映射（SYSCFG_EXTICR）

每条 EXTI 线只能连接一个 GPIO 端口，通过 SYSCFG_EXTICR1~4 配置：

```c
// EXTI0 可以连接 PA0/PB0/PC0/PD0/PE0/PF0/PG0/PH0
// 通过 SYSCFG_EXTICR1 的位[3:0] 选择

// ── HAL 方式 ──
HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);  // 内部调用 SYSCFG_EXTICR1 配置

// ── 寄存器级 ──
SYSCFG->EXTICR[0] &= ~SYSCFG_EXTICR1_EXTI0;  // 清除 EXTI0 源
SYSCFG->EXTICR[0] |= SYSCFG_EXTICR1_EXTI0_PA; // PA0 → EXTI0

// SYSCFG_EXTICR 完整结构:
// EXTICR1: EXTI[3:0] 各 4 位 = 16 位,  偏移 0x08
// EXTICR2: EXTI[7:4] 各 4 位 = 16 位,  偏移 0x0C
// EXTICR3: EXTI[11:8] 各 4 位 = 16 位, 偏移 0x10
// EXTICR4: EXTI[15:12] 各 4 位 = 16 位, 偏移 0x14

// GPIO 编码（SYSCFG_EXTICR 字段值）:
// 0b0000 = PA, 0b0001 = PB, 0b0010 = PC,
// 0b0011 = PD, 0b0100 = PE, 0b0101 = PF,
// 0b0110 = PG, 0b0111 = PH
```

### EXTI 中断通道与 NVIC 映射

```c
// STM32F4 EXTI → NVIC IRQn 映射

// EXTI0    → EXTI0_IRQn      (IRQ 6)
// EXTI1    → EXTI1_IRQn      (IRQ 7)
// EXTI2    → EXTI2_IRQn      (IRQ 8)
// EXTI3    → EXTI3_IRQn      (IRQ 9)
// EXTI4    → EXTI4_IRQn      (IRQ 10)
// EXTI5~9  → EXTI9_5_IRQn    (IRQ 23)
// EXTI10~15→ EXTI15_10_IRQn  (IRQ 40)
// EXTI16   → EXTI16_IRQn(PVD)(IRQ 1)
// EXTI17   → EXTI17_IRQn(RTC) (IRQ 2)
// EXTI18   → EXTI18_IRQn(USB) (IRQ 42)
```

**关键约束**：同一 EXTI 通道的中断在同一个 ISR 中处理。例如 EXTI9_5_IRQHandler 需要读取 EXTI->PR 来判断具体是哪条线触发：

```c
void EXTI9_5_IRQHandler(void) {
    if (EXTI_GetITStatus(EXTI_Line5)) {
        // PB5 中断处理
        EXTI_ClearITPendingBit(EXTI_Line5);
    }
    if (EXTI_GetITStatus(EXTI_Line6)) {
        // PC6 中断处理
        EXTI_ClearITPendingBit(EXTI_Line6);
    }
    // ...
}
```

### EXTI 完整配置示例

```c
// ── 配置 PA0 上升沿触发外部中断 ──

// 步骤 1: 使能时钟
RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;            // GPIOA 时钟
RCC->APB2ENR |= RCC_APB2ENR_SYSCFGEN;            // SYSCFG 时钟

// 步骤 2: 配置 GPIO 为输入模式
GPIOA->MODER &= ~(GPIO_MODER_MODER0);             // 00 = 输入

// 步骤 3: 配置 EXTI 线源（哪个 GPIO 端口）
SYSCFG->EXTICR[0] &= ~SYSCFG_EXTICR1_EXTI0;       // 清除
SYSCFG->EXTICR[0] |= SYSCFG_EXTICR1_EXTI0_PA;     // PA0 → EXTI0

// 步骤 4: 配置 EXTI 触发方式
EXTI->IMR |= EXTI_IMR_MR0;                        // 不屏蔽 EXTI0 中断
EXTI->RTSR |= EXTI_RTSR_TR0;                      // 上升沿触发

// 步骤 5: 配置 NVIC 优先级并使能
NVIC_SetPriority(EXTI0_IRQn, 2);                  // 优先级 2
NVIC_EnableIRQ(EXTI0_IRQn);                       // 使能中断

// 步骤 6: 实现 ISR
void EXTI0_IRQHandler(void) {
    if (EXTI->PR & EXTI_PR_PR0) {                 // 确认 EXTI0 挂起
        // 处理中断
        EXTI->PR = EXTI_PR_PR0;                   // 写 1 清除挂起位
    }
}
```

### EXTI 常见陷阱

| 陷阱 | 说明 | 修复 |
|------|------|------|
| 忘记使能 SYSCFG 时钟 | F1: RCC->APB2ENR, F4: RCC->APB2ENR | 检查时钟使能 |
| EXTI PR 写 0 不清除 | PR 寄存器写 1 清除，不是写 0 | `EXTI->PR = EXTI_PR_PRx` |
| 同一线多端口冲突 | EXTI0 同时配置 PA0 和 PB0 → 行为未定义 | 每条线只能选一个端口 |
| 边沿触发丢失 | 脉冲宽度小于 HCLK 周期 | 使用门控或两级采样 |
| EXTI5~9/10~15 共用 ISR | 不检查具体线号会误处理 | ISR 内逐线检查 PR |
| 软件触发不清 PR | SWIER 触发后 PR 位会置位 | ISR 退出前需清除对应 PR |

---

## 4. 中断优先级设计模式

### 通用分层策略

```
优先级层级 | 例子           | 临界区影响
───────────┼────────────────┼────────────────
Level 0-1  | TIM 时基、ADC  | 永不关闭（高于 MAX_SYSCALL）
Level 2-3  | 通信收发、DMA  | 永不关闭（高于 MAX_SYSCALL）
Level 4-5  | 按键、传感器   | 被临界区延迟（但可接受）
Level 6-7  | 普通外设       | 延迟可达数 ms
Level 8-14 | 背景任务 ISR   | 延迟较大
Level 15   | PendSV/SysTick | RTOS 调度专用，最低
```

### NVIC 优先级配置要点

```c
// 原则 1: 系统异常优先级高于所有 IRQ
NVIC_SetPriority(SVCall_IRQn, 0);
NVIC_SetPriority(SysTick_IRQn, 0xFF);   // 最低（FreeRTOS 约定）
NVIC_SetPriority(PendSV_IRQn, 0xFF);    // 最低（FreeRTOS 约定）

// 原则 2: 时序关键中断优先级最高
NVIC_SetPriority(TIM1_UP_IRQn, 1);      // 1ms 控制循环
NVIC_SetPriority(ADC_IRQn, 1);          // 同步采样

// 原则 3: 调用 FreeRTOS API 的中断遵守 configMAX_SYSCALL_INTERRUPT_PRIORITY
NVIC_SetPriority(UART_IRQn, 5);         // xQueueSendFromISR 可以安全调用
NVIC_SetPriority(SPI_IRQn, 6);          // 同上

// 原则 4: ISR 耗时越短，优先级越高
//   1μs 的 ISR → 优先级 0
//   100μs 的 ISR → 优先级 8
//   1ms 的 ISR → 优先级 12

// 原则 5: 通过 BASEPRI 实现零延迟临界区
__set_BASEPRI(5 << 4);      // 屏蔽优先级 ≥5 的所有中断（FreeRTOS 用法）
// 优先级 0~4 的中断不受影响 → 零延迟
__set_BASEPRI(0);            // 恢复（解除屏蔽）
```

### 临界区设计

```c
// 策略 1: 全局关中断（粗暴但简单）
__disable_irq();              // 设置 PRIMASK
// 临界区代码
__enable_irq();               // 清除 PRIMASK
// 缺点: 延迟所有中断，包括时序关键中断

// 策略 2: BASEPRI 临界区（推荐 RTOS）
__set_BASEPRI(5 << 4);        // 屏蔽优先级 ≥5
// 临界区代码（优先级 0~4 仍可响应）
__set_BASEPRI(0);             // 恢复
// 优点: 时序关键中断不受影响

// 策略 3: 特定中断屏蔽（最精细）
NVIC_DisableIRQ(USART1_IRQn); // 只关 USART1
NVIC_EnableIRQ(USART1_IRQn);
// 缺点: 被中断嵌套 → 需要计数保护

// 策略 4: 中断安全的数据访问（无锁）
// 适用于单次读/写 32 位变量的场景
volatile uint32_t shared_flag;  // volatile 保证不优化
// 单次 32 位 load/store 是原子的，无需临界区！
```

### 中断安全 ISR 设计原则

```c
// 原则 1: ISR 越短越好
void TIM_IRQHandler(void) {
    TIM->SR &= ~TIM_SR_UIF;     // 清标志
    flag = 1;                   // 设置标志，主循环轮询
    // 不要在 ISR 中执行复杂处理！
}

// 原则 2: 可重入性——避免在 ISR 和主循环中使用同一个变量
// 错误: 主循环和 ISR 都用 process_data()
// 正确: ISR 只设标志/放队列，主循环处理

// 原则 3: 共享变量的 volatile + 原子操作
volatile uint32_t tick_count;  // ISR 修改，主循环读取

// 线程安全的单生产者/单消费者队列:
// ISR (生产者): xQueueSendFromISR(queue, &data, &woken);
// 主循环 (消费者): xQueueReceive(queue, &data, portMAX_DELAY);

// 原则 4: DMA + 中断配合时的数据一致性
// ISR 中 DMA 传输完成:
void DMA_IRQHandler(void) {
    DMA->IFCR = channel_flag;           // 清中断标志
    SCB_InvalidateDCache_by_Addr(buf, len);  // M7: 刷新 D-Cache
    ready_flag = 1;
}

// 原则 5: 嵌套中断中不要做假定
// 高优先级中断可以在任意时刻打断低优先级 ISR！
// 在 ISR 开头保护所有共享资源访问
```

---

## 5. 向量表管理

### VTOR 与向量表重定位

```c
// 向量表默认在 Flash 起始地址 (0x08000000)
// 通过 VTOR 寄存器可以重定位到 SRAM 或其他地址

// 查看当前向量表基址
uint32_t vtor = SCB->VTOR;

// ── IAP Bootloader 中的向量表切换 ──

// 场景: Bootloader 在 0x08000000, APP 在 0x08020000

// 步骤 1: APP 启动时重定位向量表
#define APP_BASE 0x08020000

// 方法 A: 直接设置 VTOR（Cortex-M3/M4/M7）
SCB->VTOR = APP_BASE;
DSB();
ISB();

// 方法 B: 如果你的启动代码修改了 VTOR（例如 SystemInit 中）
// 先跳到 APP 的 Reset_Handler
uint32_t app_stack  = *(volatile uint32_t*)APP_BASE;
uint32_t app_entry  = *(volatile uint32_t*)(APP_BASE + 4);
__set_MSP(app_stack);          // 设置 APP 的 MSP（重要！）
SCB->VTOR = APP_BASE;          // 切换向量表
DSB();
ISB();
((void (*)(void))app_entry)(); // 跳转到 APP Reset_Handler

// ── 动态向量表（在 SRAM 中运行时修改中断）──

#define VECTOR_TABLE_SRAM 0x20000000
#define VECTOR_TABLE_SIZE (84 * 4)  // STM32F411: 84 个中断 × 4 字节

// 1. 将 Flash 向量表复制到 SRAM
memcpy((void*)VECTOR_TABLE_SRAM, (void*)SCB->VTOR, VECTOR_TABLE_SIZE);

// 2. 重定位 VTOR 到 SRAM
SCB->VTOR = VECTOR_TABLE_SRAM;

// 3. 修改 SRAM 中的 ISR 地址
volatile uint32_t *vector_table = (uint32_t*)VECTOR_TABLE_SRAM;
vector_table[USART1_IRQn + 16] = (uint32_t)&my_usart_isr;  // 动态替换
DSB();
ISB();
```

### 向量表结构

```
向量表（从 VTOR 指向的地址开始）:
 偏移    内容                异常编号
 ──────────────────────────────────────
 +0x000  MSP 初始值           —
 +0x004  Reset_Handler        1
 +0x008  NMI_Handler          2
 +0x00C  HardFault_Handler    3
 +0x010  MemManage_Handler    4      (M3+)
 +0x014  BusFault_Handler     5      (M3+)
 +0x018  UsageFault_Handler   6      (M3+)
 +0x01C  —                    7~10   (保留)
 +0x02C  SVCall_Handler       11
 +0x030  DebugMon_Handler     12
 +0x034  —                    13     (保留)
 +0x038  PendSV_Handler       14
 +0x03C  SysTick_Handler      15
 ──────────────────────────────────────
 +0x040  IRQ0_Handler         16     (第一个外设中断)
 +0x044  IRQ1_Handler         17
  ...
 +0x040 + N×4  IRQn           16+N
```

---

## 6. 故障处理

### 故障类型一览

| 故障 | 异常编号 | 触发条件 | 是否可配置 |
|------|---------|---------|-----------|
| **HardFault** | 3 | 其他故障无法处理时升级而来 | N/A (固定) |
| **MemManage** | 4 | MPU 违例、非法访问 | 可配置为 fault 或 NMI |
| **BusFault** | 5 | 总线错误（地址/时序/PRECISERR/IMPREISERR） | 可配置 |
| **UsageFault** | 6 | 未定义指令、非对齐访问、除零 | 需使能相关检测位 |

### HardFault 解码

```c
// HardFault 发生时，首先读取 SCB 中的故障状态寄存器
// CFSR (Configurable Fault Status Register) = SCB->CFSR (0xE000ED28)

uint32_t cfsr = SCB->CFSR;

// CFSR 分解为三个 8 位字段:
uint8_t ufsr = (cfsr >> 16) & 0xFF;  // UsageFault Status
uint8_t bfsr = (cfsr >> 8)  & 0xFF;  // BusFault Status
uint8_t mfsr = cfsr & 0xFF;          // MemManage Status

// ── MemManage Status ──
if (mfsr & (1 << 7)) { /* MMARVALID — MMAR 有效 */ }
if (mfsr & (1 << 4)) { /* MSTKERR — 入栈时 MPU 违例 */ }
if (mfsr & (1 << 3)) { /* MUNSTKERR — 出栈时 MPU 违例 */ }
if (mfsr & (1 << 1)) { /* DACCVIOL — 数据访问 MPU 违例 */ }
if (mfsr & (1 << 0)) { /* IACCVIOL — 指令取指 MPU 违例 */ }

// ── BusFault Status ──
if (bfsr & (1 << 7)) { /* BFARVALID — BFAR 有效 */ }
if (bfsr & (1 << 4)) { /* STKERR — 入栈时总线错误 */ }
if (bfsr & (1 << 3)) { /* UNSTKERR — 出栈时总线错误 */ }
if (bfsr & (1 << 2)) { /* IMPRECISERR — 精确总线错误（可恢复） */ }
if (bfsr & (1 << 1)) { /* PRECISERR — 精确总线错误 */ }
if (bfsr & (1 << 0)) { /* IBUSERR — 指令预取总线错误 */ }

// ── UsageFault Status ──
if (ufsr & (1 << 9)) { /* DIVBYZERO — 除零（需使能 CCR.DIV_0_TRP） */ }
if (ufsr & (1 << 8)) { /* UNALIGNED — 非对齐访问（需使能 CCR.UNALIGN_TRP） */ }
if (ufsr & (1 << 1)) { /* NOCP — 协处理器未使能 */ }
if (ufsr & (1 << 0)) { /* UNDEFINSTR — 未定义指令 */ }

// HFSR (HardFault Status Register) = SCB->HFSR (0xE000ED2C)
uint32_t hfsr = SCB->HFSR;
if (hfsr & (1 << 30)) { /* FORCED — 强制故障（其他故障无法处理 → 升级为 HardFault） */ }
if (hfsr & (1 << 1))  { /* VECTBL — 向量表读取错误 */ }

// BFAR (BusFault Address Register) = SCB->BFAR
// MMAR (MemManage Address Register) = SCB->MMAR
uint32_t fault_addr = SCB->BFAR;  // 或 SCB->MMAR
```

### HardFault 调试流程

```text
HardFault 发生后，调试器 halt:

1. 检查 HFSR.FORCED → 如果是，说明是升级故障
   ├─ 检查 CFSR → 定位具体故障源
   │   ├─ MemManage → 检查 MMAR
   │   ├─ BusFault → 检查 BFAR
   │   └─ UsageFault → 检查 UFSR 位
   └─ 读取当前 PC
       └─ 通过 LR 或栈回溯找到触发指令

2. 读取 EXC_RETURN (LR 的值) 判断异常返回模式:
   0xFFFFFFF1 — 返回到 Handler 模式 (MSP)
   0xFFFFFFF9 — 返回到 Thread 模式 (MSP)
   0xFFFFFFFD — 返回到 Thread 模式 (PSP)

3. 根据 EXC_RETURN 找到对应栈指针
   栈上帧布局: [xPSR, PC, LR, R12, R3, R2, R1, R0]
   → PC 指向触发故障的指令

4. 查看 PC 指向的指令 → 是 LDR/STR → 数据访问异常
                        → BLX/BX → 跳转到非法地址
                        → 未定义指令 → UsageFault
```

### 故障预防与配置

```c
// 使能 UsageFault 检测（默认关闭）
SCB->CCR |= SCB_CCR_DIV_0_TRP;       // 使能除零检测
SCB->CCR |= SCB_CCR_UNALIGN_TRP;     // 使能非对齐访问检测

// 使能 MemManage/BusFault/UsageFault（默认使能，但预防性配置）
SCB->SHCSR |= SCB_SHCSR_MEMFAULTENA;   // 使能 MemManage
SCB->SHCSR |= SCB_SHCSR_BUSFAULTENA;   // 使能 BusFault
SCB->SHCSR |= SCB_SHCSR_USGFAULTENA;   // 使能 UsageFault

// 不可屏蔽的 HardFault 调试方法（当调试器连接不上时）:
// 在 HardFault_Handler 中设置断点或输出特征值:
void HardFault_Handler(void) {
    GPIOA->BSRR = (1 << 5);     // 亮灯
    while(1);                    // 死循环，调试器附着
}
```

---

## 7. 中断延迟分析与优化

> Cortex-M 硬件中断架构提供了咬尾、晚到、抢占等硬件优化机制，
> 但错误的软件配置（优先级分组、临界区选择、ISR 长度）会让这些硬件优化完全失效。
>
> 关联技能：
> - `arm-core-registers` — NVIC/SysTick 寄存器级操作
> - `freertos-module` — FreeRTOS 中断安全 API
> - `embedded-reviewer` — 中断安全代码审查

### 场景

- **中断响应慢了** — GPIO 中断从触发到 ISR 执行花了 200 个周期，需要减到 50
- **系统被中断淹没了** — 高频中断把 CPU 占满，任务级代码跑不动
- **临界区影响了实时性** — 关中断时间太长，其他中断被阻塞
- **FreeRTOS 中断不响应** — configMAX_SYSCALL_INTERRUPT_PRIORITY 配置不当
- **想设计中断优先级方案** — 不知道哪些中断该设高优先级、哪些该共享优先级

### 输入

- MCU 型号（确定 NVIC 优先级位数和中断源数量）
- 每个中断的触发频率和最坏情况处理时间
- 是否使用 RTOS（决定临界区策略和中断安全 API）
- 实时性要求（哪些中断必须在多少 μs 内响应）

### Cortex-M 中断延迟模型

```
外设触发中断
    │
    ▼  ↓ 6-12 周期（硬件压栈：8 个寄存器）
CPU 入栈（R0-R3, R12, LR, PC, xPSR）
    │
    ▼  ↓ 2-3 周期
CPU 查向量表取 ISR 地址
    │
    ▼  ↓ 1-2 周期
取指/译码 → 执行 ISR 第一条指令
    │
    ▼
ISR 执行（软件决定长度 ≈ 手动优化空间最大）
    │
    ▼  ↓ 8-12 周期（出栈 + 恢复）
CPU 恢复现场
```

| 阶段 | 周期数 | 说明 |
|------|--------|------|
| 硬件入栈 | 6-12 | 自动压 8 寄存器，FLASH 等待影响 |
| 查向量表 | 2-3 | 访问 0x00000000+4*IRQn |
| 取指 | 1-2 | 预取缓存命中影响 |
| **软件执行** | **ISR 长度** | **这是优化最有效的部分** |
| 出栈恢复 | 8-12 | 硬件自动恢复 |

### Cortex-M 硬件自动优化

| 机制 | 说明 | 效果 |
|------|------|------|
| **咬尾** Tail-chaining | 中断返回时如果有更高/同级中断挂起，不出栈直接进下一个 ISR | 节省 8-12 出栈+12 入栈 = ~20 周期 |
| **晚到** Late-arrival | 入栈过程中更高优中断到达，CPU 替换向量直接处理高优 ISR | 不增加高优中断延迟 |
| **抢占** Preemption | 高优中断可打断低优中断执行 | 不影响高优响应，低优延迟增加 |
| **惰性压栈** Lazy stacking | FPU 寄存器在第一次使用 FPU 时才压栈 | FPU 任务切换节省 100+ 周期 |

> **关键**：错误的优先级设置会阻止咬尾和晚到机制生效。
> 多个中断使用 **相同抢占优先级** 时，硬件咬尾才能工作。

### 优化步骤

#### Step 1: 测量当前中断延迟

```c
/* 用 DWT 周期计数器测量中断延迟 */
volatile uint32_t irq_entry_time;

void TIM2_IRQHandler(void)
{
    /* ISR 第一行 */
    irq_entry_time = DWT->CYCCNT;  // 测量入口时间
    // ... 处理中断 ...
    TIM2->SR = 0;                   // 清标志
}
```

```bash
# 在 main 中获取触发前的时间戳
DWT->CTRL |= 1;                     // 使能 DWT
uint32_t before = DWT->CYCCNT;
TIM2->SR = 0;
TIM2->DIER |= TIM_DIER_UIE;        // 触发中断

# 延迟 = irq_entry_time - before（周期数）
# 延迟时间 = 周期数 / CPU 频率
```

#### Step 2: 设计优先级分组策略

```c
/* 第一步：确定优先级分组（每个 MCU 不同） */
/* STM32F4: NVIC 4 位抢占优先级 = 16 级 */
/* STM32H7: NVIC 4 位中断优先级（抢占统一，无子优先级） */

/* 推荐分组：按延迟要求分 3-4 级 */
#define PRIO_CRITICAL      0   // 零延迟中断（定时器、PWM 保护）
#define PRIO_HIGH          1   // 高优外设（DMA、关键通信）
#define PRIO_MID           2   // 普通外设（UART、I2C）
#define PRIO_LOW           3   // 可延迟处理（非关键数据采集）

/* FreeRTOS 要求：configMAX_SYSCALL_INTERRUPT_PRIORITY */
/* 优先级 >= 此值的中断可调用 FreeRTOS API */
/* STM32F4 上推荐值 = 5（优先级 0-4 不能调 FreeRTOS API） */
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY    5
```

#### Step 3: 选择合适的临界区类型

```c
/* ========== 三种临界区对比 ========== */

/* 1. PRIMASK（关 ALL 中断）— 最重，副作用最大 */
__disable_irq();
// 只在这里放极短的操作（< 1μs）
__enable_irq();

/* 2. BASEPRI（按优先级屏蔽）— 推荐 */
/* 屏蔽优先级 < 设定值的中断 */
__set_BASEPRI(PRIO_CRITICAL << (8 - NVIC_PRIO_BITS));
// 高优中断（PRIO_CRITICAL）仍可响应
// 低优中断被屏蔽
__set_BASEPRI(0);  // 恢复

/* 3. FreeRTOS 调度器锁 — 最轻，不影响中断 */
taskENTER_CRITICAL();
// 只关任务调度，不关中断
// 适合保护任务间共享数据
taskEXIT_CRITICAL();
```

#### Step 4: 设计零延迟中断

某些中断必须在任何情况下都能响应（如电机 PWM 保护、电源监测）：

```c
/* 零延迟中断 = 中断优先级设最高 + 不被任何临界区屏蔽 */

/* 配置：优先级设 0，BASEPRI 锁不住 */
NVIC_SetPriority(TIM1_BRK_IRQn, 0);

/* ISR 中不能调用任何 FreeRTOS API（不能用 FromISR 版也不行）
 * 不能访问被临界区保护的资源（需要时取原子变量） */

volatile uint32_t g_pwm_fault = 0;

void TIM1_BRK_IRQHandler(void)
{
    /* 直接写寄存器，不走 HAL */
    TIM1->BDTR |= TIM_BDTR_MOE;  // 立即关 PWM 输出
    g_pwm_fault = 1;              // 原子写（32 位对齐自然原子）

    /* 这里不能用 xQueueSendFromISR */
    /* 不能访问可能被互斥锁保护的资源 */
}
```

#### Step 5: 缩短 ISR 执行时间

```c
/* ❌ 错误：ISR 里做太多事 */
void USART1_IRQHandler(void)
{
    uint8_t byte = USART1->DR & 0xFF;
    parse_protocol(byte);          // 协议解析可能耗时 100μs+
    process_command();              // 命令处理可能耗时 1ms+
}

/* ✅ 正确：ISR 只做最少操作，耗时任务交给任务 */
void USART1_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    uint8_t byte = USART1->DR & 0xFF;

    /* ISR 中只放数据到队列 */
    xQueueSendFromISR(xUartQueue, &byte, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}

/* 任务中做耗时处理 */
void vUartProcessTask(void *pvParameters)
{
    uint8_t byte;
    for (;;) {
        xQueueReceive(xUartQueue, &byte, portMAX_DELAY);
        parse_protocol(byte);      // 在任务级处理
    }
}
```

#### Step 6: 合并同优先级中断

```c
/* 多个中断使用相同抢占优先级时，硬件咬尾机制生效 */
/* 不嵌套、不出栈、连续处理 */

NVIC_SetPriority(USART1_IRQn, 2);
NVIC_SetPriority(USART2_IRQn, 2);  // 同优先级
NVIC_SetPriority(TIM2_IRQn, 2);    // 同优先级

/* 当 USART1 ISR 返回时，如果 USART2 和 TIM2 都已挂起：
 * 咬尾 → 不进行出栈/入栈，直接进下一个 ISR
 * 节省约 20 周期 ×（N-1）个中断 */
```

### 延迟优化对照表

| 优化项 | 降低延迟 | 说明 |
|--------|---------|------|
| ISR 只做最少操作 | **几百~几千周期** | 最关键优化 |
| 同优先级中断合并 | ~20 周期/每次咬尾 | 限制优先级层级 |
| 代码放 ITCM/SRAM 执行 | 10-30 周期 | 避免 FLASH 等待周期 |
| 不使用 FPU（ISR 中） | ~100 周期 | 避免惰性压栈 |
| 中断向量放 SRAM | 2-5 周期 | 需启动时复制 VTOR 到 SRAM |
| 使用 RAM 向量表 | 1-3 周期 | 避免 FLASH 读取延迟 |
| 减少临界区长度 | 取决于场景 | 临界区外高优中断可抢占 |
| 提高时钟频率 | 线性降低所有延迟 | 功耗上升 |
| 使能 I-Cache (M7) | 向量和 ISR 指令命中率 >90% | Cache 一致性管理 |
| 用 BASEPRI 替代 PRIMASK | 高优先级中断零延迟 | 需要优先级分组设计 |

### 常见陷阱

| # | 现象 | 根因 | 解决 |
|---|------|------|------|
| 1 | 高优 ISR 延迟达几百周期 | 临界区长时间关中断 | 用 BASEPRI 代替 PRIMASK |
| 2 | FreeRTOS 任务不调度 | ISR 中未调用 portYIELD_FROM_ISR | ISR 末尾加 yield |
| 3 | 中断不触发 | 优先级 > configMAX_SYSCALL_INTERRUPT_PRIORITY | 设优先级为 5+ |
| 4 | 咬尾不生效 | 所有中断抢占优先级都不同 | 同优先级中断合并 |
| 5 | 入栈额外多 100 周期 | FPU 惰性压栈触发 | ISR 不操作 float 变量 |
| 6 | 临界区死锁 | 临界区内调用了阻塞 API | 临界区只做快速操作 |
| 7 | 中断丢失 | 同优先级中断太多，pending 被覆盖 | 增大优先级等级数 |
| 8 | ISR 中 malloc 死机 | malloc 不可重入 | 用静态分配或消息队列 |

### 输出

每次使用后输出：
1. **中断延迟分析** — 当前延迟周期数和主要瓶颈
2. **优先级方案** — 推荐的中断优先级分组表
3. **临界区策略** — 哪种临界区适合当前场景
4. **优化建议** — 可执行的具体优化项清单

---

## 8. 异常编号速查 (STM32F411 示例)

```c
// NVIC IRQ 通道编号（系统异常 1~15，IRQ0=16）

IRQn                编号    VTOR 偏移
────────────────────────────────────────
WWDG_IRQn           0     0x040
PVD_IRQn            1     0x044
TAMP_STAMP_IRQn     2     0x048
RTC_WKUP_IRQn       3     0x04C
FLASH_IRQn          4     0x050
RCC_IRQn            5     0x054
EXTI0_IRQn          6     0x058
EXTI1_IRQn          7     0x05C
EXTI2_IRQn          8     0x060
EXTI3_IRQn          9     0x064
EXTI4_IRQn          10    0x068
DMA1_Stream0_IRQn   11    0x06C
    ...
USART1_IRQn         37    0x0D4
    ...
TIM1_UP_IRQn        41    0x0E8
EXTI15_10_IRQn      40    0x0E4
```

---

## 参考文档

- ARMv7-M Architecture Reference Manual (DDI 0403E) — 异常模型/NVIC/故障
- Cortex-M3/M4/M7 TRM — 中断延迟时序、咬尾/晚到详情
- STM32F4 Reference Manual (RM0090) — EXTI 配置/中断映射
- STM32F1 Reference Manual (RM0008) — EXTI/AFIO 配置差异
- AN4084 — EXTI 使用指南和常见问题
- AN4908 — 中断延迟测量和优化
- FreeRTOS 文档: 中断优先级配置和临界区
