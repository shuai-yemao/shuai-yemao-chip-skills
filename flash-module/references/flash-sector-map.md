# Flash Sector / Page 布局速查表

## STM32F103 (F1)

### 中容量 F103C8T6 (64KB)

| 页 | 起始地址 | 大小 | 用途 |
|----|---------|------|------|
| Page 0 | 0x08000000 | 1KB | 中断向量表 + Bootloader |
| Page 1~62 | 0x08000400~ | 1KB | 应用代码 |
| Page 63 | 0x0800FC00 | 1KB | 末页 |

### 大容量 F103ZET6 (512KB)

| 页 | 起始地址 | 大小 |
|----|---------|------|
| Page 0~255 | 0x08000000~ | 2KB/页，共 512KB |

**注意**：F103 页大小在 16KB 以下芯片为 1KB，16KB 以上为 2KB。

## STM32F407ZGT6 (1MB)

| 扇区 | 起始地址 | 大小 | Bank |
|------|---------|------|------|
| S0 | 0x08000000 | 16KB | Bank 1 |
| S1 | 0x08004000 | 16KB | Bank 1 |
| S2 | 0x08008000 | 16KB | Bank 1 |
| S3 | 0x0800C000 | 16KB | Bank 1 |
| S4 | 0x08010000 | 64KB | Bank 1 |
| S5 | 0x08020000 | 128KB | Bank 1 |
| S6 | 0x08040000 | 128KB | Bank 1 |
| S7 | 0x08060000 | 128KB | Bank 1 |
| S8 | 0x08080000 | 128KB | Bank 2 |
| S9 | 0x080A0000 | 128KB | Bank 2 |
| S10 | 0x080C0000 | 128KB | Bank 2 |
| S11 | 0x080E0000 | 128KB | Bank 2 |

## STM32F411CEU6 (512KB)

| 扇区 | 起始地址 | 大小 | Bank |
|------|---------|------|------|
| S0 | 0x08000000 | 16KB | Bank 1 |
| S1 | 0x08004000 | 16KB | Bank 1 |
| S2 | 0x08008000 | 16KB | Bank 1 |
| S3 | 0x0800C000 | 16KB | Bank 1 |
| S4 | 0x08010000 | 64KB | Bank 1 |
| S5 | 0x08020000 | 128KB | Bank 1 |
| S6 | 0x08040000 | 128KB | Bank 1 |
| S7 | 0x08060000 | 128KB | Bank 1 |

> 512KB 版本只有 Bank 1 (S0~S7)，无 Bank 2。

## STM32F405/407 1MB (同上 S0~S11)

## STM32H743 (2MB)

| 扇区 | 起始地址 | 大小 | Bank |
|------|---------|------|------|
| S0 | 0x08000000 | 128KB | Bank 1 |
| S1 | 0x08020000 | 128KB | Bank 1 |
| S2~S6 | ... | 128KB | Bank 1 |
| S7 | 0x080E0000 | 128KB | Bank 1 |
| S8~S15 | 0x08100000~ | 128KB | Bank 2 |

> H7 每个 Sector 固定 128KB，前 8 个 Sector = Bank1 (1MB)，后 8 个 = Bank2 (1MB)

## STM32G474 (512KB)

| 页范围 | 起始地址 | 大小 | Bank | 页数 |
|--------|---------|------|------|------|
| Page 0~127 | 0x08000000 | 2KB | Bank 1 | 128 |
| Page 128~255 | 0x08040000 | 2KB | Bank 2 | 128 |

## Flash 容量读取

```c
// 通过 MCU ID 寄存器读取 Flash 大小（各系列不同）
// F4: 0x1FFF7A22
// H7: 0x1FF1E880
// G4: 0x1FFF75E0

// F4 示例：
uint16_t flash_size_kb = *(uint16_t *)0x1FFF7A22;
printf("Flash: %d KB\n", flash_size_kb);
```

## 向量表位置

所有 STM32 的 Flash 起始地址（复位后默认）：
```
0x08000000 — Main Flash 起始
0x00000000 — 别名映射（由 BOOT 引脚决定映射源）
```

BOOT 配置：
| BOOT0 | BOOT1 | 启动区域 |
|-------|-------|---------|
| 0 | X | Main Flash (0x08000000) |
| 1 | 0 | System Memory (Bootloader) |
| 1 | 1 | SRAM (0x20000000) |
