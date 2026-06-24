---
name: watchdog-module
description: STM32 看门狗（IWDG/WWDG）配置、开发与故障排查。涵盖 IWDG 时钟源与分频计算、窗口模式、WWDG 窗口上下限计算、EWI 早唤醒中断、喂狗策略（单任务/多任务/RTOS 集成）、调试冻结（DBGMCU）、复位原因分析、低功耗行为、寄存器级与 HAL/LL 接口。当用户提到看门狗、IWDG、独立看门狗、WWDG、窗口看门狗、喂狗、喂狗复位、硬件复位、复位原因、复位标志、RCC_CSR、调试冻结、DBGMCU、系统死锁自动恢复、硬狗、软狗、任务级看门狗时使用。
version: "1.0.0"
---

# STM32 看门狗开发指南

> 看门狗是嵌入式系统最后一道防线——在软件跑飞或死锁时自动复位系统。
> 与 `arm-interrupt-exception`（NMI/异常架构）互补：本 skill 覆盖 IWDG/WWDG 独有的时钟计算、窗口策略、喂狗设计和故障排查。
> 与 `bootloader-design`（看门狗回滚）互补：本 skill 覆盖看门户外设本身的配置与调试。

## 适用场景

- 配置 IWDG 独立看门狗（LSI/LSE 时钟源、分频、重装载值）
- 配置 WWDG 窗口看门狗（APB 时钟、窗口上下限、EWI 早唤醒中断）
- 设计喂狗策略（主循环喂狗、多任务喂狗、RTOS 任务级看门狗）
- 仿真暂停时冻结看门狗（DBGMCU 寄存器）
- 硬件复位原因分析（RCC_CSR 复位标志读取）
- 看门狗引发的异常复位排查
- 低功耗模式下看门狗行为分析与处理
- Option Bytes 配置 IWDG 硬件模式
- 多种看门狗组合方案（IWDG + WWDG 双保险）

## 必要输入

- MCU 型号（IWDG 时钟源频率因系列而异）
- 目标看门狗类型（IWDG / WWDG / 两者皆用）
- 期望的超时时间范围（IWDG）或窗口时间范围（WWDG）
- 是否需要调试时冻结
- 是否在低功耗模式下运行
- RTOS 方案（如果使用 FreeRTOS，需要给出任务列表）

## 看门狗架构概览

### IWDG vs WWDG 对比

| 特性 | IWDG（独立看门狗） | WWDG（窗口看门狗） |
|------|------------------|------------------|
| 时钟源 | LSI (~32kHz) 或 LSE (32.768kHz) | APB 总线时钟（PCLK） |
| 时钟可靠性 | **独立于主时钟**，LSI 失效时仍有 LSE 后备 | 依赖主时钟，主时钟停摆则 WWDG 失效 |
| 复位条件 | 计数器减到 0（只设下限） | 计数器减到 0x3F，或在窗口上限之前喂狗 |
| 窗口控制 | 可选窗口寄存器（IWDG_WINR） | 必须同时配置上限和下限 |
| 提前警告 | 无（直接复位） | EWI（Early Wakeup Interrupt），提前复位前触发中断 |
| 调试冻结 | DBGMCU_APB1_FZ 或 DBGMCU_APB2_FZ 中的 DBG_IWDG_STOP / DBG_WWDG_STOP | 同左 |
| 低功耗行为 | STOP/STANDBY 模式下继续运行（可选择停止） | STOP/STANDBY 模式下停止（时钟源关闭） |
| 典型用途 | 系统死锁恢复（最可靠） | 窗口时序检查（检测是否提前喂狗—暗示任务执行异常偏快） |

### 选择指南

```
需要主时钟失效后仍能复位? ──Yes──→ IWDG（独立时钟源）
                        │
                        └─No──→ 需要检测任务提前完成? ──Yes──→ WWDG（窗口上限）
                                              │
                                              └─No──→ IWDG（更简单可靠）
```

### 组合策略

| 策略 | IWDG | WWDG | 说明 |
|------|------|------|------|
| 单 IWDG | ✓ | ✗ | 最常用方案，简单可靠 |
| 双保险 | ✓ | ✓ | IWDG 防死锁，WWDG 防任务时序异常 |
| 任务级监控 | ✓（主循环） | ✓（RTOS 监控任务） | IWDG 由主循环喂，WWDG 由高优先级监控任务喂 |

## IWDG 独立看门狗

