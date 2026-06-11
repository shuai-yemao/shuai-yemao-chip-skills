---
name: flash-module
version: "1.0.0"
description: "STM32 内部 Flash 存储器编程与配置指南。涵盖 Flash 架构（Sector/Page/Bank 布局）、读写擦操作（HAL 与寄存器级）、等待周期配置、Option Bytes（RDP/WRP/PCROP）、IAP Bootloader、EEPROM 模拟、双 Bank 模式、错误处理与调试。当用户提到 Flash、内部 Flash、Flash 编程、Flash 擦除、Flash 写入、Flash 保护、Option Bytes、读保护、写保护、PCROP、IAP、Bootloader、Flash 等待周期、Flash 延迟、Flash EEPROM 模拟、Flash 双 Bank、Flash 错误、Flash 操作失败、HAL_FLASH、Flash 扇区、Flash 页面、Flash 擦写寿命、Flash 磨损均衡时使用。"
---

# Flash 模块开发指南

## Flash 架构概览

### 各系列 Flash 架构对比

| 系列 | 架构 | 擦除单元 | 编程粒度 | 双 Bank | 总容量范围 |
|------|------|---------|---------|---------|-----------|
| F1 (F103) | 大容量/互联型 | Page (1/2KB) | Half-word (16bit) | 无 | 64KB~1MB |
| F4 (F411) | 统一/多 Sector | Sector (16/64/128KB) | Word (32bit) / Half-word | 有 (1MB+) | 256KB~2MB |
| F4 (F407) | 统一/多 Sector | Sector (16/64/128KB) | Word (32bit) | 有 (1MB+) | 512KB~1MB |
| H7 | 双 Bank 独立 | Sector (8/128KB) | Quad-word (256bit) | 有 (默认) | 1MB~2MB |
| G4 | 双 Bank 可选 | Page (2KB) | Double-word (64bit) | 可配置 | 64KB~512KB |
| G0 | 统一 | Page (256B~2KB) | Half-word/Word | 无 | 16KB~512KB |

> 完整 Sector/Page 大小表见 `references/flash-sector-map.md`
> EEPROM 模拟实现见 `references/flash-programming-guide.md`（状态机 + 磨损均衡 + 多字节编程）

### F4 (STM32F411) Sector 布局

```
1MB Flash (F411CEU6):
+--------+--------+--------+--------+--------+--------+--------+--------+
| S0  16K| S1  16K| S2  16K| S3  16K| S4  64K| S5 128K| S6 128K| S7 128K|
+--------+--------+--------+--------+--------+--------+--------+--------+
| S8 128K| S9 128K| S10 128K| S11 128K|
+--------+--------+--------+--------+
Bank 1 (S0~S7)    | Bank 2 (S8~S11)
```

## Flash 读取

### CPU 直接读

```c
// CPU 通过 I-Bus / D-Bus 直接读取 Flash
// 速度取决于 Flash 等待周期 (WS/Latency)

// 在 SystemClock_Config 中配置等待周期
__HAL_FLASH_SET_LATENCY(FLASH_LATENCY_3);  // F411 @ 100MHz 需要 3 WS
```

### 等待周期 (Wait State) 速查

| fHCLK (F411) | 所需 WS | VOS 等级 |
|-------------|--------|---------|
| ≤ 24 MHz | 0 WS | VOS1 |
| ≤ 48 MHz | 1 WS | VOS1 |
| ≤ 72 MHz | 2 WS | VOS1 |
| ≤ 96 MHz | 3 WS | VOS1 |
| ≤ 100 MHz | 3 WS | VOS1 |

```c
// 安全设置流程：升频前先+WS，降频后可以-WS
// 错误示范：
void bad_clock_config(void)
{
    // ❌ 先提频再设 WS → HCLK > Flash 速度 → HardFault
    HAL_RCC_OscConfig(...);      // 提频
    __HAL_FLASH_SET_LATENCY(3);  // 晚了！
}

// 正确示范：
void good_clock_config(void)
{
    // ✅ 先增加等待周期再提频
    __HAL_FLASH_SET_LATENCY(FLASH_LATENCY_3);
    HAL_RCC_OscConfig(...);
    HAL_RCC_ClockConfig(...);

    // 降频时可以反过来：先降频再减 WS
}
```

### ART Accelerator (F4/F7)

