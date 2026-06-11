---
name: fatfs-module
version: "1.0.0"
description: "FatFs 文件系统移植、配置与开发指南。涵盖 FatFs 架构与应用层接口、disk_io 底层驱动实现（SDIO/SPI/Flash）、多盘管理、长文件名/Unicode、时间戳、分区表、常见故障排除。当用户提到 FatFs、FATFS、文件系统、SD卡文件系统、Flash文件系统、f_open、f_read、f_write、f_mount、f_mkfs、disk_ioctl、SDIO 文件系统、SPI 文件系统、ffconf、长文件名、LFN、文件系统故障、TF卡读写、日志存储、数据记录、文件损坏、f_close、FatFs 移植、FatFs 配置时使用。"
---

# FatFs 模块开发指南

> 返回码速查见 `references/fatfs-return-code.md`（FRESULT 全部 20 个代码含义 + 访问模式 + disk_ioctl 命令 + 代码片段）

## FatFs 架构

### 三层结构

```
Application Layer
  f_open/f_read/f_write/f_close/f_mkfs/...
        ↕
FatFs Middleware (ff.c, ff.h, ffconf.h)
  FAT 文件系统核心逻辑（不依赖硬件）
        ↕
Disk I/O Layer (diskio.c, diskio.h)
  disk_initialize/disk_status/disk_read/disk_write/disk_ioctl
  需要用户实现：绑定到具体硬件（SDIO/SPI Flash/NOR Flash）
```

### 版本

```c
// 当前主流：FatFs R0.15 (2023) 或 CubeMX 集成版
// CubeMX 集成版路径：Middlewares/Third_Party/FatFs/src/
// 独立版本：http://elm-chan.org/fsw/ff/00index_e.html

// CubeMX 中使能：
// Middleware → FATFS → Mode: SD Card / SPI Flash / USB Disk / RAM Disk
```

## 配置 (ffconf.h)

```c
// ffconf.h 关键配置
#define FF_USE_LFN         2          // 长文件名: 0=关, 1=BSS, 2=堆, 3=栈
#define FF_MAX_LFN         255        // 最大文件名长度
#define FF_FS_RPATH        0          // 相对路径: 0=关, 1/2=开
#define FF_VOLUMES         2          // 卷数量 (SD + Flash 等)
#define FF_MIN_SS          512        // 最小扇区大小
#define FF_MAX_SS          512        // 最大扇区大小
#define FF_MULTI_PARTITION 0          // 多分区支持
#define FF_USE_STRFUNC     1          // f_puts/f_gets: 0=关, 1=开
#define FF_FS_NORTC        1          // 无 RTC: 1=使用固定时间戳
#define FF_NORTC_MON       1          // 默认月
#define FF_NORTC_MDAY      1          // 默认日
#define FF_NORTC_YEAR      2025       // 默认年
#define FF_FS_LOCK         0          // 文件锁(多任务安全)
#define FF_FS_REENTRANT    0          // 多任务安全(需 osal 层)
```

### 多任务安全

```c
// 当 FreeRTOS + FatFs 多任务访问时：
#define FF_FS_REENTRANT    1
#define FF_FS_TIMEOUT      1000       // 超时 ms
#define FF_SYNC_t          SemaphoreHandle_t

// 需要实现 osal 回调：
// ff_sys.c 或新建 ff_osal.c：
#include "FreeRTOS.h"
#include "semphr.h"

int ff_cre_syncobj(BYTE vol, FF_SYNC_t *m)
{
    *m = xSemaphoreCreateMutex();
    return (*m != NULL);
}

int ff_del_syncobj(FF_SYNC_t m)
{
    vSemaphoreDelete(m);
    return 1;
}

int ff_req_grant(FF_SYNC_t m)
{
    return xSemaphoreTake(m, pdMS_TO_TICKS(FF_FS_TIMEOUT)) == pdTRUE;
}

void ff_rel_grant(FF_SYNC_t m)
{
    xSemaphoreGive(m);
}
```

## Disk I/O 实现

### 通用接口

```c
// diskio.c 中必须实现的 5 个函数：

DSTATUS disk_initialize(BYTE pdrv);              // 初始化
DSTATUS disk_status(BYTE pdrv);                   // 检查状态
DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count);   // 读扇区
DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count); // 写扇区
DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff);  // 控制命令

// pdrv: 物理驱动器编号 (0=SD, 1=Flash, ...)
// sector: 扇区地址 (LBA 模式)
// count: 扇区数
// buff: 数据缓冲区（注意对齐）
```

### SDIO + SD 卡

