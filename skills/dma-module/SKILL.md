---
name: dma-module
version: "1.0.0"
description: "STM32 DMA 直接存储器访问配置、开发与故障排查。涵盖 DMA 架构（V1/V2/V3）、Stream/Channel 请求映射、传输类型（M2P/P2M/M2M）、双缓冲/环形缓冲、FIFO 管理、DMA + Cache 一致性、中断处理、寄存器级调试。当用户提到 DMA、直接存储器访问、DMA 传输、DMA 中断、DMA 双缓冲、DMA 环形缓冲、DMA+PingPong、DMA FIFO、DMA 通道分配、DMA 请求映射、DMA 效率、DMA 内存访问冲突、DMA 数据错位、DMA 缓冲区全零、DMA 半传输、DMA 循环模式、DMA 双缓冲 CT 标志、DMA 传输完成、DMA 报错、H7 DMA、MDMA 时使用。"
---

# DMA 模块开发指南

## DMA 架构概览

### 各系列 DMA 架构表

| 系列 | DMA 控制器 | 架构版本 | 数据流/通道 | 特点 |
|------|-----------|---------|------------|------|
| F1 | DMA1/DMA2 | V1 (Basic) | 7/12 通道 | 无 Stream，直接 Channel + Request |
| F4 | DMA1/DMA2 | V2 (Stream) | 8 Stream × 8 Channel | Stream 架构，FIFO + 双缓冲 |
| H7 | DMA1/DMA2/MDMA | V3 (BDMA) | 8 Stream × 8 Channel | 可编程优先级，独立 FIFO，MDMA |
| G4 | DMA1/DMA2/DMAMUX | V2 + DMAMUX | 8 Stream × 16 Channel | DMAMUX 灵活通道映射 |
| G0 | DMA1 | V1 (Basic) | 7 通道 | 无 Stream，有 DMAMUX |

### V1 (F1/G0) 架构

```
DMA1/DMA2
  ├─ 通道 1 ~ 7
  │    └─ 每个通道关联一个外设 DMA 请求
  ├─ 优先级仲裁 (CHxPL[1:0])
  ├─ 传输: Normal / Circular / Mem2Mem
  └─ 中断: TC / HT / TE
```

### V2 (F4/G4) Stream 架构

```
DMA1/DMA2
  └─ Stream 0 ~ 7
       ├─ 通道选择 (CHSEL[2:0]) → 8 选 1
       ├─ FIFO (4 字深)
       │    ├─ Direct Mode (FIFO = 旁路)
       │    └─ FIFO Mode (阈 1/4, 1/2, 3/4, Full)
       ├─ 优先级 (PL[1:0])
       ├─ 传输: Normal / Circular / PFC
       ├─ 双缓冲 (DBM)
       └─ 中断: TC / HT / TE / DME / FE
```

### V3 (H7) 增强架构

```
DMA1/DMA2
  └─ Stream 0 ~ 7
       ├─ 与 F4 类似但增强
       ├─ 可编程优先级 (4 级)
       ├─ 独立 FIFO 控制
       ├─ 支持 Linked List (扩展模式)
       └─ 每个 Stream 有 8 个可映射请求
MDMA (Master DMA)
  └─ 8 × 16 字节 FIFO
       ├─ 64 位 AXI 总线传输
       ├─ Linked List 模式
       ├─ 用于 Flash→SRAM, SRAM→SRAM 高速搬运
       └─ 可配合 DMA1/DMA2 形成 DMA-MDMA 链路
```

## DMA 请求映射

### F4 典型请求映射 (8 Stream × 8 Channel)

```
DMA2_Stream0: CH0=SPI4_RX,  CH1=SPI1_RX,   CH2=USART1_TX, CH3=SDIO, CH4=TIM8_CH3
DMA2_Stream1: CH0=SPI4_TX,  CH1=SPI1_TX,   CH2=USART1_RX, CH3=SDIO, CH4=TIM8_CH4
DMA2_Stream2: CH0=SPI4_RX,  CH1=TIM_CH3,   CH2=SPI1_RX,   CH3=I2S3ext, CH4=TIM8_CH2
// ...
```

