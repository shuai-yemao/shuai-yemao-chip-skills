# 编码器、霍尔、单脉冲、主从同步、DMA 突发

## 编码器模式

### 原理

STM32 通用定时器支持直接连接正交编码器（Quadrature Encoder）：

```
A相 → TIMx_CH1 (TI1)
B相 → TIMx_CH2 (TI2)
```

内部逻辑根据 A/B 相位差自动判断方向并增减 CNT。

### 三种计数模式

| 模式 | TI1 计数边沿 | TI2 计数边沿 | 每转脉冲数 (PPR) |
|------|------------|------------|----------------|
| 模式 1 (TI1) | √ | — | 1× PPR |
| 模式 2 (TI2) | — | √ | 1× PPR |
| 模式 3 (TI1+TI2) | √ | √ | **2× PPR** (常见) |

**模式 3 最常用**：A、B 相每个边沿都计数，四个边沿一个完整周期 → 4 倍频解码。对于 1000 PPR 编码器，每转计数值 = 4000。

### 编码器配置

```c
/* TIM3 编码器模式：CH1=PA6(A相), CH2=PA7(B相) */

htim3.Init.Prescaler     = 0;                // 不分频
htim3.Init.Period        = 65535;            // 16bit 最大值
htim3.Init.CounterMode   = TIM_COUNTERMODE_UP; // 编码器模式忽略此字段
HAL_TIM_Encoder_Init(&htim3, &sConfig);

/* 编码器配置 */
TIM_Encoder_InitTypeDef sConfig = {0};
sConfig.EncoderMode  = TIM_ENCODERMODE_TI12;  // 模式 3：TI1+TI2
sConfig.IC1Polarity  = TIM_ICPOLARITY_RISING;
sConfig.IC1Selection = TIM_ICSELECTION_DIRECTTI;
sConfig.IC1Prescaler = TIM_ICPSC_DIV1;
sConfig.IC1Filter    = 0;
sConfig.IC2Polarity  = TIM_ICPOLARITY_RISING;
sConfig.IC2Selection = TIM_ICSELECTION_DIRECTTI;
sConfig.IC2Prescaler = TIM_ICPSC_DIV1;
sConfig.IC2Filter    = 0;

/* 启动 */
HAL_TIM_Encoder_Start(&htim3, TIM_CHANNEL_ALL);

/* 读取计数值 */
int16_t pos = (int16_t)TIM3->CNT;  // 用 int16_t 处理正反转
```

**注意**：
- 编码器模式下 CNT 是**有符号值**（自动增减），读取时强制转为 `int16_t` 或 `int32_t`
- 编码器的最大计数速度受 TIM_CLK 限制：每个边沿需至少 2~4 个 TIM_CLK 周期
- 对高速编码器可设 ICF 滤波器抑制噪声

### 测速

```c
/* 固定时间间隔读取 CNT 差值得速度 */
int16_t last_cnt = 0;
int16_t current_cnt;

void speed_measure_task(void)
{
    current_cnt = (int16_t)TIM3->CNT;       // 当前计数值
    int16_t delta = current_cnt - last_cnt;  // 时间间隔内的脉冲增量
    last_cnt = current_cnt;
    
    // 速度 = delta × (1/PR) × 60 [RPM]
    // PR = 编码器每转脉冲数 × 倍频系数 (模式3=4倍)
    float rpm = (float)delta * 60.0f / (PPR * 4) / interval_seconds;
}
```

## 霍尔传感器模式

### 原理

BLDC 电机的三个霍尔传感器（H1/H2/H3）输出 120° 间隔的 3 位编码，指示转子位置（6 个状态）。STM32 高级定时器可以直接连接霍尔输入：

```
H1 → TIMx_CH1 (TI1)
H2 → TIMx_CH2 (TI2)
H3 → TIMx_CH3 (TI3)
```

**配置**：TIM 设为"异或输入模式"（TI1F_ED = TI1⊕TI2⊕TI3），配合编码器模式判断换向时机。

```c
/* TIM1 霍尔模式配置（高级定时器专有） */
TIM_ HallSensor_InitTypeDef sHallConfig = {0};
sHallConfig.HallSensorMode = TIM_HALLSENSOR_ENABLE;  // TI1⊕TI2⊕TI3
sHallConfig.IC1Polarity    = TIM_ICPOLARITY_RISING;
sHallConfig.IC1Prescaler   = TIM_ICPSC_DIV1;
sHallConfig.IC1Filter      = 0;
HAL_TIMEx_HallSensor_Init(&htim1, &sHallConfig);
```

## 单脉冲模式 (One-Pulse)

### 原理

单脉冲模式：外部触发（如 GPIO 边沿）启动定时器，输出一个指定宽度的脉冲后自动停止。

```
输入触发 ━━┓
           ┃
输出脉冲  ━╋━━━━━━━━━━┓
           ┃          ┃
           ┃ t_delay  ┃ t_pulse
```

### 配置