### 时钟源选择

| 系列 | LSI 典型频率 | LSE 可选 | 备注 |
|------|------------|---------|------|
| STM32F0/F1/F3/F4 | 32 kHz (40kHz 典型) | 否 | LSI 频率因芯片个体差异在 30~60kHz 间波动 |
| STM32F7 | 32 kHz | 否 | 可使用 LSE 作为 RCC_LSICmd 源 |
| STM32G0/G4 | 32 kHz | 是 (IWDG_CLK_LSE) | 可在 CubeMX 中选择 LSE |
| STM32H7 | 32 kHz | 是 | IWDG1 和 IWDG2 独立配置 |
| STM32L0/L4 | 32 kHz | 是 | 低功耗系列推荐 LSE 提高精度 |

**LSI 精度问题**：LSI 频率在不同芯片和温漂下变化可达 ±50%，量产时务必留余量。
**LSE 优势**：32.768kHz 晶振精度通常在 ±20ppm 以内，适合对超时精度有要求的场景。

### IWDG 工作原理

```
IWDG 框图:

LSI ──→ 预分频器 (PR) ──→ 12位递减计数器 (RLR) ──→ 复位输出
          /4/8/16/32/64/128/256     重装载值 0~0xFFF
                                          ↑
                                    键寄存器 (KR)
                                    0x5555=允许访问
                                    0xAAAA=喂狗(重装载)
                                    0xCCCC=启动看门狗
```

**工作流程**：
1. 写入 `IWDG_KR = 0xCCCC` 启动看门狗（启动后不可停止，除非硬件复位）
2. 写入 `IWDG_KR = 0x5555` 允许访问 PR 和 RLR 寄存器
3. 配置 `IWDG_PR`（预分频系数）和 `IWDG_RLR`（重装载值）
4. 写入 `IWDG_KR = 0xAAAA` 重装载计数器（喂狗）
5. 计数器从 RLR 递减到 0 时触发系统复位

### IWDG 超时时间计算

```
tIWDG = (RLR + 1) × 分频系数 / fLSI

分频系数：
  PR=0 → /4     PR=1 → /8     PR=2 → /16    PR=3 → /32
  PR=4 → /64    PR=5 → /128   PR=6 → /256   PR=7 → /256（STM32G0/G4/H7 等）
```

| PR | 分频 | LSI=32kHz 最小超时(RLR=0) | LSI=32kHz 最大超时(RLR=0xFFF) |
|----|------|------------------------|-----------------------------|
| 0  | /4   | 125 μs                 | 512 ms                      |
| 1  | /8   | 250 μs                 | 1.024 s                     |
| 2  | /16  | 500 μs                 | 2.048 s                     |
| 3  | /32  | 1 ms                   | 4.096 s                     |
| 4  | /64  | 2 ms                   | 8.192 s                     |
| 5  | /128 | 4 ms                   | 16.384 s                    |
| 6  | /256 | 8 ms                   | 32.768 s                    |
| 7  | /256 | 8 ms                   | 32.768 s                    |

> **量产余量计算**：按 LSI 最大偏差 +50% 和 -50% 分别计算实际超时范围。
> 例如 PR=6, RLR=0xFFF, LSI=32kHz: 标称 32.768s
>   LSI=48kHz (-50%) 时: 实际 ≈ 21.8s
>   LSI=16kHz (+50%) 时: 实际 ≈ 65.5s

### IWDG 窗口模式（IWDG_WINR）

F0/G0/G4/H7/L0/L4 等较新系列支持窗口模式：

- 配置 `IWDG_WINR` 窗口寄存器
- **喂狗必须在计数器值 < WINR 且 ≥ RLR 时进行**
- 窗口上限 = WINR 对应的时间，窗口下限 = RLR 对应的时间
- **过早喂狗（计数器 > WINR）也会触发复位**

**典型用例**：检测任务是否运行过快（如 while(1) 空转提前喂狗）。

```
时间轴:  0 ←── WINR ──←── RLR ────→ 复位
喂狗窗口:         [  允许喂狗区间  ]
过早喂狗→复位      正常喂狗点     过晚喂狗→复位
```

### IWDG HAL API

