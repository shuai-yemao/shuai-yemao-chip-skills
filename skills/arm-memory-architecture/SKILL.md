---
name: arm-memory-architecture
description: ARM Cortex-M 系统级内存架构指南——系统地址映射、MPU 完整配置（Region/SubRegion/Attribute/RBAR/RLAR）、Cortex-M7 Cache 维护（I/D-Cache Clean/Invalidate 操作）、内存屏障（DMB/DSB/ISB 场景速查）、TCM 配置、总线矩阵（AXI/AHB/APB 访问路径与内存映射）、内存序模型与写缓冲、位带架构。当用户提到系统地址映射、内存映射、MPU 配置、MPU 区域、MPU 子区域、Cache 维护、Cache 清理、Cache 无效化、I-Cache、D-Cache、M7 Cache、内存屏障、DMB、DSB、ISB、内存序、写缓冲、总线矩阵、AHB、APB、AXI、TCM 配置、DTCM、ITCM 配置、位带架构、内存属性、memory type、shareable、cacheable、内存保护、内存分区、链接器内存布局、分散加载内存映射时使用。
version: "1.0.0"
---

# ARM Cortex-M 系统级内存架构指南

> 填补现有 skill 中缺失的内存架构知识。与 arm-core-registers（内核寄存器/MPU 寄存器级）和 sram-module（内部 SRAM 布局）互补——本 skill 关注**系统级**内存架构设计、配置与调试。

## 适用场景

- 系统地址映射理解与配置（代码/外设/内存区域划分）
- MPU 完整配置（不止寄存器读写，含 Region/SubRegion/Attribute 策略设计）
- Cortex-M7 Cache 维护操作（I-Cache 无效化、D-Cache Clean/Invalidate 时机）
- 内存屏障插入决策（DMB/DSB/ISB 三者的选择与位置）
- TCM 紧耦合内存的链接器配置与 DMA 限制
- 总线矩阵分析（DMA 从哪个总线访问外设、内存访问延迟预判）
- 内存序相关的诡异 Bug 诊断（Cache 一致性、写缓冲延迟、外设误读）
- 位带架构原理解释与别名区计算

## 必要输入

- Cortex-M 内核版本（M0+/M3/M4/M7/M33 — 特性差异较大）
- STM32 系列（F1/F4/F7/H7/G4 — 总线矩阵不同）
- 具体需求场景：MPU 防护 / Cache 维护 / 内存屏障 / 总线分析

---

## 1. Cortex-M 系统地址映射

所有 Cortex-M 使用统一的 4GB 地址空间划分：

```
地址范围             区域          总线接口    典型用途
─────────────────────────────────────────────────────────
0x00000000-0x1FFFFFFF Code         I-Bus/D-Bus  Flash, I-Cache 预取
0x20000000-0x3FFFFFFF SRAM         D-Bus/S-Bus  主 SRAM, DTCM
0x40000000-0x5FFFFFFF 外设          D-Bus        外设寄存器 (AHB/APB)
0x60000000-0x9FFFFFFF 外部 RAM     AHB 外部      FSMC/FMC/QUADSPI
0xA0000000-0xDFFFFFFF 外部设备      AHB 外部      NAND Flash
0xE0000000-0xE00FFFFF 系统级外设    Private Bus   SCB/NVIC/MPU/SysTick/ITM
0xE0100000-0xFFFFFFFF 系统保留      —             —
```

### 关键规则

| 规则 | 说明 |
|------|------|
| Code 区指令预取 | I-Bus 从 Code 区预取指令，不含 D-Cache 的 SRAM 区域指令预取绕过 D-Cache |
| SRAM 区别名 | 0x20000000 和 0x22000000 互为位带别名（仅 F1/F4 等 M3/M4） |
| 外设区强序 | 外设区默认 Strongly-ordered（M0+/M3）或 Device（M4/M7），读写不可合并 |
| 系统区不可缓存 | 0xE0000000+ 系统级外设空间永不缓存 |

---

## 2. MPU 完整配置（含策略设计）

### MPU 架构差异

