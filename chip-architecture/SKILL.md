---
name: chip-architecture
description: |
  MCU 芯片架构与开发方式对比中央参考。覆盖 ARM Cortex-M 全系列（M0/M0+/M3/M4/M7/M33）、
  STM32 各系列（F0/F1/F3/F4/F7/G0/G4/H5/H7/L0/L4/L5/U5/WL/WB）、
  ESP32 系列（ESP32/S2/S3/C3/C6/H2/P4）、国产替代（GD32/AT32/CH32）、
  NXP i.MX RT、Nordic nRF52 的架构差异和开发方式对比。
  提供 HAL/SPL/寄存器/ESP-IDF/Arduino 多种开发方式的等效操作映射表。
  当用户涉及跨平台开发、芯片选型、移植评估、或外设 skill 需要跨平台参考时使用。
  触发词：芯片架构、MCU 选型、Cortex-M、STM32 系列、ESP32 架构、
  GD32 兼容、国产替代、开发方式、HAL vs SPL、寄存器开发、ESP-IDF、
  平台差异、芯片对比、ARM 内核、M0 M3 M4 M7 区别、移植评估、
  外设差异、时钟树对比、GPIO AF 对比。
version: "1.0.0"
---

# MCU 芯片架构与开发方式对比

> 中央参考 skill。本 skill 不作为独立知识库，而是为所有外设技能（uart/i2c/spi/tim/adc/dma 等）提供跨平台差异的依据。
> 当外设 skill 引用「平台差异」时，核心细节在此展开。

## 适用场景

- 需要在不同 MCU 平台间做移植评估
- 需要一个外设在 STM32 HAL / ESP-IDF / 寄存器方式下的等效配置
- 需要比较 Cortex-M0 / M3 / M4 / M7 的外设差异
- 需要了解 GD32 与 STM32 的兼容程度
- 需要为产品做芯片选型

## ARM Cortex-M 内核架构

### 内核家族对比

| 内核 | 架构 | 指令集 | 硬件除法 | FPU | DSP | MPU | Cache | 中断数 | 位带 |
|------|------|--------|---------|-----|-----|-----|-------|--------|------|
| **M0** | ARMv6-M | Thumb/Thumb-2 子集 | 无 | 无 | 无 | 无 | 无 | 32 | 无 |
| **M0+** | ARMv6-M | 同上 | 无 | 无 | 无 | 可选 | 无 | 32 | 无 |
| **M3** | ARMv7-M | Thumb-2 完整 | 有(S/U) | 无 | 可选 | 可选 | 无 | 240 | 有 |
| **M4** | ARMv7E-M | Thumb-2 完整 | 有(S/U) | 单精度 | 有 | 可选 | 无 | 240 | 有 |
| **M7** | ARMv7E-M | Thumb-2 完整 | 有(S/U) | 双精度 | 有 | 有 | I/D-Cache | 240 | 有 |
| **M33** | ARMv8-M | Thumb-2 + TrustZone | 有(S/U) | 单精度 | 有 | 有 | 可选 | 480 | 无 |

### 内核差异对外设开发的影响

| 特性 | 影响范围 |
|------|---------|
| **NVIC 中断数** | M0=32, M3/M4/M7=240 — 中断号在不同系列间不可移植 |
| **位带操作** | M3/M4/M7 支持，M0/M0+/M33 不支持 — GPIO BSRR 替代方案 |
| **DSP/SIMD** | M4/M7/M33 有，M0/M3 无 — 影响音频/FFT/滤波代码移植 |
| **FPU** | M4F=单精度，M7=双精度，M0/M3=软件浮点 — 精度和性能差异巨大 |
| **MPU** | M3/M4=可选，M7/M33=标配 — RTOS 内存保护需要 MPU |
| **Cache** | 仅 M7 有 I/D-Cache — DMA 缓冲区需维护一致性 |
| **异常模型** | M0/M0+ 无 BusFault/UsageFault/MemManage — HardFault 是唯一故障入口 |

### 中断/异常模型差异

```
M0/M0+ (ARMv6-M):
  仅有: Reset, NMI, HardFault, SVCall, PendSV, SysTick + 外部中断
  HardFault 是唯一可配置故障异常(无 CFSR/BFSR/MMFSR/UFSR)
  栈帧仅 8 个字 (无 FPU 帧)

M3/M4 (ARMv7-M):
  有完整异常模型: HardFault + MemManage + BusFault + UsageFault
  CFSR @ 0xE000ED28 可解码异常根因
  M4F 栈帧含 FPU 上下文 (S0-S15 + FPSCR)

M7 (ARMv7E-M):
  继承 M4F 全部特性
  双精度浮点栈帧 (S0-S31 + FPSCR, 双字对齐)

M33 (ARMv8-M):
  TrustZone 安全/非安全两个世界
  SAU/IDAU 安全属性单元配置
  栈帧扩展支持 FPU + 安全状态
```