```c
// === IWDG 初始化 ===
IWDG_HandleTypeDef hiwdg;
hiwdg.Instance = IWDG;
hiwdg.Init.Prescaler = IWDG_PRESCALER_64;   // 分频 /64
hiwdg.Init.Reload    = 0xFFF;                // 重装载值 4095
// 窗口模式（可选，不带窗口的系列无此字段）：
hiwdg.Init.Window    = 0x800;                // 窗口上限（仅部分系列支持）
HAL_IWDG_Init(&hiwdg);

// === 喂狗（重装载） ===
HAL_IWDG_Refresh(&hiwdg);                    // 对应 KR = 0xAAAA
```

### IWDG 寄存器级操作

```c
// === 启动 IWDG ===
IWDG->KR = 0xCCCC;    // 启动（写入此值即启动，不可撤销）

// === 配置 PR 和 RLR（需先解锁） ===
IWDG->KR = 0x5555;    // 解锁 PR 和 RLR
IWDG->PR = 5;         // PR=5 → /128
IWDG->RLR = 0xFFF;    // 重装载值 4095

// === 喂狗 ===
IWDG->KR = 0xAAAA;

// === 读取状态（等待 PR/RLR 更新完成） ===
while (IWDG->SR & IWDG_SR_PVU) {}    // PR 更新进行中
while (IWDG->SR & IWDG_SR_RVU) {}    // RLR 更新进行中
while (IWDG->SR & IWDG_SR_WVU) {}    // WINR 更新进行中（窗口模式）
```

### IWDG LL API

```c
// F4/G0/G4/H7 等系列可用 LL 接口
LL_IWDG_Enable(IWDG);                      // KR = 0xCCCC
LL_IWDG_ReloadCounter(IWDG);               // 喂狗
LL_IWDG_EnableWriteAccess(IWDG);           // KR = 0x5555
LL_IWDG_SetPrescaler(IWDG, LL_IWDG_PRESCALER_64);
LL_IWDG_SetReloadCounter(IWDG, 0xFFF);
while (LL_IWDG_IsReady(IWDG));              // 等待 PR/RLR 更新完成
```

## WWDG 窗口看门狗

### WWDG 工作原理

```
WWDG 框图:

PCLK ──→ 预分频器 ──→ 7位递减计数器 (CFR[6:0]) ──→ 复位输出 (CNT<0x40)
                             ↑                    ↑
                         喂狗(重载 CFR)     EWI 中断 (CNT=0x40)
```

**WWDG 特点**：
- 7 位递减计数器（T[6:0]），计数值从配置值递减到 0x3F 时复位
- **窗口上限**（W[6:0]）：计数器值大于 W 时喂狗触发复位（不允许在窗口外喂狗）
- **EWI 中断**：计数器到达 0x40 时触发中断，可在复位前执行紧急操作
- 喂狗即重新装载 CFR 寄存器中的计数值

### WWDG 超时时间计算

```
tWWDG = (T[5:0] + 1) × (4096 × 2^WDGTB) / fPCLK

其中：
  T[5:0] = CFR[6:0] - 0x40（实际可用的有效计数位数，不计 0x3F~0x40 复位区）
  WDGTB = 预分频系数 (0=×1, 1=×2, 2=×4, 3=×8)
```

| WDGTB | 分频 | fPCLK=36MHz | fPCLK=54MHz | fPCLK=72MHz |
|-------|------|-------------|-------------|-------------|
| 0     | ×1   | 113.8 μs    | 75.9 μs     | 56.9 μs     |
| 1     | ×2   | 227.6 μs    | 151.7 μs    | 113.8 μs    |
| 2     | ×4   | 455.1 μs    | 303.4 μs    | 227.6 μs    |
| 3     | ×8   | 910.2 μs    | 606.8 μs    | 455.1 μs    |

> 上表为 1 个计数的步长（T[5:0] = 1），最大超时时间 = 步长 × 63（T[5:0] 最大为 0x3F）。

### WWDG 窗口配置

喂狗必须在计数器值 ≤ W[6:0] 且 ≥ 0x40 时进行。

```
计数器值:  0x7F → ... → W+1 → W → ... → 0x40 → 0x3F → ... → 0x00
喂狗:                     [复位] [  允许喂狗区间  ] [复位区]

窗口上限 W 越小 → 喂狗时间窗口越窄 → 时序检查越严格
W = 0x7F → 无窗口限制（等效于无窗口看门狗）
W = 0x5F → 需要在计数器 ≤ 0x5F 后喂狗
```

### WWDG EWI 早唤醒中断

EWI 在计数器到达 0x40 时触发，此时距离复位（0x3F）还有 **一个计数周期**。

