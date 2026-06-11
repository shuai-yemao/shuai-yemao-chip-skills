# Flash 编程与 EEPROM 模拟详解

## HAL_FLASH_Program 编程时序

### F4 Word 编程 (Typical: 2~4µs @ 100MHz)

```
解锁 → PG=1 → 写目标地址 → BSY 等待 → 清除 PG → 锁
         ↑            ↑              ↑
      ~0.5µs     一次写操作       ~0.2µs
                    ~2-4µs
```

### H7 Quad-word 编程 (Typical: 1~2µs)

```
解锁 → PG=1 → 写目标地址(连续 4 个 WORD) → BSY → 清除 PG
                     ↑
             硬件自动完成 burst 写入
```

## 多字节编程策略

### 方法 1：逐字节 HAL 调用（不推荐）

```c
// ❌ 每次调用 HAL_FLASH_Program 都有函数调用开销
for (i = 0; i < len; i++) {
    HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, addr + i * 4, data[i]);
    // 每次等 BSY
}
```

### 方法 2：以页为单位缓存 + 一次性编程（推荐）

```c
// ✅ 先缓存整页数据，一次性擦除+写入
#define PAGE_SIZE   (16 * 1024)  // F4 Sector 0 大小

uint8_t page_buf[PAGE_SIZE] __attribute__((aligned(4)));

void write_flash_page(uint32_t sector_addr, uint8_t *data, uint32_t len)
{
    // 1. 读当前页到缓冲区
    memcpy(page_buf, (void *)sector_addr, PAGE_SIZE);

    // 2. 修改缓冲区内容
    memcpy(page_buf + offset, data, len);

    // 3. 擦除整页
    HAL_FLASH_Unlock();
    FLASH_EraseInitTypeDef erase = {
        .TypeErase = FLASH_TYPEERASE_SECTORS,
        .Sector = get_sector_from_addr(sector_addr),
        .NbSectors = 1,
        .VoltageRange = VOLTAGE_RANGE_3
    };
    HAL_FLASHEx_Erase(&erase, &sector_error);

    // 4. 逐字编程
    for (uint32_t i = 0; i < PAGE_SIZE; i += 4) {
        uint32_t word = *(uint32_t *)(page_buf + i);
        HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD, sector_addr + i, word);
    }

    HAL_FLASH_Lock();
}
```

### 方法 3：双 Bank 后台擦写

```c
// F4 1MB+/H7 双 Bank：在 Bank1 执行代码，同时擦写 Bank2
// 适用于 OTA 下载 + 后台写入方案

void ota_write_background(uint32_t bank2_sector, uint8_t *data)
{
    HAL_FLASH_Unlock();

    // 擦除目标 Bank 的 Sector（不影响 Bank1 代码执行）
    FLASH_EraseInitTypeDef erase = {
        .TypeErase = FLASH_TYPEERASE_SECTORS,
        .Sector = bank2_sector,
        .NbSectors = 1,
        .VoltageRange = VOLTAGE_RANGE_3
    };
    HAL_FLASHEx_Erase(&erase, &sector_error);

    // 写入新固件数据
    for (uint32_t i = 0; i < SECTOR_SIZE; i += 4) {
        HAL_FLASH_Program(FLASH_TYPEPROGRAM_WORD,
                          BANK2_BASE + sector_offset + i,
                          *(uint32_t *)(data + i));
    }

    HAL_FLASH_Lock();
}
```

## EEPROM 模拟详细实现

### 存储布局

```
Page 0 (0x0800C000, 16KB) — Active Page
+--------+--------+--------+--------+--------+
| Header | Var1   | Var2   | Var3   | Free   |
| (4B)   | (8B)   | (8B)   | (8B)   | space  |
+--------+--------+--------+--------+--------+

Page 1 (0x08010000, 16KB) — Transfer Page
+--------+--------+--------+--------+--------+
| Header | Free   | Free   | Free   | Free   |
| (4B)   | space  | space  | space  | space  |
+--------+--------+--------+--------+--------+
```

### 变体存储结构

```c
// 每个变量记录：虚拟 ID (2B) + 数据 (2B) = 4B
// 加奇偶校验或 CRC 可扩展为 8B

typedef struct {
    uint16_t VirtID;    // 变量虚拟 ID (0x0000~0xFFFF)
    uint16_t Data;      // 变量数据
} EE_Variable;

// Page Header: 4 字节状态标志
// 0xFFFF FFFF = Erased (空白页)
// 0xAAAA AAAA = Active (当前活动页)
// 0x0000 0000 = Transfer (正在转移数据)
```

### 完整读/写/转移流程