---

## STM32 系列架构

### 内核 → 系列映射

| 内核 | STM32 系列 | 最大主频 | 典型 Flash | 定位 |
|------|-----------|---------|-----------|------|
| **M0** | STM32F0, G0 | 48-64MHz | 16-256KB | 入门/成本敏感 |
| **M0+** | STM32L0 | 32MHz | 32-192KB | 超低功耗 |
| **M3** | STM32F1, F2, L1 | 72-120MHz | 64-1024KB | 通用/性价比 |
| **M4** | STM32F3, F4, G4, L4, L4+ | 72-180MHz | 64-2048KB | 平衡/DSP/FPU |
| **M33** | STM32L5, U5, H5, WL, WB | 48-250MHz | 256-2048KB | 安全/TrustZone |
| **M7** | STM32F7, H7 | 216-480MHz | 512-2048KB | 高性能/M7+M4双核 |

### 关键架构差异（从外设开发视角）

#### 时钟树
| 特性 | F1(M3) | F4(M4) | H7(M7) |
|------|--------|--------|--------|
| HSI | 8MHz | 16MHz | 64MHz |
| SYSCLK max | 72MHz | 180MHz | 480MHz |
| PLL 结构 | 1路PLL | 2路PLL | 3路PLL+专门PLL48 |
| APB1 max | 36MHz | 45MHz | 120MHz |
| APB2 max | 72MHz | 90MHz | 120MHz |
| USB 48MHz | 无专用 | PLL48CK | PLL3Q |

#### GPIO
| 特性 | F1 | F4/G0/G4 | H7 | G0 |
|------|-----|-----------|-----|-----|
| 复用方式 | AFIO 重映射 | GPIO_AFx (AFRL/AFRH) | 同F4 | 同F4, 更少IO |
| 输出速度 | 2/10/50MHz | Low/Med/High/VeryHigh | 同F4 | 同F4 |
| AFIO 时钟 | 必须使能 | 不需要(SYSCFG) | 不需要 | 不需要 |
| BSRR | 有 | 有 | 有 | 有 |
| 位带 | 支持 | 支持 | 支持 | 不支持(Cortex-M0+) |

#### USART
| 特性 | F1 | F4 | H7 | G0 |
|------|-----|-----|-----|------|
| OVER8 | 无(默认/16) | 可配(/16或/8) | 可配 | 可配 |
| RTO(超时) | 无 | 有 | 有 | 有 |
| FIFO | 无 | 无 | 有(TX/RX 8级) | 无 |
| 自动波特率 | 无 | 有 | 有 | 有 |

#### I2C
| 特性 | F1(v1) | F4/G0/G4(v2) | H7(v2) |
|------|--------|---------------|--------|
| BUSY bug | **有**(硬件bug) | 无 | 无 |
| TIMINGR | 无(CCR配置) | 有 | 有 |
| 时序计算 | `CCR=PCLK/(2*速度)` | 工具生成TIMINGR | 工具生成 |

#### SPI
| 特性 | F1 | F4 | H7 |
|------|-----|-----|-----|
| SPI 实例 | SPI1/2 | SPI1/2/3 | SPI1/2/3/4/5/6 |
| 32位帧 | 无 | 无 | 有 |
| BSY 标志 | 有(CR1 SPE复位) | 有 | 有 |
| TI模式 | 无 | 有 | 有 |

### STM32 开发方式对比

| 维度 | HAL | LL | SPL | 寄存器 |
|------|-----|-----|-----|--------|
| **代码量** | 大 | 中 | 中 | 小 |
| **性能** | 中(状态机开销) | 高 | 高 | 最高 |
| **可移植性(M3/M4/M7)** | 好 | 好 | 差(系列绑定) | 差 |
| **CubeMX 支持** | 完整 | 部分 | 无 | 无 |
| **学习曲线** | 低 | 中 | 中 | 高 |
| **调试友好** | 好(HAL_Delay + ErrorCallback) | 中 | 中 | 差 |
| **推荐场景** | 原型/量产 | 性能敏感 | 遗留项目 | 裸机/学习 |

**选型建议**：
- 新项目 → HAL（开发速度快，CubeMX 生成）
- 量产优化 → LL（比 HAL 小 30-50% 代码量）
- 遗留项目 → SPL（有现成代码）
- 学习/极简 → 寄存器（理解原理）
- M7 项目 → HAL（Cache 维护已封装）

---

## ESP32 系列架构