**用途**：
- 在复位前保存关键数据到备份寄存器或 Flash
- 记录最后一次喂狗的任务 ID（辅助调试）
- 通知主控进入安全状态

```c
void WWDG_IRQHandler(void)
{
    if (LL_WWDG_IsActiveFlag_EWKUP(WWDG))
    {
        /* 复位前紧急操作：保存数据、记录上下文 */
        backup_regs->last_task_id = current_task_id;
        backup_regs->reset_reason = RESET_REASON_WWDG;

        LL_WWDG_ClearFlag_EWKUP(WWDG);

        /* 注意：不要在这里长时间阻塞！只做最必要的操作 */
    }
}
```

### WWDG HAL API

```c
// === WWDG 初始化 ===
WWDG_HandleTypeDef hwwdg;
hwwdg.Instance = WWDG;
hwwdg.Init.Prescaler = WWDG_PRESCALER_8;      // WDGTB=3, ×8
hwwdg.Init.Window   = 0x5F;                   // 窗口上限
hwwdg.Init.Counter  = 0x7F;                   // 初始计数值
hwwdg.Init.EWIMode  = WWDG_EWI_ENABLE;        // 使能早唤醒中断
HAL_WWDG_Init(&hwwdg);

// === 喂狗（重装载） ===
HAL_WWDG_Refresh(&hwwdg);

// === 中断回调 ===
void HAL_WWDG_EarlyWakeupCallback(WWDG_HandleTypeDef *hwwdg)
{
    /* EWI 中断触发，即将复位 */
}
```

### WWDG 寄存器级操作

```c
// === 配置 WWDG ===
/* CFR: 配置窗口和预分频 */
WWDG->CFR = (0x5F << 9)       // W[6:0]=0x5F, 窗口上限
          | (3 << 7)          // WDGTB[1:0]=3, ×8
          | WWDG_CFR_EWI;     // 使能 EWI 中断

/* CR: 配置计数器并启动 */
WWDG->CR = 0x7F;              // T[6:0]=0x7F, 初始值 + 启动(WDGA=1 自动置位)

// === 喂狗 ===
WWDG->CR = 0x7F;              // 重新写入计数值（自动清除 WDGA? 需确认）

// === 清除 EWI 标志 ===
WWDG->SR = 0x00;              // 写 0 清除 EWI 标志
```

### WWDG LL API

```c
LL_WWDG_Enable(WWDG);                         // 启动
LL_WWDG_SetPrescaler(WWDG, LL_WWDG_PRESCALER_8);
LL_WWDG_SetWindowValue(WWDG, 0x5F);           // 窗口上限
LL_WWDG_SetCounter(WWDG, 0x7F);              // 初始计数值
LL_WWDG_EnableIT_EWKUP(WWDG);                // 使能 EWI 中断
LL_WWDG_RefreshCounter(WWDG);                  // 喂狗
```

### WWDG 与窗口配置速查

```
目标：WWDG 超时时间 = 10ms, fPCLK = 72MHz

1. 选 WDGTB=3 (×8), 每步长 = (4096 × 8) / 72M = 455.1 μs
2. T[5:0] = 10ms / 455.1μs ≈ 21.97 → 取 22
3. CFR[6:0] = 0x40 + 22 = 0x56
4. W (窗口上限) = 需要确定可接受的最早喂狗时间

  若允许在 3ms 后喂狗：W = 0x40 + (10ms - 3ms) / 455.1μs ≈ 0x40 + 15 = 0x4F
```

## 喂狗策略设计

### 原则

1. **不在中断中喂狗**——中断喂狗会掩盖主循环死锁
2. **喂狗点间隔 ≤ 看门狗超时的 1/3**（留余量应对 LSI 漂移）
3. **喂狗后立即检查关键状态**——如果喂狗后立即出现死锁，看门狗依然能恢复

### 策略一：主循环喂狗（裸机最简方案）

```c
void main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_IWDG_Init();          // 初始化 IWDG

    while (1)
    {
        process_sensors();    // 传感器处理
        update_display();     // 显示更新
        check_comm_timeout(); // 通信超时检查

        /* 喂狗：执行到这里说明上述函数未死锁 */
        HAL_IWDG_Refresh(&hiwdg);
    }
}
```

**风险**：如果 `process_sensors()` 中的某个子函数卡死（如在 HAL 状态机中卡住），喂狗无法执行，最终复位。

### 策略二：分段喂狗（检测各模块运行状态）

