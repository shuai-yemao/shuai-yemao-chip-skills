---
name: sram-module
version: "1.0.0"
description: "STM32 内部 SRAM 存储器配置与使用指南。涵盖 SRAM 架构（SRAM1/2/3/CCM/DTCM/ITCM）、各系列 SRAM 布局与映射、DMA 缓冲区定位、备份 SRAM、低功耗保持、ECC 保护、堆栈配置、链接脚本调整、内存性能优化。当用户提到 SRAM、内部 SRAM、内存、RAM、CCM RAM、DTCM、ITCM、备份 SRAM、BKPSRAM、堆栈配置、链接脚本、ld 文件、内存映射、DMA 缓冲区放置、SRAM ECC、SRAM 保持、STOP 模式 RAM、SRAM 性能、零等待 SRAM、内存不足、RAM 溢出、SRAM 分区、TCM RAM、AXI SRAM、SRAM 地址时使用。"
---

# SRAM 模块开发指南

## SRAM 架构概览

### 各系列 SRAM 布局

| 系列 | SRAM1 | SRAM2 | SRAM3/CCM | DTCM | ITCM | AXI SRAM | 总计 |
|------|-------|-------|-----------|------|------|---------|------|
| F103 (RCT6) | 48KB | — | — | — | — | — | 48KB |
| F103 (VET6) | 64KB | — | — | — | — | — | 64KB |
| F411 | 96KB | 32KB | — | — | — | — | 128KB |
| F407 | 112KB | 16KB | 64KB CCM | — | — | — | 192KB |
| H743 | 512KB | — | — | 128KB | 64KB | 1MB | ~1.4MB |
| G474 | 32KB | 16KB | — | — | — | — | 48KB |
| G070 | 36KB | — | — | — | — | — | 36KB |

> 完整映射和地址见 `references/sram-memory-map.md`
> GCC ld/Keil scatter 脚本配置见 `references/sram-config-guide.md`

### F4 SRAM 分区

```
STM32F411CEU6 (128KB)
+------------------+ 0x20000000
|    SRAM1 96KB    |  主 SRAM（D-Bus）
+------------------+ 0x20018000
|    SRAM2 32KB    |  辅 SRAM（D-Bus）
+------------------+ 0x20020000

STM32F407ZGT6 (192KB)
+------------------+ 0x10000000
|  CCM RAM 64KB    |  CPU 专用（D-Bus，无 DMA）
+------------------+ 0x10010000
+------------------+ 0x20000000
|   SRAM1 112KB    |  主 SRAM（AHB 总线）
+------------------+ 0x2001C000
|   SRAM2 16KB     |  辅 SRAM（AHB 总线）
+------------------+ 0x20020000
```

### H7 SRAM 分区

```
STM32H743 (1MB AXI SRAM + 128KB DTCM + 64KB ITCM + ...)
+------------------+ 0x00000000
|  ITCM 64KB       |  指令紧耦合（CPU 专用）
+------------------+ 0x00010000
+------------------+ 0x20000000
|  DTCM 128KB      |  数据紧耦合（CPU 专用）
+------------------+ 0x20020000
+------------------+ 0x24000000
|  AXI SRAM 512KB  |  AXI 总线（DMA 可访问）
+------------------+ 0x24080000
|  SRAM1           |  AHB 总线
+------------------+ 0x30000000
|  SRAM2 288KB     |  AHB 总线
+------------------+ 0x30048000
|  SRAM3 32KB      |  AHB 总线
+------------------+ 0x30050000
|  SRAM4 64KB      |  低功耗域（LP 域，STOP 保持）
+------------------+ 0x38000000
|  Backup SRAM 4KB |  VBAT 供电
+------------------+ 0x38800000
```

## SRAM 的主要用途

