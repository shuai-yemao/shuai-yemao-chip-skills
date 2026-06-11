---
name: stm32-spl-development
description: |
  STM32 标准外设库 (SPL) 开发指南。覆盖：
  - SPL 架构与文件系统（conf.h/it.h/外设 .c/.h）
  - SPL vs HAL/LL 全面对比（理念/中断/DMA/时钟）
  - 外设配置速查（RCC/GPIO/USART/SPI/I2C/TIM/ADC/DMA）
  - SPL 中断模型（固定 ISR vs HAL 回调）
  - 常见陷阱（F1 AFIO 时钟/结构体清零顺序/DMA 标志清除/启动文件选型）
  - SPL→HAL/LL 迁移（逐外设对照表 + ST SPL2LL-Converter 工具）
  - 固件维护（F1/F4/F0/L1 版本差异 + AC5/AC6 编译器兼容）
  - 国产 MCU 适配（GD32/AT32/CH32 SPL 兼容性）
  触发词：标准库、SPL、StdPeriph、STM32 标准库、stm32f10x、FWLib、固件库、SPL 移植、SPL 转 HAL、GD32 SPL、AT32 SPL、CH32 标准库、SPL 陷阱、SPL 中断。
version: "1.0.0"
---

# STM32 标准外设库 (SPL) 开发指南

> 与 `stm32-hal-development`（HAL 框架）、`mcu-peripheral-registers`（寄存器级）和 `code-porting`（SPL↔HAL 移植）互补——本 skill 专注 SPL **库架构、外设配置模式、固件维护和国产兼容 MCU 适配**。

## 适用场景

- 维护/开发基于 SPL 的遗留项目
- 理解 SPL 架构与文件组织方式
- SPL 外设配置（RCC/GPIO/USART/SPI/I2C/TIM/ADC/DMA）
- SPL 中断处理与中断向量表管理
- SPL 固件移植（F1↔F4↔F0，不同芯片系列）
- SPL → HAL/LL 代码迁移
- 国产兼容 MCU 的 SPL 适配（GD32/AT32/CH32）
- SPL 常见陷阱排查

## 使用方式与执行步骤

当用到此 skill 时，按以下步骤执行：

| 步骤 | 操作 | 产出 |
|------|------|------|
| 1. 确认上下文 | 确定 STM32 系列、目标外设、操作类型 | 明确的工作范围 |
| 2. 检查 SPL 版本 | 查看 `stm32f10x.h` 中 `__STM32F10X_STDPERIPH_VERSION` | 版本 ≥ 3.6.0 |
| 3. 定位代码模式 | 选对应的外设配置章节（RCC/GPIO/USART/SPI/I2C） | 参考代码模板 |
| 4. 检查陷阱清单 | 对照 #5 常见陷阱，逐条排除 | 避免已知坑 |
| 5. 迁移路径（如需） | SPL→HAL 参考 #6，SPL→LL 用 ST SPL2LL-Converter | 迁移方案 |
| 6. 国产适配（如需） | 参考 #7 查 GD32/AT32/CH32 差异 | 适配方案 |

> 如果只有模糊想法需细化需求 → 先调用 `brainstorming` skill
> 需要完整的开发执行 → 调用 `workflow` 流水线（bsp-bringup / add-peripheral）
> 涉及代码规范审查 → 串联 `coding-standards` + `embedded-reviewer`

## 必要输入

- STM32 系列（F1/F4/F0/L1 — SPL 版本差异较大）
- 目标外设（GPIO/USART/SPI/I2C/TIM/ADC/DMA）
- 操作类型（新开发/维护/迁移到 HAL）

---

## 1. SPL 架构概述

### SPL vs HAL vs LL 对比

| 特性 | SPL | HAL | LL |
|------|-----|-----|----|
| 首次发布 | 2008 (F1) | 2014 (F0/F4) | 2014 (同 HAL) |
| 抽象层级 | 函数封装 | 状态机封装 | 寄存器宏封装 |
| 初始化方式 | struct 配置 → Init | Handle 结构体 → Init | 直接写寄存器 |
| 中断模型 | 固定 ISR 名 + 用户回调 | HAL_XXX_Callback 弱符号 | 裸中断 |
| DMA 管理 | 手动通道配置 | 句柄+状态机自动管理 | 寄存器级 |
| 代码体积 | 小 | 大（状态机 + 超时） | 极小 |
| 实时性 | 高 | 中（超时机制增加延迟） | 最高 |
| 学习曲线 | 简单（直接） | 中（状态机概念） | 陡（寄存器理解） |
| CubeMX 支持 | 不直接 | 原生 | 可选 |
| 适用场景 | 遗留/国产兼容 | 新项目快速开发 | 性能/资源受限 |
| 仍在使用 | F1/GD32/AT32 生态 | STM32 主流 | 性能敏感场景 |

### SPL 文件结构