```c
uint32_t task_steps = 0;

void main(void)
{
    while (1)
    {
        task_steps = 0;

        if (process_sensors() == HAL_OK)  task_steps |= (1 << 0);
        if (update_display() == HAL_OK)   task_steps |= (1 << 1);

        /* 所有分段都完成才喂狗 */
        if (task_steps == 0x03)
        {
            HAL_IWDG_Refresh(&hiwdg);
        }
        else
        {
            /* 某模块异常——不喂狗，让看门狗复位 */
        }
    }
}
```

### 策略三：RTOS 任务级喂狗（推荐）

```c
/* 监控任务：高优先级，周期性喂狗 */
void WatchdogTask(void *argument)
{
    uint32_t wdt_interval_ms = 500;  // IWDG 喂狗间隔

    for (;;)
    {
        /* 检查各任务是否正常运行 */
        if (xTaskGetTickCount() - last_feed_time[APP_TASK] < 2 * wdt_interval_ms)
        {
            HAL_IWDG_Refresh(&hiwdg);
        }
        else
        {
            /* APP_TASK 已超时无反馈——不喂狗，让 IWDG 复位 */
        }
        vTaskDelay(pdMS_TO_TICKS(wdt_interval_ms));
    }
}
```

### 策略四：FreeRTOS 任务状态监控 + IWDG

结合 FreeRTOS 任务通知机制，各任务定期给监控任务发通知：

```c
/* 各任务在关键路径上发送"我还活着"信号 */
void AppTask(void *argument)
{
    for (;;)
    {
        do_work();
        xTaskNotifyGive(WatchdogTaskHandle);
        vTaskDelay(pdMS_TO_TICKS(100));
    }
}

/* 监控任务 */
void WatchdogTask(void *argument)
{
    const TickType_t timeout_ticks = pdMS_TO_TICKS(2000);

    for (;;)
    {
        /* 等待任意一个任务的通知——有超时限制 */
        if (ulTaskNotifyTake(pdTRUE, timeout_ticks) == 0)
        {
            /* 超时——有任务未及时通知，不喂狗 */
            continue;
        }

        /* 确保所有任务都上报后才喂狗 */
        if (all_tasks_reported())
        {
            HAL_IWDG_Refresh(&hiwdg);
        }
    }
}
```

## 调试冻结

### DBGMCU 寄存器

仿真暂停时，看门狗仍在运行——如果不冻结，单步调试时会不断触发复位。

```c
// === HAL 方式（CubeMX 自动生成） ===
__HAL_DBGMCU_FREEZE_IWDG();
__HAL_DBGMCU_FREEZE_WWDG();

// === 寄存器级 ===
// F1 系列：DBGMCU->CR (地址 0xE0042004)
DBGMCU->CR |= DBGMCU_CR_DBG_IWDG_STOP;    // 位 8（F1）
DBGMCU->CR |= DBGMCU_CR_DBG_WWDG_STOP;    // 位 11（F1）

// F4 系列：DBGMCU->APB1_FZ (地址 0xE0042008)
DBGMCU->APB1_FZ |= DBGMCU_APB1_FZ_DBG_IWDG_STOP;  // 位 12
DBGMCU->APB1_FZ |= DBGMCU_APB1_FZ_DBG_WWDG_STOP;  // 位 11

// H7 系列：
DBGMCU->APB1FZ1 |= DBGMCU_APB1FZ1_DBG_IWDG1_STOP;
DBGMCU->APB1FZ2 |= DBGMCU_APB1FZ2_DBG_IWDG2_STOP;
DBGMCU->APB1FZ1 |= DBGMCU_APB1FZ1_DBG_WWDG1_STOP;
DBGMCU->APB1FZ2 |= DBGMCU_APB1FZ2_DBG_WWDG2_STOP;

// === Keil 初始化文件（debug_init.ini） ===
// 在调试器初始化时自动设置：
// SETLANG SCHEME=Syntax
// FUNC void SetupWatchdogFreeze(void) {
//   unsigned long addr;
//   addr = 0xE0042008;
//   _WDWORD(addr, _RDWORD(addr) | 0x1800);  // IWDG(bit12)+WWDG(bit11)
// }
// SetupWatchdogFreeze();
```

### 各系列 DBGMCU 寄存器地址差异

