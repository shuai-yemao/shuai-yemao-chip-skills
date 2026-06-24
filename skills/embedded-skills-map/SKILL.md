---
name: embedded-skills-map
version: "1.0.0"
description: "嵌入式技能地图——按领域分类管理所有嵌入式相关 skills，提供基于 Obsidian「领域/嵌入式/」知识库结构的分层导航。当用户需要了解可用技能、选择适合当前任务的 skill、查找技能之间的关系、或进行技能体系梳理时使用。触发词：技能地图、技能导航、skill map、技能清单、有哪些skills、我要用什么skill、技能分类、skill 推荐、嵌入式技能树、技能索引、所有嵌入式skills、skill目录、skill MOC、sk_map。"
---

# 嵌入式技能地图 (Embedded Skills MOC)

本 skill 是一份嵌入式开发技能的 **Map of Content (MOC)**，参照 Obsidian Vault 中 `领域/嵌入式/` 的目录结构对已安装的嵌入式技能进行分类管理。

> 完整分类映射表见 `references/skill-mapping.md`（53 个 skills × 10 大分类的完整映射）

## 使用方式

| 场景 | 操作 |
|------|------|
| 想了解所有可用技能 | `sk_map` — 列出全部分类 |
| 不知道用哪个 skill | `sk_map: 我要做XX` — 推荐匹配的技能 |
| 分类查看某一领域 | `sk_map: 工具链` / `sk_map: 通信协议` |

## 技能分类体系

### 通信协议

| 类别 | 技能名称 | 说明 |
|------|---------|------|
| **有线通信** | `i2c-bus` | I2C 总线配置/死锁恢复/时序/HAL 陷阱 |
| | `spi-bus` | SPI 总线配置/BSY 恢复/NSS/DMA 一致性 |
| | `uart-module` | UART/USART 串口/波特率/RS485/LIN/DMA |
| | `can-debug` | CAN 总线调试/监听/发送/节点扫描 |
| | `modbus-debug` | Modbus RTU/TCP 调试/寄存器读写 |
| **无线通信** | `ble-module` | BLE 低功耗蓝牙/STM32WB/ESP32/nRF52 |
| | `wifi-module` | WiFi/ESP32/AT 模块/配网/TCP-UDP |
| | `lora-module` | LoRa/LoRaWAN SX1278/SX1262 远距离 |
| | `cellular-module` | 4G/NB-IoT/Cat-M 蜂窝通信 |
| | `gps-module` | GPS/北斗 GNSS 定位/NMEA 解析 |
| **物联网协议** | `mqtt-module` | MQTT 协议/ESP-MQTT/paho/云平台对接 |

### 开发板 (MCU 架构)

| 架构 | 技能名称 | 说明 |
|------|---------|------|
| **ARM** | `stm32-hal-development` | STM32 HAL 工程开发全指南 |
| | `stm32-spl-development` | **STM32 标准外设库 (SPL) 开发 — 新增** |
| | `arm-core-registers` | Cortex-M 内核寄存器/SCB/NVIC/SysTick/DWT |
| | `arm-memory-architecture` | 系统内存架构/MPU/Cache/内存屏障/总线矩阵/TCM/位带 |
| | **`arm-interrupt-exception`** | **中断/异常/NVIC/EXTI/HardFault/向量表/ISR 设计 — 新增** |
| | `mcu-peripheral-registers` | STM32 外设寄存器级操作 |
| | `flash-jlink` | J-Link 烧录/校验 |
| | `flash-openocd` | OpenOCD 烧录 |
| | `debug-gdb-openocd` | OpenOCD GDB 调试 |
| | `flash-keil` | Keil MDK 烧录 |
| | `build-keil` | Keil MDK 命令行编译 |
| | `build-iar` | IAR 命令行编译 |
| | `build-cmake` | CMake + ARM GCC 构建 |
| | `build-platformio` | PlatformIO 构建 |
| | `flash-platformio` | PlatformIO 烧录 |
| | `debug-platformio` | PlatformIO GDB 调试 |
| **RISC-V** | `build-idf` | ESP-IDF 构建 |
| | `flash-idf` | ESP32 系列烧录 |

### 操作系统 (RTOS)

| 技能名称 | 说明 |
|---------|------|
| `rtos-debug` | FreeRTOS/ThreadX/RT-Thread 任务/栈/死锁/HardFault 分析 |