```c
// 使用 STM32 SDIO 外设（F4/H7）

DSTATUS disk_initialize(BYTE pdrv)
{
    if (pdrv != 0) return STA_NOINIT;

    // HAL SD 初始化
    HAL_SD_Init(&hsd);
    HAL_SD_ConfigWideBusOperation(&hsd, SDIO_BUS_WIDE_4B);

    // 获取卡信息（扇区大小、块数）
    HAL_SD_GetCardInfo(&hsd, &sd_card_info);
    HAL_SD_GetCardCSD(&hsd, &sd_csd);

    return 0;
}

DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count)
{
    if (HAL_SD_ReadBlocks(&hsd, buff, sector, count, HAL_MAX_DELAY) == HAL_OK) {
        // 等待传输完成 (DMA 方式需要)
        while (HAL_SD_GetCardState(&hsd) != HAL_SD_CARD_TRANSFER);
        return RES_OK;
    }
    return RES_ERROR;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count)
{
    if (HAL_SD_WriteBlocks(&hsd, (uint8_t *)buff, sector, count, HAL_MAX_DELAY) == HAL_OK) {
        while (HAL_SD_GetCardState(&hsd) != HAL_SD_CARD_TRANSFER);
        return RES_OK;
    }
    return RES_ERROR;
}

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff)
{
    switch (cmd) {
        case GET_SECTOR_COUNT:
            *(uint32_t *)buff = sd_card_info.LogBlockNbr;
            break;
        case GET_SECTOR_SIZE:
            *(uint16_t *)buff = sd_card_info.LogBlockSize;
            break;
        case GET_BLOCK_SIZE:
            *(uint32_t *)buff = sd_csd.BlockSize;
            break;
        case CTRL_SYNC:
            while (HAL_SD_GetCardState(&hsd) != HAL_SD_CARD_TRANSFER);
            break;
        default:
            return RES_PARERR;
    }
    return RES_OK;
}
```

### SPI + SD 卡

```c
// 使用 SPI 连接 SD 卡（兼容性好，速度慢）

// 初始化：
// 1. SPI 低速初始化（~400kHz）→ 发 CMD0 进 IDLE
// 2. 发 CMD8 检测 SD V2.0
// 3. 发 ACMD41 初始化
// 4. 切回高速 SPI 模式
// 初始化代码量较大，建议使用 CubeMX 生成版

// 关键点：
// - SPI 时钟空闲为高 (CPOL=0, CPHA=0)
// - SPI 数据 MSB 先行
// - CS 由 GPIO 手动控制（非硬件 NSS）
// - 读写以单字节为单位
```

### Flash 作为存储

```c
// 使用外部 SPI Flash 做文件系统（W25Q64 等）

DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count)
{
    uint32_t addr = sector * 512;  // 扇区到 Flash 地址映射
    for (UINT i = 0; i < count; i++) {
        W25Q_Read(buff + i * 512, addr + i * 512, 512);
    }
    return RES_OK;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count)
{
    uint32_t addr = sector * 512;
    for (UINT i = 0; i < count; i++) {
        // Flash 必须先擦除后写
        W25Q_Erase_Sector(addr + i * 512);   // 按扇区擦除
        W25Q_Write(buff + i * 512, addr + i * 512, 512);
    }
    return RES_OK;
}

// 注意：Flash 擦写寿命 (100,000 次) 和文件系统频繁写入的冲突
// 建议：使用磨损均衡层或使用 SPI Flash 文件系统专用方案 (LittleFS)
```

## 常用 API

```c
// 挂载
FATFS fs;
f_mount(&fs, "0:", 1);  // 立即挂载

// 打开/读/写/关闭
FIL fil;
FRESULT res;

// 写文件
res = f_open(&fil, "0:/data.log", FA_WRITE | FA_CREATE_ALWAYS);
if (res == FR_OK) {
    UINT bytes_written;
    f_write(&fil, "Hello World\r\n", 13, &bytes_written);
    f_close(&fil);
}

// 读文件
res = f_open(&fil, "0:/config.ini", FA_READ);
if (res == FR_OK) {
    char buf[256];
    UINT bytes_read;
    f_read(&fil, buf, sizeof(buf), &bytes_read);
    f_close(&fil);
}

// 目录操作
DIR dir;
FILINFO fno;
f_opendir(&dir, "0:/");
while (f_readdir(&dir, &fno) == FR_OK && fno.fname[0]) {
    printf("%s  %lu bytes\n", fno.fname, fno.fsize);
}
f_closedir(&dir);

// 格式化
f_mkfs("0:", NULL, 0, 0);  // 格式化整张卡
```

## 常用技巧

### 日志循环写入

```c
// 日志文件超过最大大小后自动滚动
#define LOG_FILE   "0:/data.log"
#define LOG_MAX    (1024 * 1024)  // 1MB

void write_log(const char *msg)
{
    FIL fil;
    f_open(&fil, LOG_FILE, FA_WRITE | FA_OPEN_ALWAYS);

    // 移到文件末尾
    f_lseek(&fil, f_size(&fil));

    // 检查大小，超限截断
    if (f_size(&fil) > LOG_MAX) {
        f_close(&fil);
        // 方案：新建日志文件 data_1.log, data_2.log ...
        // 或直接覆盖
        f_open(&fil, LOG_FILE, FA_WRITE | FA_CREATE_ALWAYS);
    }

    UINT bw;
    f_write(&fil, msg, strlen(msg), &bw);
    f_write(&fil, "\r\n", 2, &bw);
    f_close(&fil);
}
```

