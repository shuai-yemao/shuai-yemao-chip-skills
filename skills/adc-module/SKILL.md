---
name: adc-module
description: STM32 ADC 模数转换器配置、开发与故障排查。涵盖时钟树与转换时序计算、规则组/注入组、过采样、校准（偏移/线性度）、模拟看门狗、双ADC模式、DMA 采集、抗混叠与 PCB 布局。当用户提到 ADC、模数转换、模拟采样、HAL ADC、ADC 校准、ADC DMA、ADC 多通道、ADC 采样率、ADC 时序、ADC 不准确、注入组、规则组、过采样、模拟看门狗时使用。
version: "1.0.0"
---

# STM32 ADC 开发指南

> ADC 是嵌入式系统中连接模拟世界的桥梁。
> 与 stm32-hal-development（HAL 通用参考）互补：本 skill 覆盖 ADC 独有的时钟树、时序计算、
> 多通道扫描、校准、噪声消除等深度知识。

## 适用场景

- 配置 STM32 ADC 进行单通道/多通道采样
- 计算采样率和总转换时间（确定能否满足 Nyquist 要求）
- 多通道扫描（规则组序列编程）
- 注入组抢占式采样（高优先级通道）
- ADC + DMA / 定时器触发（PWM 同步采样）
- 校准精度（偏移校准、线性度校准、温度补偿）
- 模拟看门狗（电压阈值监控）
- 过采样（提高有效分辨率）
- 双 ADC 模式（交织采样提高速率）
- 温度传感器 / VREFINT / VBAT 内部通道
- 采样结果不稳定/偏差大的故障排查

## 必要输入

- MCU 型号（ADC 外设版本差异大：F1 = V1, F4 = V2, G0/G4 = V3, H7 = V3）
- ADC 实例号（ADC1/ADC2/ADC3...）
- 目标通道（如 ADC1_IN1=PA1）
- 目标采样率或转换时间
- 输入信号源阻抗（计算最小采样时间用）
- 分辨率需求（8/10/12/14/16bit）

## ADC 架构基础

### 逐次逼近 (SAR) 架构

STM32 全系列使用 SAR ADC。核心特性：
- **采样电容**：对输入信号采样，然后逐位比较
- **转换时间** = 采样时间 + 逐次逼近时间
- **输入阻抗**：SAR ADC 有等效输入阻抗，信号源阻抗过高会导致采样值不准

### 两种转换组

| 特性 | 规则组 (Regular) | 注入组 (Injected) |
|------|-----------------|-----------------|
| 优先级 | 低（会被注入组打断） | 高（可抢占规则组） |
| 结果寄存器 | `DR`（仅一个，多通道需 DMA 读取） | `JDR1~JDR4`（每个通道独立） |
| 触发方式 | 软件/定时器/EXTI | 软件/定时器/EXTI |
| 典型用途 | 常规连续采样（如传感器监测） | 紧急事件捕捉（如过流保护） |
| 序列长度 | 最多 16 通道 | 最多 4 通道 |

**注入组关键特性**：当注入组触发时，会打断正在进行的规则组转换，完成注入序列后自动恢复规则组。结果存入独立的 `JDRx` 寄存器，不污染规则组数据。

### 通道类型

| 来源 | 示例 | 特点 |
|------|------|------|
| 外部 GPIO | PA0~PA7 / PB0~PB1 等 | ADC_IN0~ADC_IN15 |
| 内部参考电压 | VREFINT | 校准 VREF 用，固定通道（如 ADC_IN17） |
| 温度传感器 | TS_CAL1/TS_CAL2 | 读取芯片温度（如 ADC_IN16） |
| VBAT 监测 | VBAT/3 | 检测电池电压（如 ADC_IN18） |

## 时钟与转换时序

### ADC 时钟树

```
SYSCLK (HSI/HSE/PLL)
  → APBx (AHB Prescaler) → APB 时钟 (通常 50-120MHz)
    → ADC Prescaler (2/4/6/8) → ADC Clock (≤ 14MHz 对大多数系列)
```

**关键约束**：ADC 时钟频率有上限，不同系列不同：

