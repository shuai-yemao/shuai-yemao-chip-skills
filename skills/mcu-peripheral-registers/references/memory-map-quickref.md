# 外设内存映射速查

## STM32 通用内存映射

| 总线 | 起始地址 | 大小 | 典型外设 |
|------|---------|------|---------|
| Cortex-M 系统 | 0xE0000000 | 1 MB | SCB/NVIC/SysTick/MPU/FPU/ITM/DWT/TPIU |
| AHB3 | 0xC0000000 | 512 MB | FMC/FSMC（外部存储器） |
| AHB2 | 0x50000000 | 512 MB | USB OTG FS/HS、DCMI、RNG、HASH、CRYP |
| AHB1 | 0x40020000 | 512 MB | GPIOA~I、CRC、RCC、DMA1/2、BKPSRAM |
| APB2 | 0x40010000 | 64 KB | USART1/6、SPI1/4/5/6、TIM1/8/9/10/11、ADC1/2/3、EXTI |
| APB1 | 0x40000000 | 64 KB | TIM2~7/12~14、USART2~5、SPI2/3、I2C1~3、DAC、PWR、IWDG、WWDG、RTC |

## APB1 外设基地址 (0x40000000)

| 外设 | 基地址 | 偏移 | F1 兼容 |
|------|--------|------|---------|
| TIM2 | 0x40000000 | 0x00 | ✅ |
| TIM3 | 0x40000400 | 0x04 | ✅ |
| TIM4 | 0x40000800 | 0x08 | ✅ |
| TIM5 | 0x40000C00 | 0x0C | ❌ |
| TIM6 | 0x40001000 | 0x10 | ✅ |
| TIM7 | 0x40001400 | 0x14 | ✅ |
| USART2 | 0x40004400 | 0x44 | ✅ |
| USART3 | 0x40004800 | 0x48 | ✅ |
| UART4 | 0x40004C00 | 0x4C | ❌ |
| UART5 | 0x40005000 | 0x50 | ❌ |
| I2C1 | 0x40005400 | 0x54 | ✅ |
| I2C2 | 0x40005800 | 0x58 | ✅ |
| I2C3 | 0x40005C00 | 0x5C | ❌ |
| SPI2 | 0x40003800 | 0x38 | ✅ |
| SPI3 | 0x40003C00 | 0x3C | ❌ |
| DAC | 0x40007400 | 0x74 | ✅ |
| PWR | 0x40007000 | 0x70 | ✅ |
| IWDG | 0x40003000 | 0x30 | ✅ |
| WWDG | 0x40002C00 | 0x2C | ✅ |
| RTC (APB1) | 0x40002800 | 0x28 | ✅ (BKP) |

## APB2 外设基地址 (0x40010000)

| 外设 | 基地址 | 偏移 | F1 兼容 |
|------|--------|------|---------|
| TIM1 | 0x40010000 | 0x00 | ✅ |
| USART1 | 0x40011000 | 0x10 | ✅ |
| USART6 | 0x40011400 | 0x14 | ❌ (F4+) |
| SPI1 | 0x40013000 | 0x30 | ✅ |
| SPI4 | 0x40013400 | 0x34 | ❌ (F4+) |
| EXTI | 0x40013C00 | 0x3C | ✅ |
| ADC1 | 0x40012000 | 0x20 | ✅ |
| ADC2 | 0x40012100 | 0x21 | ✅ (F1/F4) |
| ADC3 | 0x40012200 | 0x22 | ❌ (F1/F4) |
| TIM8 | 0x40010400 | 0x04 | ❌ (F4+) |
| TIM9 | 0x40010800 | 0x08 | ❌ (F4+) |
| TIM10 | 0x40010C00 | 0x0C | ❌ (F4+) |
| TIM11 | 0x40011000 | 0x10 | ❌ (F4+) |
| SYSCFG | 0x40013800 | 0x38 | ❌ (F4+) |
| COMP | 0x40013A00 | 0x3A | ❌ (G0/G4) |

> **注意**：F1 的 SYSCFG 功能由 AFIO 替代，地址为 0x40010000。

## AHB1 外设基地址 (0x40020000)

| 外设 | 基地址 | 偏移 | 说明 |
|------|--------|------|------|
| GPIOA | 0x40020000 | 0x00 | |
| GPIOB | 0x40020400 | 0x04 | |
| GPIOC | 0x40020800 | 0x08 | |
| GPIOD | 0x40020C00 | 0x0C | |
| GPIOE | 0x40021000 | 0x10 | |
| GPIOF | 0x40021400 | 0x14 | F4/H7/G4 |
| GPIOG | 0x40021800 | 0x18 | F4/H7/G4 |
| GPIOH | 0x40021C00 | 0x1C | F4/H7 |
| CRC | 0x40023000 | 0x30 | |
| RCC | 0x40023800 | 0x38 | F4/G4/L4/H7 不同 |
| DMA1 | 0x40026000 | 0x60 | |
| DMA2 | 0x40026400 | 0x64 | |
| BKPSRAM | 0x40024000 | 0x40 | F4+ |