| 特性 | Cortex-M0+ | Cortex-M3 | Cortex-M4 | Cortex-M7 | Cortex-M33 |
|------|-----------|----------|----------|----------|-----------|
| 区域数 | 8 | 8 | 8 | 8/16 | 16 |
| Region 格式 | 传统 | 传统 | 传统 | **RBAR/RLAR** | RBAR/RLAR |
| SubRegion | 8×1/8 | 8×1/8 | 8×1/8 | 8×1/8 | 8×1/8 |
| 背景区域 | 仅特权 | 可配 | 可配 | 可配 | 可配 |
| NONSECURE | — | — | — | — | ✓ (TrustZone) |
| eXecute Never | ✓ | ✓ | ✓ | ✓ | ✓ |

### M3/M4 传统格式（`MPU_RASR`）

```
MPU_RASR 寄存器（传统格式）:
 位[31:29] — AP[2:0] 访问权限
 位[28]    — TEX[2]  类型扩展最高位
 位[27]    — 保留
 位[26:24] — TEX[1:0] 类型扩展
 位[23:22] — AP[1:0]  访问权限（与位[29] 组成 3 位）
 位[21:19] — 保留
 位[18]    — S        Sharable
 位[17]    — C        Cacheable
 位[16]    — B        Bufferable
 位[15:8]  — SRD[7:0] SubRegion Disable
 位[7:6]   — 保留
 位[5:1]   — SIZE     区域大小（2^(SIZE+1) Bytes，最小 32B）
 位[0]     — ENABLE   区域使能
```

**SIZE 编码速查**:
```
SIZE=4  → 32B    SIZE=10 → 2KB    SIZE=16 → 64KB
SIZE=5  → 64B    SIZE=11 → 4KB    SIZE=17 → 128KB
SIZE=6  → 128B   SIZE=12 → 8KB    SIZE=18 → 256KB
SIZE=7  → 256B   SIZE=13 → 16KB   SIZE=19 → 512KB
SIZE=8  → 512B   SIZE=14 → 32KB   SIZE=20 → 1MB
SIZE=9  → 1KB    SIZE=15 → 64KB   ...
```

### M7/M33 新格式（`MPU_RBAR` + `MPU_RLAR`）

```
MPU_RBAR (M7):
 位[31:5]  — BASE   区域基地址（对齐到 SIZE 边界）
 位[4]     — SH     共享属性 (0=不共享, 1=共享)
 位[3]     — AP     访问权限 (0=RW/特权, 1=RO/特权)
 位[2]     — XN     执行禁止 (1=不可执行)
 位[1]     — 保留
 位[0]     — ENABLE 区域使能

MPU_RLAR (M7):
 位[31:5]  — LIMIT  区域上限地址（必须对齐到 SIZE 边界）
 位[4]     — AttrIndx  属性索引 (指向 MAIR0/MAIR1)
 位[3:1]   — 保留
 位[0]     — ENABLE  区域使能

MAIR0/MAIR1 (Memory Attribute Indirection Registers):
  每 8 位定义一个内存属性编码，共 8 个属性 (Attr0~Attr7)
  编码: 位[7:4]=类型 (0: 设备/1: 普通), 位[3:0]=属性
  常用编码:
    0x04 — Normal Memory, Outer Non-cacheable
    0xFF — Normal Memory, Outer Write-Back Write-Allocate
    0x44 — Device Memory, nE
```

### 访问权限编码（AP[2:0]）

| AP | 特权级 | 用户级 | 说明 |
|----|--------|--------|------|
| 000 | 无访问 | 无访问 | 完全禁止 |
| 001 | RW | 无访问 | 特权保护（推荐 RTOS 内核区域） |
| 010 | RW | RO | 只读给用户任务 |
| 011 | RW | RW | 全部可读写 |
| 100 | 缓存 | — | 不可预测，避免使用 |
| 101 | RO | 无访问 | 特权只读 |
| 110 | RO | RO | 只读 |
| 111 | RO | RW | 用户可写特权只读（少见） |

### MPU 常见配置模式

