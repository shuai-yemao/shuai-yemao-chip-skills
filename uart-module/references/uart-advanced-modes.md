# RS485 / LIN / 多机 / Smartcard / 半双工 / RTO 详解

## RS485 模式

### HAL API

```c
// RS485 初始化（DE 引脚控制）
HAL_RS485Ex_Init(&huart1, UART_RS485_DEPOLARITY_LOW, 0, 0);
```

| 参数 | 说明 |
|------|------|
| `Polarity` | DE 极性：`LOW`=低有效，`HIGH`=高有效（MAX3485 通常是 HIGH） |
| `AssertionTime` | DE 拉高到开始发送的延迟（位时间） |
| `DeassertionTime` | 发送结束到 DE 拉低的延迟（位时间），用于留出最后一帧发送时间 |

### DE 切换时序

```
TX 开始 ──┐
          └─── 数据 ────┐
                        └── TX 结束
DE                    ┌────────────────────┐
──────┘               └────────────────────
                      ↑ AssertionTime      ↑ DeassertionTime
```

**DeassertionTime 最小值**：等于最后一位传输时间（1/baud）。设置过短会导致最后一个字节被截断。

### RS485 芯片常见搭配

| 芯片 | 工作电压 | 速率 | DE 极性 | 终端电阻 |
|------|---------|------|---------|---------|
| MAX3485 | 3.3V | 10 Mbps | HIGH | 120Ω |
| MAX485 | 5V | 2.5 Mbps | HIGH | 120Ω |
| SP3485 | 3.3V | 10 Mbps | HIGH | 120Ω |

## LIN 模式

### LIN 帧结构
```
间隔场 (13+ 位低电平) | 同步场 (0x55) | 标识符 (PID) | 数据 (1~8字节) | 校验和
```

### STM32 LIN 配置

```c
// 主机
HAL_LIN_Init(&huart1, LIN_BREAKDETECTIONLENGTH_10B);
HAL_LIN_SendBreak(&huart1);  // 发送间隔场 → 唤醒总线

// 从机：自动检测间隔场唤醒
void HAL_UARTEx_WakeupCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        // LIN 唤醒，开启接收
        HAL_UART_Receive_IT(huart, rx_buf, 1);
    }
}
```

**注意**：LIN 的间隔场检测要求 USART 支持断点检测（Break Detection），ST 的标准 USART（非 UART）都支持。如果使用 UART（无 USART），则无法从硬件层面检测间隔场。

## 多机通信

### 原理

多个从机共享一条 UART 总线，通过地址字节寻址：

```
主机: [地址帧: addr=0x01] [数据帧: cmd=0xA5] [数据帧: data=0x42] ...
从机1: 收到地址 0x01 → 匹配 → 继续接收后续数据帧
从机2: 收到地址 0x01 → 不匹配 → 进入静默模式（忽略后续数据）
```

### 配置

```c
/* 从机：使能静默模式 + 地址匹配 */
huart1.Init.WordLength = UART_WORDLENGTH_9B;    // 第 9 位 = 地址/数据标志位

// 地址匹配接收（第 9 位 = 1 时触发）
HAL_MultiProcessor_EnterMuteMode(&huart1);       // 进入静默模式
// 收到地址帧第 9 位 = 1 → 如果地址匹配，自动退出静默模式
// 不匹配 → 保持静默（数据帧被硬件丢弃）

// 匹配后开始接收数据（第 9 位 = 0 的数据帧）
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        if (received_address_matches) {
            // 处理数据
        }
    }
}
```

## Smartcard 模式 (ISO 7816)

### 特性

- 半双工通信
- 字符帧格式：1 起始位 + 8 数据位 + 1 校验位 + 1 保护时间位 = 11 位
- 需要额外的时钟输出（CK 引脚）
- 带 NACK 重传协议

### 配置

```c
// CubeMX: USARTx → Mode → Smartcard
huart1.Init.WordLength = UART_WORDLENGTH_9B;       // 8 数据 + 1 奇偶校验
huart1.Init.Parity = UART_PARITY_EVEN;              // 偶校验
huart1.Init.StopBits = UART_STOPBITS_1_5;           // 1.5 停止位（Smartcard 要求）
HAL_SMARTCARD_Init(&huart1);
```

## 半双工模式

### 配置

```c
// CubeMX: USARTx → Mode → Half-Duplex (Single Wire)
// TX 和 RX 复用同一个引脚
huart1.Init.Mode = UART_MODE_TX_RX;
HAL_HalfDuplex_Init(&huart1);  // 初始化半双工

// 发送（切为发送模式）
HAL_HalfDuplex_EnableTransmitter(&huart1);
HAL_UART_Transmit(&huart1, data, len, timeout);

// 接收（切为接收模式）
HAL_HalfDuplex_EnableReceiver(&huart1);
HAL_UART_Receive(&huart1, data, len, timeout);
```

**注意**：半双工模式下 TX/RX 共用引脚，需要外部上拉电阻。切换方向后需要留出总线释放时间。

## RTO (Receive Timeout) 模式

### 与 IDLE 的对比

| 特性 | IDLE 中断 | RTO (Receive Timeout) |
|------|----------|----------------------|
| 检测依据 | RX 线空闲（高电平） | 停止位之后无新数据 |
| 可配置超时 | 否（固定 1 位时间） | 是（可设任意位时间） |
| 噪声误触发 | 可能（RX 线浮空/噪声被当成空闲） | 不易 |
| 可用系列 | F1/F4/G0/G4/H7 | G0/G4/H7/U5 |

### RTO 配置

```c
// STM32H7 / G4 : 配置 RTO 超时
// RTO 以位时间为单位
huart1.Init.RTOAutoReload = UART_RTO_ENABLE;   // 自动重载
__HAL_RTO_ENABLE(&huart1);                      // 使能 RTO
SET_BIT(huart1.Instance->CR2, USART_CR2_RTOEN); // 寄存器级

// 设超时时间 = 20 位时间（波特率 115200 时 ≈ 174μs）
WRITE_REG(huart1.Instance->RTOR, 20);

// RTO 回调
void HAL_UARTEx_RtoCallback(UART_HandleTypeDef *huart)
{
    // 超时触发 → 数据包接收完成
    // 与 IDLE 不同，RTO 不会自动重启接收
}
```

**RTO 替代 IDLE 的优势**：IDLE 检测的是 RX 线逻辑电平的空闲（高电平持续一个帧时间），而 RTO 检测的是停止位之后无新字节。在噪声环境下，IDLE 可能因 RX 线上的毛刺被误触发，而 RTO 不会。
