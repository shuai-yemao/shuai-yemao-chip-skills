---
name: spi-bus
description: SPI 总线配置、驱动开发与故障排查。涵盖四种时序模式详解、STM32 HAL 状态机与 BSY 标志陷阱、NSS 管理（硬件/软件/脉冲模式）、DMA+Cache 一致性、Slave 模式 BSY 卡死恢复。当用户提到 SPI、SPI 总线、硬件 SPI、HAL SPI 卡死、BSY 标志、NSS 片选、CPOL CPHA、SPI 调试、SPI DMA、SPI 从机模式、W25Q SPI Flash 时使用。
version: "1.0.0"
---

# SPI 总线开发指南

> 总线级别的 SPI 知识与调试技能。
> 与 peripheral-driver（设备驱动开发）互补：peripheral-driver 关注"给挂在 SPI 上的设备写驱动"，
> 本 skill 关注"SPI 总线外设本身的配置、陷阱和调试"。

## 适用场景

- 配置 STM32 SPI 外设（四种模式、全双工/半双工、8/16 位）
- 排查 SPI_BSY 标志卡死、NSS 行为异常、DMA 传输异常
- NSS 片选设计决策（硬件 vs 软件 vs 脉冲模式）
- SPI Slave 模式开发（BSY 标志陷阱、中断处理）
- SPI + DMA 高吞吐传输（显示/LCD/DAC/ADC）
- 多设备同总线（独立 CS vs 菊花链）
- 高速 SPI 的信号完整性和时序问题

## 必要输入

- MCU 型号（F1/F4/H7 的 SPI 外设差异大，尤其是 H7 有全新寄存器集）
- SPI 实例号（SPI1/SPI2/SPI3...）
- 工作模式（Master/Slave）
- 目标设备支持的 SPI 模式（CPOL/CPHA，Mode 0~3）
- 数据帧格式（8bit / 16bit, MSB/LSB）
- 引脚分配（SCK/MISO/MOSI/NSS）

## SPI 协议核心要点

### 四种模式

| 模式 | CPOL | CPHA | 空闲 SCK | 数据采样 | 数据发送 | 常见设备 |
|------|------|------|---------|---------|---------|---------|
| 0 | 0 | 0 | 低 | 上升沿（第1边沿） | 下降沿（第2边沿） | W25Qxx, 多数 SPI Flash, 多数 LCD |
| 1 | 0 | 1 | 低 | 下降沿（第2边沿） | 上升沿（第1边沿） | 部分传感器 |
| 2 | 1 | 0 | 高 | 下降沿（第1边沿） | 上升沿（第2边沿） | 部分工业设备 |
| 3 | 1 | 1 | 高 | 上升沿（第2边沿） | 下降沿（第1边沿） | W25Qxx 也支持, 部分 SD 卡 |

**致命细节**：配置 CPOL/CPHA 后务必和从机数据手册逐位比对。一个小数位的偏差就会导致：
- 采样点错位 → 数据全部左移/右移 1 位
- W25Qxx 返回 `0xFF`（读 ID 全 F 通常是模式错误）
- 通信正常但数据错乱（CRC/Checksum 不通过）

### 全双工 vs 半双工

| 模式 | 线数 | MOSI | MISO | 场景 |
|------|------|------|------|------|
| 全双工 | 2数据线 | 主机输出 | 从机输出 | 标准 SPI，绝大多数设备 |
| 半双工 TX | 1数据线 | 双向 | — | D/A、单色 LED 驱动、部分寄存器写入 |
| 半双工 RX | 1数据线 | — | 双向 | A/D、触摸屏坐标读取 |

**核心约束**：SPI 是全双工协议——**每发送一个字节必然同时接收一个字节**。即使只读不写，也必须发送填充字节（dummy byte / 0x00）来产生时钟。

## STM32 HAL SPI 使用指南

### 三种传输模式

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| Polling | 简单，同步 | 阻塞 CPU | 低频、短数据、非实时 |
| IT | 不阻塞 | 中断频繁（每字节一次） | 常规短数据 |
| DMA | 极低 CPU 占用 | 需要管理 DMA 通道 | 大数据（>16 字节）、高速 |

