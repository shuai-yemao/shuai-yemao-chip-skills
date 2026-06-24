---
name: mcu-peripheral-registers
description: STM32 外设寄存器级操作指南。涵盖 CMSIS 外设结构体映射、各系列寄存器差异、外设总线与时钟使能寄存器、GPIO（MODER/BSRR/OSPEEDR/AFR）、RCC（CR/CFGR/PLLCFGR）、USART（SR/DR/CRx/BRR）、SPI（CR1/SR/DR）、I2C（CR1/SR1/SR2/CCR 或 ISR/ICR/TIMINGR）、TIM（CR1/CCER/CCRx/ARR/PSC/BDTR）、ADC（SR/CR2/SQR/DR）、DMA（SxCR/SxNDTR/SxPAR）、IWDG/WWDG/RTC 等常用寄存器的地址、位定义与读写操作。当用户提到外设寄存器、寄存器级、寄存器操作、CMSIS 结构体、GPIO 寄存器、RCC 寄存器、USART 寄存器、TIM 寄存器、ADC 寄存器、DMA 寄存器、直接操作寄存器、外设地址、外设基地址、Reference Manual 寄存器、寄存器读写、寄存器值、看寄存器值、寄存器配置、寄存器写不进、寄存器读出来不对、内存地址、位操作、LL库寄存器、裸机编程、操作寄存器、寄存器地址、寄存器位、读寄存器值时使用。
version: "1.0.0"
---

# STM32 外设寄存器指南

> 外设寄存器是 STM32 MCU 各外设的控制接口。不同系列（F1/F4/H7/G4）同一外设的寄存器布局不同。
> 与 arm-core-registers（内核寄存器）互补：本 skill 覆盖 MCU 芯片厂商设计的外设寄存器。
> 最终参考：对应 MCU 的 Reference Manual（RMxxxx）。

## 适用场景

- 不使用 HAL/LL 库，直接操作寄存器（裸机、性能关键路径）
- HAL 工作不正常时，通过读寄存器诊断问题根因
- 排查 HAL_I2C_STATE_BUSY 时直接读 I2C_SR1/SR2（或 ISR/ICR）
- 调试 DMA 时直接读 DMA_SxCR 和 SxNDTR 查看传输进度
- 需要做 HAL 不支持的寄存器操作（如触发软件更新事件 EGR.UG）
- 调试器 halt 后读取外设寄存器确认外设状态
- 比较不同 MCU 系列的同名寄存器差异（如 F1 I2C 的 SR1 vs H7 的 ISR）

## 必要输入

- MCU 系列（F1/F4/H7/G0/G4 — 决定外设寄存器版本）
- 外设名称（GPIO/RCC/USART/SPI/I2C/TIM/ADC/DMA 等）
- 寄存器名称或地址
- Reference Manual 编号（如 RM0390 for F411, RM0008 for F103）

## CMSIS 外设结构体模型

STM32 使用 CMSIS 标准：每个外设对应一个结构体，映射到固定的基地址。

```c
// CMSIS 结构体示例（GPIO — 所有系列共用一套布局）
// 定义于 stm32f4xx.h / stm32f1xx.h 等器件头文件中

typedef struct {
    volatile uint32_t MODER;       // 偏移 0x00: 模式寄存器
    volatile uint32_t OTYPER;      // 偏移 0x04: 输出类型寄存器
    volatile uint32_t OSPEEDR;     // 偏移 0x08: 输出速度寄存器
    volatile uint32_t PUPDR;       // 偏移 0x0C: 上下拉寄存器
    volatile uint32_t IDR;         // 偏移 0x10: 输入数据寄存器 (只读)
    volatile uint32_t ODR;         // 偏移 0x14: 输出数据寄存器
    volatile uint32_t BSRR;        // 偏移 0x18: 位设置/清除寄存器
    volatile uint32_t LCKR;        // 偏移 0x1C: 配置锁定寄存器
    volatile uint32_t AFR[2];      // 偏移 0x20~0x24: 复用功能寄存器 (AFRL, AFRH)
} GPIO_TypeDef;

#define GPIOA                ((GPIO_TypeDef *) GPIOA_BASE)
#define GPIOA_BASE           (AHB1PERIPH_BASE + 0x0000)
#define AHB1PERIPH_BASE      (PERIPH_BASE + 0x2000)
#define PERIPH_BASE          0x40000000
```