| 系列 | IWDG 冻结位 | WWDG 冻结位 | 寄存器 |
|------|------------|------------|--------|
| F1   | DBG_CR[8] | DBG_CR[11] | DBGMCU->CR |
| F4   | DBG_APB1_FZ[12] | DBG_APB1_FZ[11] | DBGMCU->APB1_FZ |
| F7   | DBG_APB1_FZ[12] | DBG_APB1_FZ[11] | DBGMCU->APB1_FZ |
| G0   | DBG_APB_FZ[12] | DBG_APB_FZ[11] | DBGMCU->APB_FZ |
| G4   | DBG_APB1_FZ[12] | DBG_APB1_FZ[11] | DBGMCU->APB1_FZ |
| H7   | DBG_APB1_FZ1[12] | DBG_APB1_FZ1[11] | DBGMCU->APB1FZ1 |
| L0/L4 | DBG_APB1_FZ[12] | DBG_APB1_FZ[11] | DBGMCU->APB1_FZ |

> **Cortex-M7 (F7/H7) 注意事项**：DBGMCU 位于 D3 域（总线矩阵不同），使用 `__HAL_DBGMCU_FREEZE_IWDG()` 前需要确保 DBGMCU 时钟已使能（RCC->APB3ENR 或 RCC->APB4ENR 因系列而异）。

## 复位原因分析（RCC_CSR）

系统复位后通过读取 RCC_CSR 寄存器判断是否由看门狗触发：

```c
typedef enum {
    RESET_CAUSE_POR_PDR  = 0,
    RESET_CAUSE_PIN_RESET,
    RESET_CAUSE_WDG,       // IWDG 或 WWDG 复位
    RESET_CAUSE_SW_RESET,
    RESET_CAUSE_LPWR_RESET,
    RESET_CAUSE_UNKNOWN
} ResetCause_t;

ResetCause_t GetResetCause(void)
{
    uint32_t csr = RCC->CSR;

    if (csr & RCC_CSR_IWDGRSTF)   return RESET_CAUSE_WDG;    // IWDG 复位
    if (csr & RCC_CSR_WWDGRSTF)   return RESET_CAUSE_WDG;    // WWDG 复位
    if (csr & RCC_CSR_PORRSTF)    return RESET_CAUSE_POR_PDR;
    if (csr & RCC_CSR_PINRSTF)    return RESET_CAUSE_PIN_RESET;
    if (csr & RCC_CSR_SFTRSTF)    return RESET_CAUSE_SW_RESET;
    if (csr & RCC_CSR_LPWRRSTF)   return RESET_CAUSE_LPWR_RESET;

    return RESET_CAUSE_UNKNOWN;
}

/* 注意：需要在复位后尽快读取并清除 CSR，否则下次复位后标志不清除 */
void ClearResetFlags(void)
{
    RCC->CSR |= RCC_CSR_RMVF;    // 写 1 清除所有复位标志
}
```

**调试技巧**：将复位原因写入备份 SRAM 或 RTC 备份寄存器，可在 warm reboot 后追溯：

```c
RTC_HandleTypeDef hrtc;

void RecordResetCause(void)
{
    ResetCause_t cause = GetResetCause();
    HAL_RTCEx_BKUPWrite(&hrtc, RTC_BKP_DR0, (uint32_t)cause);
    ClearResetFlags();
}

void DumpResetCause(void)
{
    uint32_t val = HAL_RTCEx_BKUPRead(&hrtc, RTC_BKP_DR0);
    // 根据 val 打印或上报复位原因
}
```

## 低功耗模式下的看门狗

| 低功耗模式 | IWDG（LSI 运行） | WWDG |
|-----------|-----------------|------|
| Sleep | 正常运行 | 正常运行 |
| Stop | 正常运行（默认）或可选停止 | **停止**（APB 时钟关闭） |
| Standby | **默认停止**，可通过 RCC_CSR 配置继续运行 | **停止** |
| Shutdown (L4/L5) | **停止** | **停止** |

### Stop 模式下 IWDG 继续运行

```c
/* Stop 模式下 IWDG 继续运行需要：在进入 Stop 前确保 IWDG 已启动 */
/* 唤醒后需要尽快喂狗——Stop 模式下 IWDG 仍在递减 */
void EnterStopMode(void)
{
    HAL_IWDG_Refresh(&hiwdg);     // 进入前先喂狗
    HAL_PWR_EnterSTOPMode(PWR_LOWPOWERREGULATOR_ON, PWR_STOPENTRY_WFI);
    /* 唤醒后代码在此继续执行 */

    /* 尽快喂狗——Stop 期间 IWDG 一直在走 */
    HAL_IWDG_Refresh(&hiwdg);

    SystemClock_Config();         // 重新配置时钟
}
```