### API 选择

| 操作 | Polling | IT | DMA |
|------|---------|----|-----|
| TX+RX (全双工) | `HAL_SPI_TransmitReceive` | `..._IT` | `..._DMA` |
| 只 TX | `HAL_SPI_Transmit` | `..._IT` | `..._DMA` |
| 只 RX | `HAL_SPI_Receive` | `..._IT` | `..._DMA` |

**关键建议**：
- **优先用 `TransmitReceive` 而不是分开的 `Transmit` + `Receive`**——省一次函数调用，减少 BSY 轮询问题
- **发送 dummy 读数据**：`HAL_SPI_TransmitReceive(&hspi, &dummy, rx_buf, len, timeout)` 一次完成

## NSS（片选）管理

### 终极建议
> **用 GPIO 软件控制，不要依赖硬件 NSS。**

### 三种方案对比

| 方案 | STM32 配置 | 工作方式 | 优缺点 |
|------|-----------|---------|--------|
| **GPIO 手动控制** ✅ | NSS 引脚配置为 GPIO 推挽输出，`SPI_NSS_SOFT` | 通信前 `CS_LOW()`，通信后 `CS_HIGH()` | 最稳定，完全可控。唯一推荐方案 |
| 硬件 NSS 输出 | `SPI_NSS_HARD_OUTPUT` + `NSSP=ENABLE` (H7) | SPI 硬件自动控制 | NSS 脉冲模式只在 H7/G4 等新品可用，F1/F4 上 NSS 与 SPE 绑定（SPE=1 时持续低电平） |
| 硬件 NSS 输入 | `SPI_NSS_HARD_INPUT` | 多主机竞争检测 | 多主机冲突时自动切从机，但很少用 |

### 硬件 NSS 行为（逐系列）

| 系列 | 硬件 NSS 输出行为 | 禁用 SPE 后 NSS 状态 |
|------|-----------------|-------------------|
| STM32F1/F4 | NSS 随 SPE=1 持续低电平，不会在每个事务后自动释放 | 三态（高阻），不是推挽高电平 |
| STM32H7/G4 | `NSSP=ENABLE` 时每个 SPI 帧后自动脉冲（高→低→高） | 可配置 `MasterKeepIOState` 保持驱动状态 |

### GPIO 手动控制最佳实践

```c
/* 手动 NSS 控制 — 标准模式 */
#define CS_LOW()   HAL_GPIO_WritePin(CS_GPIO_Port, CS_Pin, GPIO_PIN_RESET)
#define CS_HIGH()  HAL_GPIO_WritePin(CS_GPIO_Port, CS_Pin, GPIO_PIN_SET)

void spi_write_read(SPI_HandleTypeDef *hspi, uint8_t *tx, uint8_t *rx, uint16_t len)
{
    CS_LOW();
    delay_us(1);  // tCSS: 片选建立时间，至少半个 SCK 周期
    HAL_SPI_TransmitReceive(hspi, tx, rx, len, timeout);
    // 对于 DMA 模式：等待传输完成回调再释放 CS！
    // HAL_SPI_TransmitReceive_DMA 是异步的！
    CS_HIGH();
    delay_us(1);  // tCSH: 片选保持时间
}
```

**DMA 模式下 CS 释放时机**：
```c
/* ─── 错误 ─── */
CS_LOW();
HAL_SPI_TransmitReceive_DMA(&hspi, tx, rx, len, timeout);
CS_HIGH();  // [X] DMA 还没完成就拉高了！

/* ─── 正确 ─── */
volatile uint8_t spi_dma_done = 0;

void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi) {
    if (hspi->Instance == SPI1) {
        spi_dma_done = 1;
    }
}

CS_LOW();
HAL_SPI_TransmitReceive_DMA(&hspi, tx, rx, len, timeout);
while (!spi_dma_done);  // 等待完成
CS_HIGH();
spi_dma_done = 0;
```

## 常见陷阱与解决方案

### BSY 标志陷阱