> 完整映射表见 `references/dma-request-mapping.md`
> 缓冲区配置与对齐指南见 `references/dma-config-guide.md`

### 查找步骤

1. 确定外设（如 USART1_RX）
2. 查 Reference Manual 中 DMA 请求映射表（如 Table 47）
3. 找到该请求可用的 (Stream, Channel) 组合
4. 确认所选 Stream 未被其他外设占用
5. CubeMX 自动完成此步骤，但手动排查时需查表

## HAL API 使用

### 基本传输流程

```c
// 1. 配置 DMA 句柄
DMA_HandleTypeDef hdma_uart1_rx;

// 2. 在 HAL_UART_MspInit 中初始化
void HAL_UART_MspInit(UART_HandleTypeDef *huart)
{
    static DMA_HandleTypeDef hdma_rx;

    __HAL_RCC_DMA2_CLK_ENABLE();

    hdma_rx.Instance = DMA2_Stream5;
    hdma_rx.Init.Channel = DMA_CHANNEL_4;           // 请求映射
    hdma_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;   // 方向
    hdma_rx.Init.PeriphInc = DMA_PINC_DISABLE;       // 外设地址不增
    hdma_rx.Init.MemInc = DMA_MINC_ENABLE;            // 内存地址递增
    hdma_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_rx.Init.Mode = DMA_NORMAL;                   // 模式
    hdma_rx.Init.Priority = DMA_PRIORITY_LOW;
    hdma_rx.Init.FIFOMode = DMA_FIFOMODE_DISABLE;     // Direct 模式
    HAL_DMA_Init(&hdma_rx);

    // 3. 关联 UART 句柄和 DMA 句柄
    __HAL_LINKDMA(huart, hdmarx, hdma_rx);

    // 4. 使能 DMA 中断
    HAL_NVIC_SetPriority(DMA2_Stream5_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(DMA2_Stream5_IRQn);
}

// 5. 启动传输
HAL_UART_Receive_DMA(&huart1, rx_buf, BUF_SIZE);

// 6. 传输完成回调
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    // 传输完成处理
}
```

### F1 (V1) HAL 差异

```c
// F1 无 Stream 概念，直接使用 DMA_Channel_TypeDef
hdma.Instance = DMA1_Channel5;
hdma.Init.Direction = DMA_PERIPH_TO_MEMORY;
// 不需要 Init.Channel
// 不需要 FIFO 配置
```

## DMA 传输模式

| 模式 | HAL 宏 | 说明 | 典型场景 |
|------|-------|------|---------|
| **Normal** | `DMA_NORMAL` | 传输指定数量后停止 | 一次 ADC 转换、单次 UART 接收 |
| **Circular** | `DMA_CIRCULAR` | 达到数量后从起点重新开始 | ADC 连续采样、UART 循环接收 |
| **PFC** | `DMA_PFCTRL` | 外设控制传输结束 | SDIO、USB 高速传输 |
| **Mem2Mem** | `DMA_MEMORY_TO_MEMORY` | 内存到内存（F1 V1 独占） | 缓冲区拷贝（M2M 与 DBM 互斥） |

## 双缓冲模式 (DBM)

仅在 F4/V2 架构中可用，通过 CT 标志切换缓冲区。

### 配置

```c
hdma.Init.Mode = DMA_CIRCULAR;
// 双缓冲需在 Init 后单独设置
HAL_DMAEx_ConfigMuxSync(&hdma, ...);  // G4 DMAMUX
```

### 寄存器级控制