````c
// M4 传统格式示例：保护外设空间 (0x40000000, 512MB Device)
MPU->RNR  = 0;            // 区域 0
MPU->RBAR = 0x40000000;   // 基地址：外设空间
MPU->RASR = (0x02UL << 28)   // TEX=001 (Device)
          | (0x01UL << 24)   // TEX=001 续
          | (0x01UL << 18)   // S=1 (Sharable)
          | (0x00UL << 17)   // C=0 (Non-cacheable)
          | (0x00UL << 16)   // B=0 (Non-bufferable) → Device-nGnRnE
          | (0x1EUL << 8)    // SRD: 全部子区域使能
          | (0x13UL << 1)    // SIZE=19 → 512MB
          | (0x01UL << 0);   // ENABLE=1

// M7 RBAR/RLAR 格式示例：保护 SRAM (0x20000000, 512KB Normal WBWA)
MPU->RNR  = 0;
MPU->RBAR = (0x20000000)          // BASE
          | (0x00UL << 4)         // SH=00 (Non-sharable)
          | (0x00UL << 3)         // AP=0 (RW/Privilege)
          | (0x01UL << 0);        // ENABLE=1
MPU->RLAR = (0x2007FFFF)          // LIMIT (512KB, 区域对齐)
          | (0x01UL << 4)         // AttrIdx=1 (MAIR1: Normal WBWA)
          | (0x01UL << 0);        // ENABLE=1
MPU->MAIR1 = (MPU->MAIR1 & ~0xFF) | 0xFF;  // Attr1: Normal WB Write-Allocate
````

### SubRegion 用法

每个 MPU Region 可均分为 8 个 SubRegion，通过 SRD[7:0] 单独禁用：

```
区域基址 0x20000000, SIZE=16 → 64KB, 每 SubRegion=8KB
SRD=0xF7 (位 3=1) → 第 4 个 8KB 区间禁用 (0x20018000-0x20019FFF)
```

应用场景：需要保护一段连续内存但中间有一小块需要不同属性的情况。

### 策略设计原则

| 场景 | 推荐策略 |
|------|---------|
| RTOS 内核保护 | 1 个 Region 覆盖整个 SRAM，禁止用户级访问，任务通过 SVC 切换 |
| 外设隔离 | 1 Region 覆盖外设空间 (Device-nGnRnE) |
| Flash 代码保护 | 1 Region 覆盖 Flash (RO, XN 仅对数据区域) |
| MPU 违例探测 | 背景区域设为无访问，显式配置所有合法区域——违例即触发 MemManage |
| F7/H7 Cache | 将 SRAM 设为 Normal Cacheable (WBWA)，外设设为 Device |

---

## 3. Cortex-M7 Cache 维护

### Cache 架构

```
Cortex-M7:
  I-Cache: 16KB (4-way set associative, 32B line)
  D-Cache: 16KB (4-way set associative, 32B line)
  → 可通过 CCR.IC/CCR.DC 位禁用

Cache Line: 32 字节 = 8 个字
```

### 何时需要 Cache 维护

| 场景 | 需要操作 | 原因 |
|------|---------|------|
| DMA 写入内存后 CPU 读取 | D-Cache **Clean** by VA→Invalidate | DMA 直接写内存绕过 D-Cache，D-Cache 中可能有旧数据 |
| CPU 写入内存后 DMA 读取 | D-Cache **Clean** by VA | D-Cache 中的新数据还没写到内存 |
| IAP 写入 Flash 后执行 | I-Cache **Invalidate** | Flash 内容已变，I-Cache 中缓存的旧指令导致 HardFault |
| 外设 Buffer 非连续 DMA | D-Cache **Clean+Invalidate** by VA | 需要清空并重新加载指定区域 |
| MPU 区域属性更改 | D-Cache **Invalidate** | 旧 cacheline 属性与新属性冲突 |

### M7 Cache 维护操作（CMSIS 原生）

```c
// ── I-Cache 操作 ──
SCB_InvalidateICache();           // 全部无效化 I-Cache
SCB_InvalidateICache_by_Addr(ptr);// 无效化指定地址行（CMSIS 8.0+）

// ── D-Cache 操作 ──
SCB_InvalidateDCache();           // 全部无效化（丢数据！慎用）
SCB_CleanDCache();                // 全部写回内存
SCB_CleanInvalidateDCache();      // 全部写回 + 无效化（最彻底）

// ── 单行操作（推荐）──
SCB_InvalidateDCache_by_Addr(ptr, len);       // 无效化指定区域
SCB_CleanDCache_by_Addr(ptr, len);             // 写回指定区域
SCB_CleanInvalidateDCache_by_Addr(ptr, len);   // 写回 + 无效化
```