### 基地址计算
```
PERIPH_BASE  = 0x40000000          // 外设总线起点
APB1: 0x40000000 ~ 0x4000FFFF     // 低速外设（TIM2~7, I2C1~3, SPI2/3, USART2~5, PWR, IWDG, WWDG）
APB2: 0x40010000 ~ 0x40017FFF     // 高速外设（GPIO, USART1, SPI1, TIM1/8, ADC1~3, EXTI, SYSCFG）
AHB1: 0x40020000 ~ 0x4007FFFF     // DMA, RCC, CRC, Flash 接口, GPIO 非 F1
AHB2: 0x50000000 ~ 0x500FFFFF     // USB OTG FS, DCMI, RNG, HASH, CRYP (F4)
AHB3: 0x60000000 ~ 0x6FFFFFFF     // FSMC / FMC (外部存储器控制器)
```

## 外设寄存器速查

### GPIO

| 寄存器 | 偏移 | 位宽 | 描述 | 关键位 |
|-------|------|------|------|--------|
| MODER | 0x00 | 32b | 引脚模式 | `00`=输入, `01`=输出, `10`=复用, `11`=模拟 × 16 引脚 |
| OTYPER | 0x04 | 32b | 输出类型 | 0=推挽, 1=开漏 × 16 引脚 |
| OSPEEDR | 0x08 | 32b | 输出速度 | `00`=低速, `01`=中速, `10`=高速, `11`=最高速 |
| PUPDR | 0x0C | 32b | 上下拉 | `00`=浮空, `01`=上拉, `10`=下拉, `11`=保留 |
| IDR | 0x10 | 16b | 输入数据（只读） | 读取引脚电平 |
| ODR | 0x14 | 16b | 输出数据 | 写 1/0 控制输出电平 |
| BSRR | 0x18 | 32b | **位设置/清除** | 低 16 位置位, 高 16 位复位 |
| LCKR | 0x1C | 32b | 配置锁定 | 锁定后不可更改配置直至复位 |
| AFRL | 0x20 | 32b | AF 低 8 引脚 | 每引脚 4 位 = AF0~AF15 |
| AFRH | 0x24 | 32b | AF 高 8 引脚 | 同上 |

```c
// GPIO 寄存器级操作

// 设置 PA5 为推挽输出 (MODER[11:10] = 01)
GPIOA->MODER &= ~GPIO_MODER_MODER5;          // 清位
GPIOA->MODER |= GPIO_MODER_MODER5_0;          // 设 MODER5[0]=1 → 输出

// 推挽输出，高速
GPIOA->OTYPER &= ~GPIO_OTYPER_OT_5;           // 推挽
GPIOA->OSPEEDR |= GPIO_OSPEEDR_OSPEED5;       // 高速

// 原子操作 PA5（通过 BSRR）
GPIOA->BSRR = GPIO_BSRR_BS_5;                 // PA5 = 1（不修改其他引脚）
GPIOA->BSRR = GPIO_BSRR_BR_5;                 // PA5 = 0
// 对比：用 ODR 会破坏其他位（读-改-写非原子）
// GPIOA->ODR |= (1 << 5);                     // ❌ 非原子操作

// 设置 PA9 为 AF7 (USART1_TX)
GPIOA->AFR[1] |= (7 << GPIO_AFRH_AFSEL9_Pos); // AFRH[3:0] = 0111

// F1 特殊：GPIO 寄存器在 APB2 上，地址不同
// F1: GPIOA_BASE = 0x40010800（非 F4 的 0x40020000）
// CRL / CRH 替代 MODER（F1 无 MODER 寄存器）
```

