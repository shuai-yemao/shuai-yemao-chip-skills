---
name: embedded
description: "嵌入式系统开发专家 — STM32、ESP32、FreeRTOS、外设驱动、通信协议。Use when user mentions embedded, MCU, STM32, ESP32, FreeRTOS, I2C, SPI, UART, CAN, GPIO, ADC, DMA, or firmware development."
metadata:
  version: "1.0.0"
  last_updated: "2026-06-24"
  status: active
  task_type: open-ended
  related_skills:
    - firmware-development
    - hardware-design
    - testing-cicd
---

# Embedded — 嵌入式系统开发专家

嵌入式系统开发技能包，覆盖 MCU 架构、外设驱动、RTOS、通信协议、工具链等。

## 核心能力

### MCU 架构

| 芯片系列 | 覆盖方向 |
|----------|----------|
| **STM32** | Cortex-M3/M4/M7、HAL/SPL、CubeMX、寄存器操作 |
| **ESP32** | ESP-IDF、FreeRTOS、WiFi/BLE、外设驱动 |
| **RISC-V** | 基础架构、RISC-V 工具链 |
| **ARM Cortex** | core 寄存器、中断异常、内存架构 |

### 外设驱动

| 外设 | 功能 |
|------|------|
| **GPIO** | 输入/输出、中断、唤醒 |
| **ADC/DAC** | 模拟采集、DMA 传输 |
| **Timer** | PWM、输入捕获、编码器接口 |
| **DMA** | 内存到外设、外设到内存 |
| **Watchdog** | IWDG、WWDG、低功耗看门狗 |
| **RTC** | 闹钟、时间戳、备份寄存器 |
| **Flash** | 擦写、读保护、OTA |

### 总线协议

| 协议 | 特点 |
|------|------|
| **I²C** | 多设备总线、400kHz 标准速率、错误检测 |
| **SPI** | 全双工、CPOL/CPHA 配置、高速传输 |
| **UART** | 115200 默认波特率、中断/DMA 模式 |
| **CAN** | 车规总线、2.0A/2.0B、CAN FD |
| **USB** | CDC/HID/MSC 类、设备/主机模式 |

### 无线通信

| 技术 | 应用 |
|------|------|
| **BLE** | 低功耗蓝牙、GATT 服务、连接参数 |
| **WiFi** | STA/AP 模式、MQTT、HTTP |
| **LoRa** | 远距离通信、低功耗、私有协议 |
| **GPS** | NMEA 解析、定位服务 |
| **MQTT** | 轻量级消息队列、IoT 协议 |

### RTOS

| 特性 | 说明 |
|------|------|
| **任务管理** | 优先级、调度、状态机 |
| **队列/信号量** | 同步、通信、资源管理 |
| **内存管理** | 静态分配、堆管理、内存池 |
| **调试** | 运行时统计、栈溢出检测 |

### 工具链

| 工具 | 用途 |
|------|------|
| **CMake** | 跨平台构建 |
| **PlatformIO** | 嵌入式开发框架 |
| **ESP-IDF** | ESP32 官方 SDK |
| **Keil/IAR** | 商业 IDE |
| **OpenOCD/JLink** | 调试烧录 |
| **GDB** | 调试器 |

## 使用示例

### 示例 1：STM32 I²C 驱动开发

```c
// I²C 初始化
void I2C_Init(void) {
    hi2c1.Instance = I2C1;
    hi2c1.Init.ClockSpeed = 100000;  // 100kHz
    hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
    hi2c1.Init.OwnAddress1 = 0x00;
    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    HAL_I2C_Init(&hi2c1);
}

// I²C 读取
HAL_StatusTypeDef I2C_Read(uint8_t devAddr, uint8_t regAddr, uint8_t *data, uint16_t len) {
    return HAL_I2C_Mem_Read(&hi2c1, devAddr << 1, regAddr, 
                            I2C_MEMADD_SIZE_8BIT, data, len, 100);
}
```

### 示例 2：FreeRTOS 任务创建

```c
void Task_LED(void *pvParameters) {
    while (1) {
        HAL_GPIO_TogglePin(GPIOC, GPIO_PIN_13);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

// 创建任务
xTaskCreate(Task_LED, "LED", 128, NULL, 1, NULL);
```

### 示例 3：UART 中断接收

```c
uint8_t rxBuffer[1];
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART1) {
        // 处理接收数据
        ProcessData(rxBuffer[0]);
        // 重新开启接收
        HAL_UART_Receive_IT(&huart1, rxBuffer, 1);
    }
}
```

## 最佳实践

1. **资源限制**：注意 Flash 和 RAM 容量限制
2. **避免动态分配**：中断/实时路径中不使用 malloc
3. **RTOS 栈大小**：按实际使用量配置，预留 20% 余量
4. **错误处理**：所有外设操作检查返回值
5. **低功耗**：合理使用 Sleep/Stop/Standby 模式

## 相关资源

- [STM32 HAL 参考手册](https://www.st.com/resource/en/reference_manual/rm0090-stm32f405415-stm32f407427-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [ESP-IDF 编程指南](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/)
- [FreeRTOS 参考手册](https://www.freertos.org/Documentation/02-Kernel/02-Kernel-ports/01-Cortex-M/01-Porting-a-FreeRTOS-kernel/Porting-a-FreeRTOS-kernel)