| 系列 | ADC 最大时钟 | 备注 |
|------|------------|------|
| STM32F1 | 14 MHz | 12bit 分辨率 |
| STM32F4 | 36 MHz (max 42MHz 特定) | 12bit 分辨率 |
| STM32G0/G4 | 70 MHz (G4), 35 MHz (G0) | 支持硬件过采样 |
| STM32H7 | 72 MHz (ADC3: 72MHz, ADC1/2: 定比率) | 支持 16bit 分辨率 + 过采样 |
| STM32L0/L4 | 35 MHz | 支持硬件过采样 |

### 总转换时间计算

```
tCONV = tSMP + tSAR

tSMP  = 采样周期数 × tADC_CLK
tSAR  = 分辨率相关（对 12bit = 12.5 周期，对 10bit = 10.5 周期，对 8bit = 8.5 周期）
tADC_CLK = 1 / fADC

示例（F4, APB2=84MHz, ADC prescaler=6, ADC_CLK=14MHz, SMP=3 cycles, 12bit）:
tADC_CLK = 1/14M ≈ 71.4 ns
tSMP = 3 × 71.4 = 214.2 ns
tSAR = 12.5 × 71.4 = 892.5 ns
tCONV = 214.2 + 892.5 = 1106.7 ns
采样率 ≈ 1 / 1.1067μs ≈ 903 kHz
```

**ADC 时钟超过最大限制**最常见的后果：转换结果漂移、非线性、多位跳变。

### 采样时间选择

| 采样周期 | 适用场景 |
|---------|---------|
| 1.5 周期 (最小) | 极低源阻抗 (< 1kΩ)，高速采样 |
| 7.5 周期 | 中等阻抗 (< 10kΩ) |
| 13.5 周期 | 典型传感器 (> 10kΩ) |
| 28.5~239.5 周期 (最大) | 高阻抗源 (> 50kΩ)、噪声环境 |

**最小采样时间准则**：
```
Rsource_max = (tSMP - tSMP_min) / (CADC × ln(2^(N+2)))

其中 CADC ≈ 4~8pF, tSMP_min 为采样开关导通时间
```

简化经验值：
- Rs < 10kΩ：1.5~7.5 周期
- Rs < 50kΩ：13.5~28.5 周期
- Rs > 50kΩ：71.5~239.5 周期

## HAL API 使用指南

### 三种采样模式

| 模式 | Polling | IT | DMA |
|------|---------|----|-----|
| 启动 | `HAL_ADC_Start` | `HAL_ADC_Start_IT` | `HAL_ADC_Start_DMA` |
| 停止 | `HAL_ADC_Stop` | `HAL_ADC_Stop_IT` | `HAL_ADC_Stop_DMA` |
| 等待结果 | `HAL_ADC_PollForConversion` | 中断回调 | DMA 传输完成中断 |
| 读取结果 | `HAL_ADC_GetValue` | 回调中调用 | 从 DMA 缓冲区读 |
| 适用 | 单次、简单查询 | 低频、单通道 | 高频、多通道、连续 |

### 校准 API

```c
/* F4 系列偏移校准 */
HAL_ADCEx_Calibration_Start(&hadc1);

/* G0/G4/H7 偏移+线性度校准 */
HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET_LINEARITY);

/* F3/H7 差分模式校准 */
HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET, ADC_SINGLE_ENDED);
// 或 ADC_DIFFERENTIAL_ENDED
```

**校准是必须的**：未校准的 ADC 可能有 ±2~5 LSB 的偏移误差。每次上电后应执行一次。

### 多通道扫描配置

```c
/* 配置规则组序列：依次采样 CH3, CH7, CH5 */
ADC_ChannelConfTypeDef sConfig = {0};

/* 序列第一项：CH3 */
sConfig.Channel      = ADC_CHANNEL_3;       // PA3
sConfig.Rank         = ADC_REGULAR_RANK_1;  // 序列位置 1
sConfig.SamplingTime = ADC_SAMPLETIME_3CYCLES_5;  // F4 采样时间
HAL_ADC_ConfigChannel(&hadc1, &sConfig);

/* 序列第二项：CH7 */
sConfig.Channel      = ADC_CHANNEL_7;
sConfig.Rank         = ADC_REGULAR_RANK_2;
HAL_ADC_ConfigChannel(&hadc1, &sConfig);

/* 序列第三项：CH5 */
sConfig.Channel      = ADC_CHANNEL_5;
sConfig.Rank         = ADC_REGULAR_RANK_3;
HAL_ADC_ConfigChannel(&hadc1, &sConfig);

/* 启动 DMA 扫描（需开启 Scan+Continuous 模式） */
HAL_ADC_Start_DMA(&hadc1, dma_buf, 3);  // 每次转换 3 个通道
```