```
STM32F10x_FWLib/
├── Libraries/
│   ├── CMSIS/
│   │   ├── CoreSupport/        # core_cm3.h (Cortex-M3 内核)
│   │   └── DeviceSupport/
│   │       └── ST/STM32F10x/
│   │           ├── stm32f10x.h            # 外设地址映射 + 寄存器结构体
│   │           ├── stm32f10x_conf.h       # 外设头文件包含配置
│   │           ├── system_stm32f10x.c     # 系统时钟初始化
│   │           └── startup_stm32f10x_xx.s # 启动文件/向量表
│   └── STM32F10x_StdPeriph_Driver/
│       ├── inc/                           # 外设头文件
│       │   ├── stm32f10x_gpio.h
│       │   ├── stm32f10x_usart.h
│       │   ├── stm32f10x_spi.h
│       │   ├── stm32f10x_i2c.h
│       │   ├── stm32f10x_tim.h
│       │   ├── stm32f10x_adc.h
│       │   ├── stm32f10x_dma.h
│       │   ├── stm32f10x_rcc.h
│       │   ├── stm32f10x_exti.h
│       │   ├── stm32f10x_flash.h
│       │   ├── misc.h                      # NVIC/SysTick 等内核配置
│       │   └── ...                         # 其他外设
│       └── src/                            # 外设源文件
│           ├── stm32f10x_gpio.c
│           ├── stm32f10x_usart.c
│           └── ...
├── Project/
│   ├── Template/                          # 空工程模板
│   └── Examples/                          # 各外设示例
└── stm32f10x_it.c / stm32f10x_it.h        # 中断服务函数入口
```

### stm32f10x_conf.h 配置

```c
// stm32f10x_conf.h — 选择需要使用的 SPL 外设模块
// 只包含实际用到的外设头文件，减小编译时间

#include "stm32f10x_gpio.h"     // 如果不用 GPIO 可以注释掉
#include "stm32f10x_rcc.h"
#include "stm32f10x_usart.h"
// #include "stm32f10x_spi.h"  // 未使用
// #include "stm32f10x_i2c.h"
// #include "stm32f10x_tim.h"
#include "stm32f10x_adc.h"
#include "stm32f10x_dma.h"
#include "stm32f10x_exti.h"
#include "stm32f10x_flash.h"
#include "misc.h"               // NVIC/SysTick — 使用 SPL 必须包含！

// 断言配置 — 调试时打开，发布时注释
#ifdef USE_FULL_ASSERT
#define assert_param(expr) ((expr) ? (void)0 : assert_failed(...))
#else
#define assert_param(expr) ((void)0)      // 发布版本：断言为空
#endif
```

### SPL 版本速查

| 系列 | 最新 SPL 版本 | CMSIS 版本 | 内核 | 备注 |
|------|-------------|-----------|------|------|
| F1 | 3.6.1 | CMSIS 2.x | M3 | 最广泛使用，国产兼容 |
| F4 | 1.8.0 | CMSIS 3.x | M4F | 有 DSP 库 |
| F0 | 1.0.0 | CMSIS 3.x | M0 | 简化版，功能较少 |
| L1 | 1.3.0 | CMSIS 3.x | M3 | 低功耗系列 |
| F2 | 1.1.0 | CMSIS 3.x | M3 | 较少见 |

---

## 2. SPL 外设配置模式

### 通用三步走

SPL 所有外设遵循统一的配置模式：

```c
// 1. 定义结构体变量
GPIO_InitTypeDef GPIO_InitStruct;

// 2. 填充结构体成员
GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5;
GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;

// 3. 调用 Init 函数
GPIO_Init(GPIOA, &GPIO_InitStruct);
```

### RCC 时钟配置

```c
// ── SPL 时钟配置：通过 RCC 结构体 + 时钟安全系统 ──

// 1. 配置 HSE/HIS + PLL（F1 示例: SYSCLK=72MHz）
void RCC_Configuration(void) {
    ErrorStatus HSEStartUpStatus;

    // 复位 RCC 配置
    RCC_DeInit();

    // 使能 HSE 外部晶振
    RCC_HSEConfig(RCC_HSE_ON);
    HSEStartUpStatus = RCC_WaitForHSEStartUp();  // 等待稳定

    if (HSEStartUpStatus == SUCCESS) {
        // 配置 Flash 等待周期（72MHz → 2 WS）
        FLASH_SetLatency(FLASH_Latency_2);

        // 使能预取缓冲
        FLASH_PrefetchBufferCmd(FLASH_PrefetchBuffer_Enable);

        // 配置 AHB/APB 预分频
        RCC_HCLKConfig(RCC_SYSCLK_Div1);    // AHB = 72MHz
        RCC_PCLK1Config(RCC_HCLK_Div2);     // APB1 = 36MHz
        RCC_PCLK2Config(RCC_HCLK_Div1);     // APB2 = 72MHz

        // 配置 PLL: HSE 8MHz × 9 = 72MHz
        RCC_PLLConfig(RCC_PLLSource_HSE_Div1, RCC_PLLMul_9);

        // 使能 PLL
        RCC_PLLCmd(ENABLE);
        while (RCC_GetFlagStatus(RCC_FLAG_PLLRDY) == RESET);

        // 切换 SYSCLK 到 PLL
        RCC_SYSCLKConfig(RCC_SYSCLKSource_PLLCLK);
        while (RCC_GetSYSCLKSource() != 0x08);  // 0x08 = PLL
    } else {
        // HSE 失败 → 使用 HSI（8MHz 内部振荡器）
        // 进入安全模式或报警
    }
}
```

### GPIO 配置

```c
// ── SPL GPIO 与 HAL GPIO 对比 ──

// SPL:
GPIO_InitTypeDef GPIO_InitStruct;
GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5 | GPIO_Pin_6;
GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;      // 推挽输出
GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
GPIO_Init(GPIOA, &GPIO_InitStruct);

// HAL:
GPIO_InitTypeDef GPIO_InitStruct;
GPIO_InitStruct.Pin       = GPIO_PIN_5 | GPIO_PIN_6;
GPIO_InitStruct.Mode      = GPIO_MODE_OUTPUT_PP;
GPIO_InitStruct.Pull      = GPIO_NOPULL;
GPIO_InitStruct.Speed     = GPIO_SPEED_FREQ_HIGH;
HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
```