### 手动 D-Cache 维护（寄存器级）

```c
// D-Cache Clean by VA to Point of Unification (PoU)
// 使用 DCCMVAC 寄存器
asm volatile("mcr p15, 0, %0, c7, c10, 1" : : "r" (addr) : "memory");
// D-Cache Invalidate by VA to PoU
asm volatile("mcr p15, 0, %0, c7, c6, 1" : : "r" (addr) : "memory");
// D-Cache Clean+Invalidate by VA to PoU
asm volatile("mcr p15, 0, %0, c7, c14, 1" : : "r" (addr) : "memory");

// I-Cache Invalidate all (ICIALLU)
asm volatile("mcr p15, 0, %0, c7, c5, 0" : : "r" (0) : "memory");
// I-Cache Invalidate by VA to PoU
asm volatile("mcr p15, 0, %0, c7, c5, 1" : : "r" (addr) : "memory");
```

### 常见模式：DMA 缓冲区 Cache 管理

```c
// 模式 1: DMA 写入 → CPU 读取
uint8_t rx_buf[128] __attribute__((aligned(32)));
// DMA 传输完成后，CPU 读之前
SCB_InvalidateDCache_by_Addr(rx_buf, 128);   // 32B 对齐

// 模式 2: CPU 写入 → DMA 读取
uint8_t tx_buf[128] __attribute__((aligned(32)));
// CPU 写完数据后，DMA 启动之前
SCB_CleanDCache_by_Addr(tx_buf, 128);

// 模式 3: 双向（双缓冲 Ping-Pong）
SCB_CleanInvalidateDCache_by_Addr(buf, size);
// 先 Clean 确保 CPU 数据写回，再 Invalidate 让 CPU 看到 DMA 写入的新数据

// 最佳实践：分配时固定 32B 对齐 + 大小向上取整到 32 的倍数
// 否则 by_Addr 操作可能无法覆盖完整 cacheline
```

---

## 4. 内存屏障

### 三种屏障区别

| 指令 | 全称 | 作用范围 | 阻塞对象 | 典型场景 |
|------|------|---------|---------|---------|
| **DMB** | Data Memory Barrier | 内存访问序 | Load/Store 指令 | DMA 前后、外设寄存器访问 |
| **DSB** | Data Synchronization Barrier | 执行流同步 | 所有指令（直到完成） | 更新 MPU/Cache/SysTick 后，WFI 前 |
| **ISB** | Instruction Synchronization Barrier | 指令流水线刷新 | 后续指令（重新预取） | MPU 配置后、I-Cache 无效后、自修改代码 |

### 速查表

```c
// 更新 MPU/SCB 寄存器后 → 需要 DSB + ISB
MPU->CTRL = 1;
DSB();    // 等待 MPU 更新完成
ISB();    // 刷新流水线，下次内存访问使用新 MPU 配置

// DMA 启动前（确保 CPU 写入已到达内存）
SCB_CleanDCache_by_Addr(buf, len);
DMB();    // 保证 Cache Clean 在 DMA 使能之前
DMA->CCR |= DMA_CCR_EN;

// 外设寄存器访问序列
GPIO->BSRR = (1 << 5);
DMB();    // 保证上一个写操作完成后再继续
GPIO->BSRR = (1 << 3);

// WFI 进入低功耗前
DSB();    // 必须 DSB！保证所有 pending 内存操作完成
WFI();    // 否则 WFI 可能立即被 pending 的事件唤醒

// IAP 跳转 APP 前
SCB_InvalidateICache();           // 清空 I-Cache
__set_MSP(app_stack);             // 设置新栈顶
DSB();                            // 等待设置完成
ISB();                            // 刷新流水线
((void (*)(void))app_entry)();    // 跳转

// FreeRTOS 临界区退出
taskEXIT_CRITICAL();
ISB();    // 确保中断使能生效后指令流水线正确预取
```