| 芯片 | 内核 | 架构 | FPU | 无线 | 特色 |
|------|------|------|-----|------|------|
| **ESP32** | Xtensa LX6 双核 | 32-bit | 单精度 | WiFi+BLE | 经典，资料最全 |
| **ESP32-S2** | Xtensa LX7 单核 | 32-bit | 单精度 | WiFi | USB OTG, 低成本 |
| **ESP32-S3** | Xtensa LX7 双核 | 32-bit | 单精度 | WiFi+BLE | AI加速, 大SRAM |
| **ESP32-C3** | RISC-V RV32IMC | 32-bit | 无 | WiFi+BLE | 低成本RISC-V |
| **ESP32-C6** | RISC-V RV32IMAC | 32-bit | 无 | WiFi+BLE+802.15.4 | Zigbee/Thread |
| **ESP32-H2** | RISC-V RV32IMAC | 32-bit | 无 | BLE+802.15.4 | 低功耗Zigbee |
| **ESP32-P4** | RISC-V 双核 | 32-bit | 双精度 | 无(有线) | 高性能无无线 |

### ESP-IDF 开发特点

| 维度 | 特点 |
|------|------|
| **编程模型** | FreeRTOS + 事件驱动，非裸机 |
| **外设配置** | 结构体参数表（非 HAL 状态机）|
| **GPIO** | `gpio_config()` 结构体一次性配置 |
| **I2C** | `i2c_master_...()` 命令链表模式 |
| **SPI** | `spi_device_...()` 事务队列模式 |
| **UART** | 事件驱动 + 环形缓冲区 |
| **ADC** | 单次/连续+DMA |

### STM32 ↔ ESP32 外设概念映射

| STM32 概念 | ESP32 等价 |
|-----------|-----------|
| HAL_GPIO_WritePin | gpio_set_level |
| HAL_UART_Transmit | uart_write_bytes |
| HAL_I2C_Master_Transmit | i2c_master_write_to_device |
| HAL_SPI_TransmitReceive | spi_device_transmit |
| HAL_ADC_Start_DMA | adc_oneshot_read / adc_continuous_read |
| HAL_TIM_PWM_Start | ledc_channel_config (LEDC 控制器) |
| DMA Stream | GDMA (ESP32-S3) / 无(ESP32 用 I2S/SPI 内建 DMA) |
| TIM 定时器 | esp_timer / timer_group |
| NVIC 中断优先级 | 中断优先级可配(1-5级) |
| FreeRTOS xTaskCreate | 同(ESP-IDF 深度定制 FreeRTOS) |

---

## 国产替代系列

### GD32（兆易创新）

| 系列 | 对标 STM32 | 兼容度 | 关键差异 |
|------|-----------|--------|---------|
| **GD32F1x0** | STM32F0 | 引脚兼容 | 内核 M23(非M0), 主频更高 |
| **GD32F103** | STM32F103 | 软件基本兼容 | 外设地址偏移, PLL公式不同 |
| **GD32F303** | STM32F303 | 引脚兼容 | 主频 120MHz, SRAM 更大 |
| **GD32F403** | STM32F4 | 部分兼容 | 外设寄存器偏移 |
| **GD32VF103** | — | RISC-V | 非ARM, 内核 Bumblebee |

**移植要点**：
- 外设基地址可能偏移 0x400 范围内的几个字节
- RCC 寄存器布局不同（PLL 计算公式重新确认）
- GD32F1 用 SPL 库（兼容 STM32F10x 风格）
- GD32F3/F4 有自己版本的 HAL 库

### AT32（雅特力）

| 系列 | 对标 | 特点 |
|------|------|------|
| AT32F403A | STM32F4 | 主频 240MHz, SRAM 224KB |
| AT32F415 | STM32F4 | 低成本, QFN28 封装 |
| AT32F421 | STM32F4 | USB OTG + 4个USART |

**移植要点**：
- 外设架构原创性强，寄存器布局与 STM32 差异大
- 提供 AT32 BSP 库（HAL 风格）
- PLL 计算公式与 STM32 不同
- 调试器用 AT-Link（CMSIS-DAP 兼容）

### CH32（沁恒）

| 系列 | 内核 | 特点 |
|------|------|------|
| CH32V203 | RISC-V | USB+蓝牙 |
| CH32V307 | RISC-V | 以太网+USB HS |
| CH32F103 | M3 | 兼容 STM32F103(低成本)|

**移植要点**：
- RISC-V 系列中断模型与 ARM 完全不同
- 提供 CH32 标准库（类似 SPL 风格）
- 调试器用 WCH-Link

---

## 开发方式等效操作映射

### GPIO 输出

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET)` | STM32 |
| LL | `LL_GPIO_SetOutputPin(GPIOA, LL_GPIO_PIN_5)` | STM32 |
| SPL | `GPIO_SetBits(GPIOA, GPIO_Pin_5)` | STM32F1 |
| 寄存器 | `GPIOA->BSRR = GPIO_PIN_5` | STM32(支持位带) |
| ESP-IDF | `gpio_set_level(GPIO_NUM_5, 1)` | ESP32 |
| Arduino | `digitalWrite(5, HIGH)` | 通用 |

### UART 发送

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_UART_Transmit(&huart1, buf, len, timeout)` | STM32 |
| SPL | `USART_SendData(USART1, byte)` | STM32F1 |
| 寄存器 | `USART1->DR = byte` | STM32 |
| ESP-IDF | `uart_write_bytes(UART_NUM_1, buf, len)` | ESP32 |
| Arduino | `Serial1.write(buf, len)` | 通用 |