| 现象 | 根因 | 解决方案 |
|------|------|---------|
| SPI "卡死"，BSY 标志一直为 1 | 从机缺少 SCK、NSS 意外释放、传输中断 | 用 RXNE 判断传输完成，替代 BSY 轮询 |
| F1/F4 从机模式下 BSY 永远不释放 | 硬件设计缺陷，BSY 在从机模式下不可靠 | 1) `__HAL_RCC_SPI1_FORCE_RESET()` + `RELEASE_RESET()` 硬复位；2) 用 RXNE/TXE 标志替代 |
| 主机 BSY 在传输完成后仍为 1 | SPI 未完全禁能前 BSY 保护 | 调用 `HAL_SPI_DeInit()` 或先 Disable 再 Enable |
| NSS 被释放后 BSY 仍然为 1 | Slave 内部状态机丢失时钟计数 | 主机多送 1 字节 dummy clock 释放从机状态机 |

### SPI BSY 恢复代码（Slave 模式卡死）
```c
/* SPI 外设硬复位（唯一可靠的 BSY 恢复方式） */
void spi_hard_reset(SPI_HandleTypeDef *hspi)
{
    if (hspi->Instance == SPI1) {
        __HAL_RCC_SPI1_FORCE_RESET();
        __HAL_RCC_SPI1_RELEASE_RESET();
    } else if (hspi->Instance == SPI2) {
        __HAL_RCC_SPI2_FORCE_RESET();
        __HAL_RCC_SPI2_RELEASE_RESET();
    }
    // 注意：外设寄存器全部复位后，需要重新 HAL_SPI_Init()
}
```

### DMA + SPI 缓存一致性（STM32H7 必读）

H7 系列 AXI SRAM 默认使能 D-Cache。DMA 直接访问内存绕过 Cache，导致：

```c
/* 问题：CPU 写 tx_buf 可能在 Cache 中，DMA 读到的却是旧数据 */
uint8_t tx_buf[32] = {0x01, 0x02, 0x03};
HAL_SPI_TransmitReceive_DMA(&hspi, tx_buf, rx_buf, 32, timeout);
// tx_buf 在 Cache 中还没写回内存，DMA 发送了脏数据（通常是 0x00 或旧值）

/* 修复：传输前 Clean Cache，完成后 Invalidate Cache */
SCB_CleanDCache_by_Addr((uint32_t *)tx_buf, 32);  // 写回内存
HAL_SPI_TransmitReceive_DMA(&hspi, tx_buf, rx_buf, 32, timeout);
while (!spi_dma_done);
SCB_InvalidateDCache_by_Addr((uint32_t *)rx_buf, 32);   // 读最新数据
```

### NSS + DMA 时序错乱（经典 Bug）

**现象**：NSS 在 SPI DMA 传输中途提前释放（SCK 还在跑，CS 已经高了）。

**原因**：`HAL_SPI_TransmitReceive_DMA()` 返回后，用户代码立即拉高了 CS，但 DMA 还在后台传输。

**修复**：在传输完成回调中释放 CS，见上面 DMA CS 控制示例。

### SPI 引脚复用冲突

| 引脚 | 默认功能 | 冲突来源 | 排查方法 |
|------|---------|---------|---------|
| PB3 | SPI1_SCK / JTDO | JTAG 调试接口 | 禁用 JTAG（`GPIO_AF_DISABLE`）或只用 SWD |
| PB4 | SPI1_MISO / NJTRST | JTAG 调试接口 | 同上 |
| PA15 | SPI1_NSS / JTDI | JTAG 调试接口 | 同上 |
| PA4 | SPI1_NSS / DAC_OUT | DAC 输出 | CubeMX 中关闭 DAC |

**CubeMX 配置**：在 `Pinout & Configuration → System Core → SYS → Debug` 中选 `Serial Wire`（禁用 JTAG，保留 SWD）。如果用了 PB3/PB4/PA15 做 SPI，必须这么做。

## SPI 调试方法

### 寄存器级检查（J-Link halt 时）
```c
/* SPI 状态寄存器检查 */
uint32_t sr = SPI1->SR;  // 或 SPI_SR

// 关键位: BSY(7), TXE(1), RXNE(0), MODF(5), OVR(6), FRE(8)
// ─ 如果 RXNE=0 且 BSY=0 → 传输已完成
// ─ 如果 BSY=1 且 RXNE=0 → 卡住了
// ─ 如果 OVR=1 → 发生过载（RX 未及时读取）
```

