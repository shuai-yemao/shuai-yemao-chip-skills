# STM32 各系列外设差异对照表

> 用于 MCU 换型时快速定位外设级差异。只列出移植过程中会产生代码改动的关键差异，完全兼容的部分不重复列出。

## RCC（复位与时钟控制器）

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G0 | STM32G4 |
|------|---------|---------|---------|---------|---------|
| HSI 频率 | 8MHz | 16MHz | 64MHz | 16MHz | 16MHz |
| HSE 范围 | 4-16MHz | 4-26MHz | 4-48MHz | 4-48MHz | 4-48MHz |
| LSI 频率 | 40kHz | 32kHz | 32kHz | 32kHz | 32kHz |
| SYSCLK max | 72MHz | 180MHz | 480MHz | 64MHz | 170MHz |
| APB1 max | 36MHz | 45MHz | 120MHz | 32MHz | 85MHz |
| APB2 max | 72MHz | 90MHz | 120MHz | — | 85MHz |
| PLL 路数 | 1 | 2 (PLL, PLLI2S) | 3 (PLL1/2/3) | 1 | 2 |
| PLL VCO 范围 | 156-320MHz | 192-432MHz | 128-560MHz | 96-344MHz | 128-560MHz |
| USB 48MHz 来源 | 无原生 USB | PLL48CK (PLLQ) | PLL3Q | 无 | PLLQ |
| CSS 支持 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 时钟输出 | MCO | MCO1/MCO2 | MCO1/MCO2 | MCO | MCO |
| VOS 调节 | ✗ | ✗ | ✓ (VOS0~3) | ✗ | ✗ |

**移植注意**：
- F1→F4：F4 多一个 PLLI2S（给 I2S 专用时钟，不配 PLLI2S 则 I2S 可能无声）
- F4→H7：H7 的 VOS 调节影响总线频率上限（VOS0→480MHz, VOS3→200MHz）
- G0：无 APB2，只有单 APB 总线；HAL_RCC_APB2PeriphClockCmd 不可用

## GPIO

| 项目 | STM32F1 | STM32F4/H7/G0/G4 |
|------|---------|-----------------|
| 复用方式 | AFIO + Remap 宏 (`GPIO_Remap_xxx`) | AFRL/AFRH 寄存器 (`GPIO_AFx_xxx`) |
| 时钟使能 | `RCC_APB2Periph_GPIOx` | `RCC_AHB1Periph_GPIOx` (F4/H7) / `RCC_IOPxEN` (G0/G4) |
| 输出速度值 | 2MHz / 10MHz / 50MHz | Low / Medium / High / VeryHigh |
| 上下拉 | HAL_GPIO_PULLUP 不生效（需写 CRL+BSRR） | 完全通过 HAL 控制 |
| GPIO 最多 | 80 (100pin) | 114 (144pin) / F1 兼容模式 |
| BSRR 原子 | 支持 | 支持 |
| GPIO 锁定 | LCKR 寄存器 | LCKR 寄存器 (相同) |

## USART/UART

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| 模块数量 | 3 USART + 2 UART | 3 USART + 3 UART | 4 USART + 4 UART | 3 USART + 4 UART |
| OVER8 | ✗ | ✓ | ✓ | ✓ |
| RTO (超时) | ✗ | ✗ | ✓ | ✗ |
| FIFO | ✗ | ✗ | ✓ (16字节) | ✗ |
| 硬件流控 | CTS/RTS | CTS/RTS | CTS/RTS + RS485 | CTS/RTS |
| TX/RX 交换 | ✗ | ✗ | ✓ | ✗ |
| 波特率公式 | USARTDIV=fCK/(16×Baud) | USARTDIV=fCK/(8或16)×Baud | USARTDIV=fCK/(8或16)×Baud | USARTDIV=fCK/(8或16)×Baud |
| 同步模式 | ✓ | ✓ | ✓ | ✓ |
| LIN | ✓ | ✓ | ✓ | ✓ |
| Smartcard | ✓ | ✓ | ✓ | ✓ |
| IrDA | ✓ | ✓ | ✓ | ✓ |

## SPI

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| SPI 数量 | 1~3 | 1~6 | 1~6 | 1~4 |
| SPI4/5/6 | ✗ | ✓ | ✓ | ✗ |
| FIFO | ✗ | ✗ | ✓ (16位 FIFO + 4位阈值) | ✗ |
| 数据大小 | 8位/16位 | 8位/16位 | 4~32位 | 8位/16位 |
| BSY 修复 | CR1 SPE 复位可恢复 | 同左 | 同左 | 同左 |
| I2S | 仅 SPI2/3 可复用 | SPI2/3 可复用 | SPIn + 独立 I2S | ✗ |
| TI 模式 | ✗ | ✓ | ✓ | ✓ |

## I2C