### 常见错误

| 错误写法 | 问题 | 正确写法 |
|---------|------|---------|
| MPU 配置后仅 DSB 无 ISB | 后续 load/store 仍用旧 MPU 属性 | DSB + ISB 成对 |
| DMA 前不 Clean | D-Cache 数据还没写回，DMA 读旧数据 | CleanDCache + DMB |
| DMA 后不 Invalidate | CPU 读 D-Cache 中的旧数据 | InvalidateDCache + DMB |
| 写外设寄存器不 DMB | 编译器/硬件可能重排或合并写 | 有数据依赖的顺序写加 DMB |
| WFI 前用 DMB 而非 DSB | DMB 只保证内存序，不保证指令完成 | 必须用 DSB |

---

## 5. 总线矩阵与内存访问路径

### 典型总线矩阵（STM32F4/H7）

```
STM32F4:

  Cortex-M4 Core
  ┌────────────────────────┐
  │ I-Bus   D-Bus   S-Bus  │
  └───┬──────┬──────┬──────┘
      │      │      │
  ┌───▼──┐ ┌▼──────▼──┐ ┌───▼──┐
  │ I-Code│ │ D-Code / │ │ System│
  │  Bus   │ │  SRAM    │ │  Bus  │
  └───┬───┘ └──┬───────┘ └───┬──┘
      │        │              │
  ┌───▼──┐ ┌───▼────┐  ┌────▼────┐
  │ Flash │ │ SRAM1  │  │ AHB1/APB│
  │       │ │ SRAM2  │  │ 外设总线 │
  └───────┘ └────────┘  └─────────┘
      ↑        ↑
  I-Bus 取指  D-Bus 数据
  (不含外设)  + S-Bus 外设

STM32H7 (双总线架构):
  ┌─Cortex-M7───────────────┐
  │ ITCM  64KB  (0x0000)    │← 指令 TCM，CPU 专用，零等待
  │ DTCM  128KB (0x2000)    │← 数据 TCM，CPU 专用，零等待
  │ I-Cache                │← 16KB, 通过 AXI 读主 RAM
  │ D-Cache                │← 16KB, 通过 AXI 读写主 RAM
  └────────────────────────┘
            │ AXI 总线矩阵
            ▼
  ┌────────────────────────┐
  │ AXI SRAM 1MB (0x2400)  │← 可通过 DMA 访问
  │ Flash (0x0800)          │
  │ AHB/APB 外设           │
  └────────────────────────┘
```

### 关键总线约束

| 约束 | 说明 | 影响 |
|------|------|------|
| F4: I-Bus 只取指 | I-Bus 接口只能从 Code 区读取指令 | SRAM 中的代码通过 D-Bus/S-Bus 取指（速度不同） |
| F4: D-Bus 非 DMA 可达 | D-Bus 连接 SRAM，但 DMA 通过 AHB 访问 | CCM RAM 对 DMA 不可见 |
| F4: S-Bus 访问外设 | S-Bus 连接 AHB1/APB | I-Bus 取指 + S-Bus 外设访问可同时进行 |
| H7: TCM 仅 CPU 专用 | DTCM/ITCM 不经过总线矩阵 | DMA 不能访问 TCM！ |
| H7: AXI SRAM 可 DMA | AXI SRAM 挂在总线矩阵上 | DMA 缓冲区必须放 AXI SRAM 或 D2 SRAM |
| H7: D2 SRAM | 主域 D2 上的 288KB SRAM | 可通过 AHB 访问，DMA 可用 |

### DMA 缓冲区放置策略

| 目标芯片 | DMA 缓冲区位置 | 非 DMA 缓冲区位置 |
|---------|--------------|-----------------|
| F103 | SRAM (0x2000) | SRAM 或任意 |
| F407 | SRAM1/SRAM2 | CCM RAM (0x1000) 零等待 |
| F411 | SRAM1/SRAM2 | SRAM1 或 SRAM2 |
| **H743** | **AXI SRAM (0x2400)** 或 D2 SRAM | **DTCM (0x2000) 零等待** |
| G474 | SRAM1/SRAM2 | SRAM1 |

