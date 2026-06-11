---
name: ymodem-module
description: |
  Ymodem 文件传输协议开发指南。覆盖 Ymodem 协议帧格式（SOH/STX/EOT/CAN）、
  128 字节 vs 1024 字节模式、CRC-16 校验、批处理文件传输（文件名+大小）、
  STM32 Bootloader + Ymodem 串口 OTA、ESP32 Ymodem 接收、
  常见问题调试（超时/丢包/帧错）。
  当用户提到 Ymodem、串口传文件、Xmodem、Ymodem-1K、Ymodem-G、
  串口 OTA、Bootloader 升级、UART 升级、文件传输协议、CRC 帧校验、
  串口传固件、批处理传输 时使用。
version: "1.0.0"
---

# Ymodem 文件传输协议开发指南

## 适用场景

- 需要在 UART 串口上传输固件文件（典型 Bootloader OTA 场景）
- 需要实现 Ymodem 接收端（Bootloader 侧）或发送端（上位机）
- 需要选型 Ymodem vs Xmodem vs Zmodem 协议
- 需要在没有网络协议栈的情况下传输文件

## 必要输入

| 参数 | 说明 |
|------|------|
| 角色 | 接收端(Recv/Bootloader) / 发送端(Send/上位机) |
| 帧模式 | 128B(SOH) / 1024B(STX) / 自动协商 |
| 传输方向 | 固件下载(上位机→设备) / 数据上传(设备→上位机) |
| 超时设置 | 帧间超时(典型 1-3s) / 总超时(典型 10-30s) |

## 协议帧格式

### 帧类型

| 字节 | 名称 | 说明 |
|------|------|------|
| SOH (0x01) | 128 字节帧头 | 标准模式 |
| STX (0x02) | 1024 字节帧头 | 1K 模式(Ymodem) |
| EOT (0x04) | 传输结束 | 文件发送完毕 |
| ACK (0x06) | 确认 | 帧接收正确 |
| NAK (0x15) | 否认 | 帧接收错误，请求重发 |
| CAN (0x18) | 取消 | 取消传输 |
| C (0x43) | 'C' | 请求 CRC 模式 |

### 数据帧格式

```
┌──────┬───────┬───────┬───────────────┬──────┐
│ SOH  │  SEQ  │ ~SEQ  │  128 数据字节 │ CRC  │
│ /STX │  序号  │ 取反  │  (或1024字节) │ 校验 │
│ 1字节│ 1字节 │ 1字节 │    N 字节     │ 2字节 │
└──────┴───────┴───────┴───────────────┴──────┘
```

### 起始帧（发送文件名和大小）

```
SOH 00 FF "filename.bin" 00 "131072" 00...00 CRC16
└─── 帧0 ──┴─── 文件名(最长64) ──┴─── 大小(最长64) ──┴─填充0─┘
```

后续帧（数据帧）：
```
STX 01 FE <1024 字节固件数据> CRC16    ← Frame 1
STX 02 FD <1024 字节固件数据> CRC16    ← Frame 2
...
EOT                                    ← 文件结束
ACK                                    ← 接收端确认
                                   
(如果有多文件): 下一个文件的起始帧
(如果无多文件): 第二个 EOT
                                   
SOH 00 FF 00...00 CRC16               ← 结束帧(空文件名)
```

## 接收端实现（Bootloader）