## F1 特殊地址（AHB2 变体）

F1 的 RCC/GPIO 属于 AHB2/APB2 而不是 AHB1/APB2：

| 外设 | F1 地址 | 备注 |
|------|---------|------|
| GPIOA | 0x40010800 | |
| GPIOB | 0x40010C00 | |
| GPIOC | 0x40011000 | |
| RCC | 0x40021000 | |
| AFIO | 0x40010000 | 替代 SYSCFG |

## G0/G4/H7/L4/U5 差异

### G0/G4/L4+

I2C 使用 V2 寄存器：ISR (0x1C) + ICR (0x1C) 替代 SR1/SR2
ADC 使用 V3 寄存器：ISR (0x00) 替代 SR (0x00)，CR1 位定义不同

### H7

外设地址整体偏移 0x4000_0000 → 0x5800_0000（AHB1/2/3 重新划分）：

| 总线 | H7 地址 | 备注 |
|------|---------|------|
| APB1 | 0x58000000 | 比常规大 0x1800_0000 |
| APB2 | 0x58010000 | |
| AHB1 | 0x58020000 | |
| AHB2 | 0x48000000 | GPIOA~K 在这里 |
| AHB3 | 0x52000000 | FMC |
| AHB4 | 0x58024400 | RCC 在这里 |

USART SR/DR 变为 ISR/ICR/TDR/RDR
SPI 使用 V2 寄存器 (CFG1/CFG2)

## CMSIS 外设基地址宏定义

```c
// 所有外设基地址在 stm32f4xx.h（或对应头文件）中定义
#define PERIPH_BASE          0x40000000UL
#define APB1PERIPH_BASE      PERIPH_BASE
#define APB2PERIPH_BASE      (PERIPH_BASE + 0x00010000UL)
#define AHB1PERIPH_BASE      (PERIPH_BASE + 0x00020000UL)
#define AHB2PERIPH_BASE      (PERIPH_BASE + 0x10000000UL)

// GPIO 计算宏
#define GPIOA                ((GPIO_TypeDef *) GPIOA_BASE)
#define GPIOB                ((GPIO_TypeDef *) GPIOB_BASE)

// 直接访问
#define GPIOA_Base           0x40020000UL
#define GPIOA_MODER          (*(volatile uint32_t *)(GPIOA_Base + 0x00))
#define GPIOA_ODR            (*(volatile uint32_t *)(GPIOA_Base + 0x14))
```

## RCC AHB1/APB1/APB2 时钟使能寄存器

```c
// F4 系列 (0x40023800)
#define RCC_AHB1ENR          (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define RCC_APB1ENR          (*(volatile uint32_t *)(RCC_BASE + 0x40))
#define RCC_APB2ENR          (*(volatile uint32_t *)(RCC_BASE + 0x44))

// F1 系列 (0x40021000)
#define RCC_APB2ENR_F1       (*(volatile uint32_t *)(0x40021000 + 0x18))
#define RCC_APB1ENR_F1       (*(volatile uint32_t *)(0x40021000 + 0x1C))
#define RCC_AHBENR_F1        (*(volatile uint32_t *)(0x40021000 + 0x14))
```

## GPIO 寄存器偏移

```c
typedef struct {
    volatile uint32_t MODER;    // 0x00
    volatile uint32_t OTYPER;   // 0x04
    volatile uint32_t OSPEEDR;  // 0x08
    volatile uint32_t PUPDR;    // 0x0C
    volatile uint32_t IDR;      // 0x10
    volatile uint32_t ODR;      // 0x14
    volatile uint32_t BSRR;     // 0x18
    volatile uint32_t LCKR;     // 0x1C
    volatile uint32_t AFRL;     // 0x20
    volatile uint32_t AFRH;     // 0x24
} GPIO_TypeDef;
```

## 配置位宽技巧

```c
// 位段操作（F1/F4 支持，H7 不支持）：把 1-bit 展开到 alias 区
#define BITBAND(addr, bit)    ((volatile uint32_t *)(0x42000000 + ((uint32_t)&(addr) - 0x40000000) * 32 + (bit) * 4))

// 外设寄存器原子操作
#define PA0_SET                (*BITBAND(GPIOA->ODR, 0) = 1)
#define PA0_RESET              (*BITBAND(GPIOA->ODR, 0) = 0)
#define PA0_READ               (*BITBAND(GPIOA->IDR, 0))

// BSRR 原子操作（所有系列支持，推荐）
#define PA0_HIGH               (GPIOA->BSRR = GPIO_PIN_0)
#define PA0_LOW                (GPIOA->BSRR = (GPIO_PIN_0 << 16))
```
