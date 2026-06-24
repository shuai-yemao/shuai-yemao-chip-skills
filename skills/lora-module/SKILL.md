---
name: lora-module
description: |
  LoRa/LoRaWAN 远距离低功耗无线通信开发指南。覆盖 LoRa 调制原理、
  SX1278/SX1262 射频芯片驱动、ESP32+LoRa 方案、STM32+LoRaWAN 协议栈、
  LoRaWAN Class A/B/C 入网与数据收发、ADR 自适应速率、频段与扩频因子配置。
  当用户提到 LoRa、LoRaWAN、SX1278、SX1262、Lora 节点、LoRa 网关、
  远距离无线、低功耗广域网、频段配置、ADR、LoRa 调试 时使用。
version: "1.0.0"
---

# LoRa/LoRaWAN 无线通信开发指南

## 适用场景

- 需要远距离（1-15km）、低功耗、低数据速率的无线通信
- 需要搭建 LoRaWAN 传感器节点（温湿度/水表/烟感等）
- 需要选型 LoRa 方案（射频芯片 / 透传模块 / LoRaWAN 模块）
- 需要配置 LoRa 频段（CN470/EU868/US915）和扩频因子
- 需要调试 LoRa 通信距离不足、丢包、功耗问题

## 必要输入

| 参数 | 说明 |
|------|------|
| 方案类型 | 射频芯片(SX1278/SX1262) / 透传模块 / LoRaWAN 节点 |
| 频段 | CN470 / EU868 / US915 / AU915 / AS923 |
| 协议 | LoRa 点对点 / LoRaWAN (Class A/B/C) |
| 扩频因子 | SF7~SF12（SF12距离最远，速率最低）|

## LoRa 射频参数

### 关键参数与权衡

```
扩频因子 (SF):     SF7(5kbps) → SF12(293bps)   ↑距离 ↓速率
编码率 (CR):       4/5 → 4/8                    ↑抗干扰 ↓速率
带宽 (BW):         125kHz / 250kHz / 500kHz    ↑带宽=↑速率↓灵敏度
发射功率:          2~20dBm                       ↑功率=↑距离 ↓续航
```

### 典型配置对比

| 参数 | 最大距离 | 最省电 | 一般使用 |
|------|---------|--------|---------|
| SF | SF12 | SF7 | SF9 |
| BW | 125kHz | 500kHz | 125kHz |
| CR | 4/8 | 4/5 | 4/5 |
| 功率 | 20dBm | 10dBm | 14dBm |

## LoRaWAN 入网流程

### OTAA (Over-The-Air Activation) — 推荐

```
节点                          LoRaWAN 网络服务器
  │  Join Request (AppEUI+DevEUI+DevNonce)  │
  │─────────────────────────────────────────>│
  │  Join Accept (AppNonce+NetID+DevAddr)    │
  │<─────────────────────────────────────────│
  │  └─ 计算 NwkSKey + AppSKey              │
  │  已入网，进入数据收发                     │
```

### ABP (Activation By Personalization) — 简化

```
节点: 预配置 DevAddr + NwkSKey + AppSKey
节点上线后直接发送数据（无 Join 流程）
```

## 平台开发

### SX1278/SX1262 + STM32 (SPI 驱动)

```c
// LoRa 寄存器级初始化（SX1278 SPI）
void lora_init(void)
{
    // 1. 设置工作模式
    lora_write_reg(REG_OP_MODE, MODE_LONG_RANGE_MODE);  // LoRa 模式
    lora_write_reg(REG_OP_MODE, MODE_SLEEP);              // 先睡眠
    lora_write_reg(REG_OP_MODE, MODE_STDBY);              // 待机

    // 2. 配置射频参数
    lora_write_reg(REG_MODEM_CONFIG_1, BANDWIDTH_125KHZ | CODING_4_5);
    lora_write_reg(REG_MODEM_CONFIG_2, SPREADING_9 | CRC_ENABLE);

    // 3. 设置频点 (CN470: 470MHz)
    uint32_t freq = 470000000;
    lora_write_reg(REG_FRF_MSB, (freq >> 16) & 0xFF);
    lora_write_reg(REG_FRF_MID, (freq >> 8) & 0xFF);
    lora_write_reg(REG_FRF_LSB, freq & 0xFF);

    // 4. 设置发射功率 (17dBm)
    lora_write_reg(REG_PA_CONFIG, PA_BOOST | 0x0F);
}

// 发送数据
void lora_send(uint8_t *data, uint8_t len)
{
    lora_write_reg(REG_DIO_MAPPING_1, 0x40);  // TxDone 映射到 DIO0
    lora_write_reg(REG_FIFO_ADDR_PTR, 0);     // FIFO 指针复位
    for (uint8_t i = 0; i < len; i++)
        lora_write_reg(REG_FIFO, data[i]);
    lora_write_reg(REG_PAYLOAD_LENGTH, len);

    lora_write_reg(REG_OP_MODE, MODE_TX);     // 切到发射
    while ((lora_read_reg(REG_IRQ_FLAGS) & IRQ_TX_DONE_MASK) == 0);
    lora_write_reg(REG_IRQ_FLAGS, IRQ_TX_DONE_MASK);
}
```

