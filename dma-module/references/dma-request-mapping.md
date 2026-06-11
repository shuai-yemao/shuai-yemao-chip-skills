# DMA 请求映射速查

## F4 (STM32F4xx) DMA 请求映射

### DMA1 请求映射

| 通道 | Stream0 | Stream1 | Stream2 | Stream3 | Stream4 | Stream5 | Stream6 | Stream7 |
|------|---------|---------|---------|---------|---------|---------|---------|---------|
| CH0 | TIM5_CH4 | TIM5_CH4 | TIM5_CH3 | TIM5_CH3 | TIM5_CH2 | TIM5_CH2 | TIM5_CH1 | TIM5_CH1 |
| CH1 | TIM2_CH3 | TIM2_CH4 | TIM2_CH1 | TIM2_CH2 | — | TIM7_UP | TIM7_UP | TIM7_UP |
| CH2 | TIM3_CH3 | TIM3_CH4 | TIM3_CH1 | TIM3_CH2 | — | — | — | — |
| CH3 | TIM4_CH3 | TIM4_CH1 | TIM4_CH2 | TIM4_CH4 | — | — | — | — |
| CH4 | — | — | — | — | — | — | — | — |
| CH5 | — | — | — | — | — | — | — | — |
| CH6 | — | — | — | — | — | — | — | — |
| CH7 | — | — | — | — | — | — | — | — |

### DMA2 请求映射

| 通道 | Stream0 | Stream1 | Stream2 | Stream3 | Stream4 | Stream5 | Stream6 | Stream7 |
|------|---------|---------|---------|---------|---------|---------|---------|---------|
| CH0 | SPI4_RX | SPI4_TX | — | SPI4_RX | SPI4_TX | — | SPI4_RX | SPI4_TX |
| CH1 | SPI1_RX | SPI1_TX | SPI1_RX | SPI1_TX | — | — | SPI1_RX | SPI1_TX |
| CH2 | — | — | — | USART6_RX | USART6_TX | USART6_RX | USART6_TX | — |
| CH3 | SPI5_RX | SPI5_TX | SPI5_RX | SPIFAIL | SPIFAIL | SPI5_TX | SPIFAIL | SPIFAIL |
| CH4 | SPI6_RX | SPI6_TX | SPI6_RX | SPI6_TX | — | — | — | — |
| CH5 | — | — | — | — | — | — | — | — |
| CH6 | — | — | — | — | — | — | — | — |
| CH7 | — | — | — | — | — | — | — | — |

### 外设 → Stream/Channel 推荐映射（F4 常用）

| 外设 | 方向 | Stream | 通道 | 优先级 |
|------|------|--------|------|--------|
| USART1_TX | M→P | DMA2_Stream7 | CH1 | 常用 |
| USART1_RX | P→M | DMA2_Stream2 | CH1 | 常用 |
| USART2_TX | M→P | DMA1_Stream6 | CH4 | 唯一 |
| USART2_RX | P→M | DMA1_Stream5 | CH4 | 唯一 |
| SPI1_TX | M→P | DMA2_Stream3 | CH1 | 常用 |
| SPI1_RX | P→M | DMA2_Stream0 | CH1 | 常用 |
| I2C1_TX | M→P | DMA1_Stream6 | CH1 | 常用 |
| I2C1_RX | P→M | DMA1_Stream5 | CH1 | 常用 |
| ADC1 | P→M | DMA2_Stream0 | CH0 | 唯一 |
| TIM1_UP | M→P | DMA2_Stream5 | CH6 | 更新 DMA |
| SDIO | P→M | DMA2_Stream3 | CH4 | 高速 |

> **注意**：不同子系列（F405/F407/F411）的映射略有差异。表格基于 STM32F405/407 RM0090。请以你的实际芯片的 Reference Manual 为准。

## F1 (STM32F103) 请求映射

F1 无 Stream 概念，DMA1/DMA2 直接通过通道映射外设请求。

### DMA1 通道映射

| 通道 | 外设请求 |
|------|---------|
| CH1 | ADC1 / TIM2_CH3 / TIM4_UP |
| CH2 | TIM2_CH1 / TIM4_CH1 / USART1_TX |
| CH3 | TIM2_CH2 / TIM4_CH2 / I2S3_ext |
| CH4 | TIM3_CH1 / TIM7_CH1 / USART1_RX |
| CH5 | TIM3_CH2 / USART1_RX / USART2_RX |
| CH6 | TIM3_CH3 / USART1_TX / USART2_TX |
| CH7 | TIM3_CH4 / USART2_RX |

### DMA2 通道映射

| 通道 | 外设请求 |
|------|---------|
| CH1 | SPI1_RX / USART3_RX |
| CH2 | SPI1_TX / USART3_TX |
| CH3 | SPI1_RX / I2S_ext |
| CH4 | SPI2_RX / I2S2_ext |
| CH5 | SPI2_TX / I2S2_ext |
| CH6 | I2C1_RX / I2C2_RX / DAC_CH2 |
| CH7 | I2C1_TX / I2C2_TX / DAC_CH1 |

## G4 DMAMUX 灵活映射

G4 通过 DMAMUX 可将任意外设请求映射到任意 DMA Stream，不再受固定表格限制：

```c
// DMAMUX 配置示例：将 TIM1_UP 映射到 DMA1_Stream0
__HAL_RCC_DMAMUX_CLK_ENABLE();
HAL_DMAEx_ConfigMuxSync(&hdma, DMAMUX_SYNC_SIGNAL_TIM1_UP, ...);
```

## F1 (V1) 与 F4 (V2) 冲突规则对比

| 场景 | F1 (V1) | F4 (V2) |
|------|---------|---------|
| 同一外设的 TX/RX | 不可放在同通道 | 可用同 Stream 不同通道，或用不同 Stream |
| 不同外设共用通道 | 触发冲突 | Stream 不同即可，通道可冲突 |
| 高优先级抢占 | 软件优先级仲裁 | 硬件内部 Stream 优先级仲裁 |
| 同时使能多个传输 | 需避免通道冲突 | Stream 互不干扰 |

## 查找外设映射的方法

1. 打开对应芯片的 **Reference Manual**
2. 搜索 **"DMA request mapping"** 或 **"DMA table"**
3. 在表格中找到外设（如 `USART1_RX`）
4. 查看该外设的 `Channel` / `Request` 编号
5. F4: 在 (Stream, Channel) 表格中找到可用组合
6. F1: 直接选择对应通道

### 典型排查步骤

```
Q: USART1_RX 使用哪个 DMA Stream/Channel（F407）？

1. 查 RM 中 USART1_RX 的 DMA 请求表 → 通道 CH1
2. 查 DMA2 通道 CH1 可用 Stream → Stream0/2/5/7 可用
3. 检查冲突：SPI1_TX 用了 Stream3 → 避免冲突
4. 选 DMA2_Stream2_CH1 → 是 USART1_RX 的常用选项
```