```c
DMA_Stream_TypeDef *s = DMA2_Stream5;

// 使能双缓冲
s->CR |= DMA_SxCR_DBM;

// 配置两个缓冲区地址
s->M0AR = (uint32_t)buf0;  // 缓冲区 0
s->M1AR = (uint32_t)buf1;  // 缓冲区 1

// 设置传输数量
s->NDTR = BUF_SIZE;

// 检查当前使用哪个缓冲区
if (s->CR & DMA_SxCR_CT) {
    // CT=1: DMA 当前写 M1AR（用户处理 buf0）
    process(buf0, BUF_SIZE);
} else {
    // CT=0: DMA 当前写 M0AR（用户处理 buf1）
    process(buf1, BUF_SIZE);
}

// 注意：CT 标志的读取时序
// 在传输完成 (TC) 中断中读取 CT 判断哪个缓冲区已就绪
// CT = DMA_SxCR 的第 19 位，变化发生在 TC 中断触发时
```

### DBM 与 M2M 互斥

```
F4 DMA V2 限制：
- DBM 使能时，Mem2Mem 模式不可用
- DBM 仅在 Circular 模式下有意义
- DBM 和 PFC 模式互斥
```

## FIFO 管理

### Direct Mode (FIFO 旁路)

```c
hdma.Init.FIFOMode = DMA_FIFOMODE_DISABLE;
// 数据直接写入目的地，FIFO 被旁路
// 适用：源和目标数据宽度相同
// 优点：延迟最低
// 缺点：无法处理宽度不同或需打包的数据
```

### FIFO Mode

```c
hdma.Init.FIFOMode = DMA_FIFOMODE_ENABLE;
hdma.Init.FIFOThreshold = DMA_FIFO_THRESHOLD_HALFFULL;
// 阈值可选: 1/4, 1/2, 3/4, FULL (DMA_FIFO_THRESHOLD_xxx)
```

| 阈值 | 宏 | 触发条件 |
|------|-----|---------|
| 1/4 | `DMA_FIFO_THRESHOLD_1QUARTERFULL` | FIFO 写入 ≥ 1 字 |
| 1/2 | `DMA_FIFO_THRESHOLD_HALFFULL` | FIFO 写入 ≥ 2 字 |
| 3/4 | `DMA_FIFO_THRESHOLD_3QUARTERFULL` | FIFO 写入 ≥ 3 字 |
| Full | `DMA_FIFO_THRESHOLD_FULL` | FIFO 写入 ≥ 4 字 |

### 数据宽度与对齐规则

```c
// 规则：PeriphDataAlignment ≤ MemDataAlignment 时 FIFO 自动打包
// 例：外设 8bit → 内存 32bit，FIFO 每收 4 个字节打包一次写入

// 常见配置：
// UART (8bit) → 内存: Periph=BYTE, Mem=BYTE, Direct 模式
// ADC (16bit) → 内存: Periph=HALFWORD, Mem=HALFWORD, Direct 模式
// SPI (8bit) → 内存: Periph=BYTE, Mem=HALFWORD, FIFO 模式

// 注意：PeriphDataAlignment > MemDataAlignment 会导致数据丢失
// 允许的组合: Periph ≤ Mem（FIFO 打包）或 Periph = Mem（Direct）
```

### FIFO Error (FE) 处理

```c
void DMA2_Stream5_IRQHandler(void)
{
    if (__HAL_DMA_GET_FLAG(&hdma, DMA_FLAG_FEIF0_5)) {
        // FIFO 错误：通常由于数据宽度配置不匹配
        // 或 FIFO 阈值设置不合理
        __HAL_DMA_CLEAR_FLAG(&hdma, DMA_FLAG_FEIF0_5);

        // 复位 DMA
        HAL_DMA_Abort(&hdma);

        // 检查配置：
        // 1. PeriphDataAlignment 和 MemDataAlignment 是否匹配
        // 2. FIFO 阈值是否合理
        // 3. SxCR 中的 PBURST/MBURST 是否使能了 burst
    }
}
```