**Stop 模式下 IWDG 超时规划**：
```
典型 Stop 唤醒周期（如 LPUART/EXTI）： 100ms~1000ms
IWDG 超时时间应设为：唤醒周期 × 2~3（留余量）

例如每 500ms 被 LPUART 唤醒：
IWDG 超时应设为 1500ms 以上（PR=5, RLR=0xFFF, LSI=32kHz ≈ 2048ms）
```

### Standby 模式下 IWDG 运行

```c
/* Standby 模式下 IWDG 继续运行需在 RCC_CSR 中使能 */
RCC->CSR |= RCC_CSR_LSION;         // 确保 LSI 在 Standby 下保持运行
// 某些系列需要额外配置 RCC_CSR_LSISTBYDIS（低功耗禁用 LSI）

/* IWDG 配置保持不变——进入 Standby 前设好 */
HAL_IWDG_Refresh(&hiwdg);
HAL_PWR_EnterSTANDBYMode();

/* Standby 唤醒 = 重新从头执行，IWDG 重新初始化 */
```

## Option Bytes 中的 IWDG 配置

IWDG 可以通过 Option Bytes 配置为**硬件模式**（上电自动启动，无需软件使能）：

| Option Byte | 功能 | 说明 |
|------------|------|------|
| IWDG_SW (default) | 软件模式 | 需 `IWDG->KR = 0xCCCC` 启动 |
| IWDG_HW | 硬件模式 | 上电即自动启动，无法软件停止 |

**硬件模式适用场景**：
- 要求上电即保证看门狗运行的系统（车规、工控等高可靠性场景）
- 防止恶意代码在启动阶段禁用看门狗

**配置方法**（通过 `option-bytes` skill）：

```bash
# 使用 J-Link Commander 设置 Option Bytes
# 参考 option-bytes skill 文档
```

## 常见陷阱与排查

### 陷阱 1：中断中喂狗掩盖主循环死锁

```
喂狗位置:    中断服务函数中喂狗
问题:        主循环死锁，但中断仍正常触发→看门狗被不停喂→系统不复位
后果:        死锁被掩盖，系统无响应但看门狗不会恢复
```

**解决方案**：
- 只在主循环或专用监控任务中喂狗，不允许在 ISR 中直接喂狗
- 如需统计中断触发频率，使用计数器而非喂狗动作

### 陷阱 2：WWDG 窗口模式下过早喂狗复位

```c
// 错误：在任务开始时喂狗（过早）
void AppTaskEntry(void)
{
    HAL_WWDG_Refresh(&hwwdg);    // [!] 如果窗口上限 W 已设，可能触发复位
    do_work();
}

// 正确：在任务结束时、预期的时间窗口内喂狗
void AppTaskEntry(void)
{
    do_work();
    HAL_WWDG_Refresh(&hwwdg);    // ✓ 在预期的时间窗口内
}
```

### 陷阱 3：IWDG 超时余量不足（LSI 频率偏差）

```
设定值: PR=6, RLR=0xFFF → 标称 32.768s
实际 LSI 偏快 (48kHz): 实际超时 ≈ 21.8s     ← 偏差 -33%
实际 LSI 偏慢 (16kHz): 实际超时 ≈ 65.5s     ← 偏差 +100%

如果喂狗周期设为 25s，在 LSI 偏快时会频繁复位！
```

**解决方案**：量产前实测 LSI 分布，取最小值计算超时。喂狗周期 ≤ 最小超时的 1/3。

### 陷阱 4：第一次喂狗时 IWDG 尚未稳定

IWDG 启动后 PR 和 RLR 的更新需要等待几个 LSI 周期：

```c
void MX_IWDG_Init(void)
{
    hiwdg.Instance = IWDG;
    hiwdg.Init.Prescaler = IWDG_PRESCALER_64;
    hiwdg.Init.Reload = 0xFFF;
    HAL_IWDG_Init(&hiwdg);              // 内部等待 PVU/RVU

    /* [!] 这里的第一次喂狗等待是必要的 */
    HAL_Delay(1);                        // 等待至少 1ms 让 IWDG 稳定
    HAL_IWDG_Refresh(&hiwdg);
}
```