### RCC

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| CR | 0x00 | 时钟控制 | HSION[0], HSIRDY[1], HSEON[16], HSERDY[17], PLLON[24], PLLRDY[25] |
| CFGR | 0x04 | 时钟配置 | SW[1:0], SWS[3:2], HPRE[7:4], PPRE1[10:8], PPRE2[13:11], PLLSRC[16] |
| PLLCFGR | 0x08 | PLL 配置 (F4) | PLLM[5:0], PLLN[14:8], PLLP[17:16], PLLSRC[22], PLLQ[27:24] |
| AHB1ENR | 0x30 (F4) | AHB1 时钟使能 | GPIOAEN[0], GPIODEN[3], DMA1EN[21]... |
| APB1ENR | 0x40 (F4) | APB1 时钟使能 | TIM2~7, USART2~5, I2C1~3, SPI2/3, PWR |
| APB2ENR | 0x44 (F4) | APB2 时钟使能 | USART1, SPI1, TIM1/8, ADC1~3, SYSCFG |

```c
// RCC 寄存器级操作

// 使能外设时钟（以 GPIOA 为例）
RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;         // F4: 在 AHB1ENR
RCC->APB2ENR |= RCC_APB2ENR_USART1EN;        // USART1 在 APB2

// F1: 外设时钟在不同寄存器
RCC->APB2ENR |= RCC_APB2ENR_IOPAEN;           // F1 GPIOA 在 APB2ENR
RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;           // TIM2 在 APB1

// 系统时钟切换：从 HSI 切到 HSE 到 PLL
RCC->CR |= RCC_CR_HSEON;                      // 使能 HSE
while (!(RCC->CR & RCC_CR_HSERDY));           // 等待稳定

RCC->PLLCFGR = (8 << 24)      // PLLQ=8
             | (336 << 6)     // PLLN=336 (F407: 8MHz × 336 / 4 = 672MHz VCO)
             | (4 << 0);      // PLLM=4
RCC->CR |= RCC_CR_PLLON;
while (!(RCC->CR & RCC_CR_PLLRDY));

RCC->CFGR &= ~RCC_CFGR_SW;                    // 清 SW 位
RCC->CFGR |= RCC_CFGR_SW_PLL;                 // 切到 PLL 作为系统时钟
while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL);
```

### USART (F4: V2 寄存器集)

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| SR | 0x00 | 状态寄存器 | TXE[7], TC[6], RXNE[5], IDLE[4], ORE[3], NF[2], FE[1], PE[0] |
| DR | 0x04 | 数据寄存器 | DR[8:0] |
| BRR | 0x08 | 波特率寄存器 | DIV_Mantissa[15:4], DIV_Fraction[3:0] |
| CR1 | 0x0C | 控制 1 | UE[13], M[12], WAKE[11], PCE[10], PS[9], TE[3], RE[2], RXNEIE[5], TCIE[6] |
| CR2 | 0x10 | 控制 2 | STOP[13:12], LINEN[14], CLKEN[11] |
| CR3 | 0x14 | 控制 3 | EIE[0], DMAT[7], DMAR[6], RTSE[8], CTSE[9] |

```c
// USART 寄存器级收发（阻塞轮询）
#define USART1 ((USART_TypeDef *)0x40011000)  // F4 USART1 基地址

// 发送一个字节
void usart_send_byte(USART_TypeDef *usart, uint8_t data)
{
    while (!(usart->SR & USART_SR_TXE));    // 等待 TXE=1（发送数据寄存器空）
    usart->DR = data;
    while (!(usart->SR & USART_SR_TC));     // 等待 TC=1（发送完成）
}

// 接收一个字节
uint8_t usart_recv_byte(USART_TypeDef *usart)
{
    while (!(usart->SR & USART_SR_RXNE));   // 等待 RXNE=1（接收数据就绪）
    return (uint8_t)(usart->DR & 0xFF);
}

// 清除 IDLE 标志
void usart_clear_idle(USART_TypeDef *usart)
{
    uint32_t tmp = usart->SR;               // 读 SR
    (void)usart->DR;                        // 读 DR = 清除 IDLE
    (void)tmp;
}
```

