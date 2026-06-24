---
name: uart-module
description: STM32 UART/USART 串口通信配置、开发与故障排查。涵盖波特率计算与误差分析、USART vs UART 架构差异、RS485/DE 控制、LIN/多机/Smartcard 模式、硬件流控、DMA 双缓冲、printf 重定向、IDLE/ RTO 变长接收、错误恢复。当用户提到串口、UART、USART、RS232、RS485、串口通信、printf 重定向、串口 DMA、串口中断、波特率、流控、LIN 总线、多机通信、Smartcard、半双工串口时使用。
version: "1.0.0"
---

# STM32 UART 开发指南

> UART 是嵌入式世界最基础也最常用的通信接口。
> 与 stm32-hal-development（HAL API 参考 + DMA+IDLE 诊断）互补：本 skill 覆盖 UART 独有的
> 波特率计算、高级模式（RS485/LIN/多机/Smartcard）、printf 重定向、错误恢复和平台差异。

## 适用场景

- UART 基本收发（Polling/IT/DMA 模式选择）
- 波特率计算与误差分析（含非标准波特率）
- RS485 模式（DE 使能时序、半双工总线控制）
- LIN 总线通信（帧格式/休眠/唤醒）
- 多机通信（地址匹配、静默模式、静默唤醒）
- Smartcard (ISO 7816) 接口
- 硬件流控（RTS/CTS）
- 半双工单线模式
- DMA 双缓冲 + IDLE 变长接收（参考 stm32-hal-development 诊断）
- Printf 重定向（四种方式对比）
- 串口通信异常诊断（ORE/FE/NE/NF 错误恢复）

## 必要输入

- MCU 型号（决定 USART 版本和波特率上限）
- USART/UART 实例（如 USART1, USART2, LPUART1）
- 目标波特率
- 数据帧格式（8N1/8E1/8O1/9N1 等）
- 工作模式（标准/RS485/LIN/多机/Smartcard/半双工）
- 引脚分配（TX/RX 及可选的 RTS/CTS/DE）

## USART vs UART 架构

| 特性 | USART | UART | LPUART |
|------|-------|------|--------|
| 全称 | Universal Sync/Async Receiver Transmitter | Universal Async Receiver Transmitter | Low Power UART |
| 同步模式 | ✅ 支持（输出时钟 CK 引脚） | ❌ | ❌ |
| 异步模式 | ✅ | ✅ | ✅ |
| LIN 支持 | ✅ | ❌ | ❌ |
| Smartcard | ✅ | ❌ | ❌ |
| IrDA | ✅ | ❌ | ❌ |
| RS485/DE | ✅（HAL_RS485Ex） | ❌ | ❌ |
| 多机通信 | ✅ | ✅（基础） | ✅ |
| 时钟源 | PCLK（通常 50~100MHz） | PCLK | LSE/LSI（低功耗下工作） |
| 最大波特率 | PCLK / 8（OVER8） | PCLK / 16 | 取决于时钟源 |

**实用结论**：USART 是 UART 的超集。在 CubeMX 中选 USART 但只做异步通信时，等同于 UART。

## 波特率计算

### 公式

```
USARTDIV = fCK / (16 × OVER8 × BaudRate)

当 OVER8 = 1 (OVER16):  OVER8 = 1，除 16
当 OVER8 = 0 (OVER8):   OVER8 = 0.5，除 8
```

`BRR` 寄存器写入值：
```
OVER16: BRR = DIV_Mantissa × 16 + DIV_Fraction[3:0]
OVER8:  BRR = DIV_Mantissa × 8  + DIV_Fraction[3:1]（最低位不可用）
```

### 常用波特率整数分频表（fCK=80MHz, OVER16）

