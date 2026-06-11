# STM32 HAL 故障排查指南

> 常见问题、症状及解决方案

## 快速诊断流程

```
硬件不工作？
    ↓
时钟是否启用？ → CubeMX 检查
    ↓ ✓
引脚是否正确？ → CubeMX 检查
    ↓ ✓
初始化是否调用？ → main.c 检查
    ↓ ✓
返回值检查？ → 添加错误处理
    ↓ ✓
中断是否启用？ → NVIC 配置
```

## 常见问题分类

### 0. STM32F1 GPIO 内部上拉不生效

**症状：**
- GPIO 配置为 `GPIO_PULLUP`，但引脚电平始终为低
- 读取 GPIO_CRL 寄存器显示 `0x44444444`（浮空输入）
- 外接下拉电阻后读数为 0，上拉后读数不稳定

**根因：**
STM32F1 的 `HAL_GPIO_Init` 对 CRL/CRH 寄存器的写入存在缺陷——配置 `GPIO_PULLUP` 时，CNF 位未被正确置位为 `10`（上拉/下拉输入），实际写入的是 `01`（浮空输入）。

**修复方法（直接写寄存器，绕过 HAL）：**
```c
// 配置为输入 + 内部上拉
// CRL: 每引脚 4bit, CNF[3:2]=10(上拉/下拉), MODE[1:0]=00(输入)
uint32_t bit_pos, tmp = pin;
for (bit_pos = 0; tmp > 1; tmp >>= 1) bit_pos++;
port->BSRR = pin;  // ODR=1 -> 上拉方向
port->CRL = (port->CRL & ~(0x0F << (bit_pos*4))) | (0x08 << (bit_pos*4));
// 0x08 = CNF=10 + MODE=00
```

**注意：** 此方法仅适用于 STM32F1 系列（Cortex-M3）。F4/F7/H7 的 GPIO 寄存器架构不同，HAL 对该系列的上拉配置工作正常。F1 系列推荐在 BSP 层封装此操作为 `BSP_GPIO_InputPullUp()` 函数。

**参考：** RM0008 Rev 21, Section 8.2.2 "Input configuration"

---

### 1. 外设完全无响应

**症状：**
- 调用 HAL 函数后无任何反应
- GPIO 状态不改变
- 通信接口无输出

**检查清单：**
- [ ] **时钟未启用**：在 CubeMX 中检查外设时钟是否启用
- [ ] **引脚配置错误**：检查引脚模式、复用功能设置
- [ ] **初始化未调用**：在 `main.c` 的 `USER CODE BEGIN 2` 中检查
- [ ] **句柄指针错误**：确保使用 `&huart1`, `&hspi1` 等正确指针

**示例修复：**
```c
// 在 USER CODE BEGIN 2 中添加
/* USER CODE BEGIN 2 */
MX_USART1_UART_Init();  // 确保 UART 初始化被调用
/* USER CODE END 2 */
```

---

### 2. 中断不触发

**症状：**
- 中断服务函数从未执行
- 使用 `HAL_..._IT` 函数但回调不调用

**检查清单：**
- [ ] **NVIC 未启用**：在 CubeMX 中检查 NVIC Settings
- [ ] **中断优先级**：优先级配置是否合理
- [ ] **中断函数名错误**：IRQ Handler 名称必须与启动文件一致（如 `USART1_IRQHandler`），注意不要与 HAL 回调（如 `HAL_UART_RxCpltCallback`）混淆
- [ ] **IT 函数未调用**：需要先调用 `HAL_..._Start_IT`

**常见错误：**
```c
// ❌ 错误：中断函数名拼写错误（必须与 startup_stm32*.s 中一致）
void Usart1_IRQHandler(void) {  // 错误！大小写不对，应为 USART1_IRQHandler
    HAL_UART_IRQHandler(&huart1);
}

// ❌ 错误：忘记调用 IT 启动函数
void main(void) {
  // ...
  HAL_UART_Receive(&huart1, data, len, 1000);  // 错误！应该是 _IT
}

// ✅ 正确
void main(void) {
  // ...
  HAL_UART_Receive_IT(&huart1, data, len);  // 正确
}
```

---

### 3. DMA 不工作