**SPL GPIO Mode 速查**：

| Mode 宏 | 说明 |
|---------|------|
| `GPIO_Mode_AIN` | 模拟输入（ADC 用） |
| `GPIO_Mode_IN_FLOATING` | 浮空输入 |
| `GPIO_Mode_IPD` | 下拉输入（F1，需配合 BSRR） |
| `GPIO_Mode_IPU` | 上拉输入（F1，需配合 BSRR） |
| `GPIO_Mode_Out_OD` | 开漏输出 |
| `GPIO_Mode_Out_PP` | 推挽输出 |
| `GPIO_Mode_AF_OD` | 复用开漏 |
| `GPIO_Mode_AF_PP` | 复用推挽 |

> **F1 注意**：SPL 中 `IPU/IPD` 模式通过组合 MODE=输入 + `GPIOx->BSRR` 写入 ODR 来实现。 `GPIO_Init()` 内部自动处理 BSRR 置位。

### USART 配置

```c
// ── SPL USART ──
USART_InitTypeDef USART_InitStruct;

USART_InitStruct.USART_BaudRate            = 115200;
USART_InitStruct.USART_WordLength          = USART_WordLength_8b;
USART_InitStruct.USART_StopBits            = USART_StopBits_1;
USART_InitStruct.USART_Parity              = USART_Parity_No;
USART_InitStruct.USART_HardwareFlowControl = USART_HardwareFlowControl_None;
USART_InitStruct.USART_Mode                = USART_Mode_Tx | USART_Mode_Rx;
USART_Init(USART1, &USART_InitStruct);

// 使能中断（SPL 方式）
USART_ITConfig(USART1, USART_IT_RXNE, ENABLE);

// ── HAL USART ──
UART_HandleTypeDef huart1;
huart1.Instance        = USART1;
huart1.Init.BaudRate   = 115200;
huart1.Init.WordLength = UART_WORDLENGTH_8B;
huart1.Init.StopBits   = UART_STOPBITS_1;
huart1.Init.Parity     = UART_PARITY_NONE;
huart1.Init.Mode       = UART_MODE_TX_RX;
huart1.Init.HwFlowCtl  = UART_HWCONTROL_NONE;
HAL_UART_Init(&huart1);
// HAL 的使能 NVIC 需要通过 HAL_NVIC_EnableIRQ()
```

### SPI 配置

```c
// ── SPL SPI（主机模式）──
SPI_InitTypeDef SPI_InitStruct;

SPI_InitStruct.SPI_Direction         = SPI_Direction_2Lines_FullDuplex;
SPI_InitStruct.SPI_Mode              = SPI_Mode_Master;
SPI_InitStruct.SPI_DataSize          = SPI_DataSize_8b;
SPI_InitStruct.SPI_CPOL              = SPI_CPOL_Low;   // CPOL=0
SPI_InitStruct.SPI_CPHA              = SPI_CPHA_1Edge; // CPHA=0 (Mode 0)
SPI_InitStruct.SPI_NSS               = SPI_NSS_Soft;   // 软件 NSS
SPI_InitStruct.SPI_BaudRatePrescaler = SPI_BaudRatePrescaler_16;  // 72/16=4.5MHz
SPI_InitStruct.SPI_FirstBit          = SPI_FirstBit_MSB;
SPI_InitStruct.SPI_CRCPolynomial     = 7;              // CRC 多项式
SPI_Init(SPI1, &SPI_InitStruct);
SPI_Cmd(SPI1, ENABLE);

// SPL 发送接收:
uint8_t spi_txrx(uint8_t byte) {
    while (SPI_I2S_GetFlagStatus(SPI1, SPI_I2S_FLAG_TXE) == RESET);
    SPI_I2S_SendData(SPI1, byte);
    while (SPI_I2S_GetFlagStatus(SPI1, SPI_I2S_FLAG_RXNE) == RESET);
    return SPI_I2S_ReceiveData(SPI1);
}

// ── HAL SPI ──
// HAL_SPI_TransmitReceive(&hspi1, tx_buf, rx_buf, size, timeout);
// — timeout 机制 SPL 没有，SPL 靠 while 循环等待
```

### I2C 配置

```c
// ── SPL I2C（主机模式）──
I2C_InitTypeDef I2C_InitStruct;

I2C_InitStruct.I2C_Mode              = I2C_Mode_I2C;
I2C_InitStruct.I2C_DutyCycle         = I2C_DutyCycle_2;   // 标准模式
I2C_InitStruct.I2C_OwnAddress1       = 0x00;               // 主机无需地址
I2C_InitStruct.I2C_Ack               = I2C_Ack_Enable;
I2C_InitStruct.I2C_AcknowledgedAddress = I2C_AcknowledgedAddress_7bit;
I2C_InitStruct.I2C_ClockSpeed        = 100000;             // 100kHz
I2C_Init(I2C1, &I2C_InitStruct);
I2C_Cmd(I2C1, ENABLE);

// SPL I2C 发送（标准流程）:
void i2c_write_byte(uint8_t dev_addr, uint8_t reg, uint8_t data) {
    while (I2C_GetFlagStatus(I2C1, I2C_FLAG_BUSY));

    I2C_GenerateSTART(I2C1, ENABLE);
    while (!I2C_CheckEvent(I2C1, I2C_EVENT_MASTER_MODE_SELECT));

    I2C_Send7bitAddress(I2C1, dev_addr, I2C_Direction_Transmitter);
    while (!I2C_CheckEvent(I2C1, I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED));

    I2C_SendData(I2C1, reg);
    while (!I2C_CheckEvent(I2C1, I2C_EVENT_MASTER_BYTE_TRANSMITTED));

    I2C_SendData(I2C1, data);
    while (!I2C_CheckEvent(I2C1, I2C_EVENT_MASTER_BYTE_TRANSMITTED));

    I2C_GenerateSTOP(I2C1, ENABLE);
}

// ⚠ SPL I2C 事件检查需要精确的状态序列，顺序不对会卡死
// 推荐: 用超时替代纯 while 等待
// HAL 的 I2C 有状态机 + 超时 + 错误恢复，不易卡死
```

