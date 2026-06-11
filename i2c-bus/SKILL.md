---
name: i2c-bus
description: I2C 总线配置、驱动开发与故障排查。涵盖协议时序详解、STM32 HAL 状态机陷阱与恢复、多从机总线仲裁、时钟延展处理、总线死锁恢复。当用户提到 I2C、IIC、I2C 总线、硬件 I2C、HAL I2C 死锁、I2C 总线恢复、I2C 调试、I2C 从机模式、I2C 时钟延展时使用。
version: "1.0.0"
---

# I2C 总线开发指南

> 总线级别的 I2C 知识与调试技能。
> 与 peripheral-driver（设备驱动开发）互补：peripheral-driver 关注"给挂在 I2C 上的设备写驱动"，
> 本 skill 关注"I2C 总线外设本身的配置、陷阱和调试"。

## 适用场景

- 配置 STM32 I2C 外设（标准/快速/快速+模式，100kHz/400kHz/1MHz）
- 排查 I2C 总线死锁、HAL_I2C_STATE_BUSY 卡死、NACK 风暴
- 设计容错机制（总线恢复、超时、错误重试）
- 多从机总线仲裁、地址冲突排查
- I2C 从机模式开发（事件中断、时钟延展）
- I2C + DMA/IT 模式中的状态机问题
- FreeRTOS 多任务下的 I2C 互斥访问

## 必要输入

- MCU 型号（如 STM32F103、STM32F411、STM32H743）— 不同系列 I2C 外设差异大
- I2C 实例号（I2C1/I2C2/I2C3）
- 目标速率（100kHz / 400kHz / 1MHz）
- 从机设备地址（7bit 或 10bit）
- 引脚分配（SCL/SDA 端口号）

## I2C 协议核心要点

### 帧结构
```
S | 7bit 地址 + R/W | ACK | 数据字节 + ACK/NAK | ... | P
```
- **S** = START 条件（SCL 高电平时 SDA 下降沿）
- **P** = STOP 条件（SCL 高电平时 SDA 上升沿）
- **重复 START (Sr)**：不发送 STOP 直接发新的 START，用于组合读写
- **ACK**：第 9 个时钟，接收方拉低 SDA
- **NAK**：第 9 个时钟，接收方释放 SDA（高电平），通常表示：
  - 从机忙（正处理上次操作）
  - 地址不匹配
  - 数据已接收完毕（主机读最后一个字节后发 NAK 表示结束）

### 速率等级
| 模式 | 最大速率 | SCL 低/高时间 | 上拉电阻参考 |
|------|---------|--------------|------------|
| 标准模式 (Sm) | 100 kHz | 4.7/4.0 μs | 4.7kΩ~10kΩ |
| 快速模式 (Fm) | 400 kHz | 1.3/0.6 μs | 1.5kΩ~4.7kΩ |
| 快速+模式 (Fm+) | 1 MHz | 0.5/0.26 μs | 1kΩ~2.2kΩ |

### 时钟延展 (Clock Stretching)
- 从机可以拉低 SCL 来"刹车"主机，表示自己还没准备好
- STM32 作为从机时：`NoStretchMode = DISABLE`（默认）开启时钟延展
- **如果主机不支持时钟延展**，通信会出错 → 数据丢失或整个总线锁死
- 排查方法：示波器观察 SCL 低电平时间是否异常长

## STM32 HAL I2C 使用指南

### 三种传输模式

| 模式 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| Polling (阻塞) | 代码简单，无需中断 | 阻塞 CPU，不能用于 ISR | 低速、非实时、初始化阶段 |
| IT (中断) | 不阻塞，响应及时 | 需要中断优先级管理 | 常规通信 |
| DMA | 几乎零 CPU 占用 | 需要 DMA 通道，缓存一致性（H7） | 大数据量（>16 字节） |

### API 选择