**症状：**
- DMA 传输启动后无数据传输
- 传输完成后回调不触发

**检查清单：**
- [ ] **DMA 时钟未启用**：在 CubeMX 中检查 DMA 时钟
- [ ] **缓冲区对齐**：DMA 缓冲区通常需要 4 字节对齐
- [ ] **缓冲区生命周期**：缓冲区必须是全局或静态变量
- [ ] **DMA 通道冲突**：多个外设使用同一 DMA 通道
- [ ] **DMA 流/通道配置**：检查请求映射是否正确

**示例错误：**
```c
// ❌ 错误：局部数组，函数返回后内存释放
void start_dma_wrong(void) {
    uint8_t buffer[64];  // 局部变量！
    HAL_UART_Transmit_DMA(&huart1, buffer, 64);  // 错误！
}

// ✅ 正确：静态或全局数组
static uint8_t dmaBuffer[64];  // 静态变量

void start_dma_correct(void) {
    HAL_UART_Transmit_DMA(&huart1, dmaBuffer, 64);  // 正确
}
```

---

### 4. 随机崩溃 / 硬故障

**症状：**
- 程序随机进入 `HardFault_Handler`
- 复位或重启
- 栈指针异常

**检查清单：**
- [ ] **栈溢出**：增加栈大小（在 .ioc 文件中配置）
- [ ] **数组越界**：检查所有数组访问
- [ ] **空指针**：检查指针是否为 NULL
- [ ] **中断中浮点运算**：Cortex-M3 无硬件 FPU，浮点由软件库实现，速度慢且消耗大量栈空间
- [ ] **大栈数组**：ISR 中不应有大数组

**调试方法：**
```c
// 在 HardFault_Handler 中添加断点查看故障地址
void HardFault_Handler(void)
{
    __disable_irq();
    while (1)
    {
        // 在此处设置断点，查看调用栈
        // 检查：LR (R14), MSP, PSP
    }
}
```

---

### 5. 时序问题 / 竞争条件

**症状：**
- 偶发性错误
- 高速运行时出错，低速时正常
- 使用调试器时问题消失

**检查清单：**
- [ ] **共享数据未保护**：中断和主循环共享变量需保护
- [ ] **中断优先级倒置**：高优先级中断等待低优先级资源
- [ ] **重新使能中断**：在 `HAL_..._IRQHandler` 之后 HAL 会重新使能中断

**修复共享数据竞争：**
```c
// ❌ 错误：无保护
volatile uint32_t counter = 0;

void EXTI0_IRQHandler(void) {
    counter++;  // ISR 中对 counter 的单次自增在 Cortex-M3 上不是原子的（读-改-写）
}

// ✅ 正确：在主循环侧保护共享变量
volatile uint32_t counter = 0;

void EXTI0_IRQHandler(void) {
    counter++;  // ISR 中无需 disable_irq，因为同优先级中断不会嵌套
}

void main_loop(void) {
    __disable_irq();
    uint32_t local = counter;  // 主循环读取时需要保护，防止被 ISR 打断
    __enable_irq();
}
```

---

### 6. UART 通信问题

**症状：**
- 接收到错误数据
- 丢失数据
- 只收到第一个字节

**常见原因：**
| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 乱码 | 波特率不匹配 | 检查双方波特率配置 |
| 只收到首字节 | 中断模式未重启接收 | 在回调中再次调用 `HAL_UART_Receive_IT` |
| 数据丢失 | 波特率太高 | 降低波特率或使用 DMA |
| 无数据 | TX/RX 引脚反接 | 检查硬件连接 |

**接收重启示例：**
```c
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        // 处理接收到的数据
        process_data(rx_buffer);

        // 重启接收（关键！）
        HAL_UART_Receive_IT(&huart1, rx_buffer, RX_SIZE);
    }
}
```

### 6b. UART DMA + IDLE 变长接收专篇

**症状 A：DMA 中断能进入，但接收缓冲区全为 0x00**