```c
// F4/F7 有 ART Accelerator：64/128 位 Flash 预取缓冲
// 使能后可减少 Flash 等待周期的影响

// CubeMX 默认使能：
HAL_FLASH_ART_Enable();  // 使能 ART (自动预取+指令缓存+数据缓存)

// 检查状态：
if (__HAL_FLASH_ART_IS_ENABLED()) {
    // ART 已使能
}
```

## Flash 编程

### HAL API

```c
// 1. 解锁 Flash
HAL_FLASH_Unlock();

// 2. 擦除
FLASH_EraseInitTypeDef erase;
uint32_t sector_error;

erase.TypeErase = FLASH_TYPEERASE_SECTORS;
erase.Sector = FLASH_SECTOR_5;       // F4 扇区编号
erase.NbSectors = 1;
erase.VoltageRange = VOLTAGE_RANGE_3;  // 2.7V~3.6V

if (HAL_FLASHEx_Erase(&erase, &sector_error) != HAL_OK) {
    // 擦除失败，sector_error 指向出错的扇区
    Error_Handler();
}

// 3. 编程
uint32_t address = 0x08080000;  // Sector 5 起始地址
uint64_t data = 0x12345678;
if (HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, address, data) != HAL_OK) {
    // 编程失败
    Error_Handler();
}

// 4. 锁定 Flash
HAL_FLASH_Lock();
```

### 编程类型 (F4)

| 宏 | 位宽 | 地址对齐 | 典型应用 |
|------|------|---------|---------|
| `FLASH_TYPEPROGRAM_HALFWORD` | 16bit | 2 字节对齐 | F1 兼容 |
| `FLASH_TYPEPROGRAM_WORD` | 32bit | 4 字节对齐 | 常用，F4 默认 |
| `FLASH_TYPEPROGRAM_DOUBLEWORD` | 64bit | 8 字节对齐 | F4 V2.0+ |
| `FLASH_TYPEPROGRAM_QUADWORD` | 256bit | 32 字节对齐 | H7 默认 |

### 寄存器级编程 (F4)

```c
// 解锁序列
FLASH->KEYR = 0x45670123;
FLASH->KEYR = 0xCDEF89AB;

// 擦除 Sector 5
FLASH->CR |= FLASH_CR_PSIZE_1 | FLASH_CR_PSIZE_0;  // 32bit 并行
FLASH->CR |= FLASH_CR_SER;      // Sector 擦除
FLASH->CR |= (5 << FLASH_CR_SNB_Pos);  // Sector 5
FLASH->CR |= FLASH_CR_STRT;     // 开始擦除
while (FLASH->SR & FLASH_SR_BSY);  // 等待完成
FLASH->CR &= ~(FLASH_CR_SER | FLASH_CR_SNB);  // 清除标志

// 编程 Word
FLASH->CR |= FLASH_CR_PSIZE_1;  // 32bit
FLASH->CR |= FLASH_CR_PG;       // 编程模式
*(volatile uint32_t *)address = data;
while (FLASH->SR & FLASH_SR_BSY);
FLASH->CR &= ~FLASH_CR_PG;      // 退出编程模式

// 锁定
FLASH->CR |= FLASH_CR_LOCK;
```

### 编程注意事项

```
1. 写入前必须擦除（Flash 只能从 1→0，编程不能把 0 改回 1）
2. 擦除后数据为 0xFF（全 1）
3. 同一地址不能连续写两次（不擦除就写 = 数据损坏）
4. 地址必须对齐编程类型（WORD→4 字节对齐，DW→8 字节对齐）
5. 编程过程中掉电 = 该地址数据不可靠
6. Flash 擦写寿命：典型 10,000 次（Data Flash: 100,000 次）
```

## Option Bytes

> Option Bytes（选项字节）位于 Flash 的独立系统配置区，控制芯片的读保护、写保护、电压阈值、
> 看门狗模式、启动源等关键配置。解锁后编程，重新上电或系统复位后生效。

### ⚠️ 安全警告
- RDP Level 2 一旦写入，芯片将**永久锁定**，无法解除，无法调试
- 解除 RDP Level 1 会**全片擦除** Flash，固件将全部丢失
- 写 Option Bytes 失败可能导致芯片无法启动
- 所有写操作必须在 halt 状态下执行

### RDP 读保护

| 级别 | 值 | 描述 | 解除方法 |
|------|-----|------|---------|
| Level 0 | 0xAA | 无保护，可调试读取 | — |
| Level 1 | 任何非 0xAA/0xCC | 禁止调试接口读 Flash | 全片擦除后降回 Level 0 |
| Level 2 | 0xCC | 永久锁定，不可降级 | 不可逆！ |

