---
name: linker-scatter
version: "1.0.0"
description: "嵌入式链接脚本与分散加载文件指南（Keil .sct / GCC .ld / IAR .icf）。覆盖三种链接脚本语法对照、内存区域定义（ROM/RAM 地址与大小）、段布局（RO/RW/ZI/堆/栈）、自定义段放置、分散加载（多区加载/运行域）、STM32 各系列链接脚本模板、Bootloader 与 APP 分区脚本设计、链接错误诊断（region overflow/undefined symbol/implicit use）。当用户提到 SCT 文件、分散加载、链接脚本、linker script、scatter file、.sct、.ld、.icf、链接错误、region overflow、RAM 溢出、FLASH 溢出、段放置、RO 段、RW 段、ZI 段、加载域、运行域、链接器、linker、L6242E、L6225E、map 文件分析时使用。"
---

# 链接脚本与分散加载文件指南

> Keil .sct / GCC .ld / IAR .icf 三种链接脚本的语法、配置与调试。
> 解决 "region overflow"、"undefined symbol"、"implicit use" 等链接错误。
>
> 关联：`map-analyzer`（.map 文件分析）、`sram-module`（SRAM 配置）、`flash-module`（Flash 配置）

---

## 场景

- **region overflow 错误** — `Error: L6406E: No space in execution regions`
- **RAM 不够用了** — 想把 RW/ZI 段放到外部 SRAM
- **自定义段放置** — 需要把特定函数放到 RAM 执行（如 Flash 擦写函数）
- **Bootloader + APP 分区** — 两个工程的 SCT 文件需要配合
- **Keil → GCC 移植** — 需要把 .sct 翻译成 .ld
- **链接报错看不懂** — undefined symbol、implicit use 等

---

## 三种链接脚本语法对照

### 基本结构

| 概念 | Keil .sct | GCC .ld | IAR .icf |
|------|----------|---------|---------|
| 内存定义 | `LR_IROM1 0x08000000 0x00100000 { ... }` | `MEMORY { ROM (rx) : ORIGIN = 0x08000000, LENGTH = 1M }` | `define symbol __ICFEDIT_region_ROM_start__ = 0x08000000;` |
| 段放置 | `ER_IROM1 0x08000000 0x00100000 { *.o (RESET, +First) }` | `SECTIONS { .text : { *(.isr_vector) } > ROM }` | `place at address mem:0x08000000 { section .intvec };` |
| 注释 | `;` 或 `#` | `/* */` | `/* */` |

---

## Keil .sct 文件详解（最常用）

### STM32F4 标准 SCT 模板

```linker
; *************************************************************
; *** 加载域 LR_IROM1: 描述整个固件的加载位置（Flash）
; *************************************************************
LR_IROM1 0x08000000 0x00100000  {    ; 起始 0x08000000, 大小 1MB

  ; === 运行域 ER_IROM1: 在 Flash 中原地执行的段 ===
  ER_IROM1 0x08000000 0x00100000  {
    *.o (RESET, +First)                ; 中断向量表放最前面
    *(InRoot$$Sections)                ; __main 等 C 运行时
    .ANY (+RO)                         ; 所有只读段（代码+常量）
  }

  ; === 运行域 RW_IRAM1: 从 Flash 加载到 RAM 执行的段 ===
  RW_IRAM1 0x20000000 UNINIT 0x00020000  {
    .ANY (+RW +ZI)                     ; 读写数据 + 零初始化数据
  }

  ; === 运行域 ARM_LIB_HEAP: C 库堆 ===
  ARM_LIB_HEAP  +0  EMPTY 0x00000400 {
  }

  ; === 运行域 ARM_LIB_STACK: C 库栈 ===
  ARM_LIB_STACK +0  EMPTY 0x00000800 {
  }
}
```

### 语法速查

| 符号 | 含义 | 示例 |
|------|------|------|
| `+0` | 紧跟前一个域的结束地址 | `RW_IRAM1 +0 {` |
| `0x20000000` | 绝对地址 | `RW_IRAM1 0x20000000 {` |
| `UNINIT` | 不初始化（ZI 不清零） | 备份 SRAM 区域 |
| `+First` | 放在此段开头 | 中断向量表 |
| `+RO` | 只读数据（const、代码） | |
| `+RW` | 读写数据 | |
| `+ZI` | 零初始化数据 | |
| `.ANY` | 任意匹配（推荐替代通配符） | 比 `*.o` 灵活 |
| `EMPTY` | 保留空间但不产生数据 | 堆、栈 |
| `ALIGN 8` | 对齐到 N 字节 | |
| `PAD` | 填充对齐到特定大小 | |
| `FIXED` | 固定在指定地址 | 放置 OTA header |

### 常用配置修改

