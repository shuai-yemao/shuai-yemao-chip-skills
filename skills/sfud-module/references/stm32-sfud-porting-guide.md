# STM32 SFUD 串行 Flash 移植指南

> 目标平台：STM32F4 + W25Q64（SFDP 自动探测）
> 开发环境：Keil MDK（ARMCC v5）
> 库版本：SFUD v1.1.0（armink/MIT）
> 仓库地址：https://github.com/armink/SFUD

---

## 目录

1. [移植前准备](#1-移植前准备)
2. [源码获取与工程组织](#2-源码获取与工程组织)
3. [配置 sfud_cfg.h](#3-配置-sfud_cfgh)
4. [实现 sfud_port.c（核心移植）](#4-实现-sfud_portc核心移植)
5. [SPI 硬件初始化](#5-spi-硬件初始化)
6. [初始化与验证](#6-初始化与验证)
7. [适配器层封装（可选）](#7-适配器层封装可选)
8. [常见问题](#8-常见问题)
9. [检查清单](#9-检查清单)

---

## 1. 移植前准备

### 1.1 确认环境

| 项目 | 要求 |
|------|------|
| MCU | 任意带 SPI 外设的 MCU |
| Flash | 任意 SPI NOR Flash（W25Q64/W25Q128/MX25L 等） |
| SPI 模式 | 模式 0（CPOL=0, CPHA=0）或模式 3 |
| 编译器 | Keil MDK / IAR / GCC |

### 1.2 确认硬件连接

| STM32 引脚 | SPI 信号 | Flash 芯片引脚 |
|------------|---------|---------------|
| PA5 (SPI1_SCK) | SCK | CLK |
| PA6 (SPI1_MISO) | MISO | DO/DOUT |
| PA7 (SPI1_MOSI) | MOSI | DI/DIN |
| PA4 | CS | CS# |

> 注意：CS 引脚不是 SPI 外设的 NSS 引脚，而是由普通 GPIO 手动控制。

---

## 2. 源码获取与工程组织

### 2.1 获取源码

```bash
git clone https://github.com/armink/SFUD.git
```

或直接下载 ZIP：https://github.com/armink/SFUD/archive/refs/heads/master.zip

### 2.2 工程目录组织

```
project/
├── Core/Src/                    # 用户代码
├── Middlewares/SFUD/            # ← 新建目录
│   ├── inc/
│   │   ├── sfud.h              # 公共 API
│   │   ├── sfud_cfg.h          # 用户配置（需创建）
│   │   ├── sfud_def.h          # 类型定义
│   │   └── sfud_flash_def.h    # Flash 芯片参数表
│   ├── src/
│   │   ├── sfud.c              # 核心实现
│   │   └── sfud_sfdp.c         # SFDP 解析（可选）
│   └── port/
│       └── sfud_port.c         # 平台移植层（需创建）
├── MDK-ARM/
│   └── project.uvprojx
```

### 2.3 在 Keil 中添加文件

1. 新建分组 `SFUD`
2. 添加源文件：
   - `Middlewares/SFUD/src/sfud.c`
   - `Middlewares/SFUD/src/sfud_sfdp.c`
   - `Middlewares/SFUD/port/sfud_port.c`
3. 添加头文件路径：
   - `Middlewares/SFUD/inc`
   - `Middlewares/SFUD/port`

---

## 3. 配置 sfud_cfg.h

在 `Middlewares/SFUD/inc/` 下新建 `sfud_cfg.h`：

```c
#ifndef _SFUD_CFG_H_
#define _SFUD_CFG_H_

#include <stdint.h>
#include <stdbool.h>

/* ========== SFDP 自动探测（推荐） ========== *
 * 从 Flash 芯片读取 SFDP 表，自动识别容量/擦除粒度等参数。
 * 如果芯片不支持 SFDP，会回退到 Flash 信息表查询。 */
#define SFUD_USING_SFDP

/* ========== 快速读取 ========== *
 * 使用 0x0B 命令（带 1 个 dummy 字节）代替 0x03。
 * 读取速度更快，绝大部分芯片支持。 */
#define SFUD_USING_FAST_READ

/* ========== Flash 信息表回退 ========== *
 * SFDP 探测失败时，使用内置芯片参数表兼容。 */
#define SFUD_USING_FLASH_INFO_TABLE

/* ========== 调试模式 ========== *
 * 调试阶段打开可看到 SFDP 解析和初始化过程。
 * 量产时必须关闭。 */
// #define SFUD_DEBUG_MODE

/* ========== Flash 设备定义 ========== */
enum {
    SFUD_W25Q64_DEVICE_INDEX = 0,
};

/* 名称中的 "W25Q64" 仅用于标识，实际芯片通过 SFDP 自动识别 */
#define SFUD_FLASH_DEVICE_TABLE                                         \
{                                                                       \
    [SFUD_W25Q64_DEVICE_INDEX] = {                                      \
        .name = "W25Q64",                                               \
        .spi.name = "SPI1",                                             \
    },                                                                  \
}

#endif /* _SFUD_CFG_H_ */
```

> **关键**：`.spi.name = "SPI1"` 必须与 `sfud_port.c` 中的 SPI 外设对应。  
> `sfud_spi_port_init` 通过这个名称匹配设备。

---

## 4. 实现 sfud_port.c（核心移植）

在 `Middlewares/SFUD/port/` 下创建 `sfud_port.c`，这是移植最关键的一步：

```c
/* sfud_port.c — STM32F4 + SPI1 完整实现 */
#include "sfud.h"
#include "stm32f4xx.h"

/* GPIO 定义 — 根据实际接线修改 */
#define SPI1_CS_PORT            GPIOA
#define SPI1_CS_PIN             GPIO_PIN_4

/* 外设基址定义 */
#define SPI1_PERIPH             SPI1

/* ========== 临界区锁 ========== */
static sfud_err spi_lock(const char *spi_name)
{
    /* 裸机：关全局中断。若使用 FreeRTOS 应改为互斥锁 */
    __disable_irq();
    return SFUD_SUCCESS;
}

static sfud_err spi_unlock(const char *spi_name)
{
    __enable_irq();
    return SFUD_SUCCESS;
}

/* ========== CS 控制 ========== */
static void cs_active(const char *spi_name)
{
    GPIO_ResetBits(SPI1_CS_PORT, SPI1_CS_PIN);    // CS 低 = 选中
}

static void cs_deactive(const char *spi_name)
{
    GPIO_SetBits(SPI1_CS_PORT, SPI1_CS_PIN);      // CS 高 = 释放
}

/* ========== SPI 寄存器级读写 ========== */
static uint8_t spi_xfer_byte(const char *spi_name, uint8_t byte)
{
    /* 等待发送缓冲区空 */
    while (!(SPI1_PERIPH->SR & SPI_SR_TXE));
    SPI1_PERIPH->DR = byte;
    /* 等待接收缓冲区非空 */
    while (!(SPI1_PERIPH->SR & SPI_SR_RXNE));
    return (uint8_t)SPI1_PERIPH->DR;
}

/* ========== SFUD 核心 SPI 读写函数 ========== */
static sfud_err spi_write_read(const sfud_spi *spi,
                                const uint8_t *write_buf, size_t write_size,
                                uint8_t *read_buf, size_t read_size)
{
    SFUD_ASSERT(spi);

    if (spi_lock(spi->name) != SFUD_SUCCESS)
        return SFUD_ERR_TIMEOUT;

    cs_active(spi->name);

    /* 发送阶段 */
    if (write_buf && write_size) {
        for (size_t i = 0; i < write_size; i++)
            spi_xfer_byte(spi->name, write_buf[i]);
    }

    /* 接收阶段（全双工，发 0xFF 产生时钟） */
    if (read_buf && read_size) {
        for (size_t i = 0; i < read_size; i++)
            read_buf[i] = spi_xfer_byte(spi->name, 0xFF);
    }

    cs_deactive(spi->name);
    spi_unlock(spi->name);

    return SFUD_SUCCESS;
}

/* ========== SFUD 端口初始化（SFUD 库回调此函数） ========== */
sfud_err sfud_spi_port_init(sfud_flash *flash)
{
    sfud_err result = SFUD_SUCCESS;

    switch (flash->spi.id) {
    case 0:     /* sfud_cfg.h 中第一个设备 = SPI1 */
        flash->spi.wr = spi_write_read;
        break;
    default:
        result = SFUD_ERR_PARAM;
        break;
    }

    return result;
}
```

### 关键点说明

- `spi_write_read` — SFUD 的 SPI 事务函数，全双工模式，同时处理写入和读取
- `spi_lock/unlock` — 临界区保护，防止中断中的 SPI 操作破坏当前事务
- `cs_active/deactive` — 手动 CS 控制，不能用 SPI 的自动 NSS
- `sfud_spi_port_init` — SFUD 回调函数，通过 `flash->spi.id` 区分多设备

---

## 5. SPI 硬件初始化

### 5.1 使用 SPL（标准外设库）

```c
/* Spi.c */
void SPI1_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct;

    /* 使能时钟 */
    RCC_AHB1PeriphClockCmd(RCC_AHB1Periph_GPIOA, ENABLE);
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_SPI1, ENABLE);

    /* 配置 PA5(SCK), PA6(MISO), PA7(MOSI) 为 AF */
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_5 | GPIO_Pin_6 | GPIO_Pin_7;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_AF;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStruct.GPIO_OType = GPIO_OType_PP;
    GPIO_InitStruct.GPIO_PuPd  = GPIO_PuPd_NOPULL;
    GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_PinAFConfig(GPIOA, GPIO_PinSource5, GPIO_AF_SPI1);
    GPIO_PinAFConfig(GPIOA, GPIO_PinSource6, GPIO_AF_SPI1);
    GPIO_PinAFConfig(GPIOA, GPIO_PinSource7, GPIO_AF_SPI1);

    /* 配置 PA4(CS) 为推挽输出 */
    GPIO_InitStruct.GPIO_Pin   = GPIO_Pin_4;
    GPIO_InitStruct.GPIO_Mode  = GPIO_Mode_OUT;
    GPIO_InitStruct.GPIO_Speed = GPIO_Speed_50MHz;
    GPIO_InitStruct.GPIO_OType = GPIO_OType_PP;
    GPIO_Init(GPIOA, &GPIO_InitStruct);
    GPIO_SetBits(GPIOA, GPIO_Pin_4);  /* CS 初始为高 */

    /* 配置 SPI1: 模式0, 主模式, 8位, 256分频 ≈ 328kHz @ 84MHz */
    SPI1->CR1 = 0;
    SPI1->CR1 |= SPI_CR1_MSTR         /* 主模式 */
              |  SPI_CR1_SSI           /* 内部 SS 使能 */
              |  SPI_CR1_SSM           /* 软件 NSS */
              |  (7 << 3);             /* BR[2:0] = 111 → 256 分频 */
    SPI1->CR2 = 0;
    SPI1->CR1 |= SPI_CR1_SPE;          /* SPI 使能 */
}
```

### 5.2 使用 HAL 库

```c
/* SPI1 初始化（HAL 版） */
void MX_SPI1_Init(void)
{
    hspi1.Instance               = SPI1;
    hspi1.Init.Mode              = SPI_MODE_MASTER;
    hspi1.Init.Direction         = SPI_DIRECTION_2LINES;
    hspi1.Init.DataSize          = SPI_DATASIZE_8BIT;
    hspi1.Init.CLKPolarity       = SPI_POLARITY_LOW;
    hspi1.Init.CLKPhase          = SPI_PHASE_1EDGE;
    hspi1.Init.NSS               = SPI_NSS_SOFT;
    hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_256;
    hspi1.Init.FirstBit          = SPI_FIRSTBIT_MSB;
    hspi1.Init.TIMode            = SPI_TIMODE_DISABLE;
    hspi1.Init.CRCCalculation    = SPI_CRCCALCULATION_DISABLE;
    HAL_SPI_Init(&hspi1);
}

/* sfud_port.c 中改用 HAL_SPI_TransmitReceive */
/* 但注意：HAL 函数有超时依赖 HAL 时基，在 HardFault/中断中不安全 */
```

---

## 6. 初始化与验证

### 6.1 添加测试代码

```c
/* main.c */
#include "sfud.h"

int main(void)
{
    USART1_Init();           // 串口初始化（看输出用）
    SPI1_Init();             // SPI 初始化

    printf("SFUD init...\r\n");
    sfud_err ret = sfud_init();
    if (ret != SFUD_SUCCESS) {
        printf("SFUD init FAILED: %d\r\n", ret);
        while (1);
    }

    /* 获取设备并检查状态 */
    const sfud_flash *flash = sfud_get_device(SFUD_W25Q64_DEVICE_INDEX);
    if (flash == NULL || flash->state != SFUD_DEVICE_NORMAL) {
        printf("Flash device not found or error\r\n");
        while (1);
    }

    printf("Flash: %s, size: %lu bytes, page: %lu, sector: %lu\r\n",
           flash->name, flash->chip.capacity,
           flash->chip.page_size, flash->chip.erase_gran);

    /* 读写测试 */
    uint8_t buf[16];
    const char *test = "SFUD OK!";

    /* 擦除扇区 */
    sfud_erase(flash, 0, flash->chip.erase_gran);
    printf("Erase done\r\n");

    /* 写入 */
    sfud_erase_write(flash, 0, strlen(test) + 1, (uint8_t *)test);
    printf("Write done\r\n");

    /* 读取检查 */
    memset(buf, 0, sizeof(buf));
    sfud_read(flash, 0, sizeof(buf), buf);
    printf("Read: %s\r\n", buf);

    while (1);
}
```

### 6.2 预期输出（启用 SFUD_DEBUG_MODE）

```
SFUD init...
[D/SPI1] SFUD: find a Winbond flash chip. Manufacturer: EF, Capacity: 64Mb
[D/SPI1] SFUD: flash device is initialize successful.
Flash: W25Q64, size: 8388608, page: 256, sector: 4096
Erase done
Write done
Read: SFUD OK!
```

---

## 7. 适配器层封装（可选）

如果项目原有 W25Qxx 直接操作代码，可加一层适配器保持兼容：

```c
/* sfud_adapter.h */
#ifndef _SFUD_ADAPTER_H_
#define _SFUD_ADAPTER_H_

#include <stdint.h>
#include <stdbool.h>

void    W25Q64_Init(void);
bool    W25Q64_Read(uint32_t addr, uint8_t *buf, size_t len);
bool    W25Q64_Write(uint32_t addr, const uint8_t *data, size_t len);
bool    W25Q64_EraseChip(void);
bool    W25Q64_EraseSector(uint32_t addr);

#endif
```

```c
/* sfud_adapter.c */
#include "sfud_adapter.h"
#include "sfud.h"

static const sfud_flash *g_flash = NULL;

void W25Q64_Init(void)
{
    if (g_flash == NULL) {
        sfud_init();
        g_flash = sfud_get_device(0);
    }
}

bool W25Q64_Read(uint32_t addr, uint8_t *buf, size_t len)
{
    return sfud_read(g_flash, addr, len, buf) == SFUD_SUCCESS;
}

bool W25Q64_Write(uint32_t addr, const uint8_t *data, size_t len)
{
    return sfud_erase_write(g_flash, addr, len, data) == SFUD_SUCCESS;
}

bool W25Q64_EraseChip(void)
{
    return sfud_chip_erase(g_flash) == SFUD_SUCCESS;
}

bool W25Q64_EraseSector(uint32_t addr)
{
    return sfud_erase(g_flash, addr, g_flash->chip.erase_gran) == SFUD_SUCCESS;
}
```

---

## 8. 常见问题

### Q1: sfud_init 返回 -1（失败）

**排查**：
1. 用示波器/逻辑分析仪查看 SPI 波形，确认 SCK 有时钟
2. 确认 MISO 引脚上 Flash 芯片有回数据
3. 检查 SPI 极性和相位（模式 0：CPOL=0, CPHA=0）

### Q2: 读出全是 0xFF

**原因**：CS 引脚未正确拉低，Flash 芯片未选中。

**解决**：
- 确认 CS GPIO 配置为推挽输出
- 检查 `cs_active`/`cs_deactive` 中 GPIO 端口和引脚号

### Q3: 写入后读回仍是 0xFF

**原因**：NOR Flash 写入前必须擦除，且擦除操作未成功。

**解决**：
- 使用 `sfud_erase_write`（自动先擦除再写）
- 确认擦除地址是 sector 对齐的（W25Q64 擦除粒度 4KB）

### Q4: 擦除非常慢（几秒）

**原因**：NOR Flash 块擦除是耗时操作（典型 W25Q64 块擦除 ~150ms）。

**解决**：这是正常现象。如果需要擦除期间保持中断响应，可在擦除前先关中断保护，擦除后开中断。

### Q5: SPI 读取出错（数据错位）

**原因**：
1. SPI 时钟频率太高（> Flash 芯片最大频率）
2. 中断打断 SPI 事务导致 CS 时序错乱

**解决**：
- 降低 SPI 预分频（Bootloader 建议 256 分频 ~328kHz）
- 所有 SPI 事务用临界区锁保护

---

## 9. 检查清单

```
[ ] 工程添加了 sfud.c + sfud_sfdp.c + sfud_port.c
[ ] sfud_cfg.h 配置了正确的设备名称和 SPI 接口
[ ] sfud_port.c 实现了 spi_write_read/spi_lock/unlock/cs_active/deactive
[ ] SPI 硬件初始化正确（时钟/GPIO/模式0/分频）
[ ] CS 引脚配置为 GPIO 推挽输出（非 SPI NSS）
[ ] 头文件路径包含 inc/ 和 port/
[ ] 编译通过，无错误
[ ] 串口看到 SFUD 初始化成功（Flash 型号/容量）
[ ] 读写测试通过（写入→读回一致）
```

---

## 参考链接

- **SFUD 官方仓库**: https://github.com/armink/SFUD
- **SFDP 标准**: JEDEC JESD216
- **W25Q64 数据手册**: Winbond 官网
- **Armink 关联项目**: EasyLogger, CmBacktrace, EasyFlash