**系列差异**：
- F1 USART：`USART_BASE = 0x40013800 (USART1)`，寄存器布局同 F4
- H7 USART：寄存器布局改写（`ISR` 替代 `SR`，`ICR` 替代读 DR 清标志）
  - `HAL_UART_CLEAR_IDLEFLAG` → 写 `USART_ICR_IDLECF` 到 `ICR`

### SPI (F4: V1 寄存器集)

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| CR1 | 0x00 | 控制 1 | CPHA[0], CPOL[1], MSTR[2], BR[5:3], SPE[6], LSBFIRST[7], SSI[8], SSM[9], RXONLY[10], DFF[11], CRCNEXT[12], CRCEN[13], BIDIOE[14], BIDIMODE[15] |
| CR2 | 0x04 | 控制 2 | RXDMAEN[0], TXDMAEN[1], SSOE[2], ERRIE[5], RXNEIE[6], TXEIE[7] |
| SR | 0x08 | 状态寄存器 | RXNE[0], TXE[1], CHSIDE[2], UDR[3], CRCERR[4], MODF[5], OVR[6], BSY[7], FRE[8] |
| DR | 0x0C | 数据寄存器 | DR[15:0]（8/16 位由 DFF 决定） |

```c
// SPI 寄存器级收发
void spi_write_read(SPI_TypeDef *spi, uint8_t *tx, uint8_t *rx, uint16_t len)
{
    for (uint16_t i = 0; i < len; i++) {
        while (!(spi->SR & SPI_SR_TXE));     // 等待 TXE
        *(uint8_t *)&spi->DR = tx[i];        // 写发送数据（8 位）
        while (!(spi->SR & SPI_SR_RXNE));     // 等待 RXNE
        rx[i] = *(uint8_t *)&spi->DR;         // 读接收数据（8 位）
    }
    while (spi->SR & SPI_SR_BSY);             // 等待最后的 BSY 释放
    // 注意：BSY 在从机模式下不可靠（见 spi-bus skill）
}
```

**系列差异**：
- F1/F4：CR1 布局相同，BSY 在 SR[7]
- H7/G4：SPI V2 全新寄存器集（`SPI_CFG1`, `SPI_CFG2`, `SPI_CR1` 语义不同）
  - `SPI_SR` → 含义部分不同
  - 使用 `SPI_CR1.SPE` 使能，但配置在 `CFG1/CFG2` 中

### I2C (F4: V2 寄存器集)

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| CR1 | 0x00 | 控制 1 | PE[0], START[8], STOP[9], ACK[10], NACK[15], SWRST[15] |
| CR2 | 0x04 | 控制 2 | FREQ[5:0], ITERREN[8], ITEVTEN[9], ITBUFEN[10], DMAEN[11], LAST[12] |
| OAR1 | 0x08 | 自身地址 1 | ADD[9:0], ADDMODE[15] |
| DR | 0x0C | 数据寄存器 | DR[7:0] |
| SR1 | 0x14 | 状态 1 | SB[0], ADDR[1], BTF[2], ADD10[3], STOPF[4], RXNE[6], TXE[7], BERR[8], ARLO[9], AF[10], OVR[11], TIMEOUT[14] |
| SR2 | 0x18 | 状态 2 | BUSY[1]（**关键：读 SR1 后读 SR2 会清除 ADDR 位**） |
| CCR | 0x1C | 时钟控制 | CCR[11:0], DUTY[14:13], F/S[15] |
| TRISE | 0x20 | 上升时间 | TRISE[5:0] |

```c
// I2C 寄存器级诊断（HAL 卡死时）
// 读 SR1 + SR2 诊断总线状态
uint32_t sr1 = I2C1->SR1;
uint32_t sr2 = I2C1->SR2;

// 调试输出：
printf("SR1=0x%04X, SR2=0x%04X\n", sr1, sr2);
if (sr1 & I2C_SR1_BERR) printf("BUS ERROR\n");
if (sr1 & I2C_SR1_ARLO) printf("ARBITRATION LOST\n");
if (sr1 & I2C_SR1_AF)   printf("ACKNOWLEDGE FAILURE\n");
if (sr1 & I2C_SR1_OVR)  printf("OVERRUN/UNDERRUN\n");
if (sr1 & I2C_SR1_TIMEOUT) printf("SMBUS TIMEOUT\n");
if (sr2 & I2C_SR2_BUSY) printf("BUS BUSY\n");

// I2C 软件复位
I2C1->CR1 |= I2C_CR1_SWRST;
__NOP(); __NOP();
I2C1->CR1 &= ~I2C_CR1_SWRST;
```