## DMA 中断处理

### 中断使能

```c
// HAL 自动处理中断使能
// 手动寄存器级：
s->CR |= DMA_SxCR_TCIE  // 传输完成中断
      |  DMA_SxCR_HTIE  // 半传输中断
      |  DMA_SxCR_TEIE  // 传输错误中断
      |  DMA_SxCR_DMEIE;// 直接模式错误中断
```

### 中断标志

```c
// LISR: DMA1 Stream 0-3 / DMA2 Stream 0-3
// HISR: DMA1 Stream 4-7 / DMA2 Stream 4-7
// 读取后通过 LIFCR/HIFCR 清除

// 标志位模式: TE[4n+0]  HT[4n+1]  TC[4n+2]  DME[4n+3]
// 其中 n = Stream 编号 (0~7)

uint32_t lisr = DMA2->LISR;
if (lisr & DMA_LISR_TCIF5) {
    // Stream 5 传输完成
    process_data();
    DMA2->LIFCR |= DMA_LIFCR_CTCIF5;  // 清除标志
}
```

### 中断回调优先级

```
传输完成 (TC)   → 最高频，通常处理数据
半传输 (HT)     → 仅在 Circular 模式有意义，处理前半部数据
直接模式错误 (DME) → Direct Mode 下源/目标不对齐时触发
传输错误 (TE)   → 总线错误/FIFO 错误/RD/WR 错误
```

## DMA + 外设配合

### ADC + DMA

```c
// 参见 adc-module Skill
// 关键点：DMA 缓冲区大小 = 通道数 × 采样批数
// 连续扫描模式下用 Circular 模式
HAL_ADC_Start_DMA(&hadc1, dma_buf, NUM_CHANNELS * NUM_BATCHES);
```

### UART + DMA (IDLE 变长接收)

```c
// 参见 uart-module Skill + stm32-hal-development 6b
HAL_UARTEx_ReceiveToIdle_DMA(&huart1, buf, BUF_SIZE);
// 必须先清除 IDLE 标志
// DMA Normal 模式，到达 BUF_SIZE 或 IDLE 时停止
```

### SPI + DMA

```c
// 参见 spi-bus Skill
// 关键点：SPI TX/RX 通常需要双 DMA Stream
// SPI BSY 标志检查需在 DMA TC 之后
HAL_SPI_TransmitReceive_DMA(&hspi1, tx_buf, rx_buf, len);
```

### TIM + DMA (突发更新)

```c
// 参见 timer-module Skill
// DMA 突发更新 ARR + CCR 实现多相 PWM 占空比更新
// 使用 TIM DIER 的 UDE/CC1DE 等位使能 DMA 请求
```

## DMA + Cache 一致性 (H7)

```c
// H7 DMA 使用 AXI SRAM 时需要手动维护 Cache 一致性
// 因为 DMA 绕过 CPU Cache 直接访问 SRAM

// 场景 1: CPU 写入缓冲区 → DMA 发送
// CPU 写完后需要 Clean DCache（将 Cache 内容写回 SRAM）
SCB_CleanDCache_by_Addr((uint32_t *)tx_buf, BUF_SIZE);
HAL_UART_Transmit_DMA(&huart1, tx_buf, BUF_SIZE);

// 场景 2: DMA 接收 → CPU 读取
// DMA 写入后需要 Invalidate DCache（无效化 Cache，下次从 SRAM 读）
HAL_UART_Receive_DMA(&huart1, rx_buf, BUF_SIZE);
// DMA 传输完成后：
SCB_InvalidateDCache_by_Addr((uint32_t *)rx_buf, BUF_SIZE);
process(rx_buf);

// 场景 3: DMA 双缓冲 + Cache
// 每次切换缓冲区后都需要 Invalidate
if (DMA2_Stream5->CR & DMA_SxCR_CT) {
    SCB_InvalidateDCache_by_Addr((uint32_t *)buf0, BUF_SIZE);
    process(buf0, BUF_SIZE);
} else {
    SCB_InvalidateDCache_by_Addr((uint32_t *)buf1, BUF_SIZE);
    process(buf1, BUF_SIZE);
}

// 重要提示：
// - Clean 和 Invalidate 操作有性能开销（每 32 字节对齐行消耗~10 cycles）
// - 缓冲区地址建议 32 字节对齐（Cache Line 大小）
// - 缓冲区大小建议为 32 的整数倍，否则最后一个部分行需要特殊处理
```