| 诊断步骤 | 命令/检查 | 判断 |
|---------|----------|------|
| 1. 读回调 Size | 在 `HAL_UARTEx_RxEventCallback` 中打印 Size | Size=0 → IDLE 预设问题；Size>0 但 buf=0x00 → 物理层问题 |
| 2. 读 USART_SR | `huart->Instance->SR & 0xFF` | FE=1 → RX 线电平异常/噪声/Break |
| 3. 示波器挂 RX 引脚 | 观察 PA3/PB7 波形 | 持续低电平 → 从机未发送；噪声毛刺 → 浮空 |
| 4. 示波器挂 TX 引脚 | 观察 PA2/PB6 波形 | TX 引脚有波形但接收 0x00 → 从机问题；TX 无波形 → 本机 TX 故障 |

**根因①：USART_SR.IDLE 上电默认=1 → 启动 DMA 立即触发 Size=0 回调**

```c
// ❌ 错误：DMA 启动时 IDLE 已置位，HAL 立即回调 Size=0
HAL_UARTEx_ReceiveToIdle_DMA(&huart, buf, len);

// ✅ 正确：先清 IDLE 再启动
__HAL_UART_CLEAR_IDLEFLAG(&huart);
HAL_UARTEx_ReceiveToIdle_DMA(&huart, buf, len);
```

**根因②：ISR 回调中调用阻塞 HAL 函数 → HAL 状态机卡死**

```c
// ❌ 严重错误：HAL_UARTEx_RxEventCallback 在 USART 中断上下文中运行
//    不得在其中调用任何阻塞 HAL 函数（HAL_UART_Transmit, HAL_Delay 等）
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    UART_Printf(&huart1, "got %u bytes\r\n", Size);  // 阻塞发送！状态机污染！
}

// ✅ 正确：ISR 只置标记，任务/主循环消费
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (Size > 0) {
        dbg_size = Size;
        dbg_sr   = (uint8_t)(huart->Instance->SR);
        dbg_flag = 1;  // 仅置标记
    }
    usart.rx_ready = 1;
    // 重启 DMA
    __HAL_UART_CLEAR_IDLEFLAG(huart);
    HAL_UARTEx_ReceiveToIdle_DMA(huart, buf, len);
}
```

**根因③：HAL_UART_Transmit 返回 HAL_OK 但 TX 引脚实际输出 0x00**

```c
// HAL 阻塞发送只检查 TXE/TC 寄存器标志，不检测引脚电平
// 如果 TX 引脚硬件故障（短路、虚焊、IO 损坏），函数仍返回成功
//
// 诊断：示波器挂 TX 引脚 → 如果一直是低电平，说明引脚硬件问题
// 快速验证：GPIO 模式改为 PP 输出，手动翻转看波形
```

**UART DMA 诊断三板斧（按顺序执行）：**

```
1. 清 IDLE 标志
   └→ __HAL_UART_CLEAR_IDLEFLAG(huart);  // 在 HAL_UARTEx_ReceiveToIdle_DMA 之前

2. 读 SR 寄存器
   └→ FE=1 → RX 线物理层异常（从机未连接/未启动/接线错误）
   └→ ORE=1 → DMA 未及时读取（DMA 通道冲突/配置错误）
   └→ NE=1  → RX 线噪声干扰

3. ISR 只置标记不阻塞
   └→ HAL_UARTEx_RxEventCallback 中只记录数据，不在中断内调用任何阻塞函数
```

---

### 7. SPI/I2C 通信失败

**症状：**
- HAL 返回 `HAL_TIMEOUT` 或 `HAL_ERROR`
- 读取到 0xFF 或 0x00

**SPI 检查清单：**
- [ ] CPOL/CPHA 配置与从机匹配
- [ ] 时钟频率不超过从机最大频率
- [ ] NSS 引脚配置（硬件/软件控制）
- [ ] MISO/MOSI 引脚未互换

**I2C 检查清单：**
- [ ] 外部上拉电阻（通常 4.7kΩ）
- [ ] 从机地址格式（7位需左移1位）
- [ ] 时钟速度（标准 100kHz，快速 400kHz）
- [ ] 调用 `HAL_I2C_IsDeviceReady()` 确认从机存在

**示例：I2C 从机地址**
```c
// ❌ 错误：7位地址未移位
HAL_I2C_Mem_Read(&hi2c1, 0x50, reg_addr, ...);

// ✅ 正确：7位地址左移1位
HAL_I2C_Mem_Read(&hi2c1, 0x50 << 1, reg_addr, ...);
```