**系列差异**：
- F1：同 F4 寄存器布局，但有 2.9.x Errata
- G0/G4/H7/L4：**全新 I2C 寄存器集**（不再使用 SR1/SR2/CCR/TRISE）
  - `ISR` 替代 `SR1`, `ICR` 替代读 DR 清标志
  - `TIMINGR` 替代 `CCR + TRISE`
  - 状态机工作在寄存器中，不再有 EV5/EV6/EV8 事件模型

### TIM

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| CR1 | 0x00 | 控制 1 | CEN[0], UDIS[1], URS[2], OPM[3], DIR[4], CMS[6:5], ARPE[7], CKD[9:8] |
| CR2 | 0x04 | 控制 2 | CCPC[0], OIS1[8], OIS1N[9], TI1S[7], MMS[6:4], CCDS[3] |
| SMCR | 0x08 | 从模式控制 | SMS[2:0], TS[6:4], MSM[7], ECE[14], ETPS[17:16], ETF[11:8] |
| DIER | 0x0C | 中断/DMA 使能 | UIE[0], CC1IE[1], CC2IE[2], TIE[6], UDE[8] |
| SR | 0x10 | 状态 | UIF[0], CC1IF[1], CC2IF[2], TIF[6], CC1OF[9] |
| EGR | 0x14 | 事件生成 | **UG[0]**（软件更新—重新加载 PSC/ARR） |
| CCMR1 | 0x18 | 捕获/比较模式 | CC1S[1:0], OC1M[3:0], OC1PE[4], OC1FE[5], IC1PSCF[3:2], IC1F[7:4] |
| CCER | 0x20 | 捕获/比较使能 | CC1E[0], CC1P[1], CC1NE[2], CC1NP[3] |
| CNT | 0x24 | 计数器 | 当前计数值（16 或 32 位） |
| PSC | 0x28 | 预分频器 | 16bit 预分频系数 |
| ARR | 0x2C | 自动重装载 | 16bit 自动重装载值（32bit for TIM2/TIM5） |
| CCR1~4 | 0x34~0x40 | 捕获/比较 | 用于 PWM 占空比或输入捕获值 |
| BDTR | 0x44 | 刹车和死区（TIM1/8 专用） | MOE[15], BKE[12], BKP[13], OSSI[10], OSSR[11], DTG[7:0] |

```c
// TIM 寄存器级操作

// 产生软件更新（加载 PSC/ARR 影子寄存器）
TIM3->EGR |= TIM_EGR_UG;                     // 设置 UG=1 → 产生更新事件

// 读取当前计数器值（适合不停止的情况）
uint32_t cnt = TIM3->CNT;

// 运行时修改 PWM 占空比
TIM3->CCR1 = 500;                             // 直接写 CCR，随时生效

// 高级定时器使能主输出（MOE）——必须设否则无输出！
TIM1->BDTR |= TIM_BDTR_MOE;

// 输入捕获读取
uint32_t cap = TIM2->CCR1;                    // 读 CCR1 获取捕获值

// F1/F4: 同一个寄存器布局
// H7: TIM 外设 V2，寄存器名相同但部分位含义不同
```

### ADC (F4: V2 寄存器集)

| 寄存器 | 偏移 | 描述 | 关键位 |
|-------|------|------|--------|
| SR | 0x00 | 状态寄存器 | AWD[0], EOC[1], JEOC[2], JSTRT[3], STRT[4], OVR[5] |
| CR1 | 0x04 | 控制 1 | SCAN[8], JEOCIE[10], AWDIE[12], EOCIE[13], AWDCH[26:24], RES[25:24] |
| CR2 | 0x08 | 控制 2 | ADON[0], CONT[1], CAL[2], RSTCAL[3], SWSTART[30], EXTTRIG[28], ETS[27:24], ALIGN[11] |
| SMPR1 | 0x0C | 采样时间（通道 10~18） | SMP10~17[2:0] |
| SMPR2 | 0x10 | 采样时间（通道 0~9） | SMP0~9[2:0] |
| SQR1~3 | 0x2C~0x34 | 规则序列寄存器 | SQ1~16[4:0], L[23:20] — 序列长度和顺序 |
| DR | 0x4C | 规则数据寄存器 | DATA[15:0]（右对齐/左对齐由 ALIGN 控制） |

