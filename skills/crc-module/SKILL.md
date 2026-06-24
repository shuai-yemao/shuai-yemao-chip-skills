---
name: crc-module
description: |
  CRC 校验算法开发指南。覆盖常见 CRC 模型（CRC-16/CCITT/32/MODBUS）、
  查表法 vs 逐位法实现、硬件 CRC 外设（STM32 CRC 模块）、
  多项式选择与碰撞率、与校验和/哈希的对比选型、
  在 Bootloader OTA 和通信协议中的应用。
  当用户提到 CRC、循环冗余校验、CRC-16、CRC-32、CRC-8、CRC-CCITT、
  STM32 CRC、硬件 CRC、多项式、查表法、校验算法、数据完整性、
  OTA 校验、通信帧校验、Modbus CRC、CRC 计算、CRC 表生成 时使用。
version: "1.0.0"
---

# CRC 校验算法开发指南

## 适用场景

- 需要在通信协议中添加帧校验（UART/SPI/CAN/Modbus）
- 需要在 Bootloader OTA 中校验固件完整性
- 需要利用 STM32 硬件 CRC 外设加速计算
- 需要选择合适的 CRC 多项式（长度/碰撞率/速度权衡）
- 需要移植 CRC 算法到不同 MCU 平台

## 必要输入

| 参数 | 说明 |
|------|------|
| CRC 模型 | CRC-8/CRC-16-CCITT/CRC-32/CRC-32C |
| 多项式 | 由 CRC 模型决定（如 CRC-32=0x04C11DB7）|
| 初始值 | 0x0000/0xFFFF/0xFFFFFFFF（模型相关）|
| 输入反转/输出反转 | 模型相关（如 CRC-32 都反转）|
| 算法 | 查表法(快) / 逐位法(小) / 硬件 CRC |

## 常见 CRC 模型速查

| 名称 | 多项式 | 宽度 | 初始值 | 结果异或 | 反转入/出 | 典型用途 |
|------|--------|------|--------|---------|----------|---------|
| CRC-8 | 0x07 | 8 | 0x00 | 0x00 | 否/否 | 1-Wire(DHTxx) |
| CRC-16-IBM | 0x8005 | 16 | 0x0000 | 0x0000 | 是/是 | USB |
| CRC-16-CCITT | 0x1021 | 16 | 0xFFFF | 0x0000 | 否/否 | XMODEM/蓝牙 |
| CRC-16-MODBUS | 0x8005 | 16 | 0xFFFF | 0x0000 | 是/是 | Modbus RTU |
| CRC-32 | 0x04C11DB7 | 32 | 0xFFFFFFFF | 0xFFFFFFFF | 是/是 | ZIP/Ethernet |
| CRC-32C (Castagnoli) | 0x1EDC6F41 | 32 | 0xFFFFFFFF | 0xFFFFFFFF | 是/是 | iSCSI/SSE4.2 |
| CRC-32/MPEG2 | 0x04C11DB7 | 32 | 0xFFFFFFFF | 0x00000000 | 否/否 | 通信协议 |

## 实现方式

### 查表法（快速，推荐）

```c
// CRC-32 查表法（最常用）
static const uint32_t crc32_table[256] = {
    0x00000000, 0x77073096, 0xEE0E612C, 0x990951BA, /* ... 256 项 */
};

uint32_t crc32_calc(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    for (uint32_t i = 0; i < len; i++) {
        crc = crc32_table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFF;
}
// 表生成方法：python -c "import binascii; print(hex(binascii.crc32(b'hello') & 0xFFFFFFFF))"
```

### 逐位法（代码最小，适合小内存 MCU）

```c
uint32_t crc32_bitwise(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFF;
    for (uint32_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1)
                crc = (crc >> 1) ^ 0xEDB88320;
            else
                crc >>= 1;
        }
    }
    return crc ^ 0xFFFFFFFF;
}
```

### STM32 硬件 CRC（零 CPU 开销）

```c
// STM32 全系列内建 CRC 外设（CRC-32 多项式固定 0x04C11DB7）
// F1/F4 固定多项式，G0/G4/H7/L4 可配置

__HAL_RCC_CRC_CLK_ENABLE();

uint32_t crc_hw_calc(const uint8_t *data, uint32_t len)
{
    uint32_t *ptr = (uint32_t *)data;
    uint32_t words = len / 4;

    CRC->CR = CRC_CR_RESET;                    // 复位 CRC 计算器
    for (uint32_t i = 0; i < words; i++) {
        CRC->DR = ptr[i];                      // 按字写入
    }
    // 处理剩余字节（需对齐）
    uint32_t last = 0;
    memcpy(&last, data + words * 4, len % 4);
    if (len % 4) CRC->DR = last;

    return CRC->DR;                            // 读取结果
}
```

**平台差异**：
| 系列 | CRC 外设 | 多项式可配 | 备注 |
|------|---------|-----------|------|
| STM32F1/F4 | CRC | 固定(0x04C11DB7) | 只支持 CRC-32 |
| STM32G0/G4/L4 | CRC | 可配置 | 支持 CRC-8/16/32 |
| STM32H7 | CRC | 可配置 | 支持可编程多项式 |
| ESP32 | 无硬件 CRC | — | 用软件查表法 |
| GD32 | CRC | 固定 | 与 STM32F1 兼容 |

## CRC 与哈希对比

| 算法 | 输出长度 | 碰撞率 | 速度 | 适用场景 |
|------|---------|--------|------|---------|
| CRC-8 | 1 字节 | 高 | 极快 | 短数据帧校验 |
| CRC-16 | 2 字节 | 中 | 极快 | Modbus/通信帧 |
| CRC-32 | 4 字节 | 低 | 快 | OTA/文件完整性 |
| SHA256 | 32 字节 | 极低 | 慢 | 固件签名/安全校验 |

**选型建议**：
- 通信帧校验 → CRC-16 或 CRC-8（够用，额外开销小）
- 固件完整性 → CRC-32（查表法 4MB/s@72MHz）
- 安全校验 → SHA256 + 签名（CRC 不可用于防篡改）

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| CRC 不匹配 | 两端多项式/参数不一致 | 核对 CRC 模型参数（多项式/初值/XOR/反转）|
| 硬件 CRC 结果不对 | 字节序问题 | 确认输入字节序（小端/大端）|
| 查表法结果与硬件不一致 | 多项式不匹配 | F1/F4 硬件 CRC 固定使用 CRC-32 模型 |

## 边界定义

- **不覆盖** SHA 系列哈希算法 → 使用 mbedTLS 的 SHA256
- **不覆盖** 数据加密 → 使用 `aes-module`
- CRC 不是加密哈希，不能用于安全校验（CRC 可被逆向构造碰撞）

## 交接关系

- 上游：`ymodem-module`（Ymodem 帧 CRC 校验）
- 上游：`ota-package`（OTA 包头部 CRC32 校验）
- 互补：`aes-module`（CRC 完整性 + AES 加密安全组合）
- 互补：`bootloader-design`（Bootloader 中的固件 CRC 校验）
