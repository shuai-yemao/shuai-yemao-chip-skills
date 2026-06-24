# STM32 SPI Errata 与解决方案

## F1/F4 系列已知 Errata

| Errata ID | 描述 | 影响 | 解决方案 |
|-----------|------|------|---------|
| 2.8.x | BSY 标志在从机模式下可能永远不释放 | Slave 通信卡死 | 1) 程序检查 RXNE/TXE 替代 BSY；2) RCC 硬复位 |
| 2.8.4 | 在 SPE=0 后 BSY 可能仍为 1 | 无法重新配置 SPI | 等待至少 2 个 APB 时钟再操作 |
| — | MODF 错误在主模式下误触发 | 通信中断 | 设 SSM=1 + SSI=1 避免 MODF 检测 |

## BSY 卡死完全恢复方案

### 方法一：RCC 硬复位（最可靠）
```c
__HAL_RCC_SPI1_FORCE_RESET();
__HAL_RCC_SPI1_RELEASE_RESET();
// 之后必须重新 HAL_SPI_Init() 和 GPIO 初始化
```

### 方法二：外灌时钟（从机模式无主机时）
```c
/* 用 GPIO 向 SCK 引脚发 8 个脉冲释放从机 BSY */
void spi_slave_clock_pump(GPIO_TypeDef *SCK_PORT, uint16_t SCK_PIN)
{
    for (int i = 0; i < 8; i++) {
        HAL_GPIO_WritePin(SCK_PORT, SCK_PIN, GPIO_PIN_SET);
        delay_us(1);
        HAL_GPIO_WritePin(SCK_PORT, SCK_PIN, GPIO_PIN_RESET);
        delay_us(1);
    }
}
```

### 方法三：检查是否真的是"卡死"
```c
// BSY=1 不一定代表卡死——SPI 在连续传输时 BSY=1 是正常的
// 真正的卡死：BSY=1 但 TXE=1（TX FIFO 空，没数据要发）
// 正常繁忙：BSY=1 且 TXE=0（还有数据在 FIFO 里）
if ((SPI1->SR & SPI_SR_BSY) && (SPI1->SR & SPI_SR_TXE)) {
    // 真卡死：总线忙但没东西要发
    spi_hard_reset(&hspi1);
}
```

## DMA + SPI 汇总问题

### NSS 与 DMA 时序问题
根源：DMA 传输是异步的，HAL 函数返回不代表传输完成。
见 SKILL.md 中 "DMA 模式下 CS 释放时机" 部分。

### DMA 通道抢占（多 SPI 同时 DMA 时）
F4/F7 的 DMA 仲裁是轮询制的。多 SPI 同时 DMA 时可能出现 FIFO 错误 (FE)：
```c
// 如果 DMA FIFO 禁用了 HAL 仍然报 FE 错误
// 在 HAL 源码中增加 FIFO 模式判断：
if (hdma->Init.FIFOMode != DMA_FIFOMODE_DISABLE) {
    hdma->ErrorCode |= HAL_DMA_ERROR_FE;
}
```

### H7 D-Cache 问题
H7 的 D-Cache 默认使能，DMA 绕过 Cache。key 点：
- Transmit 前：`SCB_CleanDCache_by_Addr`
- Receive 后：`SCB_InvalidateDCache_by_Addr`
- 或缓冲区放 DTCM（D-Cache 不缓存 DTCM 区域）