```c
// ADC 寄存器级读（轮询）
void adc_start(ADC_TypeDef *adc)
{
    adc->CR2 |= ADC_CR2_ADON;                // 使能 ADC
}

void adc_calibrate(ADC_TypeDef *adc)
{
    adc->CR2 |= ADC_CR2_CAL;                  // 启动校准
    while (adc->CR2 & ADC_CR2_CAL);           // 等待校准完成
}

uint32_t adc_read(ADC_TypeDef *adc, uint8_t channel)
{
    adc->SQR3 &= ~ADC_SQR3_SQ1;               // 清 SQ1 通道选择
    adc->SQR3 |= channel << ADC_SQR3_SQ1_Pos; // 设通道号
    adc->CR2 |= ADC_CR2_SWSTART;              // 软件触发
    while (!(adc->SR & ADC_SR_EOC));           // 等待 EOC
    return (uint32_t)adc->DR;                  // 读取结果（自动清 EOC）
}
```

**系列差异**：
- F1：ADC 寄存器与 F4 类似，但 F1 无 RES 位（固定 12bit）
- G0/G4/H7：ADC V3 全新寄存器（不再使用 SR/CR2 的位定义，使用 ISR/IER/CFGR）

### DMA (F4: V2)

| 寄存器 | 偏移 | 描述 |
|-------|------|------|
| LISR | 0x00 | 低中断状态寄存器 |
| HISR | 0x04 | 高中断状态寄存器 |
| SxCR | 0x10 + 0x18*x | 数据流 x 配置 |
| SxNDTR | 0x14 + 0x18*x | 数据流 x 待传输数量 |
| SxPAR | 0x18 + 0x18*x | 数据流 x 外设地址 |
| SxM0AR | 0x1C + 0x18*x | 数据流 x 存储器 0 地址 |
| SxM1AR | 0x20 + 0x18*x | 数据流 x 存储器 1 地址（双缓冲时用） |
| SxFCR | 0x24 + 0x18*x | 数据流 x FIFO 控制 |

```c
// DMA 寄存器级调试
DMA_Stream_TypeDef *dma = DMA2_Stream5;       // DMA2 数据流 5

uint32_t ndtr = dma->NDTR;                    // 未传输的元素数（=0 表示传输完成）
uint32_t scr  = dma->CR;                      // 配置状态：EN[0], CIRC[8], PINC[6], MINC[7]
uint32_t lisr = DMA2->LISR;                   // 中断标志

if (lisr & (1 << 25)) printf("Stream5 TCIF\n");   // 传输完成
if (lisr & (1 << 27)) printf("Stream5 DMEIF\n");  // 直接模式错误
if (lisr & (1 << 28)) printf("Stream5 FEIF\n");   // FIFO 错误

// DMA 双缓冲场景下检查当前在用缓冲区
if (dma->CR & DMA_SxCR_CT) {
    // CT=1 → 当前使用 M1AR
    printf("DMA using M1AR = 0x%08X\n", dma->M1AR);
} else {
    printf("DMA using M0AR = 0x%08X\n", dma->M0AR);
}
```

### IWDG / WWDG / RTC