### 注入组（高优先级抢占）

```c
static void MX_ADC1_Init(void)
{
    // ... 规则组初始化 ...

    /* 注入组配置：CH1 用作过流检测 */
    ADC_InjectionConfTypeDef sConfigInjected = {0};
    sConfigInjected.InjectedChannel  = ADC_CHANNEL_1;
    sConfigInjected.InjectedRank     = ADC_INJECTED_RANK_1;
    sConfigInjected.InjectedSamplingTime = ADC_SAMPLETIME_3CYCLES_5;
    sConfigInjected.InjectedNbrOfConversion = 1;
    sConfigInjected.InjectedDiscontinuousConvMode = DISABLE;
    sConfigInjected.AutoInjectedConv  = DISABLE;
    sConfigInjected.InjectedOffset    = 0;
    sConfigInjected.InjectedOffsetNumber = ADC_INJECTED_OFFSET_NONE;
    HAL_ADCEx_InjectedConfigChannel(&hadc1, &sConfigInjected);
}

void HAL_ADCEx_InjectedConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    uint32_t val = HAL_ADCEx_InjectedGetValue(&hadc1, ADC_INJECTED_RANK_1);
    // 过流保护处理...
}
```

## 常见陷阱与解决方案

### 1. ADC 值跳动/不稳定

| 可能原因 | 排查方法 | 解决方案 |
|---------|---------|---------|
| ADC 时钟超限 | 检查 `ADC->CCR` 的 PRESC 位 | 确保 fADC ≤ 最大允许值 |
| 采样时间不足 (源阻抗大) | 检查信号源型号、外部电路 | 增大采样周期 (SMP) |
| VREF 噪声 | 万用表量 VREF 引脚纹波 | 增加去耦电容（0.1μF + 1μF）/ 外部基准 |
| 数字噪声耦合 | 采样值随 GPIO 翻转同步跳变 | 增加采样电容 / 降低 GPIO 翻转速率 |
| 未校准 | 刚上电时偏差大 | 执行 `HAL_ADCEx_Calibration_Start` |
| 通道悬空 | 未使用的通道浮空 | 未用通道设为接地或模拟输入+固定电平 |

### 2. 多通道采样数据错位

**现象**：DMA 缓冲区里 CH0 的数据出现在了 CH1 的位置。

**根因**：连续扫描模式下 DMA 缓冲区大小未对齐通道数，或 DMA 触发时机与 ADC 转换完不同步。

**修复**：
```c
// DMA 缓冲区大小 = 通道数 × 采样批次数量
// 确保使用 ADC DMA 传输完成回调（而非半传输回调）处理数据
#define NUM_CHANNELS  3
#define NUM_SAMPLES   10
uint32_t dma_buf[NUM_CHANNELS * NUM_SAMPLES];
HAL_ADC_Start_DMA(&hadc1, dma_buf, NUM_CHANNELS * NUM_SAMPLES);

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    // 此时 dma_buf 中排列方式：
    // [CH0, CH1, CH2, CH0, CH1, CH2, ...]
    // 按 NUM_CHANNELS 的步长提取各通道数据
}
```

### 3. ADC 读数全为 0 或满量程

| 现象 | 可能原因 | 检查点 |
|------|---------|--------|
| 全 0（接近 0） | ADC 未启动，或通道未使能 | `HAL_ADC_Start` 是否调用；GPIO 配置为模拟模式 |
| 全 0 | 引脚未配置为模拟模式 | `GPIO_InitStruct.Mode = GPIO_MODE_ANALOG` |
| 满量程 (4095@12bit) | VREF 未连接或对地短路 | 量 VREF+ 引脚电压 |
| 满量程 | 输入引脚电压确实接近 VREF | 万用表测量引脚 |

### 4. 注入组未触发

**现象**：配置了注入组触发但回调未调用。
**解决**：
- 注入组触发源必须独立于规则组（除非用自动注入 `AutoInjectedConv=ENABLE`）
- 检查 `HAL_ADCEx_InjectedConfigChannel` 中的触发源配置
- 检查注入组是否在序列中使能（`InjectedNbrOfConversion > 0`）

### 5. DMA 半传输和完全传输混淆