| 项目 | STM32F1 (I2C v1) | STM32F4 (I2C v2) | STM32H7 (I2C v2) | STM32G4 (I2C v2) |
|------|-------------------|-------------------|-------------------|-------------------|
| BUSY 锁死 BUG | ✓（有，需 9 脉冲恢复） | ✗ | ✗ | ✗ |
| 时序寄存器 | CCR + TRISE | TIMINGR | TIMINGR | TIMINGR |
| 最高速率 | 400kHz (Fast Mode) | 1MHz (Fast Mode+) | 1MHz (Fast Mode+) | 1MHz (Fast Mode+) |
| 时钟延展 | 从模式可禁 | 可控 | 可控 | 可控 |
| 双地址 | ✓ | ✓ | ✓ (OAR1/OAR2) | ✓ |
| SMBus | ✓ | ✓ | ✓ | ✓ |

## 定时器

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| 高级定时器 | TIM1/TIM8 | TIM1/TIM8 | TIM1/TIM8 | TIM1/TIM8 |
| 通用定时器 | TIM2~5 | TIM2~5 + TIM9~14 | TIM2~8 + TIM12~17 | TIM2~8 + TIM15~17 |
| 基本定时器 | TIM6/TIM7 | TIM6/TIM7 | TIM6/TIM7 | TIM6/TIM7 |
| TIM9~14 | ✗ | ✓ | ✓ | ✗ (G4 不同分布) |
| 16位/32位 | TIM2/TIM5 是 32位 | TIM2/TIM5 是 32位 | TIM2/TIM5 是 32位 | 除 TIM2/TIM3 外多为 16位 |
| 编码器模式 | ✓ | ✓ | ✓ | ✓ |
| 霍尔传感器 | ✗ | ✓ | ✓ | ✓ |
| PWM 输入 | ✓ | ✓ | ✓ | ✓ |
| 刹车功能 | ✓ (高级定时器) | ✓ | ✓ (6 路) | ✓ (6 路) |
| 死区插入 | ✓ | ✓ | ✓ | ✓ |

## ADC

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G0 | STM32G4 |
|------|---------|---------|---------|---------|---------|
| ADC 位数 | 12位 | 12位 | 16位 | 12位 | 12位 (硬件过采样到 16位) |
| ADC 数量 | 1~3 | 1~3 | 2 (1+2) 或 3 (F7) | 1 | 1~5 |
| fADC max | 14MHz (1μs) | 36MHz (0.5μs) | 36MHz (0.4μs) | 35MHz (0.42μs) | 60MHz (0.3μs) |
| 规则组通道 | 16 | 16 | 16 | 16 | 16 |
| 注入组通道 | 4 | 4 | 2 | — | 4 |
| 差分级输入 | ✗ | ✗ | ✗ | ✗ | ✓ |
| 过采样 | ✗ | ✗ | ✓ (16位硬件) | ✗ | ✓ (可配置) |
| VBAT 通道 | ✓ | ✓ | ✓ | ✓ | ✓ |
| VREFINT | ✓ (1.2V) | ✓ (1.2V) | ✓ (1.2V) | ✓ (1.2V) | ✓ |

## DMA

| 项目 | STM32F1 | STM32F4 | STM32H7 (MDMA) |
|------|---------|---------|----------------|
| DMA 控制器 | DMA1(7ch) + DMA2(5ch) | DMA1/DMA2(各 8 stream) | DMA1/DMA2 + MDMA + BDMA |
| stream/channel | channel 模型 | stream 模型 | stream + DMAMUX |
| 通道映射 | 固定 | 固定 | 可编程 (DMAMUX) |
| FIFO | ✗ | 4 words per stream | ✓ (MDMA: 64+64, DMA: 4 words) |
| 双缓冲 DBM | ✗ | ✓ | ✓ |
| Memory-to-Memory | ✗ | ✓ | ✓ (MDMA 为主) |
| 链表 (LPA) | ✗ | ✗ | ✓ |
| 突发传输 | 无 | ✓ (single/incr4/8/16) | ✓ |
| 传输粒度 | byte/halfword/word | byte/halfword/word | byte/halfword/word/doubleword |

## CAN

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| CAN 模块 | bxCAN | bxCAN | FDCAN | FDCAN |
| CAN 数量 | 1 | 2 (CAN1/2) 或 3 (F405) | 2 | 2~3 (G4) |
| CAN-FD | ✗ | ✗ | ✓ | ✓ |
| 邮箱数量 | 3 Tx + 2 Rx (FIFO) | 3 Tx + 2 Rx (FIFO) | 32 Rx FIFO | 32 Rx FIFO |
| 时钟 | APB1 (36MHz) | APB1 (42MHz) | FDCAN 独立时钟 | APB1 |

## USB

