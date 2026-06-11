# Chip Skills — 嵌入式系统技能包

> 130+ 技能包，覆盖嵌入式系统全链路开发  
> 兼容 Claude Code / OpenCode 的 SKILL.md 标准格式

## 技能一览

### 嵌入式底层
| 技能 | 说明 | 来源 |
|------|------|------|
| `i2c-bus` | I2C 总线调试与驱动 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `spi-bus` | SPI 总线调试与驱动 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `uart-module` | UART 串口通信 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `can-debug` | CAN 总线调试 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `usb-module` | USB 设备/主机开发 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `dma-module` | DMA 传输配置 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `adc-module` | ADC 采样配置 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `timer-module` | 定时器 PWM/输入捕获 | [mattpocock/skills](https://github.com/mattpocock/skills) |

### MCU 架构
| 技能 | 说明 | 来源 |
|------|------|------|
| `arm-core-registers` | ARM Cortex 核心寄存器操作 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `arm-interrupt-exception` | 中断/异常/优先级/NVIC | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `arm-memory-architecture` | 内存映射/MPU/位带 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `mcu-peripheral-registers` | 外设寄存器操作 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `stm32-hal-development` | STM32 HAL 库开发 | [mattpocock/skills](https://github.com/mattpocock/skills) |
| `stm32-spl-development` | STM32 SPL 标准库开发 | [mattpocock/skills](https://github.com/mattpocock/skills) |

### 无线通信
`ble-module`, `wifi-module`, `lora-module`, `gps-module`, `cellular-module`, `mqtt-module`

### RTOS
`freertos-module`, `rtos-debug`

### 构建与烧录
`build-cmake`, `build-iar`, `build-keil`, `build-idf`, `build-platformio`, `flash-jlink`, `flash-openocd`, `flash-keil`, `flash-idf`, `flash-platformio`, `code-porting`, `linker-scatter`, `map-analyzer`

### 调试与分析
`debug-gdb-openocd`, `cmbacktrace-debug`, `segger-rtt-module`, `serial-monitor`, `static-analysis`, `embedded-debugger-framework`

### 安全与固件
`aes-module`, `rsa-module`, `crc-module`, `firmware-sign`, `ota-package`, `ota-update-system`, `bootloader-design`

### 工程方法
`engineering/tdd`, `engineering/diagnose`, `engineering/triage`, `engineering/prototype`, `engineering/zoom-out`, `engineering/to-issues`, `engineering/to-prd`, `engineering/grill-with-docs`, `engineering/improve-codebase-architecture`

### 其他
`lvgl-module`, `fatfs-module`, `sfud-module`, `dsp-module`, `fft-module`, `motor-control`, `lowpower-design`, `watchdog-module`, `elog-module`, `ymodem-module`, `sram-module`, `modbus-debug`

## 使用方式

安装到 `~/.claude/skills/` 即可被 Claude Code / OpenCode 自动发现：

```bash
# 直接克隆到 skills 目录
git clone --depth 1 https://github.com/shuai-yemao/shuai-yemao-chip-skills.git ~/.claude/skills
```

或作为 Chip 系统的一部分安装（详见 Chip 主仓库）。

## 许可

各技能包的版权归其各自作者所有。  
本仓库仅为整理分发，上游来源：[mattpocock/skills](https://github.com/mattpocock/skills)