| 目标波特率 | USARTDIV | 实际 BRR | 实际波特率 | 误差 |
|-----------|---------|---------|-----------|------|
| 9600 | 520.833 | 520 + 13/16 = 520.8125 | 9599 | **-0.01%** ✅ |
| 19200 | 260.417 | 260 + 7/16 = 260.4375 | 19192 | -0.04% ✅ |
| 38400 | 130.208 | 130 + 3/16 = 130.1875 | 38401 | +0.003% ✅ |
| 57600 | 86.806 | 86 + 13/16 = 86.8125 | 57581 | -0.04% ✅ |
| 115200 | 43.403 | 43 + 6/16 = 43.375 | 115274 | -0.11% ✅ |
| 230400 | 21.701 | 21 + 11/16 = 21.6875 | 230466 | +0.03% ✅ |
| 460800 | 10.851 | 10 + 14/16 = 10.875 | 459770 | -0.22% ✅ |
| 921600 | 5.425 | 5 + 7/16 = 5.4375 | 919540 | -0.22% ✅ |
| 2 Mbps | 2.5 | 2 + 8/16 = 2.5 | 2,000,000 | **0%** ✅ |

**关键判断**：误差 < ±2% 时可正常工作；误差 > ±3% 会导致乱码。

**非标准波特率验证**：
```c
// 验证给定 fCK 下目标波特率的可行性
bool validate_baudrate(uint32_t fck, uint32_t target_bps)
{
    float usartdiv = (float)fck / 16.0f / target_bps;
    uint16_t mantissa = (uint16_t)usartdiv;
    uint16_t fraction = (uint16_t)((usartdiv - mantissa) * 16.0f + 0.5f);
    float actual = (float)fck / 16.0f / (mantissa + fraction / 16.0f);
    float error = (actual - target_bps) / target_bps * 100.0f;
    return (error >= -2.0f && error <= 2.0f);
}
```

### OVER8 模式（高速场景）

当波特率 > fCK/16 时，必须启用 OVER8：

```c
// STM32F4: fCK=84MHz, 需要 10.5Mbps
// OVER16 时最大: 84M/16 = 5.25Mbps → 不够
// OVER8 时最大: 84M/8 = 10.5Mbps → 刚好

huart1.Init.OverSampling = UART_OVERSAMPLING_8;  // 启用 OVER8
```

| 目标波特率 | fCK | 模式 | USARTDIV | 误差 |
|-----------|-----|------|---------|------|
| 10.5 Mbps | 84MHz | OVER8 | 8.0 | **0%** ✅ |
| 7 Mbps | 84MHz | OVER8 | 12.0 | **0%** ✅ |
| 4 Mbps | 84MHz | OVER16 | 13.125 | 0% ✅ |
| 12 Mbps | 100MHz | OVER8 | 8.333 | 0% ✅ |

## 数据帧格式

### 常用格式对照

| 格式 | 数据位 | 校验 | 停止位 | 应用场景 |
|------|--------|------|--------|---------|
| 8N1 | 8 | 无 | 1 | 最常用、printf、GPS |
| 8E1 | 8 | 偶校验 | 1 | Modbus RTU |
| 8O1 | 8 | 奇校验 | 1 | 部分工业设备 |
| 9N1 | 9 | 无 | 1 | 多机通信（地址位） |
| 7E1 | 7 | 偶校验 | 1 | 老式 ASCII 终端 |
| 8N2 | 8 | 无 | 2 | 慢速、噪声环境 |

### 配置代码

```c
huart1.Init.WordLength = UART_WORDLENGTH_8B;        // 8 数据位
huart1.Init.StopBits   = UART_STOPBITS_1;            // 1 停止位
huart1.Init.Parity     = UART_PARITY_NONE;           // 无校验
huart1.Init.HwFlowCtl  = UART_HWCONTROL_NONE;        // 无流控
huart1.Init.Mode       = UART_MODE_TX_RX;            // 收发都开
huart1.Init.BaudRate   = 115200;
huart1.Init.OverSampling = UART_OVERSAMPLING_16;
HAL_UART_Init(&huart1);
```

**注意**：使能校验（Parity）后，数据位实际变为 WordLength - 1。例如 `WORDLENGTH_9B + PARITY_ENABLE` → 8 数据位 + 1 校验位。

## API 使用指南

### 三种模式选型

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| Polling | 简单同步 | 阻塞 CPU，不能用于 ISR | 调试打印、初始化阶段 |
| IT | 不阻塞，按字节中断 | 每字节一次中断，高波特率时压力大 | 常规通信（< 115200） |
| DMA | 零 CPU 占用 | 需 DMA 通道，缓冲区管理复杂 | 高速（> 115200）、大数据量 |

### 何时用 __HAL_UART_CLEAR_IDLEFLAG