### 定时器 PWM 配置

```c
// ── SPL 定时器 PWM ──
TIM_TimeBaseInitTypeDef  TIM_TimeBaseStruct;
TIM_OCInitTypeDef        TIM_OCStruct;

// 时基配置: 72MHz / 72 = 1MHz → 1μs 计数步长
TIM_TimeBaseStruct.TIM_Period        = 999;        // PWM 周期 = 1000μs = 1kHz
TIM_TimeBaseStruct.TIM_Prescaler     = 71;         // (71+1) = 72 分频
TIM_TimeBaseStruct.TIM_ClockDivision = 0;
TIM_TimeBaseStruct.TIM_CounterMode   = TIM_CounterMode_Up;
TIM_TimeBaseInit(TIM2, &TIM_TimeBaseStruct);

// PWM 通道配置: CH1 (PA0)
TIM_OCStruct.TIM_OCMode      = TIM_OCMode_PWM1;
TIM_OCStruct.TIM_Pulse       = 500;            // 50% 占空比
TIM_OCStruct.TIM_OCPolarity  = TIM_OCPolarity_High;
TIM_OCStruct.TIM_OutputState = TIM_OutputState_Enable;
TIM_OC1Init(TIM2, &TIM_OCStruct);
TIM_OC1PreloadConfig(TIM2, TIM_OCPreload_Enable);

TIM_Cmd(TIM2, ENABLE);

// ── HAL PWM ──
// 使用 HAL_TIM_PWM_Init(), HAL_TIM_PWM_ConfigChannel(), HAL_TIM_PWM_Start()
// 状态机更多，但功能和 SPL 一致
```

### ADC 配置

```c
// ── SPL ADC（单次转换）──
ADC_InitTypeDef ADC_InitStruct;

ADC_InitStruct.ADC_Mode               = ADC_Mode_Independent;
ADC_InitStruct.ADC_ScanConvMode        = DISABLE;      // 非扫描
ADC_InitStruct.ADC_ContinuousConvMode  = DISABLE;      // 单次转换
ADC_InitStruct.ADC_ExternalTrigConv    = ADC_ExternalTrigConv_None;  // 软件触发
ADC_InitStruct.ADC_DataAlign           = ADC_DataAlign_Right;
ADC_InitStruct.ADC_NbrOfChannel        = 1;
ADC_Init(ADC1, &ADC_InitStruct);

// 配置通道 + 采样时间
ADC_RegularChannelConfig(ADC1, ADC_Channel_0, 1, ADC_SampleTime_55Cycles5);

// 校准
ADC_Cmd(ADC1, ENABLE);
ADC_ResetCalibration(ADC1);
while (ADC_GetResetCalibrationStatus(ADC1));
ADC_StartCalibration(ADC1);
while (ADC_GetCalibrationStatus(ADC1));

// 读取 ADC
ADC_SoftwareStartConvCmd(ADC1, ENABLE);
while (ADC_GetFlagStatus(ADC1, ADC_FLAG_EOC) == RESET);
uint16_t adc_val = ADC_GetConversionValue(ADC1);
```

---

## 3. 中断处理

### SPL 中断模型

SPL 使用**固定 ISR 名称**（在启动文件中预定义）：

```c
// 启动文件中的向量表（startup_stm32f10x_md.s）:
// DCD USART1_IRQHandler     ; USART1
// DCD USART2_IRQHandler     ; USART2
// ...

// stm32f10x_it.c — 用户必须实现这些固定名称的 ISR：
void USART1_IRQHandler(void) {
    if (USART_GetITStatus(USART1, USART_IT_RXNE) != RESET) {
        uint8_t data = USART_ReceiveData(USART1);
        // 处理收到的字节
        USART_ClearITPendingBit(USART1, USART_IT_RXNE);
    }
    if (USART_GetITStatus(USART1, USART_IT_TXE) != RESET) {
        USART_SendData(USART1, tx_buffer[tx_index++]);
        USART_ClearITPendingBit(USART1, USART_IT_TXE);
    }
}
```

### SPL vs HAL 中断模型对比

| 方面 | SPL | HAL |
|------|-----|-----|
| ISR 入口 | 固定函数名（`USART1_IRQHandler`） | 固定函数名（`USART1_IRQHandler`） |
| 中断处理 | 直接在 ISR 中处理 | ISR 调用 `HAL_UART_IRQHandler()` → 弱符号 Callback |
| 用户代码位置 | `stm32f10x_it.c` | `HAL_XXX_Callback()` 在任意 .c 重写 |
| 多实例处理 | 通过 Instance 判断 | 通过 `huart->Instance` 句柄判断 |
| 中断标志清除 | 手动调用 `XXX_ClearITPendingBit()` | 库内部自动清除 |
| 嵌套支持 | 完全手动 | 通过 `__HAL_LOCK()` 状态机防护 |

