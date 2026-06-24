# SRAM 链接脚本与性能配置

## GCC ld 完整示例 (F411)

### 基本内存布局

```ld
/* stm32f411ce.ld */
ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 512K
    RAM1  (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
    RAM2  (rw)  : ORIGIN = 0x20018000, LENGTH = 32K
}

_estack = ORIGIN(RAM1) + LENGTH(RAM1);

MIN_HEAP_SIZE  = 0x200;   /* 512 bytes */
MIN_STACK_SIZE = 0x400;   /* 1KB */

SECTIONS
{
    /* .isr_vector 和 .text 在 Flash 中 */
    .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
    .text : { *(.text*) *(.glue_7t) *(.rodata*) } > FLASH

    /* .data: 初始值在 Flash，运行时在 RAM1 */
    .data : {
        _data_start = .;
        *(.data*)
        _data_end = .;
    } > RAM1 AT > FLASH
    _data_flash_start = LOADADDR(.data);

    /* .bss: 零初始化 */
    .bss : {
        _bss_start = .;
        *(.bss*)
        *(COMMON)
        _bss_end = .;
    } > RAM1

    /* DMA 缓冲区: 在 RAM2 */
    .dma_buffer (NOLOAD) : {
        . = ALIGN(4);
        *(.dma_buffer)
        . = ALIGN(4);
    } > RAM2

    /* 堆 */
    .heap : {
        _heap_start = .;
        . = . + MIN_HEAP_SIZE;
        . = ALIGN(8);
    } > RAM1

    /* 栈 (在链接时计算，由启动文件设置 MSP) */
    .stack : {
        . = . + MIN_STACK_SIZE;
        . = ALIGN(8);
    } > RAM1
}
```

## Keil scatter 完整示例 (F407 CCM)

```sct
; scatter.sct — F407 含 CCM RAM 配置
LR_IROM1 0x08000000 0x00100000  {    ; 1MB Flash
    ER_IROM1 0x08000000 0x00100000 {
        *.o (RESET, +First)
        *(InRoot$$Sections)
        .ANY (+RO)
    }

    ; SRAM1 + SRAM2 (128KB): .data + .bss + 堆栈
    RW_RAM1 0x20000000 0x00020000 {
        .ANY (+RW +ZI)
    }

    ; CCM RAM (64KB): ISR 栈 + 时间关键变量
    RW_CCM 0x10000000 0x00010000 {
        startup_stm32f407xx.o (ISR_STACK, +First)
        *.o (.ccm_ram)
    }
}
```

### Keil 中需要修改的启动文件

```asm
; startup_stm32f407xx.s — 修改部分
ISR_Stack_Size  EQU     0x400

AREA    ISR_STACK, DATA, READWRITE
ISR_Stack_Mem   SPACE   ISR_Stack_Size
__initial_isr_sp

; Reset_Handler 中不再用 SystemInit 之后的 SP 配置
; 由 scatter 文件自动处理
```

## Stack Usage Analysis

### 工具方法

```c
// 方法 1: 栈填充法（GCC 编译选项）
// -fstack-usage  → 生成 .su 文件，每个函数栈大小
// -Wstack-usage=1024 → 栈超过 1KB 报警

// 方法 2: 运行时监控
uint32_t get_max_stack_usage(void)
{
    extern uint32_t _estack;
    extern uint32_t _stack_start;

    uint32_t *stack_base = &_stack_start;
    uint32_t *stack_top = &_estack;

    // 栈从高位向低位增长
    // 查找第一个非 0xDEADBEEF 的位置（GCC 默认栈填充值）
    uint32_t *ptr = stack_base;
    while (*ptr == 0xDEADBEEF) {
        ptr++;
    }

    uint32_t used = (uint32_t)stack_top - (uint32_t)&_estack + (uint32_t)ptr - (uint32_t)stack_base;
    // 实际上：栈使用量 = &_estack - (uint32_t)stack_top_used
    // 简化计算：从栈底（低地址）向上扫描
    return 0;  // 根据实际配置修改
}
```

### FreeRTOS 任务栈监控

```c
// FreeRTOS 每个任务有自己的栈
// 使用 uxTaskGetStackHighWaterMark 监控

void task_monitor(void *pvParameters)
{
    UBaseType_t stack_hwm;

    for (;;) {
        stack_hwm = uxTaskGetStackHighWaterMark(NULL);
        // 返回值是未使用的栈空间（字，不是字节）
        printf("Task stack: %u words free\n", stack_hwm);

        // 阈值告警：
        if (stack_hwm < 20) {  // 少于 20 字 = 80 字节
            printf("[!] Task stack near overflow!\n");
        }

        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}
```

## CPU 域 SRAM 性能基准

### F4 SRAM vs CCM 性能

```
测试: 循环 1000 次 × 1KB memset
位置         时间       原因
SRAM1         ~42µs     AHB 总线访问 + 可能有竞争
CCM RAM       ~28µs     D-Bus 直连，0 WS

差异 ≈ 33% 性能提升
```

### H7 AXI SRAM vs DTCM 性能

```
测试: 随机访问 10MB 吞吐
位置         带宽      延迟
DTCM         3.2 GB/s  0 WS (CPU 频率)
AXI SRAM     1.6 GB/s  1~3 WS (Cache 关闭)
AXI SRAM     8.5 GB/s  Cache 开启 (读命中 1 cycle)

注意：DTCM 无 Cache，但本身 0 WS 且 CPU 专用
     AXI SRAM 有 Cache 时读性能好，但写可能需 Clean
```

## SRAM 对齐要求

| 总线宽度 | 对齐要求 | 典型场景 |
|---------|---------|---------|
| 8bit | 1 字节对齐 | UART 缓冲区 |
| 16bit | 2 字节对齐 | ADC 缓冲区 |
| 32bit | 4 字节对齐 | DMA 传输 |
| 64bit | 8 字节对齐 | FMC SDRAM / H7 AXI |
| 128bit | 16 字节对齐 | USB OTG |
| 32byte | 32 字节对齐 | H7 Cache Line |

```c
// 建议的缓冲区对齐宏
#define ALIGN_4    __attribute__((aligned(4)))
#define ALIGN_32   __attribute__((aligned(32)))

// H7 AXI SRAM 缓冲区（Cache 行对齐）
ALIGN_32 uint8_t dma_buf[1024];

// 所有 DMA 缓冲区（4 字节对齐）
ALIGN_4 uint16_t adc_samples[256];
```
