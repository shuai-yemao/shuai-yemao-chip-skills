# DMA 配置详解

## 数据宽度与对齐规则

### 单次传输的数据单元

```c
// 数据宽度决定每次传输的单元大小（字节数）
PeriphDataAlignment:  BYTE=1, HALFWORD=2, WORD=4
MemDataAlignment:     BYTE=1, HALFWORD=2, WORD=4
```

### 对齐规则

| PeriphData | MemData | FIFO Mode | 行为 | 典型场景 |
|-----------|---------|-----------|------|---------|
| BYTE | BYTE | Direct | 1:1 直传 | UART 接收 |
| BYTE | HALFWORD | FIFO | 每 2 字节打包为 1 半字 | 串行 ADC 读数 |
| BYTE | WORD | FIFO | 每 4 字节打包为 1 字 | 串行 Flash 读取 |
| HALFWORD | HALFWORD | Direct | 1:1 直传 | ADC 读数 |
| HALFWORD | WORD | FIFO | 每 2 半字打包为 1 字 | 16bit DAC 转 32bit |
| WORD | WORD | Direct | 1:1 直传 | 内部 SRAM 搬运 |

### 禁则

```c
// ❌ PeriphDataAlignment > MemDataAlignment 会导致数据丢失
//   BYTE → HALFWORD ✅ (FIFO 打包)
//   BYTE → WORD     ✅ (FIFO 打包)
//   HALFWORD → BYTE ❌ (高字节丢失)
//   WORD → BYTE     ❌ (3/4 数据丢失)
//   WORD → HALFWORD ❌ (高 16 位丢失)

// 特别注意：Direct 模式下 PeriphData 必须等于 MemData
// FIFO 模式下 PeriphData ≤ MemData
```

## Burst 传输

### Burst 配置

```c
hdma.Init.PeriphBurst = DMA_PBURST_SINGLE;  // 或 INCR4/INCR8/INCR16
hdma.Init.MemBurst = DMA_MBURST_SINGLE;
```

| Burst 模式 | 宏 | 描述 | 适用 |
|-----------|-----|------|------|
| Single | `DMA_PBURST_SINGLE` | 每次 1 个数据单元 | 通用，FIFO 无限制 |
| INCR4 | `DMA_PBURST_INCR4` | 4 个突发 | 高速外设（SDIO/FMC） |
| INCR8 | `DMA_PBURST_INCR8` | 8 个突发 | 高速外设 |
| INCR16 | `DMA_PBURST_INCR16` | 16 个突发 | 高速外设 |

### Burst 重要限制

```c
// 1. Burst 只能在 FIFO 模式下使用（Direct Mode 不可用）
// 2. Burst 模式下源/目标地址必须对齐 Burst 大小
//    例：INCR4_WORD → 地址必须 16 字节对齐
// 3. NDTR 必须是 Burst 大小的整数倍
//    例：INCR4_BYTE → NDTR % 4 = 0
// 4. Burst 与 DBM 配合使用时需注意 CT 切换边界
```

## 优先级仲裁

### V2 (F4/H7) Stream 优先级

```c
hdma.Init.Priority = DMA_PRIORITY_LOW;
// 可选: LOW, MEDIUM, HIGH, VERY_HIGH
```

仲裁顺序：
1. **软件优先级** (PL[1:0]): VERY_HIGH > HIGH > MEDIUM > LOW
2. **硬件 Stream 编号**: 同优先级下 Stream 编号小的优先 (Stream0 > Stream1 > ...)

### V1 (F1) 通道优先级

```c
DMA1_Channel5->CCR |= DMA_CCR_PL;  // PL[1:0]: 00=LOW, 01=MEDIUM, 10=HIGH, 11=VERY_HIGH
```

同 V2 仲裁顺序，通道编号小的优先。

## 外设流控 (PFC)

### 配置

```c
hdma.Init.Mode = DMA_PFCTRL;
// 外设控制传输结束，DMA 不自停
// 典型：SDIO 数据传输
```

### 与 Normal 的区别

| 模式 | 何时停止 | 谁控制 | 典型外设 |
|------|---------|--------|---------|
| Normal | NDTR=0 | DMA | UART/SPI/ADC |
| PFC | 外设发停止信号 | 外设 | SDIO/USB |
| Circular | 永不停止（循环） | DMA | ADC 连续 |

## DBM 详细配置

### 初始化顺序

```c
// 1. 配置基本参数（不使能 DMA）
hdma.Init.Mode = DMA_CIRCULAR;  // DBM 必须 Circular
// 其他基本参数...

HAL_DMA_Init(&hdma);

// 2. 单独设置双缓冲
hdma.Instance->CR |= DMA_SxCR_DBM;

// 3. 设置两个缓冲区地址
hdma.Instance->M0AR = (uint32_t)buf0;
hdma.Instance->M1AR = (uint32_t)buf1;

// 4. 设置传输数量
hdma.Instance->NDTR = BUF_SIZE;

// 5. 使能
hdma.Instance->CR |= DMA_SxCR_EN;
```

