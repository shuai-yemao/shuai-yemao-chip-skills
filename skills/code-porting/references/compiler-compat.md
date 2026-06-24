# 编译器兼容性对照表

> ARM Compiler (ARMCC) v5/v6、GCC Arm Embedded、IAR ICCARM 三种编译器在嵌入式移植中的关键差异。
> 主要用于 IDE/工具链迁移场景（Keil→IAR、Keil→CMake+GCC、IAR→CMake+GCC）。

## 预定义宏

| 含义 | ARMCC v5 | ARMCC v6 (Clang) | GCC | IAR |
|------|----------|-----------------|-----|-----|
| 编译器标识 | `#ifdef __CC_ARM` | `#ifdef __ARMCC_VERSION` | `#ifdef __GNUC__` | `#ifdef __ICCARM__` |
| ARM 架构 | `__TARGET_ARCH_xx` | 同左 | `__ARM_ARCH_xx` | `__ARM_ARCH_xx` |
| Cortex-M 型号 | `__CORTEX_M` | 同左 | `__CORTEX_M` | `__CORTEX_M` |
| 大小端 | `__BIG_ENDIAN` / 缺省小端 | 缺省小端 | `__ARMEL__` (小端) / `__ARMEB__` (大端) | `__LITTLE_ENDIAN__` |
| 软/硬浮点 | `__SOFTFP__` / `__VFP_FP__` | 同左 | `__SOFTFP__` / `__ARM_PCS_VFP` | `__SOFTFP__` / 无宏则硬浮点 |
| 调试 | `__DEBUG` | 同左 | `-DNDEBUG` (release) | 自定义 |
| 优化等级 | 无统一宏 | 无统一宏 | `__OPTIMIZE__` | 无统一宏 |
| sizeof(int) | 4 | 4 | 4 | 4 |
| sizeof(long) | 4 | 4 | 4 | 4 |
| sizeof(long long) | 8 | 8 | 8 | 8 |
| sizeof(void*) | 4 (CM3/4/7) | 4 | 4 | 4 |
| char 符号 | 默认 unsigned | 默认 unsigned | 默认 signed | 默认 signed |

## 函数/变量属性

| 功能 | ARMCC v5 | ARMCC v6 | GCC | IAR |
|------|----------|---------|-----|-----|
| 中断函数 | `__irq` | `__attribute__((interrupt))` | `__attribute__((interrupt("IRQ")))` | `__interrupt` |
| 弱符号 | `__weak` | `__attribute__((weak))` | `__attribute__((weak))` | `__weak` |
| 对齐 | `__align(N)` | `__attribute__((aligned(N)))` | `__attribute__((aligned(N)))` | `__align(N)` |
| 打包 (1字节对齐) | `__packed` | `__attribute__((packed))` | `__attribute__((packed))` | `__packed` |
| 内联 | `__inline` | `__inline` | `static inline` 或 `__inline__` | `__inline` |
| 纯函数 | `__pure` | `__attribute__((const))` | `__attribute__((const))` | `__pure` |
| 已弃用 | `__declspec(deprecated)` | `__attribute__((deprecated))` | `__attribute__((deprecated))` | `__attribute__((deprecated))` |
| 未使用 | `__attribute__((unused))` | `__attribute__((unused))` | `__attribute__((unused))` | `__attribute__((unused))` |
| Section | `__attribute__((section(".xxx")))` | 同左 | `__attribute__((section(".xxx")))` | `@ ".xxx"` |
| 绝对地址 | `__attribute__((at(addr)))` | `__attribute__((section(".ARM.__at_addr")))` | 链接脚本定义 | `@ addr` |
| 长调用 | `__long_call` | `__attribute__((long_call))` | `__attribute__((long_call))` | 链接器选项 |
| RAM 函数 | `__attribute__((section(".ramfunc")))` | 同左 | 同左 | `__ramfunc` |
| 可变参数 | `__VA_ARGS__` | 同左 | 同左 | 同左 |
| 结构的静态断言 | `_Static_assert` | `_Static_assert` | `_Static_assert` (C11) | `static_assert` |

## 内联汇编

| 特性 | ARMCC (__asm) | GCC (__asm__) | IAR (asm) |
|------|--------------|---------------|-----------|
| 语法格式 | `__asm { instr }` | `__asm__("instr": out: in: clobber)` | `asm("instr")` |
| 寄存器访问 | 直接写 | 约束指定 | 直接写 |
| C 变量引用 | 可直接用 | 需通过约束 | $ 前缀 |
| MSR/MRS | 直接写 | 需 volatile | 直接写 |

**示例：CPSID 中断关**

```c
// ARMCC
__asm { CPSID I }

// GCC
__asm__ volatile ("cpsid i" : : : "memory")

// IAR
asm("cpsid i");
```

**示例：读取 MSP**

