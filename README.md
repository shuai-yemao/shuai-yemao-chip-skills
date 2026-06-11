# Chip Skills — 嵌入式系统技能包

> **130+ 技能包，覆盖嵌入式系统全链路开发**  
> 兼容 Claude Code / OpenCode 的 SKILL.md 标准格式  
> 安装到 `~/.claude/skills/` 即可被自动发现

---

## 目录

- [安装](#安装)
- [MCU 架构与内核](#mcu-架构与内核)
- [外设驱动](#外设驱动)
- [总线协议](#总线协议)
- [无线通信](#无线通信)
- [RTOS](#rtos)
- [构建系统](#构建系统)
- [烧录与部署](#烧录与部署)
- [调试与分析](#调试与分析)
- [安全与固件](#安全与固件)
- [轻量级中间件](#轻量级中间件)
- [工程方法](#工程方法)（部分引用上游）
- [生产力](#生产力)（部分引用上游）
- [知识管理](#知识管理)
- [其他工具](#其他工具)
- [许可](#许可)

---

## 安装

```bash
# 直接克隆
git clone --depth 1 https://github.com/shuai-yemao/shuai-yemao-chip-skills.git ~/.claude/skills
```

---

## MCU 架构与内核

### `arm-core-registers`
ARM Cortex-M 内核架构寄存器速查与调试指南。涵盖核心寄存器（R0~R15/PSP/MSP）、特殊寄存器（PRIMASK/BASEPRI/FAULTMASK/CONTROL）、异常返回值 EXC_RETURN 解码、中断优先级分组、OS 相关寄存器（FPU/MPU/SysTick）。

### `arm-interrupt-exception`
ARM Cortex-M 中断与异常系统完整指南——异常架构（类型/优先级/咬尾/晚到/抢占/悬起）、NVIC 编程（ISER/ICER/ISPR/ICPR/IABR）、中断延迟优化、双堆栈机制、BASEPRI 临界区、FPU 自动保存、中断安全设计模式。

### `arm-memory-architecture`
ARM Cortex-M 系统级内存架构指南——系统地址映射、MPU 完整配置（Region/SubRegion/Attribute/RBAR/RLAR）、Cortex-M7 Cache/SCB、位带操作、系统空间与外设空间布局。

### `mcu-peripheral-registers`
STM32 外设寄存器级操作指南。涵盖 CMSIS 外设结构体映射、各系列寄存器差异、外设总线与时钟使能寄存器、GPIO（MODER/BSRR/OSPEEDR/PUPDR）操作速查。

### `chip-architecture`
MCU 芯片架构与开发方式对比中央参考。覆盖 ARM Cortex-M 全系列（M0/M0+/M3/M4/M7/M33）、STM32 各系列（F0/F1/F4/F7/G0/G4/H7）、国产替代（GD32/AT32/CH32）对比。

### `stm32-hal-development`
STM32 HAL 库开发完整指南。覆盖 HAL 架构设计、CubeMX 配置、外设驱动封装（BSP 模板）、常见陷阱与调试。含参考手册、外设驱动指南、故障排查指南。

### `stm32-spl-development`
STM32 标准外设库 (SPL) 开发指南。覆盖 SPL 架构与文件系统（conf.h/it.h/外设 `.c`/`.h`）、SPL vs HAL/LL 对比、SPL 移植到新系列的方法。

---

## 外设驱动

### `adc-module`
STM32 ADC 模数转换器配置、开发与故障排查。涵盖时钟树与转换时序计算、规则组/注入组、过采样、校准（偏移/线性度）、模拟看门狗、双ADC模式、DMA 采集。

### `dma-module`
STM32 DMA 直接存储器访问配置、开发与故障排查。涵盖 DMA 架构（V1/V2/V3）、Stream/Channel 请求映射、传输类型（M2P/P2M/P2P）、FIFO 阈值与突发传输。

### `timer-module`
STM32 定时器配置、中断、PWM 与输入捕获开发指南。涵盖基本/通用/高级定时器架构、APB 时钟 ×2 规则、PWM 模式1/2 与互补输出/死区、输入捕获与编码器接口。

### `flash-module`
STM32 内部 Flash 存储器编程与配置指南。涵盖 Flash 架构（Sector/Page/Bank 布局）、读写擦操作（HAL 与寄存器级）、等待周期配置、编程/擦除错误恢复。

### `sram-module`
STM32 内部 SRAM 存储器配置与使用指南。涵盖 SRAM 架构（SRAM1/2/3/CCM/DTCM/ITCM）、各系列 SRAM 布局与映射、DMA 缓冲区分配、CCM 特殊用法。

### `usb-module`
STM32 USB 配置、开发与故障排查。涵盖 USB 架构（Device/OTG/HS）、时钟配置（48MHz）、CDC 虚拟串口、HID 设备、MSC 大容量存储、DFU 设备固件升级。

### `motor-control`
专业电机控制开发指南——多环级联/并联伺服控制。覆盖 FOC 矢量控制（Clarke/Park/SVPWM）、电流环/速度环/位置环/角度环的级联与并联架构、PID 调参指南。

### `peripheral-driver`
外部设备 BSP 驱动开发指南。提供开源驱动搜索策略、质量评估、代码适配工具和常见设备适配要点。三层 API 规范（init/read_write/irq_callback）。

### `lvgl-module`
LVGL (Light and Versatile Graphics Library) 轻量级嵌入式 GUI 开发指南。覆盖 LVGL 架构（对象树/显示驱动/输入设备）、控件系统、样式与动画、中文字体。

### `watchdog-module`
STM32 看门狗（IWDG/WWDG）配置、开发与故障排查。涵盖 IWDG 时钟源与分频计算、WWDG 窗口上下限计算、EWI 早唤醒中断、喂狗策略与调试注意事项。

### `lowpower-design`
STM32 系统低功耗设计完整指南。涵盖睡眠/停止/待机/关机四种模式、功耗数据选型、电源调节器配置（MR/LPR/ULP）、唤醒源设计（EXTI/RTC/LPTIM）。

---

## 总线协议

### `i2c-bus`
I2C 总线配置、驱动开发与故障排查。涵盖协议时序详解、STM32 HAL 状态机陷阱与恢复、多从机总线仲裁、时钟延展处理、总线死锁恢复（9脉冲法/SWRST）。

### `spi-bus`
SPI 总线配置、驱动开发与故障排查。涵盖四种时序模式详解、STM32 HAL 状态机与 BSY 标志陷阱、NSS 管理（硬件/软件/脉冲模式）、DMA+Cache 一致性处理。

### `uart-module`
STM32 UART/USART 串口通信配置、开发与故障排查。涵盖波特率计算与误差分析、USART vs UART 架构差异、RS485/DE 控制、LIN/智能卡/Sync 模式。

### `can-debug`
CAN 总线调试工具，支持通过 USB-CAN 适配器监听、发送 CAN 帧和扫描节点。涵盖 CAN 2.0 与 CAN FD 协议、位时序配置、过滤器设置、错误处理机制。

### `modbus-debug`
Modbus RTU（串口）和 Modbus TCP（网络）设备通信调试工具，支持寄存器读写、从站扫描和持续监控。

---

## 无线通信

### `ble-module`
蓝牙低功耗 (BLE) 通信开发指南。覆盖 BLE 协议栈架构（GAP/GATT/SMP/L2CAP）、广播/扫描/连接/配对全流程、STM32WB/ESP32 方案。

### `wifi-module`
WiFi 无线通信开发指南。覆盖 WiFi 协议基础（Station/AP/混杂模式）、ESP32 ESP-IDF WiFi 开发、STM32W/AT 指令方案、TCP/UDP/HTTP/TLS。

### `lora-module`
LoRa/LoRaWAN 远距离低功耗无线通信开发指南。覆盖 LoRa 调制原理、SX1278/SX1262 射频芯片驱动、ESP32+LoRa 方案、LoRaWAN 协议栈。

### `gps-module`
GPS/GNSS 全球导航卫星系统开发指南。覆盖 GNSS 基础（GPS/北斗/GLONASS/Galileo）、NMEA-0183 协议解析、UBX 二进制协议、常见 GPS 模块驱动。

### `cellular-module`
蜂窝通信（4G/NB-IoT/Cat-M）开发指南。覆盖 4G Cat-1/Cat-M/NB-IoT 差异与应用场景、SIM7xxx/BC95/AIR72x 模块驱动、TCP/HTTP/MQTT 上云。

### `mqtt-module`
MQTT 物联网通信协议开发指南。覆盖 MQTT v3.1.1 vs v5.0 差异、发布/订阅/主题/QoS、会话管理与遗愿 (Last Will)、SSL/TLS 安全连接。

---

## RTOS

### `freertos-module`
FreeRTOS 嵌入式实时操作系统开发指南。涵盖任务管理（创建/删除/优先级/栈）、队列/队列集/流缓冲区、信号量/互斥锁/优先级继承、事件组、软件定时器、中断安全 API。

### `rtos-debug`
RTOS 感知调试工具，支持 FreeRTOS/ThreadX/RT-Thread。通过 GDB+OpenOCD 查看任务列表、栈水印、堆状态、死锁分析、HardFault 诊断。

---

## 构建系统

### `build-cmake`
CMake 嵌入式工程构建。调用自带脚本解析工程文件、执行构建并定位固件产物。支持交叉编译、ARM GCC/IAR/Keil 工具链配置。

### `build-iar`
IAR Embedded Workbench 命令行编译。解析 `.ewp` 工程文件，执行 IAR 命令行构建，定位固件产物。

### `build-keil`
Keil MDK 命令行编译。调用 UV4 解析工程文件、执行构建并定位固件产物。支持 ARMCC/ARMCLANG 编译器和 Hex/axf 输出。

### `build-idf`
ESP-IDF 固件工程构建。调用 idf.py 执行构建并定位固件产物，支持 ESP32 全系列。

### `build-platformio`
PlatformIO 命令行编译嵌入式工程。解析 platformio.ini 环境配置，执行 pio run 构建并定位固件产物。

### `code-porting`
嵌入式代码移植专家。MCU 换型（STM32F1↔F4↔F7↔G0↔G4↔H7、GD32/AT32/CH32 国产替代）、HAL↔SPL 库切换、Keil↔IAR↔CMake 工程迁移。

### `linker-scatter`
嵌入式链接脚本与分散加载文件指南（Keil `.sct` / GCC `.ld` / IAR `.icf`）。覆盖三种链接脚本语法对照、内存区域定义、段放置规则。

---

## 烧录与部署

### `flash-jlink`
J-Link 调试探针烧录嵌入式固件。支持 `.hex`/`.bin`/`.elf` 格式，SWD/JTAG 接口，自动生成 Commander 脚本，多探针 SN 选择，烧录校验。

### `flash-openocd`
OpenOCD 烧录嵌入式固件。调用自带脚本配合已探测的产物与探针配置完成烧录，支持多种调试器和 MCU 平台。

### `flash-keil`
Keil MDK 烧录编译产物到目标 MCU。支持 `.hex`/`.axf` 文件通过 J-Link 烧录。与 build-keil 配合形成完整闭环。

### `flash-idf`
ESP-IDF 工具链烧录固件到 ESP32 系列芯片。支持 esptool 协议、idf.py flash、JTAG 调试。

### `flash-platformio`
PlatformIO 烧录固件到目标板。利用 platformio.ini 中的上传配置自动完成烧录。

### `gang-flash`
多路并行量产烧录工具。支持 OpenOCD 多 ST-Link、J-Link Multi-Emulator、esptool 多串口并行烧录，内建自动重试、读回校验。

### `ota-package`
嵌入式 OTA 固件包生成与测试工具。支持全量包、差分包 (bsdiff)、压缩包 (zlib)、分段包 (chunked)、ESP32 OTA、A/B 分区元数据。

### `ota-update-system`
嵌入式 OTA 升级系统架构设计与开发指南。涵盖 A/B 双区/单区+恢复/外置 Flash/双芯片架构、OTA 状态机、签名验证、版本管理、回滚策略。

### `bootloader-design`
嵌入式 Bootloader 设计与开发完整指南。涵盖启动流程架构（硬件初始化→完整性校验→引导决策→APP 跳转）、Flash 分区策略（单区/双区/自定义）、安全升级链。

---

## 调试与分析

### `debug-gdb-openocd`
OpenOCD GDB 调试工具。启动或附着 GDB 会话，完成固件下载、在线调试、崩溃现场检查。支持硬件断点、Watchpoint、内存访问。

### `cmbacktrace-debug`
CmBacktrace（Cortex Microcontroller Backtrace）ARM Cortex-M 系列 MCU 错误自动追踪与故障诊断。自动解析 HardFault 栈回溯、解码 CFSR/BFSR/UFSR。

### `segger-rtt-module`
SEGGER RTT（Real-Time Transfer）完整指南。MCU 端集成（源码/配置/API）+ PC 端监控（JLinkRTTClient/scripts），支持多通道输出。

### `serial-monitor`
串口监控工具。识别正确串口、抓取日志、分析嵌入式固件运行状态。支持自动重连、日志过滤、波特率检测。

### `embedded-debugger-framework`
嵌入式系统故障诊断框架——从现象到根因的系统性诊断方法论。覆盖五层诊断模型（供电→物理连接→波形→寄存器→状态机）、故障隔离策略。

### `map-analyzer`
解析 GCC/Keil/IAR `.map` 文件，分析 Flash/RAM 使用率、模块符号大小、版本对比 diff、风险预警与优化建议。支持彩色进度条、JSON/HTML/Text 输出。

### `static-analysis`
对嵌入式 C/C++ 代码执行静态分析。封装 cppcheck 扫描未定义行为、内存泄漏、空指针、数组越界，支持 MISRA C 检查、增量基线对比、HTML 报告。

### `embedded-reviewer`
嵌入式系统审查官的思维框架——嵌入式代码审查的单一入口。进行中断安全/可重入/DMA 缓冲区/volatile 正确性等专项审查。

### `embedded-skills-map`
嵌入式技能地图——按领域分类管理所有嵌入式相关 skills，提供基于知识库结构的分层导航。

---

## 安全与固件

### `aes-module`
AES 加密解密开发指南。覆盖 AES 算法原理（ECB/CBC/GCM/CTR 模式）、密钥长度 AES-128/192/256、STM32 CRYP 硬件加密外设配置。

### `rsa-module`
RSA 非对称加密开发指南。覆盖 RSA 算法原理、密钥生成与存储、签名验签流程（RSASSA-PKCS1-v1_5/PSS）、加密解密（OAEP）。

### `crc-module`
CRC 校验算法开发指南。覆盖常见 CRC 模型（CRC-16/CCITT/32/MODBUS）、查表法 vs 逐位法实现、硬件 CRC 外设（STM32 CRC）配置。

### `firmware-sign`
固件签名、加密与安全打包工具。支持 ECDSA/RSA/Ed25519 数字签名、AES-256-GCM/CBC 加密、固件头打包、Bootloader 验签代码生成。

### `ymodem-module`
Ymodem 文件传输协议开发指南。覆盖 Ymodem 协议帧格式（SOH/STX/EOT/CAN）、128 字节 vs 1024 字节模式、CRC-16 校验、批量文件传输。

---

## 轻量级中间件

### `fatfs-module`
FatFs 文件系统移植、配置与开发指南。涵盖 FatFs 架构与应用层接口、disk_io 底层驱动实现（SDIO/SPI/Flash）、多盘管理、长文件名/中文支持。

### `sfud-module`
SFUD（Serial Flash Universal Driver）串行 Flash 通用驱动库。覆盖 SFUD 移植、sfud_cfg.h 配置、SFDP 参数自动解析、QSPI 模式支持。

### `dsp-module`
嵌入式数字信号处理 (DSP) 开发指南。覆盖 CMSIS-DSP 软件库函数、FIR/IIR 数字滤波器设计与实现、定点 vs 浮点 DSP、FFT 频谱分析。

### `fft-module`
快速傅里叶变换 (FFT) 嵌入式开发指南。覆盖 FFT 算法原理和工程实现、CMSIS-DSP FFT 函数 (rfft/cfft)、ST 全系列及 ESP32 平台适配。

### `elog-module`
EasyLogger (elog) 轻量级嵌入式日志库指南。覆盖 elog 移植（elog_cfg.h/elog_port.c）、输出后端配置（RTT/UART/Flash）、日志级别控制与输出格式定制。

---

## 工程方法

> ℹ️ 以下技能为需求对齐流程的核心组成部分，部分参考上游 [mattpocock/skills](https://github.com/mattpocock/skills) 进行定制和扩展。

### `engineering/tdd`
测试驱动开发（TDD）——红-绿-重构循环。垂直切片（一个测试→一段实现→循环），深模块设计、接口契约先于实现、Mock 策略。

### `engineering/diagnose`
纪律化诊断流程——复现→最小化→假设→修复→回归。针对难以复现的 Bug 和性能回归，提供系统性排查方法。含 HITL 循环模板。

### `engineering/triage`
Issue 状态机分类系统。bug/enhancement、needs-triage/ready-for-agent 状态流转，支持 GitHub/GitLab/Local 后端。

### `engineering/prototype`
可丢弃原型构建方法论。在投入正式实现前快速验证设计可行性。含逻辑层/UI 层原型指导。

### `engineering/zoom-out`
全局视角切换——让 Agent 退一步给出更广阔的背景和更高层级的视角。用于理解模块间关系、系统边界、架构权衡。

### `engineering/to-issues`
将计划、规格或 PRD 拆解为可独立抓取的 Issue。每个 Issue 是垂直切片（tracer bullet），贯穿所有集成层，可独立验证。

### `engineering/to-prd`
将当前对话上下文转化为 PRD（产品需求文档）并发布到 Issue Tracker。定义测试接缝、验收标准。

### `engineering/grill-with-docs`
Grilling Session——对照现有领域模型挑战方案，精炼通用语言。含 ADR 格式、Context 格式、术语表管理。

### `engineering/improve-codebase-architecture`
渐进式重构加深模块。通过领域语言寻找深化机会，设计接口契约，实现深模块。含四步重构法：选模块→画边界→定接口→深模块。

### `engineering/setup-matt-pocock-skills`
设置技能系统。在 AGENTS.md/CLAUDE.md 中创建 `## Agent skills` 区块和 `docs/agents/` 技能文档目录。

---

## 生产力

> ℹ️ 以下技能为需求对齐流程的核心组成部分，部分参考上游 [mattpocock/skills](https://github.com/mattpocock/skills) 进行定制和扩展。

### `productivity/grill-me`
Grill 模式——围绕计划或设计持续追问用户，直到达成共识。走遍决策树的每个分支，不遗漏模糊点。

### `productivity/handoff`
上下文交接工具。将当前对话压缩为交接文档，供另一个 Agent 或人类继续。保持关键决策记录和技术细节。

### `productivity/teach`
技能传授模式。含 GLOSSARY 格式（新术语解释）、MISSION 格式（包含明确通过标准和模糊地带）、LEARNING RECORD 格式（实践记录模板）、RESOURCES 格式（学习资源结构化）。

### `workflow`
工作流引擎——串联多个 skill 完成嵌入式开发全流程。支持 6 个专用 Agent 分工协作（编译/烧录/监控、开发循环、项目管理、硬件验证、发布管理、Bug 修复）。

### `workflow-guide`
工作流体系导航与维护指南。当用户询问工作流结构、流水线清单、Agent 职责、链式触发规则、资源锁机制时使用。

### `brainstorming`
创造性工作前必须使用的技能——创建功能、构建组件、添加功能或修改行为。在实现之前先探索用户意图、需求和设计。含视觉伴侣、流程图、方案探索。

### `writing-plans`
多步骤任务实现计划生成。当你有规格说明或需求时，在动手写代码之前产出一份执行计划。

### `executing-plans`
书面实现计划执行器。当有一份实现计划需要在单独会话中执行，并设有审查检查点时使用。

### `write-a-skill`
创建新 Agent Skill 的完整指南。含目录结构、渐进式披露标准、打包机制。

### `caveman`
极限压缩通信模式。通过去除填充语、整合形容词、使用速记符号，将 token 使用量降低约 75%。

### `skills-system-builder`
技能系统搭建指南——教其他 Agent 理解、创建、优化自己的技能体系。从零开始设计技能目录结构、SKILL.md 标准模板。

---

## 知识管理

### `knowledge-base-search`
六源知识检索管线。Phase1 本地知识库（BM25+Vector+RRF+MMR）→ Phase2 芯片厂商官网文档+立创原理图 → Phase3 GitHub 代码搜索。

### `kb-datasheet`
芯片/传感器数据手册获取工具。支持 17 个厂商自动识别（ST/Espressif/NXP/TI/Nordic/Microchip/Renesas/GD/WCH 等）。

### `kb-verify`
搜索结果真伪验证引擎。三维评分模型（来源权威性 40% + 内容安全 30% + 断言交叉验证 30%），嵌入式特化一致性检查规则。

### `kb-import`
搜索成果导入本地知识库。将验证通过的高价值内容写入 imported_docs.db，实现知识沉淀闭环。

### `kb-record`
开发问题记录到 Obsidian。使用四段式诊断模板（问题描述→原因分析→实验设计→验证实验）归档调试过程。

---

## 其他工具

### `agent-packager`
Agent Package 标准化打包与版本管理系统。将嵌入式工作流 Agent 及其全套 skill 打包为工具无关的标准化格式（.agentpkg），支持全平台分发包生成、版本差分、增量更新、签名验证。

### `coding-standards`
嵌入式 C 编码规范速查手册——合并自 MISRA C:2012（143 条规则）和立芯嵌入式 C 编码规范。涵盖规则优先级协议（MISRA Mandatory/Required/Advisory）。

### `doc-automation`
嵌入式文档自动化工具集——从嵌入式 C 工程代码和配置中自动生成函数注释、API 文档、硬件接线说明、minunit 单元测试骨架和移植指南。

### `embedded-architect`
嵌入式系统架构师的思维框架——系统设计的方法论和参考模型。含分层架构模型文档。

### `embedded-learning-path-framework`
嵌入式系统学习路径架构师——从 HAL 使用者到寄存器理解者再到系统设计者的三阶段进阶模型。覆盖各阶段技能清单、里程碑项目、学习资源。

### `embedded-learning-notes`
嵌入式学习笔记管理（费曼学习法基底 + 诊断流程模板）。将开发经验、实验记录、知识体系转化为结构化 Obsidian 笔记。

---

## 许可

MIT License © 2026 shuai-yemao

嵌入式专业技能（MCU 架构/外设驱动/总线协议/无线通信/RTOS/构建/烧录/调试/安全/中间件/知识管理 等）为原创作品。  
工程方法和生产力类技能部分参考 [mattpocock/skills](https://github.com/mattpocock/skills) 进行定制和扩展。