### ESP32 + LoRa (Arduino 或 ESP-IDF)

```c
// ESP-IDF + LoRa 示例（基于乐鑫 LoRa 库）
#include "driver/spi_master.h"
#include "sx1276.h"

void app_main(void)
{
    sx1276_config_t config = {
        .spi_host = SPI2_HOST,
        .cs_io = 5,
        .reset_io = 14,
        .dio0_io = 2,
        .frequency = 470000000,   // CN470
        .spreading_factor = 9,
        .bandwidth = SX1276_BW_125KHZ,
        .coding_rate = SX1276_CR_4_5,
        .tx_power = 17,
    };
    sx1276_init(&config);

    // 发送
    uint8_t data[] = {0x01, 0x02, 0x03};
    sx1276_send_packet(data, sizeof(data));
}
```

### LoRaWAN 协议栈

| 栈 | 平台 | 特点 |
|-----|------|------|
| MCCI LoRaWAN | 全平台 C | 最成熟的嵌入式 LoRaWAN 栈 |
| IBM LMiC | ARM/STM32 | 轻量，Class A/C |
| ESP-LoRaWAN | ESP32 | ESP-IDF 集成，使用简单 |
| Arduino-LMIC | Arduino 全平台 | 入门最快 |

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 无法入网 | DevEUI/AppEUI 错，或频段不匹配 | 核对服务器注册信息，频段设置 |
| 距离太短 | 天线不匹配/发射功率低 | 检查天线阻抗匹配，提高 SF 和功率 |
| 功耗过高 | 发射时隙未休眠 | 用 Class A（发射后开接收窗再睡）|
| 丢包严重 | 同频干扰/ADR 过于激进 | 降低 SF，增加重传，限制 ADR |
| Duty Cycle 限制 | ISM 频段法规 | EU868 有 1% duty cycle 限制 |

## 平台差异

| 平台 | 射频芯片 | 协议栈 | 优点 |
|------|---------|--------|------|
| STM32+SX1278 | SX1278(Semtech) | MCCI/LMiC | 成熟，灵活 |
| STM32+SX1262 | SX1262 | MCCI/LMiC | 更优功耗，支持TDD |
| ESP32+SX1262 | SX1262 | ESP-LoRaWAN | 开发快，WiFi+LoRa |
| ASR6505 | 集成 SoC | 阿里 LinkWAN | 一体方案，成本低 |
| LoRaWAN 模块 | 封装成 AT 模块 | 模块端 | 开发最简单 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 射频初始化失败 | SPI 通信异常 | 检查 SPI 接线，CS/RESET/DIO 引脚 |
| Join 超时 | 信号太弱或频点不对 | 检查天线，降低 SF 加快速率 |
| 发送超时 | 信道繁忙或占空比限制 | 增加重试间隔，切换信道 |
| CRC 错误 | 干扰严重或距离太远 | 提高 CR(4/8)，降低 SF，加前向纠错 |

## 边界定义

### 不该激活
- 用户需要的是短距离高速无线（WiFi/BLE）→ 使用 `wifi-module` / `ble-module`
- 用户需要的是蜂窝通信（4G/NB-IoT）→ 使用 `cellular-module`
- 用户只需要串口透传（不需要 LoRaWAN）→ 点对点 LoRa 即可

### 不该做
- **禁止**在 LoRa 信道上持续发射（违反 ISM 频段 duty cycle 法规）
- **禁止**在未配置天线匹配网络时发射高功率（可能损坏射频前端）
- **禁止**多节点使用相同的 DevNonce（影响 OTAA 入网）

### 不该碰
- **不触碰**射频电路设计（匹配网络、天线阻抗）
- **不触碰**LoRaWAN 服务器配置（ChirpStack/TTN/AWS IoT）
- **不触碰**无线电频谱合规认证

## 交接关系

- 上游：`spi-bus`（SX1278/SX1262 SPI 通信底层）
- 互补：`cellular-module`（LoRa 替代或补充方案对比）
- 互补：`lowpower-design`（LoRa 节点低功耗设计）
- 参考：`chip-architecture`（LoRa 芯片选型）