```c
// IWDG — 独立看门狗（LSI 驱动）
// 向 KR 写 0x5555 → 解锁 PR/RLR
// 向 KR 写 0xCCCC → 启动看门狗
IWDG->KR = 0x5555;
IWDG->PR = IWDG_PRESCALER_64;                 // LSI/64 ≈ 32kHz/64 ≈ 500Hz
IWDG->RLR = 1250;                              // 1250 / 500 ≈ 2.5s 超时
IWDG->KR = 0xCCCC;                             // 启动
// 喂狗：
IWDG->KR = 0xAAAA;

// RTC (F4) — 写保护
// 先解锁写保护
PWR->CR |= PWR_CR_DBP;                        // 使能 RTC 和备份域写
RTC->WPR = 0xCA;                               // 写保护密钥 1
RTC->WPR = 0x53;                               // 写保护密钥 2
// 现在可以写 RTC->TR, DR, CR 等
// 写完后再锁：
RTC->WPR = 0xFF;                               // 任意值 ≠0xCA 即锁定
```

## 系列差异定位方法

```
需查阅的文档：
  RM0390 — STM32F411 Reference Manual
  RM0008 — STM32F103 Reference Manual
  RM0385 — STM32F427/437
  RM0433 — STM32H743/750
  RM0444 — STM32G4
  文档编号见芯片数据手册或 CubeMX Pack 安装目录

如何确认外设寄存器版本：
  1. 打开 RM，翻到外设章节（如第 "32.4 Register map"）
  2. 看寄存器列表是否匹配当前使用的 CMSIS header
  3. 如果寄存器名不同（SR vs ISR, CR1 vs CFG1）→ 不同版本
```

## 调试器读取外设寄存器

### J-Link Commander（halt 后）

```
// 按外设基地址批量读取
mem32 0x40020000, 10     // GPIOA 寄存器组（F4: 0x40020000, F1: 0x40010800）
mem32 0x40011000, 16     // USART1 寄存器组（16 个寄存器 = 64 字节）
mem32 0x40023800, 16     // RCC 寄存器组 (F4)
mem32 0x40012C00, 16     // TIM3 寄存器组 (F4)
mem32 0x40012000, 10     // ADC1 寄存器组 (F4)
mem32 0x4002C000, 20     // EXTI 寄存器组 (F4 SYSCFG)

// 写入寄存器（例如强制设 PA5 高电平）
mem32 0x40020018 = 0x00000020   // GPIOA->BSRR = BIT5
```

### GDB（通过 OpenOCD）

```gdb
# 读 USART1 SR (0x40011000)
p/x *(uint32_t*)0x40011000
# 读 GPIOA MODER (F4: 0x40020000)
p/x *(uint32_t*)0x40020000
# 读 TIM3 CNT (F4: 0x40000424)
p/x *(uint32_t*)0x40000424
```

## 边界定义

### 不该激活
- 用户需要的是 HAL 层 API 调用 → 使用 `stm32-hal-development`
- 用户需要的是 ARM 内核寄存器（SCB/NVIC/DWT/MPU）→ 使用 `arm-core-registers`
- 用户需要的是外设高级配置细节（如 ADC 过采样、I2C 时序配置）→ 使用对应的外设 `adc-module` / `i2c-bus` / `spi-bus` / `timer-module` / `uart-module`

### 不该做
- **禁止**不经时钟使能就直接操作外设寄存器（读可能全 0，写可能无响应或 HardFault）
- **禁止**在相关外设正在传输时直接改写关键控制寄存器（如 DMA 运行时改 SxCR）
- **禁止**在不了解系列差异的情况下直接用 F4 的寄存器位定义操作 G0/H7 的外设

### 不该碰
- **不触碰**外设时钟使能寄存器（RCC->xxxENR）中未使用或保留位
- **不触碰**保留地址空间（可能导致 HardFault）
- **不触碰**外设锁定配置（如 GPIO LCKR 锁定后不可逆）

## 交接关系

- 同层：`arm-core-registers`（内核寄存器 — 互补）
- 上游：`stm32-hal-development`（HAL 对寄存器做了封装，本 skill 教你直读）
- 下游：各外设 skill（`i2c-bus`, `spi-bus`, `adc-module`, `timer-module`, `uart-module` — 外设级配置）

## 参考资料

- STM32 各系列 Reference Manual（RMxxxx）— 官方外设寄存器定义
- STM32F4xx / F1xx / H7xx CMSIS device header — 结构体与位定义（stm32f4xx.h 等）