DMA+IDLE 变长接收的详细诊断参考 [stm32-hal-development/references/troubleshooting-guide.md](/references/troubleshooting-guide.md) 第 6b 节。
本 skill 只补充关键点：

```c
// STM32 上电后 IDLE 标志默认 = 1
// 必须在启动 DMA 接收前清除一次
__HAL_UART_CLEAR_IDLEFLAG(&huart1);
HAL_UARTEx_ReceiveToIdle_DMA(&huart1, buf, buf_len);
```

### IDLE vs RTO（新系列）

| 系列 | 变长接收手段 | 备注 |
|------|------------|------|
| STM32F1/F4 | IDLE 中断 | 传统方式，清 IDLE 标志 |
| STM32G0/G4 | IDLE + RTO | IDLE 可用，RTO 更精确 |
| STM32H7 | **RTO**（推荐） | IDLE 仍然可用，但 RTO 可配置超时时间 |
| STM32U5 | RTO | IDLE 已弃用 |

RTO 配置（H7/G4）：
```c
// RTO: 最后一位停止位之后等待指定时间触发超时
// 比 IDLE 更可靠（IDLE 检测的是 RX 线空闲，RTO 检测的是停止位后无数据）
huart1.Init.RTOAutoReload   = UART_RTO_ENABLE;
__HAL_RTO_ENABLE(&huart1);
WRITE_REG(huart1.Instance->RTOR, target_time_in_bits);  // 以位时间为单位
```

## 高级模式

### RS485 / DE 控制

```c
/* RS485 模式：DE (Driver Enable) 引脚控制发送使能 */
// CubeMX: USARTx → Mode → RS485
// DE 引脚通常接 MAX3485 的 RE/DE 脚（2->3 方向控制）

huart1.Init.Mode          = UART_MODE_TX_RX;
huart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_RS485_DEINIT;
huart1.AdvancedInit.RS485DEInit    = UART_ADVFEATURE_DEINIT;
// 或通过 HAL_RS485Ex 接口
HAL_RS485Ex_Init(&huart1, UART_RS485_DEPOLARITY_LOW, 0, 0);
```

**DE 使能时序陷阱**：RS485 芯片从发送切换到接收需要时间，DE 拉低后不能立即开始接收。建议在 DE 拉低后插入 `tDE_to_RX` 延时（通常 1~3 位时间）。

### LIN 模式

```c
/* LIN 总线配置 */
huart1.Init.Mode = UART_MODE_TX_RX;
HAL_LIN_Init(&huart1, LIN_BREAKDETECTIONLENGTH_10B);  // 10 位间隔场

void HAL_LIN_SendBreak(&huart1);  // 发送间隔场

/* LIN 从机：接收间隔场 → 自动唤醒 */
void HAL_UARTEx_WakeupCallback(UART_HandleTypeDef *huart) {
    // LIN 总线唤醒
}
```

### 多机通信（地址匹配）

```c
/* USART 多机模式：主机发送地址字节做同步字段 */
// 配置：9 位数据模式，第 9 位 = 1 表示地址帧，= 0 表示数据帧
huart1.Init.WordLength   = UART_WORDLENGTH_9B;
huart1.Init.Parity       = UART_PARITY_NONE;
// 多机模式下，从机在静默模式下不接收数据帧，只接收地址帧
__HAL_UART_MUTE_ENABLE(&huart1); // 使能从机静默模式
// 当收到匹配的地址时，静默模式自动关闭
```

### 硬件流控

```c
// RTS：请求发送（当接收缓冲区快满时拉低通知对方暂停）
// CTS：清除发送（对方拉低时本机暂停发送）
huart1.Init.HwFlowCtl = UART_HWCONTROL_RTS_CTS;

/* 最佳实践 */
// 1. 启用流控的双方必须同时启用
// 2. CTS/RTS 引脚必须正确连接
// 3. 高波特率（> 1Mbps）时强烈建议启用流控
```

## Printf 重定向（四种方式对比）