### NVIC 配置

```c
// ── SPL NVIC 通过 misc.c 配置 ──

NVIC_InitTypeDef NVIC_InitStruct;

// 设置优先级分组: 2 位抢占 + 2 位子优先级
NVIC_PriorityGroupConfig(NVIC_PriorityGroup_2);

// 配置 USART1 中断
NVIC_InitStruct.NVIC_IRQChannel                   = USART1_IRQn;
NVIC_InitStruct.NVIC_IRQChannelPreemptionPriority = 2;
NVIC_InitStruct.NVIC_IRQChannelSubPriority        = 0;
NVIC_InitStruct.NVIC_IRQChannelCmd                = ENABLE;
NVIC_Init(&NVIC_InitStruct);

// ── SPL vs HAL ──
// SPL: NVIC_PriorityGroupConfig() + NVIC_Init() 封装写法不同
// HAL: HAL_NVIC_SetPriorityGrouping() + HAL_NVIC_SetPriority() + HAL_NVIC_EnableIRQ()

// SPL 的 NVIC_PriorityGroupConfig 宏定义:
// NVIC_PriorityGroup_0 = 0x7 → 0+4
// NVIC_PriorityGroup_1 = 0x6 → 1+3
// NVIC_PriorityGroup_2 = 0x5 → 2+2
// NVIC_PriorityGroup_3 = 0x4 → 3+1
// NVIC_PriorityGroup_4 = 0x3 → 4+0
```

---

## 4. DMA 配置

```c
// ── SPL DMA（F1: DMA1 通道，F4: DMA 流+通道）──

// F1 DMA 使用通道 (Channel) 而非流 (Stream):
// 每个外设的 DMA 请求映射到固定通道
// USART1_TX → DMA1_Channel4, USART1_RX → DMA1_Channel5

DMA_InitTypeDef DMA_InitStruct;

RCC_AHBPeriphClockCmd(RCC_AHBPeriph_DMA1, ENABLE);

DMA_InitStruct.DMA_PeripheralBaseAddr = (uint32_t)&USART1->DR;
DMA_InitStruct.DMA_MemoryBaseAddr     = (uint32_t)tx_buffer;
DMA_InitStruct.DMA_DIR                = DMA_DIR_PeripheralDST;  // 内存→外设
DMA_InitStruct.DMA_BufferSize         = TX_BUFFER_SIZE;
DMA_InitStruct.DMA_PeripheralInc      = DMA_PeripheralInc_Disable;
DMA_InitStruct.DMA_MemoryInc          = DMA_MemoryInc_Enable;
DMA_InitStruct.DMA_PeripheralDataSize = DMA_PeripheralDataSize_Byte;
DMA_InitStruct.DMA_MemoryDataSize     = DMA_MemoryDataSize_Byte;
DMA_InitStruct.DMA_Mode               = DMA_Mode_Normal;     // 正常模式（非循环）
DMA_InitStruct.DMA_Priority           = DMA_Priority_High;
DMA_InitStruct.DMA_M2M                = DMA_M2M_Disable;     // 外设→内存

DMA_Init(DMA1_Channel4, &DMA_InitStruct);

// 使能 DMA 通道
DMA_Cmd(DMA1_Channel4, ENABLE);

// 使能 DMA 传输完成中断
DMA_ITConfig(DMA1_Channel4, DMA_IT_TC, ENABLE);
// USART DMA 发送完成由 DMA 通道的中断通知
// 非 USART 自身的 TXE 中断

// ── SPL F1 DMA 通道映射（部分）──
// DMA1_Channel1: ADC1/SPI3/TIM2_CH3
// DMA1_Channel2: SPI1/USART1_TX/TIM2_CH4
// DMA1_Channel3: SPI1/USART1_RX/TIM3_CH3
// DMA1_Channel4: USART1_TX/SPI2/TIM4_CH1 → 注意与 Channel2 都是 USART1_TX！
//                但 F103 中 USART1_TX 只能用 Channel4
// DMA1_Channel5: USART1_RX/ADC3/TIM4_CH2
// DMA1_Channel6: ADC2/SPI2/TIM1_CH1
// DMA1_Channel7: ADC3/SPI3/TIM1_CH2

// ⚠ F1 注意: 外设到 DMA 的请求映射是固定的！
// 查 Reference Manual 的 DMA 请求映射表确认
```

### SPL DMA vs HAL DMA 差异

| 方面 | SPL (F1) | HAL (F4) | HAL (F7/H7) |
|------|---------|---------|------------|
| DMA 单元 | DMA1 (7 通道) | DMA1/DMA2 (8 流×8 通道) | DMA1/DMA2 (流) + MDMA |
| 地址配置 | 直接填结构体 | 句柄 + 全局 Init | 同 F4 |
| FIFO 控制 | 无 | HAL 状态机内置 | 完整 FIFO 配置 |
| 循环模式 | DMA_Mode_Circular | 句柄.Init.Mode | 同 |
| 双缓冲 | 无原生支持 | DMA_InitStructure.Mode + MemoryBurst | 完善双缓冲 CT |
| 中断处理 | 固定通道 ISR | 流 ISR → HAL_DMA_IRQHandler | 同 |

---

## 5. SPL 常见陷阱

### 陷阱 1: F1 GPIO 上拉/下拉不生效