| 分区 | 特点 | 适合用途 | 注意 |
|------|------|---------|------|
| SRAM1 | 标准 AHB/总线访问 | 堆/栈/全局变量 | DMA 可访问 |
| SRAM2 | 标准 AHB 访问 | DMA 缓冲/变量 | 部分系列 STOP 保持 |
| CCM RAM (F4) | CPU 专用 (D-Bus) | 时间关键代码/ISR 栈 | DMA 不可访问 |
| DTCM (H7) | CPU 专用 | 栈/频繁读写变量 | DMA 不可访问 |
| ITCM (H7) | CPU 专用 (I-Bus) | 时间关键代码 | 数据访问需注意 |
| AXI SRAM (H7) | AXI 总线 | 大缓冲区/FB | 需 Cache 维护 |
| 备份 SRAM | VBAT 供电 | 掉电保持数据 | 容量小 (4KB) |

## SRAM 初始化与默认状态

### 上电初始化

```c
// 上电后 SRAM 内容随机（不确定值）
// 复位不影响 SRAM 内容（仅 CPU 寄存器复位）
// 调试器附着时一般不会清除 SRAM

// 建议：在 main 入口清零关键变量而非信任上电值
memset(__IO_BEGIN, 0, __IO_END - __IO_BEGIN);  // .bss 段由启动文件自动清零
// .data 段由启动文件从 Flash 复制
```

### 调试器附着后 SRAM 内容

```c
// J-Link / ST-Link halt 后，SRAM 内容保持
// 可读取任意地址检查变量值

// JLink Commander:
//   mem32 0x20000000 64     // 读 SRAM1 前 256 字节
//   mem32 0x20018000 32     // 读 SRAM2 前 128 字节
```

## DMA 缓冲区放置

### 基本原则

```c
// DMA 缓冲区必须放在 DMA 可访问的 SRAM 区域
// F4: SRAM1/SRAM2 ✅ | CCM RAM ❌
// H7: AXI SRAM/SRAM1~4 ✅ | DTCM/ITCM ❌
```

### F4 推荐布局

```c
// 大缓冲区放在 SRAM2（离 CPU 堆栈远，DMA/CPU 冲突少）
// SRAM1: 堆/栈/全局变量
// SRAM2: DMA 缓冲区

// 链接脚本语法 (GCC ld)：
/*
MEMORY
{
    RAM1 (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
    RAM2 (rw)  : ORIGIN = 0x20018000, LENGTH = 32K
}

SECTIONS
{
    .dma_buffers (NOLOAD) : {
        *(.dma_buffer)
    } > RAM2

    .data : {
        *(.data)
    } > RAM1 AT > FLASH
}
*/

// 在 C 代码中指定段：
uint8_t uart_rx_buf[1024] __attribute__((section(".dma_buffer"), aligned(4)));
uint8_t adc_buf[512] __attribute__((section(".dma_buffer"), aligned(4)));
```

### H7 推荐布局

```c
// H7 AXI SRAM 做 DMA 缓冲区但需 Cache 维护
// 或使用 SRAM1/SRAM2（AHB，无 Cache）

// 方法 1: AXI SRAM + Cache 维护
uint8_t dma_buf[1024] __attribute__((section(".axi_sram"), aligned(32)));
// 每次 DMA TX 前: SCB_CleanDCache_by_Addr(dma_buf, 1024);
// 每次 DMA RX 后: SCB_InvalidateDCache_by_Addr(dma_buf, 1024);

// 方法 2: SRAM4（LP 域，无需 Cache 维护但在低功耗域）
uint8_t dma_buf[1024] __attribute__((section(".sram4"), aligned(4)));
```

### CCM RAM (F4) 用法

```c
// CCM RAM 只能由 CPU 访问（DMA 不可达）
// 地址: 0x10000000

// GCC ld 语法:
/*
MEMORY
{
    CCM (rwx) : ORIGIN = 0x10000000, LENGTH = 64K
    RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K
}

SECTIONS
{
    .ccm_data : {
        *(.ccm_ram)
    } > CCM
}
*/

// 适合放在 CCM RAM 的内容：
// - 中断栈 (ISR stack)
// - 频繁读写变量 (循环计数、状态标志)
// - 时间关键代码

// 声明：
uint32_t critical_var __attribute__((section(".ccm_ram")));

// 不适合放在 CCM RAM 的内容：
// - DMA 缓冲区 ❌
// - 被其他总线主机访问的变量 ❌
```