### WRP 写保护

按扇区配置，防止 Flash 被意外写入/擦除。每个扇区对应 WRP 寄存器中的一位：
- 0 = 保护（不可写/擦）
- 1 = 不保护

### BOR 掉电复位电压

配置芯片在电源电压低于阈值时自动复位，防止低压误操作：

| BOR Level | 阈值 (F4) |
|-----------|-----------|
| 0 | 1.8V |
| 1 | 2.1V |
| 2 | 2.4V |
| 3 | 2.7V |

### STM32 各系列 Option Bytes 字段

#### STM32F4 系列
| 位域 | 名称 | 默认值 | 说明 |
|------|------|--------|------|
| [7:0] | RDP | 0xAA | 读保护级别 |
| [8] | nRST_STOP | 1 | 进入 STOP 模式是否复位 |
| [9] | nRST_STDBY | 1 | 进入待机模式是否复位 |
| [11:10] | BOR_LEV | 0x3 | 掉电复位阈值 |
| [12] | WDG_SW | 1 | 独立看门狗软件/硬件模式 |
| [31:16] | nWRP | 0xFFFF | 扇区写保护（0=保护） |

#### STM32H7 系列
| 位域 | 名称 | 说明 |
|------|------|------|
| [7:0] | RDP | 读保护（0xAA=L0, 0xCC=L2）|
| [25] | SECURITY | TrustZone 安全启动使能 |
| [26] | BOOT_UBE | 用户 Flash 安全区 Boot |
| [28] | BCM4/BCM7 | Cortex-M4/M7 Boot 使能（双核）|

#### STM32G0 系列
| 位域 | 名称 | 说明 |
|------|------|------|
| [7:0] | RDP | 读保护 |
| [8] | nBOOT1 | Boot 源配置（配合 BOOT0 引脚）|
| [14] | nBOOT_SEL | BOOT0 信号来源（引脚/Option Bit）|
| [23:16] | BORF_LEV | 掉电复位上升阈值 |
| [25:24] | BORR_LEV | 掉电复位下降阈值 |

### Boot 配置

```
STM32 启动源选择（以 STM32F4 为例）
BOOT1(PB2)  BOOT0  启动源
    x          0   Flash（正常运行）
    0          1   系统存储器（内置 Bootloader，用于 ISP 烧录）
    1          1   SRAM（用于调试）
```

Option Bytes 中 nBOOT_SEL=0 时，Boot0 引脚决定启动源；nBOOT_SEL=1 时，由 Option Bytes 中的 nBOOT0 位决定。

### 量产安全配置流程

```
推荐量产 Option Bytes 配置流程：
Step 1  烧录固件并验证功能正常
Step 2  设置 BOR Level（防低压运行，推荐 Level 2）
Step 3  配置 WRP（保护 Bootloader 扇区）
Step 4  最后设置 RDP Level 1（若需防读取）
        ⚠️ RDP 必须最后设置，设置后调试接口受限
Step 5  绝不设置 RDP Level 2（除非确定永不需要更新固件）
```

### OpenOCD 操作命令

#### STM32F4 系列
```
stm32f4x options_read 0          # 读取
stm32f4x options_write 0 0x...   # 写入（慎用）
stm32f4x unlock 0                 # 解锁（清除 RDP，全片擦除）
```

#### STM32H7 系列
```
stm32h7x options_read 0          # 读取
stm32h7x options_write 0 0x...   # 写入（慎用）
stm32h7x unlock 0                 # 解锁（清除 RDP，全片擦除）
```

#### 读取示例输出
```
═══════════ STM32 Option Bytes ═══════════
RDP Level    : 0 (无读保护)
nRST_STOP    : 1 (进入STOP模式不复位)
nRST_STDBY   : 1 (进入待机模式不复位)
IWDG_SW      : 1 (独立看门狗由软件控制)
BOR Level    : 3 (VBOR~2.7V)
WRP Sectors  : 无
══════════════════════════════════════════
```

### Option Bytes 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| OpenOCD 无法连接 | 读保护已启用 | 通过解锁流程清除（需全片擦除）|
| 写入超时 | 供电不稳定 | 检查 VDD 和 VBAT 供电 |
| 验证失败 | 写入值与回读不符 | 重试或检查芯片损坏 |
| `RDPKEY incorrect` | STM32L5/H5 需要 RDP 解锁密钥 | 查阅芯片手册获取正确密钥 |
| `Option bytes not readable` | 芯片在 PCROP 或 RDP2 状态 | 需硬件解除保护 |