```c
// ARMCC
__asm uint32_t __get_MSP(void)
{
    MRS R0, MSP
    BX LR
}

// GCC
__attribute__((always_inline))
static inline uint32_t __get_MSP(void)
{
    uint32_t result;
    __asm__ volatile ("MRS %0, MSP" : "=r" (result));
    return result;
}

// IAR
__arm_inline uint32_t __get_MSP(void)
{
    return __get_MSP();
    // 或直接: asm("MRS R0, MSP");
}
```

## 内建函数与 intrinsic

| 功能 | ARMCC | GCC | IAR |
|------|-------|-----|-----|
| 关中断 | `__disable_irq()` | 同左 | 同左 |
| 开中断 | `__enable_irq()` | 同左 | 同左 |
| 等待中断 | `__WFI()` | 同左 | 同左 |
| 等待事件 | `__WFE()` | 同左 | 同左 |
| 发事件 | `__SEV()` | 同左 | 同左 |
| 指令同步屏障 | `__ISB()` | 同左 | 同左 |
| 数据同步屏障 | `__DSB()` | 同左 | 同左 |
| 数据存储屏障 | `__DMB()` | 同左 | 同左 |
| 反转字节序 (32位) | `__REV` | `__REV` | `__REV` |
| 反转字节序 (16位) | `__REV16` | `__REV16` | `__REV16` |
| 位反转 | `__RBIT` | `__RBIT` | `__RBIT` |
| 前导零计数 | `__CLZ` | `__CLZ` | `__CLZ` |
| 饱和加减 | `__SSAT` / `__USAT` | 同左 | 同左 |
| 位带别名 | `__BITBAND` | 宏实现 | `__BITBAND` |
| LDREX/STREX | `__LDREXB/W/D` / `__STREXB/W/D` | 同左 (intrinsic 或 asm) | 同左 |
| BKPT | `__breakpoint(N)` | `BKPT` asm | `__BKPT(N)` |
| NOP | `__nop()` | `NOP` asm 或 `__NOP()` | `__no_operation()` |

> **注意**：ARMCC v5 的 CMSIS intrinsic 函数名以 `__` 开头（如 `__disable_irq`），ARMCC v6 兼容。GCC 的 CMSIS 实现同样提供这些函数。IAR 的 CMSIS-in-Core 头文件已全部兼容。一般移植场景无需逐个修改 intrinsic——CMSIS 头文件已统一。

## 数据类型兼容性

| C99 类型 | ARMCC | GCC | IAR |
|----------|-------|-----|-----|
| `stdint.h` | 完整 | 完整 | 完整 |
| `bool` (stdbool.h) | C99 支持 | C99 支持 | C99 支持 |
| `uint8_t` / `int8_t` | ✓ | ✓ | ✓ |
| `uint16_t` / `int16_t` | ✓ | ✓ | ✓ |
| `uint32_t` / `int32_t` | ✓ | ✓ | ✓ |
| `uint64_t` / `int64_t` | ✓ (8字节对齐) | ✓ | ✓ |
| `float` | 4字节, IEEE 754 | 4字节, IEEE 754 | 4字节, IEEE 754 |
| `double` | 8字节 | 8字节 | 8字节 |

> 移植兼容性：使用 `stdint.h` 类型（`uint32_t`, `uint8_t` 等）的代码在三种编译器下完全兼容。

## 链接脚本差异

| 特性 | ARMCC (*.sct) | GCC (*.ld) | IAR (*.icf) |
|------|--------------|------------|-------------|
| 布局语法 | LR/ER 区段 | SECTIONS / MEMORY | define / place in |
| Flash 区域 | `LR_IROM1 0x08000000 0x00100000` | `FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M` | `define symbol __ICFEDIT_region_ROM_start__ = 0x08000000` |
| SRAM 区域 | `RW_IRAM1 0x20000000 0x00020000` | `RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 128K` | `define symbol __ICFEDIT_region_RAM_start__ = 0x20000000` |
| 向量表 | `*(RESET, +First)` | `.isr_vector : { KEEP(*(.isr_vector)) }` | `place at start of ROM { section .isr_vector }` |
| 只读数据 | `*(InRoot$$Sections)` | `*(.rodata)` | 自动管理 |
| 初始化数据 | `*(+RW)`, 复制代码自动 | `.data : { *(.data) } >RAM AT>FLASH` | `initialize by copy { rw }` |
| 零初始化 | `*(+ZI)` | `.bss : { *(.bss) } >RAM` | `initialize by copy { rw }; do not initialize { zbss }` |
| 堆定义 | `ARM_LIB_HEAP 0x20004000 0x400` | 无原生堆段（OS 决定） | `define symbol __ICFEDIT_size_heap__ = 0x400` |
| 栈定义 | `ARM_LIB_STACK 0x20005000 0x400` | `_estack = ORIGIN(RAM) + LENGTH(RAM)` | `define symbol __ICFEDIT_size_cstack__ = 0x400` |
| 自定义 Section | `.ANY(+SectionName)` | `*(.SectionName)` | `place in SectionName { .* }` |