## 备份 SRAM (BKPSRAM)

### 特性

```c
// 备份 SRAM 由 VBAT 引脚供电（主电源 VDD 掉电时内容保持）
// 写入前需要解锁 PWR 域

// 容量：F4 = 4KB, H7 = 4KB, G4 = 无

// 地址：F4: 0x40024000 (AHB1), H7: 0x38800000
// 注意：BKPSRAM 地址在外设域而非 SRAM 域
```

### 使用示例

```c
// 1. 使能备份 SRAM 时钟
__HAL_RCC_BKPSRAM_CLK_ENABLE();

// 2. 使能备份 SRAM 写访问
HAL_PWR_EnableBkUpAccess();   // DBP bit in PWR_CR
__HAL_RCC_PWR_CLK_ENABLE();

// 3. 写入和读取
volatile uint32_t *bkpsram = (uint32_t *)0x40024000;
bkpsram[0] = 0xDEADBEEF;     // 写入
uint32_t val = bkpsram[0];    // 读取

// 4. 保持模式
// 在 STANDBY 模式下，默认 BKPSRAM 保持
// 如需节省功耗，可关闭：
HAL_PWR_DisableBkUpReg();     // 关闭备份域稳压器
```

## 低功耗模式下的 SRAM 保持

| 低功耗模式 | SRAM1 | SRAM2 | CCM (F4) | BKPSRAM | DTCM (H7) |
|-----------|-------|-------|----------|---------|-----------|
| SLEEP | 保持 | 保持 | 保持 | 保持 | 保持 |
| STOP (F4) | 保持 | 保持（可关） | 保持 | 保持 | — |
| STOP (H7) | 可关 | 保持 | — | 保持 | 可关 |
| STANDBY | 丢失 | 丢失 | 丢失 | 保持 | 丢失 |
| VBAT | — | — | — | 保持 | — |

```c
// STOP 模式下关闭 SRAM2 以省电（F4）
HAL_PWREx_EnableFlashPowerDown();  // Flash 掉电
// SRAM2 默认保持
// 如需关闭，需要在进入 STOP 之前设寄存器

// H7 STOP 模式下保留哪个 SRAM 域取决于 STOP 等级：
// STOP1: 大部分 SRAM 保持 ~ 150µA
// STOP2: 仅 SRAM4 保持 ~ 3µA (H7)
// STANDBY: 仅 BKPSRAM 保持 ~ 0.3µA
```

## 堆栈配置

### 栈大小估算

```c
// 启动文件中的栈设置（startup_stm32f411xe.s）：
// Stack_Size EQU 0x400  → 1KB（CubeMX 默认）
// Heap_Size  EQU 0x200  → 512B

// 实际需求取决于：
// 1. 最大函数调用深度 × 当前函数栈帧大小
// 2. ISR 嵌套深度 × 每个 ISR 栈帧
// 3. printf/sprintf 调用栈（~500B~1KB）
// 4. FreeRTOS 每个任务独立栈
```

### 栈位置选择

```c
// 链接脚本中栈通常放在 SRAM1 末尾
// 汇编启动文件：
//   LDR R0, =_estack    // _estack = SRAM1 起始 + SRAM1 大小

// 对于 F4 有 CCM RAM 的场景，可把 ISR 栈放在 CCM：
// 修改启动文件：
//   ISR_Stack_Size EQU 0x400
//   ISR_Stack      EQU 0x10000000 + ISR_Stack_Size  // CCM 末尾
//   ISR_Stack_MEM  AREA    ISR_STACK, NOINIT, READWRITE, ALIGN=3
//   ISR_Stack_MEM  SPACE   ISR_Stack_Size

// 注意：修改启动文件需要修改 Reset_Handler 中 MSP 初始化
```

