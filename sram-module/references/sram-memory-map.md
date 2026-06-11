# SRAM 内存映射速查表

## STM32F103

| 分区 | 起始 | 大小 | 总线 | DMA 可达 |
|------|------|------|------|---------|
| SRAM | 0x20000000 | 20KB/48KB/64KB | D-Bus/S-Bus | ✅ |

F103 只有单一 SRAM 块。

## STM32F411CEU6

| 分区 | 起始 | 大小 | 总线 | DMA 可达 |
|------|------|------|------|---------|
| SRAM1 | 0x20000000 | 96KB | D-Bus | ✅ |
| SRAM2 | 0x20018000 | 32KB | D-Bus | ✅ |
| **总计** | | **128KB** | | |

## STM32F407ZGT6

| 分区 | 起始 | 大小 | 总线 | DMA 可达 |
|------|------|------|------|---------|
| CCM | 0x10000000 | 64KB | D-Bus | ❌ (CPU only) |
| SRAM1 | 0x20000000 | 112KB | AHB | ✅ |
| SRAM2 | 0x2001C000 | 16KB | AHB | ✅ |
| BKPSRAM | 0x40024000 | 4KB | APB | ✅ (外设域) |
| **总计** | | **192KB** | | |

## STM32H743

| 分区 | 起始 | 大小 | 总线 | DMA 可达 | Cache |
|------|------|------|------|---------|-------|
| ITCM | 0x00000000 | 64KB | I-Bus | ❌ | 无 |
| DTCM | 0x20000000 | 128KB | D-Bus | ❌ | 无 |
| AXI SRAM | 0x24000000 | 512KB | AXI | ✅ | D-Cache |
| SRAM1 | 0x30000000 | 128KB | AHB | ✅ | 无 |
| SRAM2 | 0x30020000 | 128KB | AHB | ✅ | 无 |
| SRAM3 | 0x30040000 | 32KB | AHB | ✅ | 无 |
| SRAM4 | 0x38000000 | 64KB | AHB (LP) | ✅ | 无 |
| BKPSRAM | 0x38800000 | 4KB | APB | ✅ | 无 |
| **总计** | | **~1.4MB** | | | |

## STM32G474

| 分区 | 起始 | 大小 | 总线 | DMA 可达 |
|------|------|------|------|---------|
| SRAM1 | 0x20000000 | 32KB | AHB | ✅ |
| SRAM2 | 0x20008000 | 16KB | AHB | ✅ (ECC) |
| **总计** | | **48KB** | | |

## STM32G0B1

| 分区 | 起始 | 大小 | 总线 | DMA 可达 |
|------|------|------|------|---------|
| SRAM | 0x20000000 | 144KB | AHB | ✅ |
| **总计** | | **144KB** | | |

## 自定义段声明速查

```c
// ––––– GCC ld –––––

// DMA 缓冲区段
__attribute__((section(".dma_buffer"), aligned(4)))
uint8_t dma_buf[1024];

// CCM RAM (F4)
__attribute__((section(".ccm_ram"), aligned(4)))
uint32_t fast_counter;

// AXI SRAM (H7)
__attribute__((section(".axi_sram"), aligned(32)))
uint8_t h7_axi_buf[2048];

// DTCM (H7 — 通常 DTCM 是默认 RAM，不需特殊声明)
// 但如需显式放在 DTCM:
__attribute__((section(".dtcm"), aligned(4)))
uint32_t critical_flag;

// ––––– Keil __attribute__ –––––
// IAR 类似，无显式段名的可用 #pragma location

// ––––– IAR –––––
// #pragma location = 0x20001000
// uint8_t my_buffer[256];
```

## 复位/STOP 后 SRAM 保持情况

| 状态 | F4 SRAM1/2 | F4 CCM | H7 AXI | H7 DTCM | H7 SRAM4 | BKPSRAM |
|------|-----------|--------|--------|---------|---------|---------|
| 上电复位 | 随机 | 随机 | 随机 | 随机 | 随机 | 保持 |
| 系统复位 | 保持 (✔) | 保持 (✔) | 保持 | 保持 | 保持 | 保持 |
| STOP (F4) | 保持 | 保持 | — | — | — | 保持 |
| STOP1 (H7) | 保持 | — | 保持 | 保持 | 保持 | 保持 |
| STOP2 (H7) | 关 | — | 关 | 可关 | 保持 | 保持 |
| STANDBY | 丢失 | 丢失 | 丢失 | 丢失 | 丢失 | 保持 |
| VBAT | — | — | — | — | — | 保持 |

> **系统复位**（非上电复位）时 SRAM 内容保持。调试中热复位后，SRAM 中的全局变量保留之前的值——这是常见陷阱：不要依赖复位后的变量初始值。