### 陷阱 5：WWDG EWI 中断优先级高于其他中断

EWI 充当"即将复位"警告——如果其优先级过高，会抢占关键中断服务：

**建议**：将 EWI 优先级设为最低，使其只在系统空闲时触发警告，而非干扰高优先级实时任务。

```c
HAL_NVIC_SetPriority(WWDG_IRQn, 15, 0);    // 最低抢占优先级
HAL_NVIC_EnableIRQ(WWDG_IRQn);
```

### 陷阱 6：FreeRTOS 中 tickless idle 模式下 IWDG 停止

FreeRTOS 进入 tickless idle 时会进入 WFI/WFE 甚至 Stop 模式：
- 如果 MCU 进入 Stop 且 IWDG 未停止：唤醒后 IWDG 已临近超时
- **解决方案**：在 `configPRE_SLEEP_PROCESSOR` 中先喂狗，或禁用 tickless idle

```c
// FreeRTOSConfig.h
#define configUSE_TICKLESS_IDLE         0    // 方式1：禁用 tickless idle

// 方式2（推荐）：在 tickless hook 中喂狗
void vApplicationSleep(TickType_t xExpectedIdleTime)
{
    HAL_IWDG_Refresh(&hiwdg);             // 入睡前先喂狗
    HAL_PWR_EnterSLEEPMode(PWR_MAINREGULATOR_ON, PWR_SLEEPENTRY_WFI);
}
```

## 边界定义

### 不该激活
- 用户需要的是独立于看门狗的系统复位原因分析 → 使用 `arm-core-registers`（RCC_CSR）
- 用户需要的是系统级死锁恢复方案（而非看门狗配置）→ 使用 `embedded-debugger-framework`
- 用户没有具体的 MCU 型号，纯概念性讨论

### 不该做

- **禁止**在 ISR 中喂狗——这会掩盖主循环死锁
- **禁止**将 WWDG 窗口设得过窄（典型 > 50% 的周期宽度）
- **禁止**在 IWDG 启动配置未完成前喂狗（需等待 PVU/RVU）
- **禁止**在多任务系统中每个任务各自喂狗（需通过监控任务统筹）
- **禁止**IWDG 超时时间 < 喂狗周期 × 2（LSI 温漂余量不足）

## 不该碰

- **不碰** IWDG 启动后的 PR/RLR——写入 `0xCCCC` 启动后需要硬件复位才能改
- **不碰** 在 Standby 唤醒后未重配时钟就喂 WWDG（时钟源未恢复）
- **不碰** 在看门狗复位后不清除 RCC_CSR 标志（下次无法判断复位来源）
- **不碰** LSI 固有频率偏差——量产时每个芯片都可能不同，留足余量

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | IWDG 等价 | WWDG 等价 | 时钟源 |
|------|----------|----------|--------|
| STM32 HAL | `HAL_IWDG_Init(&hiwdg)` | `HAL_WWDG_Init(&hwwdg)` | LSI~32kHz / APB |
| STM32 寄存器 | `IWDG->KR = 0xCCCC` 使能 | `WWDG->CR = WWDG_CR_WDGA` | LSI~32kHz / APB |
| ESP-IDF | `esp_task_wdt_add`(TWDT) | —(无窗口狗) | LAC 时钟 |
| ESP32(硬件) | RTC 模块内建 | 无 | RTC_CLK |
| GD32 | `fwdgt_write_enable` | `wwdg_write_enable` | 同 STM32 |
| Linux | `watchdog` 设备驱动 | 无 | 系统时钟 |

注：ESP32 无硬件 IWDG/WWDG 外设，使用任务看门狗（TWDT）和中断看门狗（IWDT）替代。

## 交接关系
- 下游：`ota-update-system`（升级失败看门狗恢复）
- 同层：`timer-module` / `adc-module`（同为外设配置+调试类 Skill）
- 调试时：`embedded-debugger-framework`（喂狗复位诊断）
- RTOS 配合：`freertos-module`（任务级喂狗 + tickless idle）

## 参考资料

- STM32 Reference Manual: RCC 章节（LSI 频率规格、CSR 寄存器）
- STM32 Reference Manual: IWDG 章节（寄存器描述、时序图）
- STM32 Reference Manual: WWDG 章节（窗口计算、EWI 时序）
- STM32 Reference Manual: DBGMCU 章节（调试冻结配置）
- AN3153: STM32 IWDG application note
- AN5225: STM32 WWDG application note
