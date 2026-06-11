---
name: sfud-module
version: "1.0.0"
description: "SFUD (Serial Flash Universal Driver) 串行 Flash 通用驱动库。覆盖 SFUD 移植、sfud_cfg.h 配置（SFDP/快速读取/芯片表/调试）、sfud_port.c 平台层实现（SPI读写/CS控制/临界区锁）、sfud_adapter.c 兼容层封装（保持旧API）、多芯片支持、API 参考（init/read/write/erase/sfdp）、常见问题排查。当用户提到 SFUD、serial flash、W25Q64、W25Q128、SPI Flash、Flash 驱动、串行 Flash、NOR Flash、sfud_init、sfud_read、sfud_write、sfud_erase、sfud_sfdp、Flash 通用驱动、sflash、SPI Nor Flash 时使用。"
---

# SFUD 串行 Flash 通用驱动指南

> **SFUD** (Serial Flash Universal Driver) — 开源的串行 SPI Flash 通用驱动库，支持自动 SFDP 参数探测。
>
> 官方仓库：https://github.com/armink/SFUD（MIT 许可，1.8K+ Stars，v1.1.0）
>
> STM32 移植文档：`references/stm32-sfud-porting-guide.md`
>
> 适用平台：STM32 / ESP32 / AT32 / GD32 等所有带 SPI 接口的 MCU

## 场景

- **新板适配** — 需要在新的 MCU/板上接入 SPI Flash 芯片
- **跨型号兼容** — 同一固件需要支持 W25Q64/W25Q128 等多种 Flash
- **SFDP 自动探测** — 不想手动维护每个 Flash 芯片的参数表
- **Bootloader OTA** — 在 Bootloader 中读写 Flash 存储固件
- **文件系统底层** — 为 FATFS/LittleFS 提供统一的 Flash 读写接口

## 输入

- MCU 型号（确定 SPI 外设和 GPIO）
- Flash 芯片型号（确定容量/页大小/擦除粒度）
- SPI 引脚分配（SCK/MISO/MOSI/CS）

## 依赖

- **标准 SPI** — STM32 HAL_SPI / SPL SPI / 寄存器 SPI
- **临界区** — `__disable_irq()` / `__enable_irq()` 或 FreeRTOS 互斥锁

## 步骤

### Step 1: 获取源码

```bash
git clone https://github.com/armink/SFUD.git
```

SFUD v1.1.0 目录结构（非 QSPI 版本）：

```
SFUD/
├── inc/
│   ├── sfud.h              # 公共 API
│   ├── sfud_cfg.h          # 用户配置
│   ├── sfud_def.h          # 类型定义/版本
│   └── sfud_flash_def.h    # 预定义 Flash 芯片参数表（可选）
├── src/
│   ├── sfud.c              # 核心实现
│   └── sfud_sfdp.c         # SFDP 解析（可选）
├── port/
│   └── sfud_port.c         # 平台移植层模板
└── sfud_adapter.c          # 兼容适配层（可选，项目自建）
```

### Step 2: 配置 sfud_cfg.h

```c
#ifndef _SFUD_CFG_H_
#define _SFUD_CFG_H_

#include <stdint.h>
#include <stdbool.h>

/* ========== 功能开关 ========== */

/* 启用 SFDP 探测（自动检测 Flash 参数，推荐） */
#define SFUD_USING_SFDP

/* 启用快速读取（0x0B 命令，1 个 dummy 字节） */
#define SFUD_USING_FAST_READ

/* 启用 Flash 芯片信息表（SFDP 失败时回退查询） */
#define SFUD_USING_FLASH_INFO_TABLE

/* 调试模式（调试阶段打开，量产关闭） */
// #define SFUD_DEBUG_MODE

/* QSPI 模式（仅支持标准 SPI 时注释掉） */
// #define SFUD_USING_QSPI

/* ========== Flash 芯片定义表 ========== */
/* 定义板上实际的 Flash 芯片。多个芯片可用逗号分隔 */
enum {
    SFUD_W25Q64_DEVICE_INDEX = 0,       // 第一个 Flash
    // SFUD_W25Q128_DEVICE_INDEX = 1,   // 第二个 Flash（可选）
};

#define SFUD_FLASH_DEVICE_TABLE                                         \
{                                                                       \
    [SFUD_W25Q64_DEVICE_INDEX] = {                                      \
        .name = "W25Q64",             /* 芯片名称，仅用于标识 */         \
        .spi.name = "SPI1",           /* SPI 接口名称，sfud_port.c 用 */ \
    },                                                                  \
}

#endif /* _SFUD_CFG_H_ */
```