```c
// F1 的 GPIO 上拉/下拉不是通过 MODE 位配置的！
// 而是通过 ODR 寄存器配合输入模式实现:
// 输入 + ODR=1 → 上拉
// 输入 + ODR=0 → 下拉

// SPL 正确处理:
GPIO_InitTypeDef GPIO_InitStruct;
GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_0;
GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_IPU;     // SPL 内部自动处理 BSRR
// 或手动:
// GPIO_SetBits(GPIOB, GPIO_Pin_0);  // 先写高
// GPIO_InitStruct.GPIO_Mode = GPIO_Mode_IN_FLOATING;
GPIO_Init(GPIOB, &GPIO_InitStruct);

// 如果先 Init 再 SetBits → 不生效（Init 已经覆盖了 ODR）
// 正确顺序: SetBits → Init (SPL 内部按 GPIOMode_IPU/IPD 处理)
```

### 陷阱 2: AFIO 时钟使能（F1 特有）

```c
// F1 的 GPIO 复用功能重映射和 EXTI 配置需要使能 AFIO 时钟
// F4+ 中 AFIO 功能合并到 SYSCFG，但 F1 需要单独使能

// ⚠ 这个非常容易遗漏！
RCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO, ENABLE);

// 使用场景:
// 1. EXTI 配置（SYSCFG_EXTICR 在 F1 属于 AFIO）
GPIO_EXTILineConfig(GPIO_PortSourceGPIOB, GPIO_PinSource5);

// 2. 复用功能重映射（如 USART1 从 PA9/PA10 重映射到 PB6/PB7）
GPIO_PinRemapConfig(GPIO_Remap_USART1, ENABLE);
```

### 陷阱 3: SPL 结构体未初始化完全

```c
// SPL 的 Init 函数内部不会将结构体清零！
// 未赋值的成员保持随机值 → 外设配置错误

// ✅ 正确:
GPIO_InitTypeDef GPIO_InitStruct;
GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5;
GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
GPIO_Init(GPIOA, &GPIO_InitStruct);  // 三成员都已赋值

// ❌ 错误:
GPIO_InitTypeDef GPIO_InitStruct;
GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5;
GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_Out_PP;
// GPIO_Speed 未赋值！→ 随机值 → 可能配置错误速度
GPIO_Init(GPIOA, &GPIO_InitStruct);

// 最佳实践：先清零再赋值
GPIO_InitTypeDef GPIO_InitStruct = {0};  // 清零初始化
// 或 memset(&GPIO_InitStruct, 0, sizeof(GPIO_InitStruct));
```

### 陷阱 4: DMA 中断标志清除顺序（F1）

```c
// F1 DMA 中断处理中，必须在清除通道标志之前读取剩余数据量
// 否则可能丢失传输完成事件

void DMA1_Channel4_IRQHandler(void) {
    // ⚠ 先读取当前剩余数据量
    uint16_t remaining = DMA_GetCurrDataCounter(DMA1_Channel4);

    // ⚠ 再清除中断标志
    DMA_ClearITPendingBit(DMA1_Channel4, DMA_IT_TC4);
    DMA_ClearITPendingBit(DMA1_Channel4, DMA_IT_GL4);

    // 此时使用 remaining 值
    // ...
}
```

### 陷阱 5: 断言在 Release 版中占用代码空间

```c
// SPL 默认每个 Init 函数内部都有 assert_param() 检查
// Release 版本需在 stm32f10x_conf.h 中:
#ifdef USE_FULL_ASSERT
#define assert_param(expr) ...
#else
#define assert_param(expr) ((void)0)   // ← 必须定义，否则链接失败！
#endif

// 如果 USE_FULL_ASSERT 未定义 → assert_param 为空 → 无检查
// 但函数参数仍然会计算（虽然不会被使用）
// 对性能有影响 → Release 中建议注释掉不需要的外设文件
```

---

## 6. SPL 到 HAL 迁移

### 逐外设迁移对照

```c
// ── GPIO ──
// SPL:
GPIO_InitTypeDef gi;
gi.GPIO_Pin = GPIO_Pin_5;
gi.GPIO_Mode = GPIO_Mode_Out_PP;
gi.GPIO_Speed = GPIO_Speed_50MHz;
GPIO_Init(GPIOA, &gi);
GPIO_SetBits(GPIOA, GPIO_Pin_5);

// HAL:
GPIO_InitTypeDef gi;
gi.Pin = GPIO_PIN_5;
gi.Mode = GPIO_MODE_OUTPUT_PP;
gi.Pull = GPIO_NOPULL;
gi.Speed = GPIO_SPEED_FREQ_HIGH;
HAL_GPIO_Init(GPIOA, &gi);
HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);

// ── USART ──
// SPL: USART_Init() → USART_Cmd() → USART_ITConfig()
// HAL: HAL_UART_Init() → HAL_UART_Receive_IT()/HAL_UART_Transmit_DMA()

// ── I2C ──
// SPL: 事件序列 I2C_CheckEvent()
// HAL: HAL_I2C_Master_Transmit() / HAL_I2C_Mem_Write()
// 差异最大！SPL 需要逐事件等待，HAL 封装为完整事务

// ── TIM ──
// SPL: TIM_TimeBaseInit → TIM_OCxInit → TIM_Cmd
// HAL: HAL_TIM_Base_Init → HAL_TIM_PWM_ConfigChannel → HAL_TIM_PWM_Start
// 功能接近，但 HAL 使用 Handle 状态机

// ── ADC ──
// SPL: ADC_SoftwareStartConvCmd → while(EOC) → ADC_GetConversionValue
// HAL: HAL_ADC_Start() → HAL_ADC_PollForConversion() → HAL_ADC_GetValue()
// HAL 增加超时，不易卡死

// ── DMA ──
// SPL: DMA_Init → DMA_Cmd → DMA_ITConfig
// HAL: HAL_DMA_Init() → HAL_DMA_Start_IT()
// HAL 内部处理了中断服务，通过回调通知完成
```