> **H7 常见误区**：DTCM 速度最快（零等待，400MHz），但 DMA 不能访问。新手常将 DMA 缓冲区放在 DTCM 导致 DMA 传输无反应。

---

## 6. TCM 配置指南

### 链接器中的 TCM 配置

```ld
/* STM32H743 链接脚本 TCM 示例 */
MEMORY
{
  ITCM (xrw)     : ORIGIN = 0x00000000, LENGTH = 64K   /* 指令 TCM */
  DTCM (xrw)     : ORIGIN = 0x20000000, LENGTH = 128K  /* 数据 TCM */
  AXI_SRAM (xrw) : ORIGIN = 0x24000000, LENGTH = 512K  /* AXI SRAM */
  FLASH (rx)     : ORIGIN = 0x08000000, LENGTH = 2048K /* 主 Flash */
}

SECTIONS
{
  /* 关键中断函数放 ITCM 零等待 */
  .isr_text : {
    *(.isr_text)
  } > ITCM AT > FLASH

  /* 实时性要求高的数据放 DTCM */
  .fast_data : {
    *(.fast_data)
  } > DTCM AT > FLASH

  /* DMA 缓冲区必须放 AXI SRAM */
  .dma_buf (NOLOAD) : {
    *(.dma_buf)
  } > AXI_SRAM
}
```

```c
// C 代码中指定段属性
__attribute__((section(".isr_text")))
void HardFault_Handler(void) { /* 零等待执行 */ }

__attribute__((section(".fast_data")))
volatile uint32_t system_tick;  /* DTCM 零等待 */

__attribute__((section(".dma_buf"), aligned(32)))
uint8_t dma_rx_buffer[1024];    /* AXI SRAM，DMA 可达 */
```

### TCM 注意事项

| 注意点 | 说明 |
|--------|------|
| H7: TCM 无 Cache | TCM 不经过 L1 Cache，读写是确定性的——适合实时控制 |
| H7: TCM 不支持 DMA | 任何 DMA 操作无法访问 TCM（总线矩阵不可达） |
| H7: DTCM 位带 | DTCM 不支持位带操作（AXI SRAM 才支持） |
| H7: ITCM 仅指令 | ITCM 只能放指令，不能放数据 |
| H7: TCM 使能 | 复位后 TCM 默认使能，通过 `TCM_CR` 寄存器可配置 |

---

## 7. 位带架构

### 位带区域

| 芯片 | 位带区 | 基地址 | 别名区 | 别名基地址 |
|------|--------|--------|--------|-----------|
| M3/M4 (F1/F4) | SRAM | 0x20000000 | 0x22000000 | 0x22000000 |
| M3/M4 (F1/F4) | 外设 | 0x40000000 | 0x42000000 | 0x42000000 |
| M7 (H7) | AXI SRAM | 0x24000000 | 0x26000000 | 0x26000000 |
| M7 (H7) | 外设 | 0x40000000 | 0x42000000 | 0x42000000 |
| M0+ | **不支持位带** | — | — | — |

### 别名地址计算

```c
// 公式: alias_addr = alias_base + (byte_addr - bitband_base) * 32 + bit_num * 4

// 宏定义
#define BITBAND_SRAM(addr, bit)  (*(volatile uint32_t *) \
    (0x22000000 + ((uint32_t)(addr) - 0x20000000) * 32 + (bit) * 4))
#define BITBAND_PERIPH(addr, bit) (*(volatile uint32_t *) \
    (0x42000000 + ((uint32_t)(addr) - 0x40000000) * 32 + (bit) * 4))

// 使用示例
#define GPIOA_ODR    ((volatile uint32_t *)0x40020014)
BITBAND_PERIPH(GPIOA_ODR, 5) = 1;  // 原子置位 PA5，无需 RMW
uint8_t bit = BITBAND_SRAM(&flag_var, 3);  // 原子读取 flag_var 的位 3
```

---

## 8. 内存属性与序模型

### 内存类型