### 堆性能优化

```c
// 堆在 SRAM 中，malloc/free 的性能取决于堆管理算法
// CubeMX 使用 newlib nano: _sbrk 管理堆

// 常见问题：堆碎片化
// 症状：多次 malloc/free 后获得很大块可用但 malloc 失败
// 方案：减少动态分配，使用静态分配/内存池

// 简单内存池示例：
#define POOL_SIZE 10
#define BLOCK_SIZE 64

static uint8_t pool[POOL_SIZE][BLOCK_SIZE];
static uint8_t pool_used[POOL_SIZE];

void *pool_alloc(void)
{
    for (int i = 0; i < POOL_SIZE; i++) {
        if (!pool_used[i]) {
            pool_used[i] = 1;
            return pool[i];
        }
    }
    return NULL;
}

void pool_free(void *ptr)
{
    for (int i = 0; i < POOL_SIZE; i++) {
        if (pool[i] == ptr) {
            pool_used[i] = 0;
            return;
        }
    }
}
```

## SRAM ECC (H7/G4)

### ECC 特性

```c
// H7: AXI SRAM 和 DTCM 支持 8-bit ECC
// G4: SRAM2 支持 ECC (SEC-DED)
// 每 64bit 数据 + 8bit ECC 码

// ECC 可纠正 1-bit 错误 (SEC)
// ECC 可检测 2-bit 错误 (DED) → 触发 NMI 或 HardFault

// 上电时 ECC 校验通过 = 正确
// 复位时 SRAM 内容保持但 ECC 码可能无效
// 所以复位后第一次读未初始化的 SRAM 可能触发 ECC 错误！
```

### ECC 初始化

```c
// H7 上电后必须初始化 SRAM 或禁用 ECC 检查
// CubeMX 默认配置：启动时自动初始化 SRAM

// 方案 1: 使能 HW ECC 初始化（推荐）
// CubeMX → SYS → ECC → Enable ECC on AXI SRAM

// 方案 2: 软件初始化
void sram_ecc_init(void)
{
    // 在 main 入口处向所有 SRAM 写 0
    // 这样 ECC 码被正确初始化
    for (uint32_t *p = (uint32_t *)0x24000000;
         p < (uint32_t *)0x24080000; p++) {
        *p = 0;  // 写 AXI SRAM 512KB
    }
}

// 方案 3: 禁用 ECC 错误上报（测试用，不推荐生产）
// 修改 RAMECC 寄存器
```

### G4 SRAM2 ECC

```c
// G4 SRAM2 使用 SEC-DED ECC
// 1-bit 错误: 自动纠正 + 可通过中断通知
// 2-bit 错误: 触发 NMI

// G4 ECC 中断处理：
void SRAM2_ECC_IRQHandler(void)
{
    if (ECC_GetFlagStatus(ECC_FLAG_SRAM2_1BIT_ERR)) {
        // 1-bit 错误已纠正
        ECC_ClearFlag(ECC_FLAG_SRAM2_1BIT_ERR);
    }
    if (ECC_GetFlagStatus(ECC_FLAG_SRAM2_2BIT_ERR)) {
        // 2-bit 错误不可纠正
        // 触发 NMI 或 HardFault
        save_critical_data();
        NVIC_SystemReset();
    }
}
```

## 链接脚本常用模式

### GCC ld 多 SRAM 分区 (F4)

```ld
MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K
    RAM1  (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
    RAM2  (rw)  : ORIGIN = 0x20018000, LENGTH = 32K
}

SECTIONS
{
    /* 普通数据段在 SRAM1 */
    .data : { *(.data) } > RAM1 AT > FLASH
    .bss  : { *(.bss)  } > RAM1
    .heap : { _heap_start = .; . += HEAP_SIZE; } > RAM1
    .stack : { _stack_start = .; . += STACK_SIZE; } > RAM1

    /* DMA 缓冲区在 SRAM2 */
    .dma_buf (NOLOAD) : {
        . = ALIGN(4);
        *(.dma_buffer)
        . = ALIGN(4);
    } > RAM2
}
```