```linker
; 1. 增大栈（默认 0x400→0x800）
ARM_LIB_STACK +0  EMPTY 0x00000800 { }

; 2. 把某个函数放到 RAM 执行（加速 Flash 擦写）
RW_IRAM1 0x20000000 0x00020000 {
  *(.my_ram_functions)                  ; 自定义段
  .ANY (+RW +ZI)
}

; 3. 外部 SRAM（FSMC）
RW_EXT_SRAM 0x60000000 UNINIT 0x00100000 {
  *(.ext_sram_data)
}

; 4. Bootloader + APP 分区（Bootloader 只占 32KB）
LR_IROM1 0x08000000 0x00008000 {       ; 32KB Bootloader
  ER_IROM1 0x08000000 0x00008000 {
    *.o (RESET, +First)
    .ANY (+RO)
  }
  RW_IRAM1 0x20000000 0x00020000 {
    .ANY (+RW +ZI)
  }
}
```

---

## GCC .ld 文件要点

```ld
/* STM32F4 GCC 链接脚本片段 */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1M
  RAM   (xrw) : ORIGIN = 0x20000000, LENGTH = 128K
}

SECTIONS
{
  .isr_vector : {
    KEEP(*(.isr_vector))            ; 保留中断向量表（即使没引用）
  } > FLASH

  .text : {
    *(.text*)
    *(.rodata*)
  } > FLASH

  /* 放在 RAM 执行的函数 */
  .ram_func : {
    *(.ram_functions*)
  } > RAM AT > FLASH                 ; 加载在 Flash，运行在 RAM
  _ram_func_loadaddr = LOADADDR(.ram_func);

  .data : {
    _sdata = .;
    *(.data*)
    _edata = .;
  } > RAM AT > FLASH

  .bss : {
    _sbss = .;
    *(.bss*)
    _ebss = .;
  } > RAM

  _estack = ORIGIN(RAM) + LENGTH(RAM);  /* 栈顶 */
}
```

---

## 自定义段放置

### 在代码中声明自定义段

```c
/* Keil ARMCC */
#if defined(__CC_ARM)
    /* 放在 RAM 执行的 Flash 擦写函数 */
    #define RAM_FUNC __attribute__((section(".my_ram_functions")))

    /* 放在固定地址的配置信息 */
    #define AT_APP_HEADER __attribute__((section(".app_header"), zero_init))

/* GCC */
#elif defined(__GNUC__)
    #define RAM_FUNC __attribute__((section(".ram_functions")))
    #define AT_APP_HEADER __attribute__((section(".app_header")))

/* IAR */
#elif defined(__ICCARM__)
    #define RAM_FUNC __ramfunc
    #define AT_APP_HEADER __attribute__((section(".app_header")))
#endif

/* 使用 */
RAM_FUNC void flash_erase_sector(uint32_t addr)
{
    /* 此函数在 RAM 中执行，擦 Flash 时不会断片 */
    FLASH->KEYR = 0x45670123;
    FLASH->KEYR = 0xCDEF89AB;
    FLASH->CR |= FLASH_CR_SER;
    FLASH->AR = addr;
    FLASH->CR |= FLASH_CR_STRT;
    while (FLASH->SR & FLASH_SR_BSY);
}

AT_APP_HEADER const uint32_t g_app_header[4] = {0};
```

### SCT 中放置自定义段

```linker
; 1. 放在 RAM 执行（常用来加速 Flash 擦写）
RW_IRAM1 0x20000000 0x00020000 {
  *.o (.my_ram_functions)              ; 自定义函数段
  .ANY (+RW +ZI)
}

; 2. 放在 Flash 特定地址（APP Header / OTA 信息）
ER_IROM1 0x08000000 0x00100000 {
  *.o (RESET, +First)
  *.o (.app_header)                    ; 放在向量表之后
  .ANY (+RO)
}
```

---

## 常见链接错误

| 错误信息 | 根因 | 解决 |
|---------|------|------|
| `L6406E: No space in execution regions` | Flash/RAM 溢出 | 增大 region 或优化代码 |
| `L6407E: Sections of aggregate size > region` | 段总和超 region 限制 | 分区或优化 |
| `L6305W: Implicit use of ..\xxx.o` | 未显式匹配的 .o 文件 | 确认 SCT 匹配规则 |
| `L6242E: Cannot link object xxx.o` | 目标文件不兼容 | 检查编译器版本 |
| `Undefined symbol __main` | 缺少 C 运行时库 | 检查 --libpath 或 ML 选项 |
| `L6218E: Undefined symbol xxx` | 函数未定义 | 检查头文件路径和源文件 |
| `.ANY placement fails` | .ANY 没有足够空间 | 减少 .ANY 或增大 region |
| `region RAM overflowed by 1024 bytes` | .bss/.data 超 RAM | 减小 BSS 或增大 RAM |

---

## 输出

- SCT/LD/ICF 文件配置 — 针对具体需求的链接脚本
- 错误诊断 — 链接错误的根因分析和修复方案
- 自定义段方案 — 函数级/数据级放置策略

---

## 边界

- **不覆盖 .map 文件分析** — 那是 `map-analyzer` skill
- **不覆盖内存架构理论** — 那是 `arm-memory-architecture` skill
- **不覆盖 Flash/SRAM 外设配置** — 那是 `flash-module` / `sram-module`
- **不覆盖 Bootloader 分区设计** — 那是 `bootloader-design`
- Keil .sct / GCC .ld / IAR .icf 语法差异大，本 skill 以 .sct 为主，附带对照