## 常见陷阱与排查

| 编号 | 现象 | 根因 | 解决方案 |
|------|------|------|---------|
| 1 | DMA 传输**不启动** | 外设时钟未使能 | `__HAL_RCC_DMAx_CLK_ENABLE()` |
| 2 | DMA 只传输**一次**后停止 | Normal 模式，需重启 | 改用 Circular 或每次重启 |
| 3 | FIFO Error (FE) 中断 | 数据宽度不对或阈值不合理 | 检查 Periph/Mem 对齐，切 Direct 模式 |
| 4 | 数据**错位/乱序** | 半字/字对齐问题 | 确保缓冲区地址对齐到数据宽度 |
| 5 | 双缓冲模式下**数据被覆盖** | HT/TC 回调中未及时读取另一个缓冲区 | 在 TC 中断中立即处理，减少处理时间 |
| 6 | DMA + UART 收到**全 0** | UART 未使能 DMA 请求 | `__HAL_UART_ENABLE_IT(huart, UART_IT_DMAR)` |
| 7 | Circular 模式**速度慢** | FIFO 阈值过低，频繁触发 | 提高 FIFO 阈值，减小中断频率 |
| 8 | 中断中读写 NDTR 为 **0** | 传输已完成后才读取 | 在 TC 中断中读 NDTR 为 0 是正常的 |
| 9 | H7 DMA 数据**不正确** | Cache 未 Invalidate | 添加 `SCB_InvalidateDCache_by_Addr` |
| 10 | 外设传输**一直 Busy** | DMA 还挂在老传输上 | 调用 `HAL_DMA_Abort` 后再启动 |

### NDTR 调试

```c
// NDTR 显示剩余未传输的数据单元数（非字节数）
// 单元大小 = PeriphDataAlignment 指定的大小
// 初始值 = 编程时设置的传输数量
// 传输过程中递减，传输完成 = 0

// 调试时读取当前进度
uint32_t remaining = DMA2_Stream5->NDTR;
uint32_t total = BUF_SIZE;  // 初始值
uint32_t transferred = total - remaining;  // 已传输单元数
// 实际字节数 = transferred × 数据宽度（字节）
```

### 软件触发 Mem2Mem

```c
// V1 (F1) 使用 MEM2MEM 位
DMA1_Channel6->CCR |= DMA_CCR_MEM2MEM;
DMA1_Channel6->CNDTR = len;
DMA1_Channel6->CPAR = (uint32_t)src;
DMA1_Channel6->CMAR = (uint32_t)dst;
DMA1_Channel6->CCR |= DMA_CCR_EN;  // 写 CNDTR/CPAR/CMAR 后使能

// V2 (F4) 用软件触发：DMA_SxCR 的 EN 位
DMA2_Stream0->CR &= ~DMA_SxCR_DIR;  // DIR=00 (Per-to-Per) 或
DMA2_Stream0->CR |= 0 << DMA_SxCR_DIR_Pos; // 但实际上 F4 Mem2Mem
// 无法直接软件触发——需要用外设请求触发或使用 DMAMUX (G4+)
```

## 寄存器级调试

