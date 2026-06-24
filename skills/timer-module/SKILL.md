---
name: timer-module
description: STM32 定时器配置、中断、PWM 与输入捕获开发指南。涵盖基本/通用/高级定时器架构、APB 时钟 ×2 规则、PWM 模式1/2 与互补输出/死区、输入捕获（频率/脉宽/滤波器/预分频）、编码器模式、单脉冲模式、主从同步。当用户提到定时器、TIM、PWM、输入捕获、脉宽测量、频率测量、Encoder 编码器、霍尔传感器、互补PWM、死区时间、刹车输入、单脉冲、主从定时器时使用。
version: "1.0.0"
---

# STM32 定时器开发指南

> 定时器是 STM32 功能最丰富的外设——从简单的定时中断到复杂的电机控制。
> 与 stm32-hal-development（HAL API 参考）互补：本 skill 覆盖定时器独有的时钟树 ×2 规则、
> 各种工作模式选型、配置计算和常见陷阱。

## 适用场景

- 定时器中断（周期性调用回调，如 1ms、100μs）
- PWM 输出（电机、LED 调光、舵机）
- 互补 PWM + 死区时间 + 刹车输入（电机驱动、H 桥）
- 输入捕获（测量输入信号频率、占空比、脉宽）
- PWM 输入模式（单通道同时测频率和占空比）
- 编码器接口（正交解码、测速/测位置）
- 霍尔传感器接口（BLDC 换向）
- 单脉冲模式（精确延迟后输出指定宽度脉冲）
- 定时器同步（一个定时器触发另一个）
- 定时器 DMA 突发（多通道 PWM 同时更新）

## 必要输入

- MCU 型号（决定定时器实例和 APB 时钟频率）
- 目标定时器实例（如 TIM2, TIM1）
- 工作模式（base/PWM/IC/encoder/one-pulse）
- 目标频率/周期（如 PWM 1kHz, 定时中断 10ms）
- 输入信号特性（输入捕获用：频率范围、边沿、是否需要滤波）
- 输出负载特性（PWM 用：频率、占空比范围、是否需要互补/死区）

## 定时器架构

### 三类定时器

| 类型 | 实例 | 位宽 | 特性 |
|------|------|------|------|
| **基本** (Basic) | TIM6, TIM7 | 16bit | 仅有定时功能，无外部 IO |
| **通用** (General) | TIM2~5, TIM12~17 | 16/32bit | 定时/PWM/输入捕获/编码器 |
| **高级** (Advanced) | TIM1, TIM8, TIM20 | 16bit | 通用功能 + 互补输出 + 死区 + 刹车 + 霍尔 |

**关键**：TIM2 和 TIM5 是 **32bit**（STM32F4/H7），计数值可达 0~4294967295，低频长周期场景优势巨大。

### 定时器框图（核心路径）
```
时钟源 (CK_INT / ITRx / TIx / ETR)
  → PSC (16bit 预分频器) → CK_CNT (计数器时钟)
    → CNT (16/32bit 计数器) → 比较 / 捕获 / 更新
```

## 时钟树：APB ×2 规则（最常见配置错误）

```
HCLK → APBx Prescaler → APBx 时钟 (TIMx 外设时钟)
                         │
                         如果 APB Prescaler ≠ 1 → TIMx_CLK = APBx × 2
                         如果 APB Prescaler = 1 → TIMx_CLK = APBx
```

**举例（STM32F411, HCLK=100MHz）**：
```
APB1 Prescaler = 2 → APB1 = 50MHz, TIM_CLK(APB1) = 50MHz × 2 = 100MHz
APB2 Prescaler = 1 → APB2 = 100MHz, TIM_CLK(APB2) = 100MHz × 1 = 100MHz
```

**实用结论**：不管 APB 分频多少，TIM_CLK 总是等于 HCLK（100MHz）。但在 F1 上 APB1=36MHz 时 TIM_CLK=72MHz（×2）。