```c
#define EE_PAGE0_ADDR   0x0800C000   // Page 0 = Sector 3
#define EE_PAGE1_ADDR   0x08010000   // Page 1 = Sector 4
#define EE_PAGE_SIZE    (16 * 1024)  // 16KB

// 查找变量
uint16_t EE_FindVar(uint32_t page_addr, uint16_t var_id)
{
    uint32_t addr = page_addr + 4;  // 跳过 Header
    while (addr < page_addr + EE_PAGE_SIZE) {
        uint16_t vid = *(volatile uint16_t *)addr;
        if (vid == 0xFFFF) break;   // 遇到空白 = 未找到
        if (vid == var_id) {
            return *(volatile uint16_t *)(addr + 2);  // 返回数据
        }
        addr += 4;  // 到下一个 Var 记录 (4B)
    }
    return 0xFFFF;  // 未找到
}

// 写入变量（追加新版本）
EE_Status EE_Write(uint16_t var_id, uint16_t data)
{
    // 1. 找到当前 Active Page
    uint32_t active = EE_GetActivePage();
    if (active == 0) return EE_ERROR;

    // 2. 查找空白位置
    uint32_t free_pos = EE_FindFreePos(active);

    // 3. 如果当前页已满 → 转移
    if (free_pos >= active + EE_PAGE_SIZE - 4) {
        EE_Transfer(active);
        active = EE_GetActivePage();
        free_pos = active + 4;
    }

    // 4. 写入新值
    *(volatile uint16_t *)free_pos = var_id;
    *(volatile uint16_t *)(free_pos + 2) = data;

    return EE_OK;
}

// 页转移（当 Active 页满时）
void EE_Transfer(uint32_t full_page)
{
    uint32_t other_page = (full_page == EE_PAGE0_ADDR) ?
                           EE_PAGE1_ADDR : EE_PAGE0_ADDR;

    // 标记 Full Page 为 Transfer 状态
    *(volatile uint32_t *)full_page = 0x00000000;

    // 擦除 Other Page
    ErasePage(other_page);

    // 将所有非最新的变量复制到 Other Page
    uint32_t addr = full_page + 4;
    while (addr < full_page + EE_PAGE_SIZE) {
        uint16_t vid = *(volatile uint16_t *)addr;
        uint16_t data = *(volatile uint16_t *)(addr + 2);
        if (vid == 0xFFFF) break;

        // 只复制最新版本的变量
        if (EE_IsLatest(full_page, vid, addr)) {
            uint32_t dst = EE_FindFreePos(other_page);
            *(volatile uint16_t *)dst = vid;
            *(volatile uint16_t *)(dst + 2) = data;
        }
        addr += 4;
    }

    // 标记 Other Page 为 Active
    *(volatile uint32_t *)other_page = 0xAAAAAAAA;

    // 擦除 Full Page（变成空白页）
    ErasePage(full_page);
}
```

## Flash 操作电源要求

| 操作 | 最小 VDD | 最大温度 | 典型电流 |
|------|---------|---------|---------|
| 读取 | 1.8V (F4: 1.7V) | 85°C/105°C | ~20mA |
| 编程 (Word) | 2.0V (VR3) | 85°C | ~20mA |
| 编程 (Half-word) | 1.8V (VR1) | 85°C | ~15mA |
| 擦除 (Sector) | 2.0V (VR3) | 85°C | ~20mA |
| 擦除 (Mass) | 2.0V (VR3) | 85°C | ~20mA |

> **注意**：低电压下编程/擦除可能失败。如果在电池供电场景中需要写 Flash，确保在 VDD 充足时操作。

## Flash 磨损均衡示例

```c
// 简单磨损均衡：两个 Bank 轮流用于参数存储
// 每次写参数时切换到一个新 Sector

#define PARAM_SECTORS 4  // 4 个 Sector 轮流使用
#define PARAM_BASE    0x08080000  // 从 Bank2 开始

uint32_t param_sector_idx = 0;  // 当前 Sector 索引

void save_params(void *data, uint32_t len)
{
    uint32_t addr = PARAM_BASE + (param_sector_idx * 0x20000);

    // 擦除 + 写入
    erase_sector_by_index(param_sector_idx);
    write_flash(addr, data, len);

    // 下一次使用下一个 Sector
    param_sector_idx = (param_sector_idx + 1) % PARAM_SECTORS;

    // 寿命: 10,000 × 4 = 40,000 次写入
}
```

## Flash 编程时序（@100MHz F4）

| 操作 | 典型时间 | 说明 |
|------|---------|------|
| 读 1 Word | 1 HCLK + WS | WS=3 时 = 4 HCLK = 40ns |
| 编程 1 Word | ~2µs (with ART) | — |
| 擦除 1 Sector (16KB) | ~100ms | — |
| 擦除 1 Sector (128KB) | ~400ms | — |
| Mass Erase (1MB) | ~3s | 整片擦除 |
| 编程 1KB (连续 Word) | ~2ms | 256 次 Word 编程 |