### Step 3: 实现 sfud_port.c（核心移植）

这是移植 SFUD 最关键的一步。实现 SPI 读写、CS 控制和临界区锁：

```c
/* sfud_port.c — STM32F4 + SPI1 示例 */
#include "sfud.h"
#include "stm32f4xx.h"

/* SPI 接口号，与 sfud_cfg.h 中 spi.name 对应 */
#define SFUD_SPI1_CS_GPIO       GPIOA
#define SFUD_SPI1_CS_PIN        GPIO_PIN_4

/* 根据 SPI 名称查找对应的 SPI 外设基址 */
static sfud_err spi_lock(const char *spi_name)
{
    /* 裸机：关全局中断。FreeRTOS：取互斥锁 */
    __disable_irq();
    return SFUD_SUCCESS;
}

static sfud_err spi_unlock(const char *spi_name)
{
    __enable_irq();
    return SFUD_SUCCESS;
}

/* CS 拉低（选中） */
static void cs_active(const char *spi_name)
{
    GPIO_ResetBits(SFUD_SPI1_CS_GPIO, SFUD_SPI1_CS_PIN);
}

/* CS 拉高（释放） */
static void cs_deactive(const char *spi_name)
{
    GPIO_SetBits(SFUD_SPI1_CS_GPIO, SFUD_SPI1_CS_PIN);
}

/* SPI 全双工读写字节 */
static uint8_t spi_read_write_byte(const char *spi_name, uint8_t byte)
{
    while (!(SPI1->SR & SPI_SR_TXE));  // 等待发送缓冲区空
    SPI1->DR = byte;
    while (!(SPI1->SR & SPI_SR_RXNE)); // 等待接收缓冲区非空
    return (uint8_t)SPI1->DR;
}

/* SFUD 核心 SPI 读写函数 */
static sfud_err spi_write_read(const sfud_spi *spi, const uint8_t *write_buf,
                                size_t write_size, uint8_t *read_buf, size_t read_size)
{
    sfud_err result = SFUD_SUCCESS;

    /* Step 1: 锁定 */
    if (spi_lock(spi->name) != SFUD_SUCCESS) {
        return SFUD_ERR_TIMEOUT;
    }

    /* Step 2: CS 选中 */
    cs_active(spi->name);

    /* Step 3: 发送写数据 */
    if (write_buf && write_size) {
        for (size_t i = 0; i < write_size; i++) {
            spi_read_write_byte(spi->name, write_buf[i]);
        }
    }

    /* Step 4: 接收读数据（发送 0xFF 产生时钟） */
    if (read_buf && read_size) {
        for (size_t i = 0; i < read_size; i++) {
            read_buf[i] = spi_read_write_byte(spi->name, 0xFF);
        }
    }

    /* Step 5: CS 释放 */
    cs_deactive(spi->name);

    /* Step 6: 解锁 */
    spi_unlock(spi->name);

    return result;
}

/* sfud_port.c 必须导出的函数 — SFUD 库通过弱符号调用 */
sfud_err sfud_spi_port_init(sfud_flash *flash)
{
    flash->spi.wr = spi_write_read;
    return SFUD_SUCCESS;
}
```

### Step 4: 初始化与使用