### SPL2LL-Converter 工具

ST 官方提供 `SPL2LL-Converter` 工具，可将 SPL 源码自动迁移到 STM32Cube LL API：

| 项目 | 说明 |
|------|------|
| 下载 | [st.com/spl2ll-converter](https://www.st.com/en/development-tools/spl2ll-converter.html) |
| 原理 | Perl 脚本 + 等价 API 数据库，逐函数替换 |
| 约束 | 源码需遵守 C 编码规范（无别名、函数指针作参数、中断/标志单操作） |
| 支持系列 | F0/F1/F2/F3/F4/L1 — 同一系列内完全迁移，跨系列部分迁移 |
| 使用流程 | 选择源系列→选择目标系列→选择输入路径→选择输出路径→运行 |
| 前置条件 | Perl ≥ 5.24.1（推荐 ActivePerl） |

> ⚠ **建议**：SPL2LL 适合大规模机械化迁移。对于小规模外设，手动逐外设替换更可控（参考下面的对照表）。
> HAL 与 LL 可混合使用：HAL 负责初始化，LL 负责 I/O 操作。

### 迁移步骤
   RCC_Configuration() → SystemClock_Config() via CubeMX
   RCC_APB2PeriphClockCmd() → __HAL_RCC_GPIOA_CLK_ENABLE()

2. 替换 GPIO
   结构体成员名修改 + 增加 Pull 字段
   GPIO_SetBits/ResetBit → HAL_GPIO_WritePin()

3. 替换 USART
   USART_Init() → HAL_UART_Init()
   USART_ITConfig() → HAL_UART_Receive_IT()
   ISR 中 USART_GetITStatus() → 在 HAL_UART_IRQHandler() 的 Callback 中处理

4. 替换定时器
   结构体基本一样，成员名有差异
   TIM_Cmd() → HAL_TIM_Base_Start()

5. 替换 I2C（差异最大）
   事件循环 → 事务化 HAL 函数
   需要重新设计读写函数

6. 替换 NVIC
   NVIC_PriorityGroupConfig() → HAL_NVIC_SetPriorityGrouping()
   NVIC_Init() → HAL_NVIC_SetPriority() + HAL_NVIC_EnableIRQ()
```

### 延时函数替换

```c
// SPL: 基于 SysTick 的精确延时 (不在 SPL 库中，需用户实现)
void Delay(uint32_t ms) {
    // 通常使用 SysTick 递减计数
}

// HAL: HAL_Delay() 基于 HAL_IncTick()
// 但 HAL_Delay() 不能在 ISR 中使用！
// 替代: 在 ISR 中用 DWT 或 TIM 延时

// 如果从 SPL 迁移，建议保留原有延时实现
// 或使用 DWT 周期计数器实现跨平台通用延时
```

---

## 7. 国产兼容 MCU 适配

### GD32 (GigaDevice)

```c
// GD32F103 系列与 STM32F103 高度兼容
// SPL 头文件替换:
// #include "stm32f10x.h" → #include "gd32f10x.h"

// API 兼容性:
// GPIO_SetBits()  → gpio_bit_set()    (参数不同)
// GPIO_Init()     → gpio_init()       (结构体成员不同)
// RCC 配置        → rcu_xxx 系列函数   (完全不同)

// ⚠ GD32 SPL 不是完全二进制兼容！
// 实际上 GD32 有自己的固件库，虽然概念类似但 API 不兼容
// 迁移需要逐函数替换

// 如果要原 STM32 SPL 源码在 GD32 上编译:
// 推荐使用 stm32-to-gd32 转换工具或手动替换库
```

### AT32 (ArteryTek)

```c
// AT32F403A 对标 STM32F405
// 提供 AT32 标准库，风格类似 SPL
// 寄存器地址兼容，但库函数完全不同

// 关键差异:
// AT32 的 GPIO 模式配置使用 PORTx_MUXx 方式
// RCC 配置使用 CRM 外设
// AT32 支持主频更高 (240MHz vs 168MHz)
```

### CH32 (WCH, RISC-V)

```c
// CH32V/F 系列使用 RISC-V 内核
// 外设风格类似 SPL 但使用沁恒提供的标准库
// 中断模型与 ARM 完全不同 (CLIC/PLIC)
// Periph 命名风格类似 SPL:
// GPIO_WriteHigh(), USART_SendData(), TIM2_Init()
```

---

## 8. SPL 固件维护

### 工程结构建议

```
Project/
├── Libraries/
│   ├── CMSIS/                       # CMSIS 核心 (可升级)
│   └── STM32F10x_StdPeriph_Driver/  # SPL 库 (固定版本)
├── User/
│   ├── main.c                       # 主函数
│   ├── stm32f10x_it.c               # 中断处理
│   ├── stm32f10x_conf.h             # 外设配置选择
│   ├── system_stm32f10x.c           # 系统时钟
│   ├── bsp/                         # BSP 板级支持包
│   │   ├── bsp_led.c
│   │   ├── bsp_uart.c
│   │   └── bsp_timer.c
│   └── app/                         # 应用层
│       └── ...
├── startup_stm32f10x_hd.s           # 启动文件
├── Project.uvprojx                  # Keil 工程
└── Makefile                         # (可选) GCC 构建
```

### SPL 版本锁定

```c
// 不建议混合不同版本的 SPL 库文件
// 建议在 README 中记录 SPL 版本和对应芯片

// stm32f10x.h 中的版本标识:
#define __STM32F10X_STDPERIPH_VERSION  0x00030601  // v3.6.1

// 检查版本:
#if (__STM32F10X_STDPERIPH_VERSION < 0x00030600)
    #error "SPL 版本过低！需 v3.6.0+"
#endif
```

### 编译器兼容

```c
// Keil MDK (ARMCC):
//   使用 SPL 的最佳选择，启动文件/链接脚本原生支持
//   注意: ARMCC v6 (AC6) 需处理 __IO 等关键字兼容
//   Keil MDK v5.37+ 默认编译器切换为 AC6 (LLVM/Clang)
//   如需 AC5 (ARMCC 5.06): 先装 v5.36 + 升级保留，或单独下载 AC5 组件
//   SPL 在 AC6 下常见警告: __IO 重定义、匿名字段、函数声明不匹配

// GCC (ARM-NONE-EABI):
//   需要修改启动文件为 GCC 汇编格式
//   链接脚本需自行编写
//   大部分 SPL 源码可直接编译

// IAR:
//   需要 IAR 格式的启动文件
//   SPL 源码通常可直接编译

// 跨编译器关键: __attribute__, 内联汇编, 中断函数声明
// SPL 中使用 __ASM, __INLINE, __STATIC_INLINE 等 CMSIS 兼容宏
```

---

## 边界条件与错误处理

### 不该做的

| ❌ 不要做 | 原因 |
|----------|------|
| 混合不同版本 SPL 库文件 | 结构体成员/宏定义可能不兼容 → 链接失败 |
| 在新系列 MCU（G0/G4/H5/H7/U5/WB）上强用 SPL | ST 已停止 SPL 更新，这些系列无 SPL 支持 |
| 在 AC6 下直接迁移 AC5 的 SPL 工程而不改警告 | AC6 对 `__IO`、匿名字段、函数声明更严格 |
| 忽略启动文件选型（HD vs MD vs XL） | 向量表溢出 → 中断无法触发 |
| 混用 STM32 SPL 和 GD32 SPL 的头文件 | API 签名不同 → 编译通过但运行异常 |
| 在 Release 版中保留 `USE_FULL_ASSERT` | 增加代码体积和运行时开销 |
| 用 `HAL_Delay()` 代替 SPL 延时 | SPL 工程无 HAL_IncTick，SysTick 需自行配置 |

### 常见错误与诊断

| 症状 | 根因 | 排查方向 |
|------|------|---------|
| 编译 OK 烧录后不跑 | 启动文件选型错误 (HD/MD/XL) | 检查 `startup_stm32f10x_xx.s` 匹配 Flash 容量 |
| 外设寄存器写不进 | AFIO 时钟未使能 (F1) | 检查 `RCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO)` |
| 中断不触发 | 启动文件中缺少 ISR 声明（MD 限制 64 中断） | 换 HD/XLD 启动文件 |
| ADC 校准卡死 | 时钟使能后 ADC 校准前缺少足够延迟 | 校准前加 `for(i=0;i<0xFFFF;i++);` |
| DMA 传输不完成 | 中断标志清除顺序错误（先读计数器后清标志） | 参考 #4 DMA 章节 |
| I2C 卡在 BUSY | I2C 事件序列不完整，或总线被从机拉低 | 恢复方法：复位 I2C 外设 + 发 9 个 SCL 脉冲 |
| AC6 下大量 `__IO` 警告 | ARMCC v6 对 `volatile` 宏的兼容差异 | 加 `#pragma diag_suppress` 或换用 CMSIS 5.9+ |
| 串口数据错位 | 结构体 `GPIO_InitTypeDef` 未清零 | 始终 `= {0}` 初始化 |