### 常用模块

| 类别 | 技能名称 | 说明 |
|------|---------|------|
| **ADC 采集** | `adc-module` | ADC 时序/规则注入组/过采样/校准/DMA |
| **定时器** | `timer-module` | PWM/输入捕获/编码器/单脉冲/主从同步 |
| **看门狗** | `watchdog-module` | IWDG/WWDG 配置/窗口计算/喂狗策略/调试冻结/复位溯源 |
| **外设驱动(通用)** | `peripheral-driver` | 传感器/存储器/显示屏 BSP 驱动适配 |

### 系统级设计

| 类别 | 技能名称 | 说明 |
|------|---------|------|
| **系统低功耗** | `lowpower-design` | Sleep/Stop/Standby/Shutdown 模式/电源架构/唤醒源/时钟门控/VOS |
| **Bootloader** | `bootloader-design` | 启动架构/分区/跳转/回滚/安全引导/调试 |
| **OTA 系统** | `ota-update-system` | OTA 状态机/协议/安全/双芯片/量产策略 |

### 必备开发工具

| 类别 | 技能名称 | 说明 |
|------|---------|------|
| **串口日志** | `serial-monitor` | 串口日志抓取/分析 |
| **RTT 日志** | `rtt-monitor` | SEGGER RTT 实时日志 |
| **静态分析** | `static-analysis` | cppcheck 代码扫描/MISRA |
| **单元测试** | `doc-automation` | minunit 生成 + 运行 (docgen_test.py + minunit_runner.py) |
| **MAP 分析** | `map-analyzer` | Flash/RAM 用量/符号分析 |
| **量产烧录** | `gang-flash` | 多路并行量产烧录 |
| **固件签名** | `firmware-sign` | ECDSA/RSA 签名/加密 |
| **OTA 打包** | `ota-package` | 全量/差分/分段 OTA |
| **Option Bytes** | `option-bytes` | 读保护/写保护/BOR 配置 |
| **VISA 仪器** | `visa-debug` | GPIB/USB/TCP 仪器控制 |
| **Agent 打包** | `agent-packager` | Agent Package 标准化打包/版本管理/跨工具分发 |
| **技能系统搭建** | `skills-system-builder` | Agent 用技能创建规范/模板/流程指南 |
| **芯片架构对比** | `chip-architecture` | MCU 架构差异 + 开发方式对比中央参考 |
| **原理图分析** | `pcb-analysis` | LCEDA Pro 原理图 BOM/电源树/引脚/网络/DRC |

### 编码规范与代码质量

| 技能名称 | 说明 |
|---------|------|
| `coding-standards` | **编码规范速查（MISRA + 立芯，合并）** |
| `embedded-reviewer` | 中断安全/DMA/并发/内存审查（吸收审查框架） |
| `static-analysis` | cppcheck MISRA 自动扫描 |

### 嵌入式项目文档与工作流

| 技能名称 | 说明 |
|---------|------|
| `workflow` | 编译→烧录→监控 流水线编排 |
| `devlog` | 开发日志自动生成（见 FACT.md） |
| `embedded-debugger-framework` | 五层诊断模型故障排查 |
| `embedded-learning-path-framework` | 三阶段学习路径规划 |

### 知识管理

| 技能名称 | 说明 |
|---------|------|
| `knowledge-base-search` | 六源知识检索管线 |
| `kb-verify` | 真伪验证引擎 |
| `kb-import` | 知识导入 |
| `kb-record` | 问题记录归档 |
| `kb-datasheet` | 数据手册获取 |

### 中间件

| 技能名称 | 说明 |
|---------|------|
| `fatfs-module` | FATFS 文件系统移植/配置/开发 |
| `aes-module` | AES 加密/STM32 CRYP 硬件/软件库 |
| `rsa-module` | RSA 非对称加密/签名验签 |
| `crc-module` | CRC 校验/查表法/硬件 CRC |
| `ymodem-module` | Ymodem 串口文件传输协议 |
| `lvgl-module` | LVGL 嵌入式图形界面/GUI |
| `dsp-module` | DSP 数字信号处理/FIR/IIR/CMSIS-DSP |
| `fft-module` | FFT 频谱分析/窗函数/Goertzel |

## 任务→技能推荐矩阵