| 项目 | STM32F1 | STM32F4 | STM32H7 |
|------|---------|---------|---------|
| 类型 | Device FS | OTG_FS / OTG_HS | OTG_FS / OTG_HS |
| 时钟 | 48MHz (外部) | PLL48CK (48MHz) | PLL3Q (48MHz) |
| ULPI | ✗ | HS 可用 | HS 可用 |
| 端点数量 | 8 | 4 IN + 4 OUT (Device) / 6 (Host) | 6 IN + 6 OUT |
| DMA | 不需要 | 可选 (专用 DMA) | MDMA |
| LPM | ✗ | ✓ | ✓ |
| BCD | ✗ | ✓ | ✓ |

## 中断控制器 (NVIC)

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| IRQ 通道 | 68 | 82 | 100 | 91 |
| 优先级位 | 4 (固定) | 4 (可配) | 4 (可配) | 4 (可配) |
| 优先级分组 | NVIC_PriorityGroup_2 固定 | 可配 | 可配 | 可配 |
| 向量表偏移 | VTOR (0xE000ED08) | VTOR | VTOR | VTOR |
| 非屏蔽中断 NMI | 1 | 1 | 1 | 1 |

## SYSTICK

完全兼容，所有 Cortex-M3/M4/M7 实现一致：
- RVR (Load), CVR (Current), CSR (Control & Status)
- 时钟源：AHB/8 或 AHB 直通
- 仅 24位

## MPU（内存保护单元）

| 项目 | Cortex-M3 | Cortex-M4F | Cortex-M7 |
|------|-----------|-----------|-----------|
| MPU 数量 | 1 | 1 | 1 |
| 区域数 | 8 | 8 | 16 |
| 子区域 | 8 每区域 | 8 每区域 | 8 每区域 |
| XN (Execute Never) | ✓ | ✓ | ✓ |
| 背景区域 | ✓ | ✓ | ✓ |
| TEX/SCB 缓存控制 | ✓ | ✓ | ✓ |

## FPU

| 项目 | Cortex-M3 | Cortex-M4F | Cortex-M7 |
|------|-----------|-----------|-----------|
| FPU | ✗ | FPv4-SP | FPv5-D16 |
| 精度 | 软件浮点 | 单精度 | 单精度 + 双精度 |
| 寄存器 | — | S0~S31 (32×32位) | S0~S31 + D0~D15 (32×32位 + 16×64位) |
| 自动状态保存 | — | Lazy stacking | Lazy stacking |
| CPACR 配置 | — | `CPACR |= (3<<20)` (CP10) | `CPACR |= (0xF<<20)` (CP10+CP11) |

## 常见外设地址映射差异

| 外设 | STM32F1 | STM32F4 | STM32H7 |
|------|---------|---------|---------|
| USART1 | 0x40013800 | 0x40011000 | 0x40011000 |
| USART2 | 0x40004400 | 0x40004400 | 0x40004400 |
| SPI1 | 0x40013000 | 0x40013000 | 0x40013000 |
| I2C1 | 0x40005400 | 0x40005400 | 0x40005400 |
| TIM2 | 0x40000000 | 0x40000000 | 0x40000000 |
| DMA1 | 0x40020000 | 0x40026000 | 0x40020000 (DMA1) / 0x58026400 (MDMA) |
| ADC1 | 0x40012400 | 0x40012000 | 0x40022000 |
| RCC | 0x40021000 | 0x40023800 | 0x58024400 |
| GPIOA | 0x40010800 | 0x40020000 | 0x58020000 |

> **注意**：以上地址仅作参考，具体以各系列参考手册为准。F4 的 GPIO 基地址从 F1 的 `0x4001xxxx` 变到 `0x4002xxxx`，代码中直接操作寄存器时必须更新。

## Flash 架构

| 项目 | STM32F1 | STM32F4 | STM32H7 | STM32G4 |
|------|---------|---------|---------|---------|
| 扇区大小 | 1KB~2KB (小容量) / 4KB (中容量) / 2K~128K (大容量) | 16KB (4) + 64KB (1) + 128KB (N) | 128KB (扇区) | 2KB (页) |
| 等待周期 | 0~2 WS (72MHz) | 0~5 WS (168MHz) | 0~4 WS 单Bk / 0~12 WS 双Bk | 0~4 WS |
| 双 Bank | ✗ | ✗ | ✓ | ✓ (可选) |
| RWW | ✗ | ✗ | ✓ (双Bank) | ✓ |
| ECC | ✗ | ✗ | ✓ (每256位) | ✗ |

## 调试接口

| 项目 | STM32F1 | STM32F4/H7/G0/G4 |
|------|---------|-----------------|
| SWD 引脚 | SWDIO/SWCLK (固定 PA13/PA14) | 同左 |
| JTAG 引脚 | TMS/TCK/TDI/TDO/nTRST (固定) | 同左 |
| DBGMCU | 可配置 STOP/STANDBY 下调试 | 同左 |
| TRACESWO | PE2 (SWO) | 同左 |
| 调试器 | ST-Link V2 | ST-Link V3 建议 (H7 高速) |