```c
/* TIM2 单脉冲模式：外部触发(PA0)启动，输出一个脉冲(PA1) */

/* 基础配置 */
htim2.Init.Prescaler     = 100 - 1;   // 计数值决定延迟
htim2.Init.Period        = 1000;      // ARR 决定脉冲宽度
htim2.Init.OnePulseMode  = TIM_OPMODE_SINGLE;   // 单脉冲
HAL_TIM_OnePulse_Init(&htim2, TIM_OPMODE_SINGLE);

/* 触发源：TI1 (PA0) 上升沿 */
sConfig.ICPolarity  = TIM_ICPOLARITY_RISING;
sConfig.ICSelection = TIM_ICSELECTION_DIRECTTI;
sConfig.ICFilter    = 0;
HAL_TIM_IC_ConfigChannel(&htim2, &sConfig, TIM_CHANNEL_1);

/* 输出：OC1 反转 */
sConfigOC.OCMode     = TIM_OCMODE_TOGGLE;
HAL_TIM_OC_ConfigChannel(&htim2, &sConfigOC, TIM_CHANNEL_2);
```

## 主从同步

### 应用场景
- TIM1 更新事件触发 ADC 采样
- TIM2 输出 PWM 控制 TIM3 输入捕获的时序
- 多个定时器级联实现复杂波形

### 配置方式

```c
/* 主定时器 TIM1：PWM 输出，TRGO 送更新事件 */
TIM_MasterConfigTypeDef sMasterConfig = {0};
sMasterConfig.MasterOutputTrigger = TIM_TRGO_UPDATE;  // 更新事件作为 TRGO
sMasterConfig.MasterSlaveMode     = TIM_MASTERSLAVEMODE_ENABLE;
HAL_TIMEx_MasterConfigSynchronization(&htim1, &sMasterConfig);

/* 从定时器 TIM2：使用 ITR0 (内部触发 0 = TIM1) 作为时钟 */
TIM_SlaveConfigTypeDef sSlaveConfig = {0};
sSlaveConfig.SlaveMode      = TIM_SLAVEMODE_EXTERNAL1;  // 外部时钟模式
sSlaveConfig.InputTrigger   = TIM_TS_ITR0;               // ITR0 = TIM1
HAL_TIM_SlaveConfigSynchronization(&htim2, &sSlaveConfig);
```

### 内部触发连接（ITR0~ITR3）

| 定时器 | ITR0 | ITR1 | ITR2 | ITR3 |
|-------|------|------|------|------|
| TIM1 | — | — | — | — |
| TIM2 | TIM1 | TIM8 | TIM3 (F4) | TIM4 (F4) |
| TIM3 | TIM1 | TIM8 | TIM4 (F4) | TIM5 (F4) |
| 具体查参考手册 "TIM internal trigger connection" 表 |

## DMA 突发更新（多通道 PWM 同时更新）

### 应用场景
三相电机控制：同时更新 U/V/W 三相的占空比，防止电机抖动。

### 原理
用 DMA 一次性将多组 CCR 值写入定时器，所有通道在下一个更新事件同步生效。

```c
/* TIM1 三通道 PWM + DMA 突发 */
#define NUM_CHANNELS   3
uint32_t pwm_values[NUM_CHANNELS];

/* DMA 配置：TIM1_UP (更新 DMA) 请求 → 从内存传输 3 个值到 TIM1_CCR1/2/3 */
// CubeMX: TIM1 → DMA Settings → Add → Update
// Direction: Memory to Peripheral
// Data Width: Word (32bit)

/* 更新占空比（三个通道同时更新） */
void update_pwm(uint16_t duty1, uint16_t duty2, uint16_t duty3)
{
    pwm_values[0] = duty1;
    pwm_values[1] = duty2;
    pwm_values[2] = duty3;
    
    // 启动 DMA 传输：TIM1_UP 事件触发
    HAL_DMA_Start(&hdma_tim1_up, (uint32_t)pwm_values,
                  (uint32_t)&TIM1->CCR1, NUM_CHANNELS);
    // TIM1 更新事件 → DMA 传输 3 words → 同步更新 CCR1/2/3
}
```

## 定时器输出比较（非 PWM）

| OC 模式 | 行为 | 用途 |
|---------|------|------|
| 冻结 (TIM_OCMODE_FROZEN) | CCR 无影响 | 调试 |
| 高电平 (TIM_OCMODE_ACTIVE) | CNT=CCR 时输出高 | 精确延时触发 |
| 低电平 (TIM_OCMODE_INACTIVE) | CNT=CCR 时输出低 | 精确复位 |
| 翻转 (TIM_OCMODE_TOGGLE) | CNT=CCR 时翻转 | 信号发生器 |
| 强制高/低 | 忽略比较结果 | 故障强制输出 |

**翻转模式使用场景**：软件生成任意频率的方波。每次比较中断中更新 CCR 为下一个翻转点，可精确控制每个高低电平持续时间（比如模拟 DHT22/1-Wire 时序）。