| 操作 | Polling | IT | DMA |
|------|---------|----|-----|
| 主机写 | `HAL_I2C_Master_Transmit` | `..._IT` | `..._DMA` |
| 主机读 | `HAL_I2C_Master_Receive` | `..._IT` | `..._DMA` |
| 存储器写 | `HAL_I2C_Mem_Write` | `..._IT` | `..._DMA` |
| 存储器读 | `HAL_I2C_Mem_Read` | `..._IT` | `..._DMA` |
| 从机听 | — | `HAL_I2C_EnableListen_IT` | — |
| 设备就绪 | `HAL_I2C_IsDeviceReady` | — | — |

**关键区别**：`Master_Transmit/_Receive` vs `Mem_Write/_Read`
- 前者发送裸数据——用于简单设备（如 IO 扩展器）
- 后者自动处理"设备地址→存储器地址→数据"时序（含重复 START）
- **EEPROM 读写一定用 Mem_Write/Mem_Read**，不要手动拼地址

### 设备就绪轮询（替代 HAL_Delay）

写 EEPROM 等设备时，每次写操作后设备需要时间（5ms）将数据写入内部存储。在此期间设备会 NAK 任何操作。正确做法：

```c
/* 替代 HAL_Delay(10) — 有超时，不盲目等待 */
while (HAL_I2C_IsDeviceReady(&hi2c1, DEV_ADDR, 3, HAL_MAX_DELAY) != HAL_OK) {
    /* 设备忙，重试，最多等 HAL_MAX_DELAY */
}
```

**为什么不能用 HAL_Delay**：
- HAL_Delay(10) 是固定延时，设备可能 2ms 就就绪了，浪费 8ms
- 干扰严重时设备可能需要 15ms，固定延时不够会挂
- `IsDeviceReady` 是"忙等直到就绪"，总时间由设备实际速度决定

## 常见陷阱与解决方案

### HAL I2C 状态机陷阱

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `HAL_I2C_STATE_BUSY` 卡死 | 前一次传输未完成（中断/DMA 回调没调用）就发起新的传输 | 1) 用信号量/标志位跟踪传输完成；2) 不依赖 `HAL_I2C_GetState()` 做任务间同步 |
| `HAL_I2C_STATE_BUSY_RX` | 从机模式下 RX DMA 一直开启，然后试图 TX | 从机 RX 完成后应先发送响应，再重新开启 RX |
| `I2C_WaitOnFlagUntilTimeout` 超时不生效 | `HAL_GetTick()` 在低功耗模式下停止递增 | 1) 改用 RTC 提供 tick；2) 停止模式下用 RTC 闹钟唤醒 |
| `HAL_I2C_ErrorCallback` 一直触发 (AF) | Master 正常通信结束后发 NAK 也会触发 AF 错误 | AF 在 Master 读最后一个字节时是正常现象，不是错误。检查是否应视为正常流程 |
| NAK 标志未清除导致后续通信挂死 | HAL 某版本中 `HAL_I2C_Mem_Write` 未清除 AF 标志 | 手动 `__HAL_I2C_CLEAR_FLAG(hi2c, I2C_FLAG_AF)` |
| 中断永远触发无法退出 | 中断标志在 HAL 状态机不同步时未被清除 | 在中断中检查并清除所有挂起的标志位，必要时软件复位 I2C 外设 |

### 总线死锁与恢复

**死锁场景**：
- 主机复位时 SCL 为高、从机正输出 ACK（拉低 SDA）→ 从机等 SCL 变低释放 SDA，主机等 SDA 变高才继续 → 永久死锁
- 复位后 SDA/SCL 电平组合被误判为 START 条件 → BUSY 位置位

**恢复方法**（软件 9 脉冲法）：