### 互补技能关系

```
stm32-spl-development (本 skill — SPL 参考手册)
    ↓ 分场景：
    ├─ 想改用 HAL → stm32-hal-development (HAL 框架)
    ├─ 想操作寄存器 → mcu-peripheral-registers (寄存器级)
    ├─ 需要代码审查 → embedded-reviewer (ISR/DMA/并发审查)
    ├─ 需要迁移计划 → code-porting (SPL↔HAL 移植) [动态注册]
    └─ 需要编译烧录 → workflow (build-keil → flash-keil)
```

## 交接关系

- 迁移目标：`stm32-hal-development`（SPL->HAL 升级路径）
- 辅助：`code-porting`（SPL->HAL 移植工具）
- 互补：`mcu-peripheral-registers`（寄存器级操作参考）
- 审查：`embedded-reviewer`（ISR/DMA/并发安全审查）
- 平台：`flash-module`（Flash 分区/等待周期配置）

## 参考文档

- STM32F10x SPL 用户手册 (UM0427)
- STM32F4xx SPL 用户手册 (UM1727)
- STM32F10x Reference Manual (RM0008)
- STM32F4xx Reference Manual (RM0090)
- GD32F10x 用户手册 (GD32 官网)
- AT32F403A 标准库文档 (ArteryTek)
- 正点原子/野火 SPL 教程