**自动转换建议**：使用 `ld.sct2ld` 或手动对照上表逐映射。链接脚本的修改直接影响程序运行，必须逐行验证。

## 编译器命令行选项

| 功能 | ARMCC v5 | ARMCC v6 (Clang) | GCC | IAR |
|------|----------|-----------------|-----|-----|
| CPU | `--cpu Cortex-M4` | `--target=arm-arm-none-eabi -mcpu=cortex-m4` | `-mcpu=cortex-m4` | `--cpu Cortex-M4` |
| FPU | `--fpu=FPv4-SP-D16` | `-mfpu=fpv4-sp-d16` | `-mfpu=fpv4-sp-d16` | `--fpu VFPv4_sp` |
| 浮点 ABI | 不支持选择（默认 softfp） | `-mfloat-abi=soft/hard` | `-mfloat-abi=soft/hard` | `--aeabi --aapcs --hard/--soft` |
| 优化 | `-O0/-O1/-O2/-O3` | `-O0/-O1/-O2/-O3/-Ofast` | `-O0/-O1/-O2/-O3/-Os/-Ofast` | `-Ol/-Oh/-Om/-Oz` |
| 调试 | `--debug -g` | `-g` | `-g` | `--debug` |
| C 标准 | `--c99` / `--c11` | `-std=c99/c11/c17` | `-std=c99/c11/c17/gnu11` | `--c99` / `--c11` |
| 包含路径 | `-I path` | 同左 | 同左 | `-I` |
| 宏定义 | `-D MACRO` | 同左 | 同左 | `-D` |
| 警告等级 | `-W` 系列 | `-Wall -Wextra -Wpedantic` | `-Wall -Wextra -Wpedantic` | `-We` |
| 错误停止 | 默认 | `-Werror` | `-Werror` | `--no_warnings` |
| 输出 | `-o output.o` | `-o output.o` | `-o output.o` | `-o output.o` |

### IAR 优化选项说明

| IAR 选项 | 等级 | 说明 |
|----------|------|------|
| `-Ol` | Low | 最小优化，适合调试 |
| `-Om` | Medium | 平衡优化 |
| `-Oh` | High | 高性能优化 |
| `-Oz` | Size | 代码体积优先 |
| `-Ohz` | High + Size | 高性能 + 体积平衡 |

## 启动代码差异

| 项目 | ARMCC | GCC | IAR |
|------|-------|-----|-----|
| 启动文件名 | `startup_xxx.s` | `startup_xxx.s` | `startup_xxx.s` |
| 向量表格式 | DCD | .word / .long | DC32 |
| 弱符号默认 ISR | `__weak` | `__attribute__((weak))` | `__weak` |
| 堆栈初始化 | LDR SP, =_estack | 同左 | 同左 |
| .bss 清零 | 循环清零 | 循环清零 | 循环清零 |
| .data 复制 | 复制代码 | 复制代码 | 复制代码 |
| SystemInit 调用 | BL SystemInit | BL SystemInit | BL SystemInit |
| main 调用 | BL __main (ARMCC 库) | BL main | BL main |
| FPU 使能 | 可放入 SystemInit | 可放入 SystemInit | 可放入 SystemInit |

> **关键差异**：ARMCC 的 `__main` 会先调用 C 库初始化后再跳转到 `main()`；GCC 和 IAR 的启动文件直接跳转到 `main()`。在 `__main` 执行的初始化代码（如分散加载、堆栈初始化）在 ARMCC 中由链接器自动插入，GCC/IAR 则完全由启动文件中的汇编代码完成。因此 ARMCC 的 `.sct` 中由 `InRoot$$Sections` 管理的 Section 在迁移到 GCC 时需要在 `.ld` 中手动处理。

## 代码大小/性能对比经验

| 场景 | ARMCC v5 | ARMCC v6 | GCC (-Os) | IAR (-Oz) |
|------|----------|---------|-----------|-----------|
| 代码密度 (典型) | 基线 | -5%~+10% | -5%~+5% | -10%~+0% |
| 浮点算力 (CM4F) | 基准 | +0~5% | +0~10% | 基准 |
| 中断延迟 | 基准 | 基准 | 略高 (10~20 cycles) | 基准 |
| Misra 检查 | 有限 | 有限 | 外部工具 | 内置 |

> **注意**：IAR 通常代码密度最优（特别是 -Oz），GCC 通常代码密度略差但在调试友好度上最优。移植后建议在目标平台上重新测量性能基线，不要依赖于原平台的性能数据。