### MISO/MOSI 回环测试

```c
/* 硬件接线验证：短路 MOSI 和 MISO */
uint8_t tx = 0xA5;
uint8_t rx = 0x00;
HAL_SPI_TransmitReceive(&hspi, &tx, &rx, 1, 100);
// 如果接线正确（短接），rx 应该等于 0xA5
// 否则排查引脚配置和硬件连接
```

### 读 ID 全 0xFF 排查清单

1. [ ] GPIO 复用功能是否正确（AF 号查手册）
2. [ ] CPOL/CPHA 是否匹配从机要求的 Mode
3. [ ] CS 拉低/拉高时序是否正确
4. [ ] 时钟频率是否超过从机规格
5. [ ] 从机是否上电、脚位是否虚焊
6. [ ] MISO/MOSI 是否接反
7. [ ] 回环测试验证硬件通路

## 平台差异速查

| 系列 | SPI 外设 | BSY Bug | 注意点 |
|------|---------|---------|--------|
| STM32F1 | V1（经典） | Slave 模式 BSY 不可靠 | Errata 明确标注 BSY 问题，用 RXNE 替代 |
| STM32F4 | V1 | 同 F1 | F4/F7 的 BSY 问题在 Errata 有描述 |
| STM32G0/G4 | V2（新） | 改进但仍有 | NSSP 脉冲模式可用，需配置 `MasterKeepIOState` |
| STM32H7 | V2（全新寄存器集 SPI_CFG1/2） | 无 BSY 硬件 bug | D-Cache 一致性是主要风险，新寄存器操作方式不同 |
| STM32L0/L4 | V1/V2 混合 | 与系列相关 | 查具体型号参考手册 |

## 边界定义

### 不该激活
- 用户需要的是给 SPI 设备写驱动（Flash/传感器/LCD 等）→ 使用 `peripheral-driver`
- 用户需要的是通用 STM32 HAL 开发指导 → 使用 `stm32-hal-development`
- 用户需要的是 I2C/CAN/Modbus 等其他总线调试 → 使用对应 skill

### 不该做
- **禁止**在 SPI 中断回调中调用阻塞式 HAL 函数
- **禁止**在 SPI DMA 传输中在完成前释放 NSS/CS
- **禁止**在 H7 上使用 DMA+SPI 而不处理 D-Cache 一致性
- **禁止**在 Slave 模式下依赖 BSY 标志判断传输完成

### 不该碰
- **不触碰** CubeMX 生成的 SPI 初始化代码（`.ioc` 修改优先）
- **不触碰** DMA 通道分配（CubeMX 自动处理，用户只需配置缓冲区地址）
- **不触碰**中断优先级分组（NVIC 分组由 `HAL_Init()` 设置，统一管理）

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | 收发 API | 关键差异 |
|------|---------|---------|
| STM32 HAL | `HAL_SPI_TransmitReceive` | 状态机，F1 BSY bug(CR1 SPE 复位) |
| STM32 SPL | `SPI_I2S_SendData`+轮询 | 轮询 TXE/RXNE 标志 |
| STM32 寄存器 | `SPI1->DR = data` | 轮询 SR.TXE/SR.RXNE/SR.BSY |
| ESP-IDF | `spi_device_transmit` | 事务队列模式，自动 DMA |
| Arduino | `SPI.transfer(byte)` | 全双工单字节收发 |

## 交接关系
- 调试时：`serial-monitor`（输出调试日志）、`can-debug`（同名类似总线调试技能）

## 参考资料

- [references/spi-mode-selection.md](references/spi-mode-selection.md) — SPI 四种模式与 CPOL/CPHA 详解
- [references/spi-nss-management.md](references/spi-nss-management.md) — NSS 硬件/软件管理全面对比
- [references/spi-errata-workarounds.md](references/spi-errata-workarounds.md) — STM32 SPI Errata 与解决方案