```c
/* I2C 总线恢复：向 SCL 发 9 个脉冲 */
void i2c_bus_recover(I2C_HandleTypeDef *hi2c)
{
    GPIO_InitTypeDef gpio;

    /* 1. DeInit I2C 外设 */
    HAL_I2C_DeInit(hi2c);

    /* 2. SCL 临时配置为推挽输出 */
    gpio.Mode  = GPIO_MODE_OUTPUT_PP;
    gpio.Pull  = GPIO_PULLUP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    gpio.Pin   = I2C_SCL_PIN;
    HAL_GPIO_Init(I2C_SCL_PORT, &gpio);

    /* 3. 发送 9 个 SCL 脉冲 */
    for (int i = 0; i < 9; i++) {
        HAL_GPIO_WritePin(I2C_SCL_PORT, I2C_SCL_PIN, GPIO_PIN_RESET);
        delay_us(5);  // > 4.7μs (100kHz 半周期)
        HAL_GPIO_WritePin(I2C_SCL_PORT, I2C_SCL_PIN, GPIO_PIN_SET);
        delay_us(5);
    }

    /* 4. 产生 STOP 条件：SCL 高时 SDA 上升沿 */
    HAL_GPIO_WritePin(I2C_SDA_PORT, I2C_SDA_PIN, GPIO_PIN_RESET);
    delay_us(5);
    HAL_GPIO_WritePin(I2C_SDA_PORT, I2C_SDA_PIN, GPIO_PIN_SET);
    delay_us(5);

    /* 5. 重新初始化 I2C */
    HAL_I2C_Init(hi2c);
}
```

### FreeRTOS + I2C 死锁

**问题**：HAL I2C Polling 函数内部用 while 轮询等待标志位，在 FreeRTOS 下：
- 任务不主动 yield → 低优先级任务饿死
- 如果每次轮询超时 25ms，且调用频率 50Hz（20ms 间隔），则永远超时 → 永久死锁

**解决方案**：
1. **用 IT/DMA 模式 + 信号量**，不在任务中轮询
2. **I2C 访问用互斥信号量保护**（HAL 非线程安全）
3. 超时时间设置要小于任务调用周期
4. **I2C 中断优先级必须满足 FreeRTOS 要求**（`configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY`）

### 初始化顺序导致 BUSY（经典 Bug）

**现象**：I2C 初始化后一直 BUSY，无法通信。

**根因**：I2C 时钟使能后外设立即开始检测 BUSY。如果此时 SCL/SDA 引脚尚未配置为开漏输出（仍为浮空输入），且无外部上拉，引脚电平为低 → BUSY 位置位。

**修复**：**先配置 GPIO，再使能 I2C 时钟**：

```c
/* 错误顺序 */
__HAL_RCC_I2C1_CLK_ENABLE();       // I2C 时钟先使能
HAL_GPIO_Init(I2C_SCL_PORT, ...);  // GPIO 后配置 → SCL 浮空=低 → BUSY 卡死

/* 正确顺序 */
HAL_GPIO_Init(I2C_SCL_PORT, ...);  // 先配 GPIO，确保引脚电平正确
HAL_GPIO_Init(I2C_SDA_PORT, ...);
__HAL_RCC_I2C1_CLK_ENABLE();       // 再使能 I2C 时钟
```

## 时钟配置

### F1/F3 系列（I2C_CR2 + I2C_CCR）
```c
hi2c1.Init.ClockSpeed = 100000;     // 100 kHz
hi2c1.Init.DutyCycle  = I2C_DUTYCYCLE_2;  // 或 I2C_DUTYCYCLE_16_9
// CCR = APB1 clock / (2 * ClockSpeed)
// DutyCycle=2 时: 36MHz / 200kHz = 180
// DutyCycle=16_9 时用于 400kHz
```

### F4/H7/G0/G4/L4 系列（I2C_TIMINGR）
使用 ST 官方工具 `STM32CubeMX → Tools → I2C Timing Configuration` 生成 TIMINGR 值。

**手动估算**：TIMINGR = `PRESC << 28 | SCLL << 0 | SCLH << 8 | SDADEL << 16 | SCLDEL << 20`
强烈推荐用工具计算，手动极易出错。

## 平台差异速查

| 系列 | I2C 外设版本 | 时序配置 | 已知 HAL Bug |
|------|------------|---------|-------------|
| STM32F1 | V1 | CCR (无 TIMINGR) | 硬件 I2C 有已知 errata（总线仲裁问题），部分场景推荐软件 I2C |
| STM32F4 | V2 | TIMINGR | AF 标志未清除 Bug（见上方） |
| STM32G0/G4 | V2 | TIMINGR | 从机模式下 OVR/欠载问题 |
| STM32H7 | V2 | TIMINGR | Lock/Unlock 竞态（ISR 中检查锁状态），D-Cache 需维护 |
| STM32L0/L4 | V2 | TIMINGR | 从机模式下 RXNE 读取两次的问题 |

