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

> 参考 Option Bytes 专用 skill：`option-bytes`

```c
// Option Bytes 在 Flash 的独立区域
// 解锁后编程，重新上电或系统复位后生效

// 常用选项：
// RDP (Read Protection): 0xAA=无, 0xBB=Level1, 0xCC=Level2
// WRP (Write Protection): 按扇区保护
// PCROP (Proprietary Code Readout Protection): 代码读保护
// BOR (Brown Out Reset) 阈值
// nRST_STOP/STDBY: 复位脚在低功耗模式下
```

### RDP 等级

| 等级 | 值 | 描述 | 解除方法 |
|------|-----|------|---------|
| Level 0 | 0xAA | 无保护 | — |
| Level 1 | 任何非 0xAA/0xCC | 读保护 | 全片擦除后降回 Level 0 |
| Level 2 | 0xCC | 永久保护 | 不可逆！ |

**警告**：从 Level 1 退到 Level 0 会触发全片擦除（Mass Erase），全部数据丢失。

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
- **Option Bytes 详细配置** — 使用专用 skill `option-bytes`
- Bootloader 和 IAP 的高级安全策略参考 `firmware-sign`