```c
/* main.c */
#include "sfud.h"

int main(void)
{
    SPI1_Init();            // 初始化 SPI 硬件
    sfud_init();            // 初始化 SFUD（会自动探测所有配置的 Flash）

    /* 获取第一个 Flash 设备 */
    const sfud_flash *flash = sfud_get_device(SFUD_W25Q64_DEVICE_INDEX);
    if (flash == NULL || flash->state != SFUD_DEVICE_NORMAL) {
        /* Flash 初始化失败（SPI/SFDP/参数错误） */
        while (1);
    }

    /* 读取：从地址 0x000000 读 256 字节 */
    uint8_t buf[256];
    sfud_read(flash, 0x000000, sizeof(buf), buf);

    /* 擦除：擦除 4KB 扇区 */
    sfud_erase(flash, 0x001000, 4096);

    /* 写入+擦除：自动处理擦除+写入 */
    const char *data = "Hello SFUD!";
    sfud_erase_write(flash, 0x001000, strlen(data), (uint8_t *)data);

    while (1);
}
```

### Step 5: 适配器层（可选，兼容旧代码）

如果项目已有基于 W25Qxx 的直接操作代码，可在 SFUD 上封装一层适配器，保持旧 API 兼容：

```c
/* sfud_adapter.c — 兼容层 */
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
    return sfud_erase(g_flash, addr, 4096) == SFUD_SUCCESS;
}
```

## 错误

| 错误现象 | 根因 | 解决 |
|---------|------|------|
| `sfud_init` 返回错误 | SPI 引脚/时钟未正确配置 | 检查 GPIO alternate function 和时钟使能 |
| SFDP 探测失败 | 芯片不支持 SFDP 或 SPI 通信异常 | 确保 `SFUD_USING_FLASH_INFO_TABLE` 启用，降级查表 |
| 读写数据全 0xFF | CS 引脚未正确拉低 | 检查 CS GPIO 配置和 cs_active 实现 |
| 写入后读取仍是 0xFF | 写入前未擦除 | 使用 `sfud_erase_write` 自动处理擦除 |
| 擦除很慢（数秒） | NOR Flash 擦除是耗时操作 | 正常现象，确保不关中断时间不超临界区 |
| SPI 时钟太快导致数据错位 | 时钟频率超过芯片上限 | 降低 SPI 预分频器（例如 256 分频 ~328kHz） |

## 输出

SFUD 正常运行后提供：
1. **Flash 设备枚举** — `sfud_init()` 探测所有芯片，打印名称/容量/页大小到调试口
2. **SFDP 解析** — 如果启用 SFDP，自动检测芯片支持的擦除粒度
3. **统一读写接口** — `sfud_read/sfud_write/sfud_erase` 跨芯片类型通用

## 边界

- **不覆盖 QSPI 模式** — SFUD 支持 QSPI 但本 skill 仅覆盖标准 SPI
- **不覆盖 Flash 均衡磨损** — SFUD 是低级驱动，不管理磨损均衡或坏块
- **不覆盖文件系统** — SFUD 提供块设备接口，文件系统（FATFS/LittleFS）需上层对接
- 与 `fatfs-module` 互补：SFUD 是底层驱动，FATFS 是文件系统层
- 与 `flash-module` 搭配：SFUD 管理外部 SPI Flash，flash-module 管理内部 MCU Flash

## 交接

- **SPI 通信异常** → 使用 `spi-bus` skill 排查 SPI 时序/BSY 问题
- **初始化失败** → 示波器查看 SCK/MOSI/MISO 波形，确认时钟极性(CPOL)和相位(CPHA)匹配
- **数据一致性问题** → 在所有 SPI 事务前后调用临界区锁（防止 ISR 中断事务）
- **需要文件系统** → 使用 `fatfs-module` skill 对接 FATFS

## 参考资料

- **官方仓库**: https://github.com/armink/SFUD
- **API 文档**: https://github.com/armink/SFUD/blob/master/docs/api/api.md
- **SFDP 标准**: JEDEC JESD216
- **作者**: armink（与 CmBacktrace/EasyFlash 同作者）