**现象**：用 `HAL_ADC_Start_DMA` 循环采样，数据缓冲区被覆盖。

**关键**：DMA 循环模式下，缓冲区写满后从头开始覆盖。必须在一半（HalfCplt）和完全（Cplt）两个时间点取走数据：

```c
#define ADC_BUF_SIZE  256
uint32_t adc_buf[ADC_BUF_SIZE];
volatile uint32_t *buf_ready = NULL;

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
    buf_ready = adc_buf;                       // 前半段就绪
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    buf_ready = adc_buf + ADC_BUF_SIZE / 2;    // 后半段就绪
}
```

## 过采样 (Oversampling)

硬件过采样（G0/G4/H7 支持）以降低采样率为代价提高有效分辨率：

```
ENOB = 实际分辨率 + 0.5 × log2(Oversampling_Ratio)

示例：12bit + 16× 过采样 → ENOB ≈ 12 + 0.5×4 = 14bit
```

```c
/* 在 CubeMX 中使能 Oversampling 或在代码中配置 */
ADC_OversamplingTypeDef sOvs = {0};
sOvs.Ratio       = ADC_OVERSAMPLING_RATIO_16;  // 16 倍过采样
sOvs.RightBitShift = ADC_RIGHTBITSHIFT_4;      // 右移 4 位（等效 2^4=16 归一化）
sOvs.TriggeredMode = ADC_TRIGGEREDMODE_SINGLE_TRIGGER;
HAL_ADCEx_ OversamplingConfig(&hadc1, &sOvs);
```

**风险**：过采样增加转换时间 `16×`，降低有效采样率。适用于低频、高精度场景（如温度、压力）。

## 双 ADC 模式（交织采样）

F4/H7 支持两个 ADC 在同一总线上交织采样，双倍提升采样率：

| 模式 | 描述 | 有效采样率 |
|------|------|-----------|
| 常规同步 | ADC1 和 ADC2 同时采样不同通道 | 2× 单 ADC |
| 交织 | ADC1 和 ADC2 交替采样同一通道 | 2× 单 ADC（等间隔） |

**配置**：在 CubeMX 中 `ADCx → ADC_ETC → Mode = Dual regular simultaneous` 等。

## 平台差异速查

| 系列 | ADC 外设 | 最大时钟 | 过采样 | 校准 | 特色 |
|------|---------|---------|--------|------|------|
| STM32F1 | V1 | 14 MHz | 软件 | 偏移 | 最基础，注入组只支持 1 通道 |
| STM32F3 | V1 增强 | 14 MHz | 软件 | 偏移+线性度 | 差分模式、可编程增益 (PGA) |
| STM32F4 | V2 | 36 MHz | 软件 | 偏移 | 双 ADC、注入组 4 通道 |
| STM32G0 | V3 | 35 MHz | 硬件(16x) | 偏移+线性度 | 硬件过采样 |
| STM32G4 | V3 | 70 MHz | 硬件(1024x) | 偏移+线性度 | 高分辨率(16bit)、过采样、PGA |
| STM32H7 | V3 | 72 MHz | 硬件(1024x) | 偏移+线性度 | 16bit、差分、双 ADC+双 DAC |
| STM32L0 | V2 | 35 MHz | 硬件(16x) | 偏移 | 低功耗 |
| STM32L4 | V3 | 35 MHz | 硬件(1024x) | 偏移+线性度 | 低功耗+高精度 |

## 硬件设计要点

### PCB 布局原则
1. **模拟地 VS 数字地**：模拟部分（VREF、VDDA）单点连接到数字地
2. **VREF 去耦**：VREF+引脚接 0.1μF + 10μF 电容，靠近引脚
3. **VDDA 去耦**：0.1μF + 4.7μF，与 VREF 共用参考地
4. **输入走线**：远离高频数字信号（PWM、SPI SCK）
5. **串联电阻**：输入回路可串联 10~100Ω 限制浪涌电流
6. **外部电容**：ADC 输入并联 1~10nF 电容抑制噪声（但会延长建立时间）

### 输入阻抗匹配
```c
// 根据外部信号源阻抗选择采样时间
// 经验公式：Rs_max ≈ tSMP / (fADC × CADC × ln(2^(N+2)))
// 常用值（fADC=14MHz, 12bit）：
// SMP=1.5cycles → Rs_max ≈ 1kΩ
// SMP=13.5cycles → Rs_max ≈ 12kΩ
// SMP=239.5cycles → Rs_max ≈ 220kΩ
```