---

### 8. ADC 测量不准确

**症状：**
- 读数波动大
- 测量值明显错误
- 通道间串扰

**检查清单：**
- [ ] **采样时间**：高阻抗信号需要更长采样时间
- [ ] **时钟频率**：ADC 时钟不超过 14MHz
- [ ] **参考电压**：VREF+ 连接和稳定性
- [ ] **输入阻抗**：信号源阻抗应 < 10kΩ
- [ ] **校准**：上电后调用 `HAL_ADCEx_Calibration_Start()`

**改进采样：**
```c
// 增加采样时间（在 CubeMX 中配置）
// 或使用多次采样平均
uint32_t adc_read_average(ADC_HandleTypeDef *hadc, uint8_t channel, uint8_t samples)
{
    uint32_t sum = 0;
    ADC_ChannelConfTypeDef sConfig = {0};

    sConfig.Channel = channel;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLETIME_239CYCLES5;  // 长采样时间

    HAL_ADC_ConfigChannel(hadc, &sConfig);

    for (uint8_t i = 0; i < samples; i++) {
        HAL_ADC_Start(hadc);
        HAL_ADC_PollForConversion(hadc, 100);
        sum += HAL_ADC_GetValue(hadc);
        HAL_ADC_Stop(hadc);
    }

    return sum / samples;
}
```

---

## 调试技巧

### 1. 使用 SWO / ITM 输出调试信息
```c
// 在初始化后配置 ITM
void debug_init(void) {
    // 需要调试器支持 SWO
    ITM_SendChar('A');
}

// 使用
ITM_SendChar('X');
```

### 2. GPIO 调试（翻转引脚）
```c
// 在关键位置翻转引脚，用示波器/逻辑分析仪观察
void debug_toggle(void) {
    HAL_GPIO_TogglePin(DEBUG_GPIO_Port, DEBUG_Pin);
}

// 在代码中插入
void function_to_debug(void) {
    HAL_GPIO_WritePin(DEBUG_GPIO_Port, DEBUG_Pin, GPIO_PIN_SET);
    // 关键代码
    HAL_GPIO_WritePin(DEBUG_GPIO_Port, DEBUG_Pin, GPIO_PIN_RESET);
}
```

### 3. 返回值检查
```c
HAL_StatusTypeDef status;

status = HAL_UART_Transmit(&huart1, data, len, 1000);
if (status != HAL_OK) {
    // 处理错误
    if (status == HAL_TIMEOUT) {
        // 超时处理
    } else if (status == HAL_ERROR) {
        // 错误处理
    }
}
```

### 4. 查看寄存器状态
```c
// 查看 UART 状态
if (huart1.Instance->SR & USART_FLAG_RXNE) {
    // 接收缓冲区非空
}

// 查看 GPIO 状态
if (GPIOA->IDR & GPIO_PIN_5) {
    // PA5 为高电平
}
```

---

## 性能优化

### 减少中断开销
```c
// 使用 DMA 代替中断模式
HAL_UART_Receive_DMA(&huart1, rx_buffer, RX_SIZE);

// 在接收完成回调中处理
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    // 一次性处理所有数据
}
```

### 使用缓冲队列
```c
// 简单环形缓冲区
#define BUFFER_SIZE 128
static uint8_t ring_buffer[BUFFER_SIZE];
static volatile uint16_t head = 0, tail = 0;

void buffer_write(uint8_t data) {
    ring_buffer[head] = data;
    head = (head + 1) % BUFFER_SIZE;
}

uint8_t buffer_read(void) {
    uint8_t data = ring_buffer[tail];
    tail = (tail + 1) % BUFFER_SIZE;
    return data;
}
```

---

## 参考资料

- [STM32F1 HAL 驱动用户手册 UM1850](https://www.st.com/resource/en/user_manual/um1850-description-of-stm32f1xx-hal-drivers-stmicroelectronics.pdf)
- [STM32F103 参考手册 RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-microcontrollers-stmicroelectronics.pdf)
- [STM32 数据手册 DS5319](https://www.st.com/resource/en/datasheet/stm32f103rb.pdf)