| 方式 | 原理 | 速度 | 占用 | 适用 |
|------|------|------|------|------|
| **半主机 (Semihosting)** | 通过调试器 JTAG/SWD 输出 | 慢 (~10KB/s) | 阻塞 | 调试阶段 |
| **Syscall (`_write`)** | 重定向 `_write()` 到 UART | 中等 | 可用 IT/DMA | 通用，推荐 |
| **ITM (Instrumentation Trace)** | SWO 引脚输出 | 快 (~1MB/s) | 非阻塞 | 需要 SWO 引脚（SWD） |
| **DMA 后台打印** | DMA 循环队列 + 空闲时刷 | 最快 | 非阻塞 | 生产环境，高性能 |

### Syscall 重定向（最常用）

```c
// 用于 ARM GCC / ARMCC
int _write(int file, char *ptr, int len)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)ptr, len, 1000);
    return len;
}

// 注意：HAL_UART_Transmit 是阻塞的！
// 如果中断或 DMA 模式下 printf 会影响实时性，改用 IT/DMA 版本
```

### 非阻塞 DMA 打印（环形缓冲）

```c
/* DMA 循环缓冲 + 空闲时发送 — 不阻塞主循环 */
#define PRINTF_BUF_SIZE  256
static uint8_t printf_buf[PRINTF_BUF_SIZE];
static uint16_t printf_head = 0, printf_tail = 0;

void dma_printf(const char *fmt, ...)
{
    va_list args;
    va_start(args, fmt);
    int len = vsnprintf((char*)printf_buf, PRINTF_BUF_SIZE, fmt, args);
    va_end(args);
    
    // 简单轮询发送（或用队列）
    HAL_UART_Transmit_DMA(&huart1, printf_buf, len);
    // 注意：多任务下需要互斥保护
}
```

## 常见陷阱与解决方案

### 1. 串口乱码 | 波特率误差 > ±2%

**诊断**：
```c
// 读取实际 BRR 值反推波特率
uint32_t brr = USART1->BRR;
uint32_t mantissa = brr >> 4;
uint32_t fraction = brr & 0x0F;
float actual = (float)fck / 16.0f / (mantissa + fraction / 16.0f);
```

**解决**：调整 fCK 或选择更低误差的整数分频。

### 2. TXC 标志未清除导致首次发送失败

**现象**：系统初始化后的第一次 `HAL_UART_Transmit` 超时。

**根因**：上电后 TC 位默认为 1，HAL 发送前等待 TC=0 可能超时。

**修复**：
```c
// 在初始化后、首次发送前清 TC
__HAL_UART_CLEAR_FLAG(&huart1, UART_FLAG_TC);
```

### 3. ORE (OverRun Error) 后死锁

**现象**：接收中断不再触发，系统看起来正常但串口收不到数据。

**根因**：HAL 检测到 ORE 后会调用 `HAL_UART_ErrorCallback`，如果回调中没处理，状态机卡死。

**修复**：
```c
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    uint32_t sr = huart->Instance->SR;   // F4/G4: ORE(3), FE(1), NE(2)
    if (sr & USART_SR_ORE) {
        // 读 DR 清除 ORE
        (void)huart->Instance->DR;
        // 重启接收
        HAL_UART_Receive_IT(huart, rx_buf, 1);
    }
    if (sr & USART_SR_FE) {
        // 帧错误：检查波特率、接线
    }
}
```

### 4. ISR 中调用阻塞 HAL 函数

**根因**：`HAL_UART_RxCpltCallback` 在中断上下文中运行。在其中调用 `HAL_UART_Transmit(..., HAL_MAX_DELAY)` 会导致死锁（HAL 状态机污染）。

**修复**：ISR 中只置标志位，实际数据在任务/主循环中处理。

### 5. DMA 接收缓冲区全 0x00