### I2C 写入

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_I2C_Master_Transmit(&hi2c1, addr, buf, len, timeout)` | STM32 |
| SPL | `I2C_SendData(I2C1, byte)` | STM32F1 |
| 寄存器 | 轮询 SR1/SR2/DR | STM32 |
| ESP-IDF | `i2c_master_write_to_device(I2C_NUM_0, addr, buf, len, 1000/pdMS_TO_TICKS)` | ESP32 |
| Linux | `ioctl(fd, I2C_SLAVE, addr); write(fd, buf, len)` | Linux |

### SPI 收发

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_SPI_TransmitReceive(&hspi1, tx, rx, len, timeout)` | STM32 |
| 寄存器 | 轮询 SPI_SR/SPI_DR | STM32 |
| ESP-IDF | `spi_device_transmit(handle, &trans)` | ESP32 |
| Arduino | `SPI.transfer(byte)` | 通用 |

### ADC 单次读取

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_ADC_Start(&hadc); HAL_ADC_PollForConversion(&hadc, timeout)` | STM32 |
| SPL | `ADC_RegularChannelConfig(ADC1, ch, 1, ADC_SampleTime_55Cycles5); ADC_SoftwareStartConvCmd(ADC1, ENABLE)` | STM32F1 |
| 寄存器 | `ADC1->CR2 |= ADC_CR2_SWSTART; while(!(ADC1->SR & ADC_SR_EOC)){}; val = ADC1->DR` | STM32 |
| ESP-IDF | `adc_oneshot_read(adc_handle, channel, &val)` | ESP32 |
| Arduino | `analogRead(pin)` | 通用 |

### 定时器 PWM

| 方式 | 代码 | 平台 |
|------|------|------|
| HAL | `HAL_TIM_PWM_Start(&htim2, TIM_CHANNEL_1)` | STM32 |
| SPL | `TIM_SetCompare2(TIM2, pulse)` | STM32F1 |
| 寄存器 | `TIM2->CCR1 = pulse; TIM2->CR1 |= TIM_CR1_CEN` | STM32 |
| ESP-IDF | `ledc_set_duty(ledc_speed, chan, duty); ledc_update_duty(ledc_speed, chan)` | ESP32 |

---

## 平台选型速查

| 需求 | 推荐平台 | 理由 |
|------|---------|------|
| 学习入门 | STM32F103C8T6 | 资料最全, 成本低 |
| 量产性价比 | GD32F103 / CH32F103 | 成本更低, 供货稳 |
| 高性能 + 生态 | STM32H743 / ESP32-S3 | H7=480MHz, S3=AI加速 |
| 无线连接 | ESP32-S3 | WiFi+BLE, 生态最好 |
| 超低功耗 | STM32L4 / STM32U5 | 待机 nA 级 |
| 安全要求 | STM32L5 / STM32U5 | TrustZone, 加密加速 |
| 国产化 | GD32F4 / AT32F4 | 资源丰富, 性能强 |
| RISC-V 学习 | CH32V307 / ESP32-C3 | 低成本RISC-V |
| 实时控制 | STM32G4 | HRTIM, CORDIC, 数学加速 |

---

## 边界定义

### 不该激活
- 用户只需要使用一个已知平台的特定外设（不涉及跨平台对比）→ 使用对应的外设 skill
- 用户需要的是 Bootloader / OTA / 低功耗 等系统级方案（而非芯片对比）
- 用户讨论的是纯概念性的计算机体系结构（与本 skill 无关）

### 不该做
- **禁止**在一份外设 skill 中重复展开所有平台细节（本 skill 是中央参考，外设 skill 只需引用）
- **禁止**对不熟悉的平台给出具体的寄存器值（必须查对应 RM）
- **禁止**推荐未经验证的国产替代方案

### 不该碰
- **不触碰** 各厂商的官方 SDK 源码
- **不触碰** 用户项目的芯片选型决策（只提供参考，不替用户做决定）

## 交接关系

- 上游：外设 skill（uart-module / i2c-bus / spi-bus 等引用本 skill 的平台差异内容）
- 互补：`code-porting`（跨平台移植时参考本 skill 的差异表）
- 下游：`stm32-hal-development`（ST 系开发首选）+ `build-idf`（ESP32 开发入口）
- 学习：`embedded-learning-path-framework`（根据所选芯片规划学习路径）