| 类型 | M3/M4 编码 | M7 MAIR | 缓存策略 | 写合并 | 访问序保证 |
|------|-----------|---------|---------|-------|-----------|
| **Strongly-ordered** | TEX=000,C=0,B=0 | — | 不缓存 | 禁止 | 严格序 |
| **Device-nGnRnE** | TEX=001,C=0,B=0 | 0x00 | 不缓存 | 禁止 | 严格序 |
| **Device-nGnRE** | — | 0x04 | 不缓存 | 禁止 | 读可合并 |
| **Device-nGRE** | — | 0x44 | 不缓存 | 可合并 | 无保证 |
| **Device-GRE** | — | 0x84 | 不缓存 | 可合并 | 无保证 |
| **Normal Non-cacheable** | TEX=001,C=1,B=0 | 0x04 | 不缓存 | — | — |
| **Normal WBWA** | TEX=000,C=1,B=1 | 0xFF | WB,WA | 可合并 | — |

> Strongly-ordered < Device < Normal：越"强"序越安全，但性能越差。

### 共享属性 (Shareability)

| 属性 | 适用场景 | Cache 行为 |
|------|---------|-----------|
| Non-shareable | CPU 独占区域（栈、局部变量） | 正常 Cache |
| Write-Through Sharable | 多核共享数据（H7 D2 域） | D-Cache 绕过写缓冲 |
| Write-Back Sharable | 多核低争用 | 需要软件维护一致性 |

---

## 9. 调试与故障排查

### 常见问题速查

| 症状 | 最可能根因 | 验证方法 | 修复 |
|------|-----------|---------|------|
| H7 DMA 传输无数据 | DMA 缓冲区在 DTCM | 检查 DMA 源/目的地址 | 将缓冲区改到 AXI SRAM |
| F4 CCM 变量 DMA 读零 | CCM RAM 对 DMA 不可见 | 检查地址是否在 0x1000xxxx | 放 SRAM1/SRAM2 |
| MPU 使能后 HardFault | 未配置背景区域 | 检查 MPU->CTRL PRIVDEFENA | 使能背景区域或补全所有区域 |
| IAP 跳转后执行异常 | I-Cache 中有旧指令 | 跳转前 ICache 未清 | `SCB_InvalidateICache()` |
| D-Cache 开启后数据错误 | DMA 后未 Invalidate | 观察新旧数据值 | `InvalidateDCache_by_Addr` |
| 写外设寄存器被优化 | 缺少 volatile | 反汇编看是否被合并 | 外设指针加 volatile + DMB |
| MPU 配置后不生效 | 缺少 DSB+ISB | 读回 MPU->RBAR | 配置后 DSB; ISB; |
| WFI 提前唤醒 | 用了 DMB 而非 DSB | 检查 MCU 唤醒时间 | 换 DSB; WFI; |

### 诊断命令速查

```c
// 查看 MPU 配置
// 通过调试器读取
uint32_t mpu_type = MPU->TYPE;    // 区域数: (TYPE+1)*8
uint32_t rbar = MPU->RBAR;        // 当前区域基址
uint32_t rlar = MPU->RLAR;        // 当前区域上限+属性 (M7)
uint32_t rasz = MPU->RASR;        // 当前区域属性 (M3/M4)
uint32_t ccr  = SCB->CCR;         // Cache/MPU 使能状态

// 查看 Cache 状态 (M7)
uint32_t ccsidr = SCB->CCSIDR;    // Cache size info
// 位[29] — 行大小 (log2(bytes) - 4)
// 位[27:13] — 组数 (Associativity - 1)
// 位[12:4] — 集合数 (NumSets - 1)
```

---

## 参考文档

- ARMv7-M Architecture Reference Manual (DDI 0403E) — MPU/Cache/内存序
- ARMv8-M Architecture Reference Manual (DDI 0553) — M33/MPU/TrustZone
- Cortex-M7 Generic User Guide (DUi 0646B) — Cache 维护操作
- STM32H7 Reference Manual (RM0433) — 总线矩阵/内存映射
- STM32F4 Reference Manual (RM0090) — 位带/总线矩阵/CCM
- AN4838 — MPU 使用指南
- AN4839 — Level 1 Cache 在 STM32F7/H7 上的使用