| 任务类型 | 推荐 skill (优先级) |
|---------|-------------------|
| 新建工程、做项目 (HAL) | `stm32-hal-development` → `workflow` |
| 新建工程、做项目 (SPL) | `stm32-spl-development` → `workflow` |
| 编译固件 (Keil) | `build-keil` |
| 编译固件 (ESP-IDF) | `build-idf` |
| 烧录固件 (J-Link) | `flash-jlink` |
| 烧录固件 (Keil) | `flash-keil` |
| 量产烧录 | `gang-flash` |
| 看串口日志 | `serial-monitor` |
| 看 RTT 日志 | `rtt-monitor` |
| 板子不工作/跑飞 | `embedded-debugger-framework` → `arm-core-registers` (HardFault) |
| HardFault 分析 | `arm-core-registers` (CFSR/HFSR 解码) |
| 调试 FreeRTOS 死锁 | `rtos-debug` → `embedded-debugger-framework` |
| 外设不工作 | `stm32-hal-development` → `mcu-peripheral-registers` (寄存器级诊断) |
| 写 I2C 驱动 | `i2c-bus` → `peripheral-driver` |
| 写 SPI 驱动 | `spi-bus` → `peripheral-driver` |
| 配置串口 | `uart-module` |
| 配定时器/PWM | `timer-module` |
| 配 ADC | `adc-module` |
| 配看门狗 | `watchdog-module` |
| 系统低功耗设计 | `lowpower-design` |
| 复位原因分析 | `watchdog-module` → `arm-core-registers` |
| 喂狗策略/看门狗死锁 | `watchdog-module` → `freertos-module` |
| 改引脚定义 | `embedded-reviewer` (代码审查) |
| 代码规范检查 | `coding-standards` |
| 静态代码分析 | `static-analysis` |
| 单元测试 | `doc-automation` |
| OTA 升级 | `ota-package` → `firmware-sign` |
| 分析内存用量 | `map-analyzer` |
| 查知识库/数据手册 | `knowledge-base-search` → `kb-datasheet` |
| 记录开发问题 | `kb-record` |
| 生成开发日志 | `devlog` |
| 规划学习路线 | `embedded-learning-path-framework` |
| 读 .map 文件 | `map-analyzer` |
| 配置 Option Bytes | `option-bytes` |
| 指令仪器 (SCPI) | `visa-debug` |
| CAN 总线调试 | `can-debug` |
| Modbus 调试 | `modbus-debug` |

## 技能关系图

```
                        knowledge-base-search (知识底座)
                              ↕
     embedded-learning-path-framework  ←→  embedded-debugger-framework
                              ↕                      ↕
     stm32-hal-development ───↕────────────────────── embedded-reviewer
         ↕         ↕         ↕         ↕          ↕
   build-keil  uart-module  i2c-bus   timer-module  watchdog-module
   flash-jlink  spi-bus    adc-module  peripheral-driver  lowpower-design
       ↕              ↕
   serial-monitor   can-debug
   rtt-monitor      modbus-debug
       ↕
   arm-core-registers ←→ mcu-peripheral-registers ←→ map-analyzer
          ↕                        ↕
   rtos-debug              static-analysis / doc-automation
   option-bytes
   gang-flash / firmware-sign / ota-package
```

## 执行步骤

1. 用户提出问题或任务描述 → 分析属于哪个分类
2. 引用上述技能矩阵，推荐最匹配的 1~3 个 skill
3. 说明推荐的 skill 之间的配合关系（哪个先用，哪个作为补充）
4. 如需了解 skill 详情，告知如何调用（`/<skill_name>`）

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 无法匹配到合适的 skill | 任务描述过于模糊 | 请用户补充具体 MCU 型号、外设类型、开发环境 |
| 用户需要不存在的能力 | 超出当前技能覆盖范围 | 推荐 `skill-creator` 创建新 skill，或建议 `peripheral-driver` 作为兜底 |
| 多个 skill 都可胜任 | 能力重叠 | 按优先级推荐 + 说明各 skill 侧重点差异 |

## 边界定义

- 本 skill 不执行任何编译/烧录/调试操作——只做**导航推荐**
- 不覆盖非嵌入式领域 skills（如 docx/pdf/xlsx/ppt 等办公类）
- 已安装但禁用的 skills 标注在 references 中，不在主要推荐中
- 不修改其他 skill 的内容和结构