### CT 标志使用

```c
// CT (Current Target) = DMA_SxCR 的 bit 19
// CT=0: DMA 当前写 M0AR（用户可安全读 M1AR）
// CT=1: DMA 当前写 M1AR（用户可安全读 M0AR）

// 在 TC 中断中的标准处理模式：
void HAL_DMA_TC_Callback(DMA_HandleTypeDef *hdma)
{
    if (hdma->Instance->CR & DMA_SxCR_CT) {
        // CT=1: DMA 刚完成 M0AR 的写入，已切换到 M1AR
        // 用户处理 buf0 的数据
        process_buffer(buf0, BUF_SIZE);
    } else {
        // CT=0: DMA 刚完成 M1AR 的写入，已切换到 M0AR
        // 用户处理 buf1 的数据
        process_buffer(buf1, BUF_SIZE);
    }
}

// 注意：CT 在 TC 中断中已翻转
// 中断触发时 DMA 已完成当前缓冲区的写入并切换了 CT
```

### Ping-Pong 缓冲的大小要求

```c
// DMA 双缓冲要求两个缓冲区物理连续还是独立？
// 答：独立——M0AR 和 M1AR 可以指向任意地址
// 不需要物理连续、不需要页对齐

// 但建议：
// 1. 缓冲区大小相同
// 2. 地址不重叠
// 3. 对齐到总线宽度（H7 建议 32 字节对齐）
```

## H7 DMA + Cache 完整示例

### Clean + Invalidate 流程

```c
#define BUF_SIZE      256
#define BUF_SIZE_ALIGN  ((BUF_SIZE + 31) / 32 * 32)  // 对齐到 Cache Line

ALIGN_32BYTES uint8_t tx_buf[BUF_SIZE_ALIGN];
ALIGN_32BYTES uint8_t rx_buf[BUF_SIZE_ALIGN];

// CPU → DMA（CPU 写完数据给 DMA 发送）
void send_via_dma(uint8_t *data, uint32_t len)
{
    memcpy(tx_buf, data, len);
    // ⚠️ 必须 Clean：将 Cache 中的 tx_buf 写回 SRAM
    SCB_CleanDCache_by_Addr((uint32_t *)tx_buf, BUF_SIZE_ALIGN);
    HAL_UART_Transmit_DMA(&huart1, tx_buf, len);
}

// DMA → CPU（DMA 接收后 CPU 读取）
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    // ⚠️ 必须 Invalidate：抛弃 Cache 中旧的 rx_buf，下次从 SRAM 读
    SCB_InvalidateDCache_by_Addr((uint32_t *)rx_buf, BUF_SIZE_ALIGN);
    process(rx_buf);
    // 重新启动接收
    HAL_UART_Receive_DMA(&huart1, rx_buf, BUF_SIZE);
}

// DMA 双缓冲 + Cache
#define ALIGN_32BYTES __attribute__((aligned(32)))
ALIGN_32BYTES uint8_t dma_buf0[BUF_SIZE_ALIGN];
ALIGN_32BYTES uint8_t dma_buf1[BUF_SIZE_ALIGN];

void HAL_DMA_TC_Callback(DMA_HandleTypeDef *hdma)
{
    uint8_t *ready_buf;

    if (hdma->Instance->CR & DMA_SxCR_CT) {
        ready_buf = dma_buf0;  // CT=1 → buf0 就绪
    } else {
        ready_buf = dma_buf1;  // CT=0 → buf1 就绪
    }

    // ⚠️ 必须 Invalidate
    SCB_InvalidateDCache_by_Addr((uint32_t *)ready_buf, BUF_SIZE_ALIGN);
    process(ready_buf);
}
```

## DMA 传输公式

### 带宽计算

```
传输速率 = fHCLK / (DMA 存取周期数)
典型 DMA 存取周期: Direct Mode = 4 HCLK, FIFO Mode = 5~7 HCLK

有效带宽 ≈ 数据宽度(字节) × NDTR / 传输时间

示例:
HCLK=100MHz, Direct Mode, WORD传输, 单次 4 HCLK
理论峰值 = 100MHz / 4 × 4B = 100 MB/s
实际带宽受总线仲裁影响，约为 60~80%
```

### 延迟

```
DMA 启动延迟 = 总线仲裁等待 (通常 1~6 HCLK)
传输总时间 ≈ (NDTR × 每次存取周期) + 启动延迟

MDMA (H7):
  - AXI: 64bit 传输, 单次 1 HCLK
  - 理论峰值: 100MHz × 8B = 800 MB/s (AXI)
```