## 内部通道详解

| 通道 | F4 映射 | H7 映射 | 用途 |
|------|---------|---------|------|
| VREFINT | ADC_IN17 | ADC_IN19 | 内部参考电压校准 |
| TS (温度) | ADC_IN16 | ADC_IN18 | 芯片温度（TS_CAL1@30°C, TS_CAL2@130°C或110°C） |
| VBAT | ADC_IN18 | ADC_IN17 | V_BAT/3（通过 3:1 分压） |

**温度传感器读取**：
```c
// 温度 = (TS_CAL2 - TS_CAL1) / (110°C - 30°C) × (TS_DATA - TS_CAL1) + 30°C
// 或从系统存储器读取校准值：
uint16_t cal30 = *((uint16_t*)0x1FFF7A2C);   // F4 @30°C
uint16_t cal110 = *((uint16_t*)0x1FFF7A2E);  // F4 @110°C

// 读取当前温度通道值后：
int32_t temperature = (110 - 30) * (int32_t)(ts_data - cal30) / (cal110 - cal30) + 30;
```

## 调试方法

### 寄存器级检查（J-Link halt 时）
```c
// 检查 ADC 状态
uint32_t sr  = ADC1->SR;   // F4: EOC(1), EOS(5), OVR(4), AWD(0)
uint32_t cr1 = ADC1->CR1;
uint32_t cr2 = ADC1->CR2;
uint32_t dr  = ADC1->DR;   // 读此值会清除 EOC 标志！

// 规则组状态
if (sr & ADC_SR_EOC) {
    printf("ADC conversion done, DR = %lu\n", dr);
}

// 注入组状态（F4）
uint32_t jdr1 = ADC1->JDR1;  // 独立读取，不干扰规则组
```

### 测试序列
1. **回读 VREFINT**：读取内部 VREFINT 通道，应在已知值 ±2% 内
2. **对地短路**：ADC 输入接 GND → 读数应接近 0（±1~2 LSB）
3. **对 VREF 短路**：ADC 输入接 VREF → 读数应接近满量程（4095@12bit）
4. **温度传感器**：读 TS 通道，应在合理室温范围

## 边界定义

### 不该激活
- 用户需要的是 DAC 配置（相反方向）→ 数字转模拟
- 用户需要的是定时器/PWM 等通用外设配置 → 使用 `stm32-hal-development`
- 用户需要的是外设驱动（传感器通过 ADC 读取）→ 使用 `peripheral-driver`
- 用户需要的是其他 MCU 平台（ESP32 等）

### 不该做
- **禁止**在 ADC 中断回调中调用阻塞式函数
- **禁止**在多通道 DMA 时使用单通道缓冲区大小
- **禁止**在 ADC 时钟超过最大限制时运行（结果不可靠）
- **禁止**在未校准的情况下依赖绝对精度

### 不该碰
- **不触碰** CubeMX 生成的 ADC 初始化代码
- **不触碰** ADC 中断优先级分组（由 HAL_Init 统一管理）
- **不触碰** 系统存储器中的 TS_CAL 校准值

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | 单次读取 | 连续/DMA | 校准 |
|------|---------|---------|------|
| STM32 HAL | `HAL_ADC_Start`+`HAL_ADC_PollForConversion` | `HAL_ADC_Start_DMA` | `HAL_ADCEx_Calibration_Start` |
| STM32 SPL | `ADC_SoftwareStartConvCmd`+轮询 EOC | `ADC_DMACmd` | `ADC_StartCalibration` |
| STM32 寄存器 | CR2.SWSTART -> SR.EOC -> DR | CR2.DDS + DMA | CR2.CAL |
| ESP-IDF | `adc_oneshot_read` | `adc_continuous_read` | 硬件自动校准 |
| Arduino | `analogRead(pin)` | 无内建 | 无 |

注：ESP32 ADC 线性度不如 STM32，建议多点校准。

## 交接关系
- 同层：`i2c-bus` / `spi-bus`（同为外设配置+调试类 Skill）
- 调试时：`serial-monitor`（输出采样值）

## 参考资料

- [references/adc-calibration-guide.md](references/adc-calibration-guide.md) — 校准方法详解
- [references/adc-timing-config.md](references/adc-timing-config.md) — 时钟树与转换时序计算