### 各系列 APB 与 TIM 时钟对照

| 系列 | HCLK | APB1 Presc | APB2 Presc | APB1 TIM_CLK | APB2 TIM_CLK |
|------|------|-----------|-----------|-------------|-------------|
| F411 | 100MHz | /2 (50MHz) | /1 (100MHz) | 100MHz (×2) | 100MHz (×1) |
| F103 | 72MHz | /2 (36MHz) | /1 (72MHz) | 72MHz (×2) | 72MHz (×1) |
| H743 | 480MHz | /4 (120MHz) | /4 (120MHz) | 240MHz (×2) | 240MHz (×2) |

**知识点**：TIM_CLK 在 STM32 上乘以 2 的原因是 APB 预分频器为 1 时，TIM 时钟直接来自 APB；预分频不为 1 时，TIM 从 APB 的倍频器获取 2× 频率。

## 定时中断（Basic Timing）

### 配置计算

```c
/* 目标：1ms 定时中断 (TIM3, APB1 TIM_CLK=100MHz) */
// TIM_CLK = 100MHz = 100,000,000 Hz
// 目标频率 = 1000 Hz (1ms)
// 总分频 = 100,000,000 / 1000 = 100,000
// PSC × (ARR + 1) = 100,000

uint16_t prescaler = 100 - 1;      // PSC = 99, 分频 100
uint16_t period    = 1000 - 1;     // ARR = 999, 计数 1000 次
// 最终频率: 100,000,000 / 100 / 1000 = 1000 Hz = 1ms

htim3.Init.Prescaler         = 99;
htim3.Init.Period            = 999;
htim3.Init.CounterMode       = TIM_COUNTERMODE_UP;
htim3.Init.ClockDivision     = TIM_CLOCKDIVISION_DIV1;
HAL_TIM_Base_Init(&htim3);
HAL_TIM_Base_Start_IT(&htim3);   // 启动中断模式
```

**PSC 和 ARR 的整数约束**：
- PSC 是 16bit: 0~65535
- ARR 是 16bit: 0~65535（TIM2/TIM5 是 32bit）
- 选择 PSC 使 ARR 在有效范围内
- PSC 尽量选大值（降低功耗）但保证 ARR 不溢出

### PSC + ARR 选择速查表（TIM_CLK=100MHz）

| 目标周期 | PSC | ARR | PSC 最大值用途 |
|---------|-----|-----|-------------|
| 1μs | 100-1=99 | 1-1=0 | 高频计数 |
| 10μs | 100-1=99 | 10-1=9 | 中等频率 |
| 100μs | 100-1=99 | 100-1=99 | 常规采样 |
| 1ms | 100-1=99 | 1000-1=999 | 主流调度 |
| 10ms | 1000-1=999 | 1000-1=999 | 慢速任务 |
| 100ms | 10000-1=9999 | 1000-1=999 | 超时监测 |
| 1s | 10000-1=9999 | 10000-1=9999 | 秒级定时 |

## PWM 输出

### 模式选择

| 模式 | 说明 | 输出极性 |
|------|------|---------|
| PWM 模式 1 (TIM_OCMODE_PWM1) | CNT < CCR 时有效 | 默认高电平有效 |
| PWM 模式 2 (TIM_OCMODE_PWM2) | CNT > CCR 时有效 | 默认低电平有效 |

**最常用的组合**：Mode 1 + `TIM_OCPOLARITY_HIGH`，调整 CCR 即可改变占空比。

### 基本 PWM 配置