## IAP (In-Application Programming)

### 基本原理

```
Bootloader (Sector 0)          App (Sector 1+)
+---------------------+        +---------------------+
| Vector Table        |        | Vector Table        |
| IAP 代码            |        | App 代码            |
| (Flash/串口/OTA接收) |  →→→   |                     |
| 擦写 App 区         |        |                     |
+---------------------+        +---------------------+
        ↑                           ↑
  0x08000000                  0x0800XXXX
  (复位入口)                   (APP 偏移地址)
```

### Bootloader 跳转代码

```c
typedef void (*pFunction)(void);

void jump_to_app(uint32_t app_addr)
{
    // 1. 检查 App 是否有有效向量表（前 4 字节 = MSP 栈顶指针）
    uint32_t msp_value = *(volatile uint32_t *)app_addr;
    if (msp_value == 0xFFFFFFFF) {
        // Flash 未烧录，不跳转
        return;
    }

    // 2. 关闭所有外设中断
    HAL_RCC_DeInit();
    HAL_DeInit();

    // 3. 关闭全局中断
    __disable_irq();

    // 4. 设置向量表偏移（可选，看 App 是否需要）
    SCB->VTOR = app_addr;

    // 5. 设置 App 的栈指针和 PC
    uint32_t reset_vector = *(volatile uint32_t *)(app_addr + 4);
    pFunction app_entry = (pFunction)reset_vector;

    // 6. 切到 App 栈
    __set_MSP(msp_value);

    // 7. 跳转（再使能中断在 App 中做）
    app_entry();
}
```

## EEPROM 模拟

### 原理

利用 Flash 的两个 Page 轮流存储数据，模拟 EEPROM 的逐字节修改能力：

```
Page A (Active)               Page B (Transfer)
+-------------------+         +-------------------+
| Header            |         | Header (empty)    |
| Var1: new_val     |  →→→    | Var1: new_val     |
| Var2: old_val     |  (满时  | Var2: updated_val |
| ...               |   转移) | ...               |
| Free space...     |         | Free space...     |
+-------------------+         +-------------------+
```

### ST HAL EEPROM 模拟

```c
// CubeMX 生成 EEPROM 模拟代码
// 使用 FLASH_If_Write/FLASH_If_Read 接口

// 初始化
uint32_t eeprom_init(void)
{
    HAL_FLASHEx_EEPROM_Enable();
    // 检查两个 Page 状态
    // 如果 Page 满，自动转移到另一个 Page 并擦除当前 Page
    return EE_OK;
}

// 写入（先查找是否存在旧值，有则追加新值）
uint32_t eeprom_write(uint16_t var_id, uint16_t data)
{
    return EE_WriteVariable(var_id, data);
}

// 读取（遍历 Page 查找最新的 Var 值）
uint32_t eeprom_read(uint16_t var_id, uint16_t *data)
{
    return EE_ReadVariable(var_id, data);
}
```

**重要限制**：
- Flash 擦写寿命 10,000 次（相比 EEPROM 的 100,000~1,000,000）
- 使用两个 Page 磨损均衡后寿命×2
- 适用于配置参数（几百次修改），不适用于频繁写数据

## 双 Bank 模式

### 适用系列

| 系列 | 双 Bank 条件 | 用途 |
|------|------------|------|
| F4 (1MB+) | 默认 Bank1/Bank2 | 读-写-读 (RWW) |
| H7 | 默认 | 同时读写两个 Bank |
| G4 | 可配置 (nDBANK) | 安全性/OTA |

### RWW (Read-While-Write)

```c
// F4 1MB+ 双 Bank 支持 RWW：
// Bank1 执行代码的同时可以擦写 Bank2（反之亦然）

// 检查当前 CPU 所在 Bank
uint32_t get_current_bank(void)
{
    uint32_t pc;
    asm volatile("MOV %0, PC" : "=r"(pc));
    if (pc < 0x08100000) return 1;  // Bank 1 (0x08000000~0x080FFFFF)
    else return 2;                   // Bank 2 (0x08100000~0x081FFFFF)
}

// 切换到另一个 Bank 后擦写
void erase_other_bank(void)
{
    // 如果当前在 Bank1，切换到 Bank2 然后擦 Bank1
    // 如果当前在 Bank2，切换到 Bank1 然后擦 Bank2
}
```