```c
// 基本状态检查
DMA2->LISR;          // 低 Stream 中断状态 (Stream 0~3)
DMA2->HISR;          // 高 Stream 中断状态 (Stream 4~7)
DMA2_Stream5->CR;    // 控制: EN, DBM, CT, CHSEL[2:0], PL[1:0]
DMA2_Stream5->NDTR;  // 剩余数量
DMA2_Stream5->PAR;   // 外设地址
DMA2_Stream5->M0AR;  // 内存地址 0
DMA2_Stream5->M1AR;  // 内存地址 1 (双缓冲)
DMA2_Stream5->FCR;   // FIFO 控制: FEIE, DMDIS, FTH[1:0]

// JLink Commander 调试
/*
mem32 0x40026400 1    // DMA2 LISR
mem32 0x40026404 1    // DMA2 HISR
mem32 0x40026060 1    // DMA2_Stream5 CR
mem32 0x40026064 1    // DMA2_Stream5 NDTR
mem32 0x40026068 1    // DMA2_Stream5 PAR
mem32 0x4002606C 1    // DMA2_Stream5 M0AR
*/
```

## F1 (V1) DMA 寄存器

```c
// F1 DMA 使用 DMA_Channel_TypeDef (非 Stream)
DMA1_Channel5->CCR;    // 控制: EN, TCIE, HTIE, TEIE, DIR, CIRC, PINC, MINC
DMA1_Channel5->CNDTR;  // 剩余数量
DMA1_Channel5->CPAR;   // 外设地址
DMA1_Channel5->CMAR;   // 内存地址

// F1 无 FIFO / 无 DBM / 无 Stream 选择
// 中断标志在 ISR/IFCR 中，非 LISR/HISR
DMA1->ISR;   // 中断状态寄存器
DMA1->IFCR;  // 中断清除寄存器
```

## 系列差异速查

| 特性 | F1 (V1) | F4 (V2) | G4 (V2+DMAMUX) | H7 (V3) |
|------|---------|---------|---------------|---------|
| Stream 架构 | 无 | 8 Stream × 8 CH | 8 × 16 CH(DMAMUX) | 8 × 8 CH |
| FIFO | 无 | 4 字深 | 4 字深 | 4 字深 |
| 双缓冲 DBM | 无 | 有 | 有 | 有 |
| Mem2Mem | 有 | 无(需外设触发) | DMAMUX 可模拟 | Linked List |
| 数据宽度 | Byte/半字/字 | 同上 | 同上 | +64bit (MDMA) |
| Linked List | 无 | 无 | 无 | 有 |
| DMAMUX | 无 | 无 | 有 | 有(扩展) |
| MDMA | 无 | 无 | 无 | 有 |
| Cache 维护 | 无需 | 无需 | 无需 | 必须 |

## 边界定义

- **本 skill 不覆盖 MDMA 高级链接列表模式**（H7 专属，需参考 RM0433）
- **不覆盖 DMAMUX 同步/触发/请求生成器细节**（G4/H7 专属）
- **不重复 adc-module/uart-module/timer-module 中外设+DMA 的应用层代码**，仅覆盖 DMA 架构和配置原则
- DMA 请求映射表因型号繁多，给出典型值和查找方法而非完整清单
## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | DMA 架构 | 请求映射 | 双缓冲 |
|------|---------|---------|--------|
| STM32F1 | DMA1(7ch)+DMA2(5ch) | 固定通道映射 | 半传+循环 |
| STM32F4 | DMA1+DMA2(8stream) | Stream+通道选择 | 双缓冲(CT 标志) |
| STM32H7 | MDMA+BDMA+DMA1/2 | DMAMUX 可编程 | D-Cache 维护 |
| ESP32-S3 | GDMA | 自动路由 | 链式描述符 |
| ESP32(原版) | 无独立DMA | 内嵌I2S/SPI | 无 |

- 上游：`stm32-hal-development`（HAL 层 DMA 初始化规范）
- 下游：`adc-module`, `uart-module`, `spi-bus`, `timer-module`（外设+DMA 应用配置）