```c
/* 目标：1kHz PWM, 50% 占空比, TIM3_CH1 (PA6) */
// TIM_CLK=100MHz, 预分频 100-1, ARR=1000-1
// PWM 频率 = 100M / 100 / 1000 = 1000Hz = 1kHz

/* 定时器基础配置 */
htim3.Init.Prescaler         = 100 - 1;
htim3.Init.Period            = 1000 - 1;
htim3.Init.CounterMode       = TIM_COUNTERMODE_UP;
HAL_TIM_PWM_Init(&htim3);

/* PWM 通道配置 */
sConfig.OCMode     = TIM_OCMODE_PWM1;
sConfig.Pulse      = 500;                   // 占空比 = 500/1000 = 50%
sConfig.OCPolarity = TIM_OCPOLARITY_HIGH;
sConfig.OCFastMode = TIM_OCFAST_DISABLE;
HAL_TIM_PWM_ConfigChannel(&htim3, &sConfig, TIM_CHANNEL_1);

/* 启动 */
HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);

/* 运行时改占空比 */
__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, new_duty);  // 0~999
```

### 边沿对齐 vs 中心对齐

| 模式 | 计数方向 | 频率 vs ARR | 特性 |
|------|---------|------------|------|
| 边沿对齐 UP | 0→ARR→0→ARR | f = TIM_CLK/(PSC+1)/(ARR+1) | 标准，简单 |
| 边沿对齐 DOWN | ARR→0→ARR→0 | 同上 | 较少用 |
| 中心对齐 1/2/3 | 0→ARR→0 循环 | f = TIM_CLK/(PSC+1)/(ARR+1)/2 | 频率减半，对称波形 |

中心对齐模式下，CCR 在增计数和减计数时各比较一次，适用于需要对称 PWM 的电机控制。

### 运行时改 PWM 频率（更新 ARR）

```c
/* 改频率需要同时考虑 ARR 和 CCR 的重新计算 */
uint32_t new_arr = (tim_clk / (prescaler + 1) / target_freq) - 1;
__HAL_TIM_SET_AUTORELOAD(&htim3, new_arr);
// 占空比百分比基于新 ARR 重新计算
__HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, new_arr * duty_pct / 100);
```

### 高级定时器：互补输出 + 死区 + 刹车

```c
/* TIM1 互补 PWM：CH1 (PA8) + CH1N (PB13) + 刹车输入 (PA12/BKIN) */

/* 互补通道配置 */
sConfig.OCMode       = TIM_OCMODE_PWM1;
sConfig.Pulse        = 500;
sConfig.OCPolarity   = TIM_OCPOLARITY_HIGH;
sConfig.OCNPolarity  = TIM_OCNPOLARITY_HIGH;       // 互补输出极性
sConfig.OCIdleState  = TIM_OCIDLESTATE_RESET;      // MOE=0 时输出状态
sConfig.OCNIdleState = TIM_OCNIDLESTATE_RESET;

/* 死区时间配置 (BDTR 寄存器) */
TIM_BreakDeadTimeConfigTypeDef sBreak = {0};
sBreak.OffStateRunMode  = TIM_OSSR_ENABLE;         // 运行态空闲
sBreak.OffStateIDLEMode = TIM_OSSI_ENABLE;         // 空闲态空闲
sBreak.LockLevel        = TIM_LOCKLEVEL_OFF;
sBreak.DeadTime         = 100;                      // 死区 = 100 × tDTS
sBreak.BreakState       = TIM_BREAK_ENABLE;         // 使能刹车输入
sBreak.BreakPolarity    = TIM_BREAKPOLARITY_HIGH;
sBreak.BreakFilter     = 0;
HAL_TIMEx_ConfigBreakDeadTime(&htim1, &sBreak);
```

**死区时间计算**：
```
tDTS = 1 / TIM_CLK × CKD 分频
     CKD = TIM_CLOCKDIVISION_DIV1 → tDTS = 10ns (100MHz)
     CKD = TIM_CLOCKDIVISION_DIV2 → tDTS = 20ns
     CKD = TIM_CLOCKDIVISION_DIV4 → tDTS = 40ns

DeadTime 寄存器编码（STM32F4/H7）：
  bits[7:0] = DT  → tD = DT × tDTS         (DT<128)
  bits[7:0] = 0x80 + (DT-64)×2 → tD = ...  (DT≥128 扩展模式)
```