## Flash 错误处理

### 错误标志

```c
// Flash SR 寄存器错误位
FLASH->SR;  // 读取后自动清除

// 常见错误：
#define FLASH_SR_PGSERR   (1 << 7)   // 编程序列错误（未擦除就写）
#define FLASH_SR_PGPERR   (1 << 6)   // 编程并行大小错误（对齐不对）
#define FLASH_SR_PGAERR   (1 << 5)   // 编程对齐错误（地址不对齐）
#define FLASH_SR_WRPERR   (1 << 4)   // 写保护错误（扇区受 WRP 保护）
#define FLASH_SR_OPERR    (1 << 1)   // 操作错误（操作冲突）
#define FLASH_SR_BSY      (1 << 0)   // 忙标志
```

| 错误 | 原因 | 解决 |
|------|------|------|
| PGAERR | 地址未按编程宽度对齐 | 确认地址对齐到编程类型宽度 |
| PGPERR | PSIZE 设置不对应硬件 | 检查 VDD 范围对应的 PSIZE |
| PGSERR | 没有先 PG=1 就写数据 | 写之前 CR_PG 置位 |
| WRPERR | 扇区受 WRP 保护 | 检查 Option Bytes |
| BSY 卡死 | Flash 控制器异常 | 检查时钟是否稳定、VDD 是否正常 |

## 系列差异

| 特性 | F1 | F4 | G4 | H7 |
|------|-----|-----|-----|-----|
| 编程粒度 | Half-word (16bit) | Word (32bit) | Double-word (64bit) | Quad-word (256bit) |
| 擦除单元 | Page (1/2KB) | Sector (16/128KB) | Page (2KB) | Sector (8/128KB) |
| 等待周期寄存器 | `FLASH->ACR` | `FLASH->ACR` (LATENCY) | `FLASH->ACR` | `FLASH->ACR` (LATENCY) |
| Key 值 | 0x45670123/0xCDEF89AB | 同左 | 同左 | 同左 |
| Option Key | 0x8C9DAEBF | 同左 | 同左 | 同左 |
| 双 Bank | 无 | 1MB+ 有 | 可配置 | 默认双 Bank |
| ART 加速 | 无 | 有 | 无 | 有 (H7 v2) |
| ECC | 无 | 无 | 有 | 有 |

## 调试技巧

```c
// 1. 验证 Flash 内容
// 使用 JLink Commander:
//   loadbin app.bin 0x08000000
//   mem32 0x08000000 16  // 读前 64 字节验证

// 2. 检查 Flash 操作状态
uint32_t check_flash_status(void)
{
    uint32_t sr = FLASH->SR;
    if (sr & FLASH_SR_BSY) return 1;       // 还在忙
    if (sr & FLASH_SR_WRPERR) return -1;   // 写保护
    if (sr & FLASH_SR_PGAERR) return -2;   // 对齐错误
    return 0;  // 正常
}

// 3. 查看扇区信息
printf("Flash Size: %d KB\n", *(uint16_t *)0x1FFF7A22);  // F4 唯一ID+容量
```

## 边界定义

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | 擦除 API | 写入 API | 等待周期 |
|------|---------|---------|----------|
| STM32 HAL | `HAL_FLASH_Erase_Sector` | `HAL_FLASH_Program` | `HAL_FLASHEx_OB_GetLatency` |
| STM32 SPL | `FLASH_ErasePage` | `FLASH_ProgramHalfWord/Word` | `FLASH_SetLatency` |
| STM32 寄存器 | `FLASH->CR |= CR_SER` | `FLASH->CR |= CR_PG; *addr = data` | `FLASH->ACR = LATENCY` |
| ESP-IDF | `spi_flash_erase_sector` | `spi_flash_write` | 硬件自动管理 |
| GD32 | `fwdgt_write...` | `fwdgt_write...` | 查对应 RM |

注：ESP32 用 SPI Flash 控制器操作，非内部 Flash 方式，API 差异大。

- **不覆盖外部 Flash (SPI NOR/NAND)** — 使用 `peripheral-driver` + `spi-bus`
- **不覆盖 OTP 区域**（一次性烧录区，各系列差异大）
- **不覆盖 Flash 加密/签名** — 使用 `firmware-sign` 和 `ota-package`
- **Option Bytes 已在本章完整覆盖** — 见上方 Option Bytes 章节
- Bootloader 和 IAP 的高级安全策略参考 `firmware-sign`