### 缓冲区对齐

```c
// SDIO DMA 模式下缓冲区必须 4 字节对齐
// FatFs 的默认缓冲区可能不对齐

// 方案 1：使用对齐缓冲区
ALIGN_4 static uint8_t file_buf[512];

// 方案 2：f_read 使用 MDMA 缓冲区
ALIGN_4 uint8_t sdio_buffer[512];

FRESULT read_aligned(FIL *fil, void *buf, UINT len, UINT *br)
{
    // 如果 buf 未对齐，用对齐缓冲中转
    if ((uint32_t)buf & 0x3) {
        f_read(fil, sdio_buffer, len, br);
        memcpy(buf, sdio_buffer, *br);
        return FR_OK;
    }
    return f_read(fil, buf, len, br);
}
```

## 常见陷阱

| 编号 | 现象 | 根因 | 解决 |
|------|------|------|------|
| 1 | f_mount 返回 FR_DISK_ERR | 底层 disk_initialize 失败 | 检查 SD 卡初始化逻辑/SPI 连接 |
| 2 | f_open 返回 FR_NO_FILESYSTEM | SD 卡未格式化 | 先调用 f_mkfs 格式化 |
| 3 | f_read 返回数据全 0xFF | 扇区偏移计算错误 | 确认 sector×512 = Flash 地址 |
| 4 | 写文件后断电，文件损坏 | 未 f_close 导致缓存未刷 | 写完后一定 f_close 或 f_sync |
| 5 | SDIO DMA 模式下数据错乱 | 缓冲区地址未对齐 | 使用 ALIGN_4 声明缓冲区 |
| 6 | 文件名只有 8.3 格式 | LFN 未使能 | FF_USE_LFN = 2 |
| 7 | f_mkfs 返回 FR_MKFS_ABORTED | 参数不对或卡写保护 | 检查 SD 卡物理写保护开关 |
| 8 | 文件操作卡死（死等） | SDIO 卡 Busy 循环超时 | 添加超时退出机制 |
| 9 | 多任务下数据混乱 | 未使能 FF_FS_REENTRANT | 使能 + 实现 osal 信号量 |
| 10 | 长文件名打开慢 | LFN 使用栈或堆分配性能差 | 加大栈或改用静态 LFN buffer |

## 系列差异

| 特性 | F1 | F4 | H7 |
|------|-----|-----|-----|
| SDIO 外设 | SDIO 1-bit/4-bit | SDIO 1-bit/4-bit | SDMMC (增强版) |
| SDIO 时钟 | ≤ 24MHz | ≤ 24MHz | ≤ 50MHz (SDR104) |
| SDIO DMA | 无 DMA | DMA2 Stream | BDMA/MDMA |
| SPI SD 兼容 | 好 | 好 | 好 |
| 缓存对齐要求 | 4 字节 | 4 字节 | 32 字节 (D-Cache) |
| H7 D-Cache | — | — | 需 Invalidate/ Clean |

```c
// H7 额外注意：SDIO 缓冲区需要 D-Cache 维护
// 每次 disk_read 后 Invalidate，disk_write 前 Clean
```

## 边界定义

## 平台差异

| 平台 | 底层存储 | disk_ioctl 实现要点 |
|------|---------|-------------------|
| STM32 SDIO | `SD_read_blocks`/`SD_write_blocks` | `CTRL_SYNC`、`GET_SECTOR_COUNT`、`GET_SECTOR_SIZE` |
| STM32 SPI + SD | `SPI_ReadWrite` + 命令/响应 | `MMC_GET_CSD` 解析扇区数 |
| STM32 SPI + Flash | `SPI_ReadWrite`(W25Qxx 命令集) | 按 Flash 块大小对齐 |
| ESP-IDF | `esp_vfs_fat_spiflash_mount` | 无需手动实现 diskio，API 直接挂载 |
| Arduino | `SD.begin` + `File` 对象 | 硬件层封装在库中 |

注：ESP32 上推荐直接用 `esp_vfs_fat_*` 系列 API，不需要手动移植 diskio 层。

- **不覆盖 LittleFS**（针对 Flash 优化的文件系统）— 适用于 SPI Flash 场景，与 FatFs 互补
- **不覆盖 exFAT** — 需要 FF_FS_EXFAT 使能，多用于 32GB+ SDXC 卡
- **不覆盖 SDIO 初始化细节** — `stm32-hal-development` 中已有 SDIO 外设配置
- **不覆盖 USB MSC 主从** — 使用 `usb-module`
- 配合 `flash-module`：内部 Flash 做文件系统需要模拟 EEPROM 或使用 FTL 层