## 调试方法

### 示波器/逻辑分析仪测量点
1. **检查 START 条件**：SDA 下降沿必须在 SCL 高电平时
2. **检查 SCL 频率**：实测频率 vs 目标 ±10%
3. **检查 ACK/NAK**：第 9 个时钟 SDA 被拉低（ACK）还是高（NAK）
4. **检查时钟延展**：SCL 低电平是否异常拉长
5. **检查 STOP 条件**：SDA 上升沿必须在 SCL 高电平时

### 寄存器级调试（J-Link/ST-Link halt 时）
```c
/* 读取 I2C 状态寄存器 */
uint32_t sr1 = I2C1->SR1;  // 或 ISR（新系列）
uint32_t sr2 = I2C1->SR2;  // 或 CR2（新系列）

/* 关键位解析 */
// SR1: BUSY(0), MSL(1), SB(3), ADDR(6), BTF(7), TXE(8), RXNE(9), STOPF(10), AF(12)
// SR1 BERR(8), ARLO(9), AF(10), OVR(11), TIMEOUT(14)
```

### 总线扫描
```c
/* 扫描总线上所有活跃设备 */
for (uint8_t addr = 0x01; addr < 0x7F; addr++) {
    if (HAL_I2C_IsDeviceReady(&hi2c1, (uint16_t)(addr << 1), 1, 10) == HAL_OK) {
        printf("I2C device found at 0x%02X\n", addr);
    }
}
```

## 边界定义

### 不该激活
- 用户需要的是给 I2C 设备写驱动（传感器/存储器等）→ 使用 `peripheral-driver`
- 用户需要的是通用 STM32 HAL 开发指导 → 使用 `stm32-hal-development`
- 用户需要的是 CAN/Modbus 等其他总线调试 → 使用 `can-debug` / `modbus-debug`
- 用户使用软件模拟 I2C（GPIO 逐位控制）→ 不适用（本 skill 针对硬件 I2C 外设）

### 不该做
- **禁止**在 I2C 中断回调中调用阻塞式 HAL 函数（`HAL_I2C_Master_Transmit` 等）
- **禁止**在 FreeRTOS 多任务中直接共享 I2C Handle 而不加互斥
- **禁止**将 GPIO 配置为推挽输出模式用于 I2C（必须开漏）

### 不该碰
- **不触碰** CubeMX 生成的 I2C 初始化代码（`.ioc` 修改优先）
- **不触碰**其他 I2C 总线的配置（只关注用户指定的实例）

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | 主机写入 | 主机读取 | 关键差异 |
|------|---------|---------|---------|
| STM32 HAL(v2) | `HAL_I2C_Master_Transmit` | `HAL_I2C_Master_Receive` | TIMINGR 配置(T4+/G0+/H7) |
| STM32 HAL(v1) | 同(函数名同) | 同 | CCR 配置(F1)，BUSY bug |
| STM32 SPL | `I2C_SendData`+状态机 | `I2C_ReceiveData`+状态机 | 软件状态机控制，需事件处理 |
| STM32 寄存器 | 轮询 SR1/SR2/DR | 轮询 SR1/SR2/DR | 手动处理 START/STOP/ACK |
| ESP-IDF | `i2c_master_write_to_device` | `i2c_master_read_from_device` | 命令链表模式，非状态机 |
| GD32 SPL | `i2c_master_write` | `i2c_master_read` | 与 STM32F1 SPL 相近 |

## 交接关系

- 上游：`stm32-hal-development`（HAL 开发规范）
- 下游：`peripheral-driver`（I2C 设备驱动开发）
- 调试时：`serial-monitor`（输出扫描结果/调试日志）

## 参考资料

- [references/i2c-timing-config.md](references/i2c-timing-config.md) — I2C 时序配置详解
- [references/i2c-hal-state-machine.md](references/i2c-hal-state-machine.md) — HAL I2C 状态机与 Bug 汇总
- [references/i2c-errata-workarounds.md](references/i2c-errata-workarounds.md) — STM32 I2C Errata 与解决方案