## 输入捕获

### 单通道频率测量

```c
/* 测量 TIM2_CH1 (PA0) 输入信号频率 */
// 捕获上升沿，记录两次捕获的计数值差
volatile uint32_t cap1 = 0, cap2 = 0, overflow_count = 0;

void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        cap1 = cap2;
        cap2 = HAL_TIM_ReadCapturedValue(&htim2, TIM_CHANNEL_1);
        // 频率 = TIM_CLK / (PSC+1) / (cap2 - cap1)
        // 注意处理溢出（cap2 < cap1 的情况）
    }
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        overflow_count++;  // 计数器溢出次数
    }
}
```

**频率计算（考虑溢出）**：
```c
// 两次捕获之间的总计数值
uint32_t total_ticks;
if (cap2 >= cap1) {
    total_ticks = cap2 - cap1;
} else {
    total_ticks = (0xFFFFFFFF - cap1 + 1) + cap2;  // 32bit 溢出
}
// 再加溢出次数 × (ARR+1)
total_ticks += overflow_count * (htim2.Init.Period + 1);

float freq = (float)tim_clk / (prescaler + 1) / total_ticks;
```

### PWM 输入模式（单通道同时测频率和占空比）

**原理**：使用两个捕获通道，通道 1 捕获周期（两次上升沿），通道 2 捕获脉宽（上升沿到下降沿）。

```c
/* TIM2 PWM 输入模式：CH1 (PA0) — 同时测频率和占空比 */
// 配置：CH1 上升沿捕获 → 触发 CH2 下降沿捕获

htim2.Init.Prescaler = 0;       // 不分频，最大精度
htim2.Init.Period    = 0xFFFF;  // 16bit，根据需要设

sConfig.ICPolarity  = TIM_ICPOLARITY_RISING;
sConfig.ICSelection = TIM_ICSELECTION_DIRECTTI;   // CH1→TI1
sConfig.ICPrescaler = TIM_ICPSC_DIV1;
sConfig.ICFilter    = 0;                          // 不滤波
HAL_TIM_IC_ConfigChannel(&htim2, &sConfig, TIM_CHANNEL_1);

sConfig.ICPolarity  = TIM_ICPOLARITY_FALLING;
sConfig.ICSelection = TIM_ICSELECTION_INDIRECTTI; // CH2→TI1 的间接映射
HAL_TIM_IC_ConfigChannel(&htim2, &sConfig, TIM_CHANNEL_2);

/* 启动 */
HAL_TIM_IC_Start(&htim2, TIM_CHANNEL_1);  // 启动捕获
HAL_TIM_IC_Start(&htim2, TIM_CHANNEL_2);

/* 回调中读取 */
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    uint32_t period = HAL_TIM_ReadCapturedValue(&htim2, TIM_CHANNEL_1);
    uint32_t duty   = HAL_TIM_ReadCapturedValue(&htim2, TIM_CHANNEL_2);
    // 频率 = TIM_CLK / (PSC+1) / period
    // 占空比 = duty / period × 100%
}
```

### 输入捕获滤波器

| ICF[3:0] | 采样频率 | 采样次数 | 滤波效果 |
|---------|---------|---------|---------|
| 0 | — | — | 不滤波 |
| 1~3 | fDTS | 2/4/8 | 轻度去抖 |
| 4~6 | fDTS/2 | 6/8 | 中等 |
| 7~9 | fDTS/4 | 6/8/12 | 较强 |
| 10~12 | fDTS/8 | 6/8/12 | 最强 |
| 13~15 | fDTS/16 | 5/6/8 | 极限 |

**选择指南**：滤波器的采样频率应远高于信号频率，否则会滤掉有效信号。对于有噪声的 PWM（电机环境），设 ICF=8~12。

### 输入捕获预分频