### Keil scatter file (F4)

```sct
; 内存布局
LR_IROM1 0x08000000 0x00080000 {    ; 512KB Flash
    ER_IROM1 0x08000000 0x00080000 {
        *.o (RESET, +First)
        *(InRoot$$Sections)
        .ANY (+RO)
    }
    RW_RAM1 0x20000000 0x00018000 { ; 96KB SRAM1
        .ANY (+RW +ZI)
    }
    RW_RAM2 0x20018000 0x00008000 { ; 32KB SRAM2
        *.o (.dma_buffer)
    }
}
```

## 内存性能对比

| SRAM 类型 | 总线 | 时钟 | 访问延迟 | 典型场景 |
|-----------|------|------|---------|---------|
| CCM (F4) | D-Bus | 同 HCLK | 0 WS | CPU 关键变量 |
| DTCM (H7) | D-Bus | 同 HCLK | 0 WS | 栈、频繁变量 |
| ITCM (H7) | I-Bus | 同 HCLK | 0 WS | 时间关键代码 |
| AXI SRAM (H7) | AXI | 同 HCLK | 1~3 WS | 大缓冲区 |
| SRAM1/2 | AHB | 同 HCLK | 1~3 WS | 通用变量 |
| 备份 SRAM | APB | 低速 | 慢 | 掉电保持 |

## 常见陷阱

| 编号 | 现象 | 根因 | 解决 |
|------|------|------|------|
| 1 | DMA 读缓冲区全为 0 | DMA 缓冲区放在了 CCM (DMA 不可达) | 移到 SRAM1/2 |
| 2 | H7 上电后 SRAM 值异常 | ECC 校验错误（未初始化 ECC） | 初始化 ECC 或写一次所有 SRAM |
| 3 | STOP 唤醒后变量值错误 | SRAM 保留不可控（H7 STOP 等级过高） | 检查 STOP 等级 (STOP1 vs STOP2) |
| 4 | 随机 HardFault | 栈溢出到其他变量区域 | 加大栈或检查栈使用量 |
| 5 | F4 CCM 代码比 SRAM1 慢 | CCM 只有 D-Bus，取指令也走 D-Bus | 数据放 CCM，代码放 Flash/ITCM |
| 6 | malloc 返回 NULL | 堆碎片化或堆太小 | 改用静态分配或内存池 |
| 7 | 后备 SRAM 写不进去 | DBP 未使能或 PWR 时钟未开 | `HAL_PWR_EnableBkUpAccess()` + `__HAL_RCC_PWR_CLK_ENABLE()` |

## 边界定义

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | SRAM 典型布局 | 特色 |
|------|-------------|------|
| STM32F1 | SRAM(20-64KB) | 单一连续段 |
| STM32F4 | SRAM1/SRAM2/CCM (128-192KB) | CCM 无 DMA 访问 |
| STM32H7 | DTCM/ITCM/AXI SRAM/SRAM1-4 (512KB-1MB) | D-Cache 需维护 |
| STM32L4 | SRAM1/SRAM2 (128-256KB) | SRAM2 低功耗保持 |
| ESP32 | DRAM/IRAM (520KB) | 片内 SRAM 分 IRAM/DRAM |
| ESP32-S3 | SRAM(512KB) | 可配置为 TCM |

- **不覆盖外部 SRAM**（FSMC/FMC 外接 SRAM/PSRAM/SDRAM）— 使用 `stm32-hal-development` + FMC 配置
- **不覆盖 MPU 配置** — 使用 `arm-core-registers`（MPU 章节）
- **不覆盖内存保护单元（MPU）与 SRAM 的配合** — 同上
- **DMA 缓冲区放置细节** 参考 `dma-module`
