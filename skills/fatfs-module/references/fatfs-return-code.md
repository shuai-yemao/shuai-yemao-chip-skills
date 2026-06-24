# FatFs 返回码与常见操作速查

## FRESULT 返回码

| 宏 | 值 | 含义 | 常见原因 |
|----|-----|------|---------|
| `FR_OK` | 0 | 成功 | — |
| `FR_DISK_ERR` | 1 | 底层硬件错误 | `disk_read/write` 返回错误 |
| `FR_INT_ERR` | 2 | 断言失败 | 文件系统损坏或 FatFs bug |
| `FR_NOT_READY` | 3 | 设备未就绪 | `disk_initialize` 失败/卡未插入 |
| `FR_NO_FILE` | 4 | 文件不存在 | 路径错误 |
| `FR_NO_PATH` | 5 | 目录不存在 | 路径中目录不存在 |
| `FR_INVALID_NAME` | 6 | 文件名无效 | 含非法字符 |
| `FR_DENIED` | 7 | 访问拒绝 | 写保护/只读属性/权限 |
| `FR_EXIST` | 8 | 文件已存在 | `FA_CREATE_NEW` 时文件已存在 |
| `FR_INVALID_OBJECT` | 9 | 文件对象无效 | 文件未打开或已被关闭 |
| `FR_WRITE_PROTECTED` | 10 | 介质写保护 | SD 卡物理开关/Flash 写保护 |
| `FR_INVALID_DRIVE` | 11 | 无效驱动器号 | `f_mount` 时驱动号 > FF_VOLUMES |
| `FR_NOT_ENABLED` | 12 | 卷未挂载 | 未调用 `f_mount` |
| `FR_NO_FILESYSTEM` | 13 | 无有效 FAT 文件系统 | 未格式化或格式不支持 |
| `FR_MKFS_ABORTED` | 14 | 格式化失败 | 参数错误/写保护 |
| `FR_TIMEOUT` | 15 | 操作超时 | `FF_FS_TIMEOUT` 到期 |
| `FR_LOCKED` | 16 | 文件被锁定 | 同文件被多次打开且 `FF_FS_LOCK` 已满 |
| `FR_NOT_ENOUGH_CORE` | 17 | 内存不足 | `FF_USE_LFN=2` 时 malloc 失败 |
| `FR_TOO_MANY_OPEN_FILES` | 18 | 打开文件过多 | 超过 `FF_FS_LOCK` 或文件对象上限 |
| `FR_INVALID_PARAMETER` | 19 | 无效参数 | 传入 NULL 或不合理参数 |

## 文件访问模式

```c
// f_open 的 mode 标志
#define FA_READ             0x01   // 读
#define FA_WRITE            0x02   // 写
#define FA_OPEN_EXISTING    0x00   // 打开已有文件(不存在则失败)
#define FA_CREATE_NEW       0x04   // 创建新文件(已存在则失败)
#define FA_CREATE_ALWAYS    0x08   // 创建(存在则覆盖)
#define FA_OPEN_ALWAYS      0x10   // 打开(不存在则创建)
#define FA_OPEN_APPEND      0x30   // 打开且定位到末尾

// 常用组合：
// "r"  = FA_READ
// "r+" = FA_READ | FA_WRITE
// "w"  = FA_CREATE_ALWAYS | FA_WRITE
// "w+" = FA_CREATE_ALWAYS | FA_WRITE | FA_READ
// "a"  = FA_OPEN_APPEND | FA_WRITE
// "a+" = FA_OPEN_APPEND | FA_WRITE | FA_READ
```

## disk_ioctl 命令

```c
// disk_ioctl 的 cmd 参数
#define CTRL_SYNC           0   // 刷新写缓冲
#define GET_SECTOR_COUNT    1   // 获取总扇区数(只读介质)
#define GET_SECTOR_SIZE     2   // 获取扇区大小(通常 512)
#define GET_BLOCK_SIZE      3   // 获取擦除块大小(NAND/Flash)
#define CTRL_TRIM           4   // 通知设备扇区已无用(SD/SSD TRIM)
#define CTRL_POWER          5   // 电源控制(SD 卡)
#define CTRL_LOCK           6   // 锁定介质
#define CTRL_EJECT          7   // 弹出(SD 卡)
#define CTRL_FORMAT         8   // 底层格式化
#define MMC_GET_TYPE        10  // 获取卡类型(SD/MMC/SDHC)
#define MMC_GET_CSD         11  // 读取 CSD 寄存器
#define MMC_GET_CID         12  // 读取 CID 寄存器
#define MMC_GET_OCR         13  // 读取 OCR 寄存器
#define MMC_GET_SDSTAT      14  // 读取 SD Status
#define ISDIO_READ          55  // I/O SDIO 读
#define ISDIO_WRITE         56  // I/O SDIO 写
#define ISDIO_MRITE         57  // I/O SDIO 多重写
```