| ICPSC | 效果 | 适用 |
|-------|------|------|
| /1 | 每边沿都捕获 | 常规频率测量 |
| /2 | 每 2 个边沿捕获一次 | 高速信号（减轻捕获中断负载） |
| /4 | 每 4 个边沿一次 | 超高速 |
| /8 | 每 8 个边沿一次 | 极限高速 |

## 定时器中断优先级

```c
/* 设定时器中断优先级 */
HAL_NVIC_SetPriority(TIM3_IRQn, 5, 0);   // 抢占优先级 5
HAL_NVIC_EnableIRQ(TIM3_IRQn);
```

**FreeRTOS 场景**：
- 如果 ISR 中调用了 FreeRTOS API（`xSemaphoreGiveFromISR` 等），中断优先级必须 ≤ `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY`
- 建议 TIM 中断优先级设为 5~7（不要用 0~3）

## 常见陷阱与解决方案

### 1. APB TIM_CLK ×2 规则被忽略

**现象**：定时器频率只有预期的 1/2。

**根因**：计算时用了 APB 时钟频率（如 50MHz）而不是 TIM_CLK（×2 后 100MHz）。

**修复**：从 CubeMX 生成的 `SystemClock_Config` 中确认 TIM_CLK 值，或直接用 `HAL_RCC_GetPCLK1/2Freq()` 查看。

### 2. PWM 无输出

| 可能原因 | 检查点 |
|---------|--------|
| GPIO 未配置为 AF 模式 | `GPIO_MODE_AF_PP` |
| AF 号错误 | 查数据手册对应引脚 AF 号 |
| 定时器未使能时钟 | `__HAL_RCC_TIMx_CLK_ENABLE()` |
| `HAL_TIM_PWM_Start` 未调用 | 检查启动顺序 |
| 通道和 CCR 未配置 | `__HAL_TIM_SET_COMPARE` 值 > 0 |

### 3. PWM 占空比改了但输出无变化

**根因**：`__HAL_TIM_SET_COMPARE` 写入了影子寄存器，但定时器在预装载使能的情况下等待更新事件才转移。如果 TIM 的 ARPE=1（默认），CCR 也是影子寄存器。

**修复**：
```c
// 方法 1：在更新事件时改（推荐自然等待）
__HAL_TIM_SET_COMPARE(&htim, channel, new_val);

// 方法 2：强制产生软件更新（会同步复位计数器，可能引起抖动）
__HAL_TIM_SET_COMPARE(&htim, channel, new_val);
// 如果 ARPE=0（不使能预装载），CCR 立即生效
```

### 4. 输入捕获值始终为 0

| 可能原因 | 检查点 |
|---------|--------|
| 极性配置反了 | `TIM_ICPOLARITY_RISING` 检查信号实际边沿 |
| 滤波器把信号滤掉了 | 信号快时 ICF 不要太大 |
| GPIO 模式错 | 输入捕获用 `GPIO_MODE_AF_PP`（不是输入模式！） |
| 捕获中断未使能 | `HAL_TIM_IC_Start_IT` 不是 `HAL_TIM_IC_Start` |

### 5. 编码器计数方向反了

**修复**：交换编码器的 A/B 相输入，或在配置中调换 TI1/TI2 映射。

### 6. 高级定时器 MOE 位导致 PWM 输出全关

**现象**：高级定时器（TIM1/8）PWM 无输出，但寄存器配置看起来都正确。

**根因**：高级定时器的输出使能受 `TIMx_BDTR` 的 `MOE`（Main Output Enable）位控制。刹车触发或初始化时 `MOE` 可能为 0。

**修复**：
```c
/* PWM 启动后需要额外使能主输出 */
HAL_TIMEx_PWMN_Start(&htim1, TIM_CHANNEL_1);  // 互补输出（同时使能 MOE）
// 或者手动设 MOE
TIM1->BDTR |= TIM_BDTR_MOE;
```

## 平台差异速查