**诊断和修复**：见 [stm32-hal-development/references/troubleshooting-guide.md#6b-uart-dma--idle-变长接收专篇]

## 平台差异速查

| 系列 | USART 版本 | 最大波特率 (OVER16) | LPUART | 特色 |
|------|----------|-------------------|--------|------|
| STM32F1 | V1 | 4.5 Mbps (72MHz/16) | 无 | 无 RTO，只能用 IDLE |
| STM32F4 | V2 | 5.25 Mbps (84MHz/16) | 无 | 无 RTO |
| STM32G0 | V3 | 3.125 Mbps (50MHz/16) | ✅ | 支持 RTO |
| STM32G4 | V3 | 4.375 Mbps (70MHz/16) | ✅ | RTO, 硬件 FIFO |
| STM32H7 | V3 | 7.5 Mbps (120MHz/16) | ✅ | RTO, 硬件 FIFO, 8/16 深 |
| STM32U5 | V3 | 若干 | ✅ | RTO, LPUART 支持 LSE/LSI |

## 调试方法

### 寄存器级检查（J-Link halt 时）
```c
// USART 状态寄存器
uint32_t sr  = USART1->SR;   // F4: TXE(7), TC(6), RXNE(5), IDLE(4), ORE(3), FE(1), NE(2)
uint32_t dr  = USART1->DR;   // 读取会消费数据并清除 RXNE
uint32_t brr = USART1->BRR;  // 读出当前波特率分频值

// 诊断 RXNE 无响应
if (!(sr & USART_SR_RXNE) && !(sr & USART_SR_IDLE)) {
    // 线上没数据——示波器挂 RX 引脚确认
}

// 诊断 ORE 是否被忽略
if (sr & USART_SR_ORE) {
    printf("Overrun error detected! Read DR to clear.\n");
    (void)USART1->DR;   // 清除 ORE
}
```

### 回环测试（验证硬件通路）
```c
// 短路 TX 和 RX 引脚后执行
uint8_t tx_test = 0xA5;
uint8_t rx_test = 0x00;
HAL_UART_Transmit(&huart1, &tx_test, 1, 100);
HAL_StatusTypeDef ret = HAL_UART_Receive(&huart1, &rx_test, 1, 100);
// ret = HAL_OK, rx_test = 0xA5 → 硬件通路正常
```

## 边界定义

### 不该激活
- 用户需要的是串口监控/日志捕获 → 使用 `serial-monitor`（工具 Skill）
- 用户需要的是 Modbus 协议调试 → 使用 `modbus-debug`
- 用户需要的是 CAN 通信 → 使用 `can-debug`
- 用户需要的是通用 STM32 HAL 开发指导 → 使用 `stm32-hal-development`
- 用户只需要 DMA+IDLE 的诊断 → 使用 `stm32-hal-development` troubleshooting 第 6b 节

### 不该做
- **禁止**在 UART 中断回调中调用阻塞式 `HAL_UART_Transmit` / `HAL_Delay`
- **禁止**ISR 回调中直接调用 `HAL_UART_Transmit`（状态机污染）
- **禁止**未处理 ORE 错误（ORE 会导致 UART 永久停收）

### 不该碰
- **不触碰** CubeMX 生成的 USART 初始化代码
- **不触碰** DMA 通道分配（CubeMX 自动处理）
- **不触碰**中断优先级分组

## 平台差异

各 MCU 平台 UART 操作方式的等效映射见 `chip-architecture`（MCU 架构对比中央参考）。

| 平台 | 发送 API | 接收 API | 波特率配置 |
|------|---------|---------|----------|
| STM32 HAL | `HAL_UART_Transmit` | `HAL_UART_Receive` | `PCLK/(16*UBRR)` 或 `PCLK/(8*UBRR)`(OVER8) |
| STM32 SPL | `USART_SendData` | `USART_ReceiveData` | 同 HAL，需手动轮询 `USART_SR` |
| STM32 寄存器 | `USART1->DR = data` | `data = USART1->DR` | 查 RM 对应系列 |
| ESP-IDF | `uart_write_bytes` | `uart_read_bytes` | `uart_param_config` 自动设置 |
| Arduino | `Serial1.write(buf, len)` | `Serial1.read()` | `Serial1.begin(baud)` |
| GD32 | `usart_data_transmit` | `usart_data_receive` | 与 STM32F1 类似 |

## 交接关系
- 下游：`modbus-debug`（Modbus RTU 通过 UART 通信）
- 同层：`i2c-bus` / `spi-bus` / `adc-module` / `timer-module`（同为外设配置+调试类 Skill）
- 调试时：`serial-monitor`（串口日志捕获工具）

## 参考资料

- [references/uart-advanced-modes.md](references/uart-advanced-modes.md) — RS485/LIN/多机/Smartcard/半双工/RTO 详解
- [references/uart-baudrate-config.md](references/uart-baudrate-config.md) — 波特率计算表与误差分析