## 常用文件操作速查

### 遍历目录

```c
FRESULT list_directory(const char *path)
{
    DIR dir;
    FILINFO fno;
    FRESULT res = f_opendir(&dir, path);

    if (res != FR_OK) return res;

    printf("Directory: %s\n", path);
    for (;;) {
        res = f_readdir(&dir, &fno);
        if (res != FR_OK || fno.fname[0] == 0) break;

        if (fno.fattrib & AM_DIR)
            printf("  [DIR]  %s\n", fno.fname);
        else
            printf("  [FILE] %s (%lu bytes)\n", fno.fname, fno.fsize);
    }
    f_closedir(&dir);
    return FR_OK;
}
```

### 读配置文件

```c
// config.ini 格式：
// key=value

FRESULT read_config(const char *filename, const char *key, char *value, UINT max_len)
{
    FIL fil;
    FRESULT res = f_open(&fil, filename, FA_READ);
    if (res != FR_OK) return res;

    char line[128];
    while (f_gets(line, sizeof(line), &fil)) {
        // 去掉换行符
        char *nl = strchr(line, '\n');
        if (nl) *nl = 0;

        // 解析 key=value
        char *eq = strchr(line, '=');
        if (eq && strncmp(line, key, eq - line) == 0) {
            strncpy(value, eq + 1, max_len - 1);
            value[max_len - 1] = 0;
            f_close(&fil);
            return FR_OK;
        }
    }
    f_close(&fil);
    return FR_NO_FILE;  // 未找到 key
}
```

### 追加日志

```c
FRESULT append_log(const char *msg)
{
    FIL fil;
    FRESULT res = f_open(&fil, "0:/log.txt", FA_OPEN_APPEND | FA_WRITE);
    if (res != FR_OK) return res;

    UINT bw;
    f_write(&fil, msg, strlen(msg), &bw);
    f_write(&fil, "\r\n", 2, &bw);
    f_close(&fil);
    return FR_OK;
}
```

## 时间戳（RTC 集成）

```c
// 如果没有硬件 RTC，FatFs 默认使用固定时间
// 如需准确时间，实现 get_fattime 函数：

DWORD get_fattime(void)
{
    // 返回格式: bit[31:25]=年(1980+), [24:21]=月, [20:16]=日
    //           [15:11]=时, [10:5]=分, [4:0]=秒/2

    // 从 RTC 读取当前时间
    RTC_TimeTypeDef rtc_time;
    RTC_DateTypeDef rtc_date;
    HAL_RTC_GetTime(&hrtc, &rtc_time, RTC_FORMAT_BIN);
    HAL_RTC_GetDate(&hrtc, &rtc_date, RTC_FORMAT_BIN);

    return ((DWORD)(rtc_date.Year + 2000 - 1980) << 25)
         | ((DWORD)rtc_date.Month << 21)
         | ((DWORD)rtc_date.Date << 16)
         | ((DWORD)rtc_time.Hours << 11)
         | ((DWORD)rtc_time.Minutes << 5)
         | ((DWORD)rtc_time.Seconds >> 1);
}
```

## 多扇区读写优化

```c
// 单扇区 vs 多扇区：
// f_read(单扇区 512 字节)  → disk_read(1 扇区) → SDIO 命令延迟 ×1
// f_read(16 扇区 8KB)     → disk_read(16 扇区) → SDIO 命令延迟 ×1

// 大文件读写建议：
// 1. 缓冲区设为 4KB~32KB 以减少 disk_read/write 调用次数
// 2. 使用 f_read 时一次性读入大缓冲区，避免小片读取
// 3. 顺序读写性能远好于随机读写（SD 卡特性）

// 读取性能对比（SDIO 4bit, 24MHz）：
// 单扇区读取:    ~300μs/扇区 → ~1.6MB/s
// 多扇区(64):    ~180μs/扇区 → ~2.7MB/s
// 连续读取(大块): ~100μs/扇区 → ~5MB/s
```