| 系列 | 32bit TIM | 高级 TIM | 通用 TIM | 备注 |
|------|----------|---------|---------|------|
| STM32F1 | 无 | TIM1,8 | TIM2~5 等 | TIM2 也是 16bit |
| STM32F4 | TIM2,5 | TIM1,8 | TIM3~14 | F411 无 TIM8 |
| STM32G4 | TIM2 | TIM1,8,20 | TIM3~17 | 新增 TIM20，HRTIM |
| STM32H7 | TIM2,5 | TIM1,8 | TIM12~24 | 定时器实例最多，TIM_CLK 高达 240MHz |

## 调试方法

### 寄存器级检查（J-Link halt 时）
```c
// 查看定时器状态
uint32_t cr1 = TIM3->CR1;   // CEN(0), ARPE(7), CMS(5:4), DIR(4)
uint32_t sr  = TIM3->SR;    // UIF(0), CC1IF(1), TIF(10)
uint32_t cnt = TIM3->CNT;   // 当前计数器值
uint32_t psc = TIM3->PSC;   // 预分频器值
uint32_t arr = TIM3->ARR;   // 自动重装载值
uint32_t ccr1 = TIM3->CCR1; // 捕获/比较值

// 检查定时器是否运行
if (cr1 & TIM_CR1_CEN) {
    printf("TIM3 is running, CNT = %lu\n", cnt);
}
```

### 使用 GPIO 输出测量定时器精度
```c
// 在中断回调中 toggle GPIO，用示波器量实际周期
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM3) {
        HAL_GPIO_TogglePin(DEBUG_GPIO_Port, DEBUG_Pin);
    }
}
```

## 边界定义

### 不该激活
- 用户需要的是系统滴答定时器（SysTick）配置 → 使用 `stm32-hal-development` 中的 `HAL_InitTick`
- 用户需要的是看门狗（IWDG/WWDG）配置 → 独立于 TIM 外设
- 用户需要的是 RTC（实时时钟）→ 独立外设
- 用户需要的是其他 MCU 平台

### 不该做
- **禁止**在定时器中断回调中调用阻塞式函数（`HAL_Delay`、`printf` 等）
- **禁止**在 FreeRTOS 任务中直接改定时器寄存器而不考虑 ISR 冲突
- **禁止**高级定时器互补输出时忽略死区配置（会导致 H 桥短路）

### 不该碰
- **不触碰** CubeMX 生成的 TIM 初始化代码
- **不触碰**其他定时器的配置（只关注用户指定的实例）
- **不触碰** NVIC 的优先级分组（由 `HAL_Init()` 统一管理）

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | PWM 输出 | 输入捕获 | 编码器 |
|------|---------|---------|--------|
| STM32 HAL | `HAL_TIM_PWM_Start` | `HAL_TIM_IC_Start` | `HAL_TIM_Encoder_Start` |
| STM32 寄存器 | TIMx->CCR1 + CR1 | TIMx->CCER + 时基 | TIMx->SMCR = SMS=3 |
| STM32 SPL | `TIM_SetCompare1` | `TIM_ICConfig` | `TIM_EncoderInterfaceConfig` |
| ESP-IDF | `ledc_set_duty`(LEDC) | `pcnt_counter_clear`(PCNT) | `pcnt_unit_config`(PCNT) |
| Arduino | `analogWrite(pin, val)` | `pulseIn(pin, HIGH)` | 无内建 |

注：ESP32 无通用定时器 PWM —— 由专用 LEDC 控制器实现。编码器用 PCNT 外设。

## 交接关系
- 同层：`i2c-bus` / `spi-bus` / `adc-module`（同为外设配置+调试类 Skill）
- 调试时：`serial-monitor`（输出捕获值）、`can-debug`（电机控制 CAN 通信）

## 参考资料

- [references/timer-clock-config.md](references/timer-clock-config.md) — APB ×2 规则详解与 PSC/ARR 计算表
- [references/timer-advanced-modes.md](references/timer-advanced-modes.md) — 编码器、霍尔、单脉冲、主从同步、DMA 突发