```c
typedef enum {
    YM_IDLE, YM_START, YM_DATA, YM_END
} ymodem_state_t;

int ymodem_receive(uint8_t *buffer, uint32_t max_size)
{
    ymodem_state_t state = YM_IDLE;
    uint32_t bytes_received = 0;

    uart_send_byte('C');  // 发送 CRC 模式请求

    while (1) {
        uint8_t byte = uart_recv_byte(TIMEOUT_1S);
        if (byte == SOH || byte == STX) {
            // 读取帧头: SEQ + ~SEQ
            uint16_t seq = uart_recv_byte(50);
            uint16_t seq_inv = uart_recv_byte(50);
            if ((seq ^ seq_inv) != 0xFF) { uart_send_byte(NAK); continue; }

            // 读取数据
            uint16_t frame_size = (byte == STX) ? 1024 : 128;
            uint8_t data[1024];
            for (int i = 0; i < frame_size; i++)
                data[i] = uart_recv_byte(50);

            // CRC 校验
            uint16_t crc_recv = (uart_recv_byte(50) << 8) | uart_recv_byte(50);
            uint16_t crc_calc = crc16_ccitt(data, frame_size);
            if (crc_recv != crc_calc) { uart_send_byte(NAK); continue; }

            if (seq == 0 && state == YM_IDLE) {
                // 起始帧：解析文件名和大小
                state = YM_START;
                uart_send_byte(ACK);
                uart_send_byte('C');
            } else if (seq > 0) {
                // 数据帧：写入 Flash
                memcpy(buffer + bytes_received, data, frame_size);
                bytes_received += frame_size;
                uart_send_byte(ACK);
            }
        }
        else if (byte == EOT) {
            uart_send_byte(ACK);
            state = YM_END;
            break;
        }
        else if (byte == CAN) return -1;  // 用户取消
    }
    return bytes_received;
}
```

## 协议对比

| 协议 | 帧大小 | 批处理 | CRC | 速率 | 应用 |
|------|--------|--------|-----|------|------|
| Xmodem | 128B | 否 | 1字节和 | 慢 | 遗留系统 |
| Xmodem-CRC | 128B | 否 | CRC-16 | 中等 | 兼容模式 |
| Ymodem | 128/1024B | **是** | CRC-16 | 快 | **Bootloader OTA** |
| Ymodem-G | 1024B(无等待) | 是 | CRC-16 | 最快 | 可靠链路 |
| Zmodem | 可变 | 是 | CRC-32 | 最快(崩溃恢复) | 高速链路 |

**Ymodem vs 其他**：
- 比 Xmodem 快（1024B 大帧）
- 比 Xmodem 好（支持批处理：文件名+大小）
- 比 Zmodem 简单（适合 Bootloader，代码量小）

## 平台差异

| 平台 | UART 接收方式 | 注意事项 |
|------|-------------|---------|
| STM32 HAL | IDLE+DMA 变长接收 | 超时用 TIM 或 DWT，不阻塞 |
| STM32 寄存器 | 轮询 RXNE 标志 | 需精确超时控制 |
| ESP32 | uart_read_bytes | FreeRTOS 下用队列通知 |
| 上位机 Python | `pyserial` + `ymodem` 库 | 使用现成库 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 起始帧不匹配 | CRC 错/帧序号错 | 重发 NAK，最多重试 10 次 |
| 接收超时 | 线不稳定或发送端停止 | 1s 超时重发 NAK，3 次失败则 CAN |
| SEQ 翻转错 | 帧序号累加错误 | 检查 seq 递增逻辑（1~255 翻转）|
| CRC 校验失败 | 数据错位或波特率不稳 | 降低波特率(115200→57600) |
| 文件大小不匹配 | 接收完大小与声明不一致 | 检查 Flash 写入完整性 |

## 边界定义

- **不覆盖** 上位机 Ymodem 发送端（SecureCRT/TeraTerm/自行实现）
- **不覆盖** Flash 写入操作 → 使用 `flash-module`
- **不覆盖** CRC-16 算法实现 → 使用 `crc-module`
- 协议假设串口 8N1 模式
- 不覆盖 Xmodem/Zmodem 协议

## 交接关系

- 上游：`uart-module`（UART 配置：波特率/中断/DMA）
- 上游：`flash-module`（接收固件后的 Flash 写入）
- 上游：`crc-module`（Ymodem 帧 CRC-16 校验算法）
- 集成：`bootloader-design`（Ymodem + Bootloader 完整 OTA 方案）
- 集成：`ota-package`（Ymodem + EEPROM 状态机 OTA 实现参考）
