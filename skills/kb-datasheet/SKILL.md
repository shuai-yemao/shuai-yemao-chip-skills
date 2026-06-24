---
name: kb-datasheet
description: 芯片/传感器数据手册获取工具。支持17个厂商自动识别（ST/Espressif/NXP/TI/Nordic/Microchip/Renesas/GD/WCH + Bosch/InvenSense/Sensirion/Honeywell/Analog/TDK/Rohm），自动生成最优搜索查询。当用户提到「数据手册」「datasheet」「规格书」「芯片手册」「传感器手册」「PDF 手册」「参考手册」「Reference Manual」或需要查找芯片/传感器的官方技术文档时使用。
version: "1.0.0"
---

# 数据手册获取

> 芯片数据手册和传感器规格书是嵌入式开发中最权威的一手来源。
> 自动识别厂商并生成最优搜索查询，通过 web 搜索获取最新官方文档。

## 获取脚本

```bash
# 脚本位置（共享 knowledge-base-search 的脚本目录）
python ../knowledge-base-search/scripts/fetch_datasheet.py
```

## 支持厂商

### MCU 厂商（10家）

| 厂商 | 自动识别关键词 | 文档类型 | 典型 URL 模式 |
|------|--------------|---------|--------------|
| **ST** | STM32, STM8 | RM / DS / AN / ES | `st.com/resource/en/` |
| **Espressif** | ESP32, ESP8266, ESP | TRM / DS / API | `docs.espressif.com` |
| **NXP** | i.MX, LPC, Kinetis | RM / DS / AN | `nxp.com/docs/en/` |
| **TI** | MSP430, CC, TMS | DS / UG / AN | `ti.com/lit/ds/` |
| **Nordic** | nRF51, nRF52, nRF53 | PS / DS / SDS | `infocenter.nordicsemi.com` |
| **Microchip** | PIC, AVR, SAM | DS / UM | `microchip.com` |
| **Renesas** | RA, RL78, RX | RM / DS | `renesas.com` |
| **GD** | GD32F, GD32E, GD32 | DS / UM | `gd32mcu.com` |
| **WCH** | CH32, CH57x, CH58x | DS / RM | `wch.cn` |
| **Sophgo** | CV, SG | DS / RM | `sophgo.com` |

### 传感器厂商（7家）

| 厂商 | 典型传感器 | 文档类型 |
|------|-----------|---------|
| **Bosch** | BME280, BMP280, BMA系列 | Datasheet / Calibration |
| **InvenSense/TDK** | MPU6050, MPU9250, ICM系列 | Datasheet / Register Map |
| **Sensirion** | SHT30, SHT31, SGP30 | Datasheet |
| **Honeywell** | HMC5883L, HSC系列 | Datasheet |
| **Analog Devices** | ADXL345, AD7793 | Datasheet |
| **ROHM** | BH1750, RPR系列 | Datasheet |
| **AMS** | TCS34725, AS7341 | Datasheet |

## 使用方式

### 搜索数据手册

```bash
# 自动识别厂商并生成搜索建议
python ../knowledge-base-search/scripts/fetch_datasheet.py --model "STM32F407VGT6" --search-only --json

python ../knowledge-base-search/scripts/fetch_datasheet.py --model "BME280" --search-only --json

python ../knowledge-base-search/scripts/fetch_datasheet.py --model "MPU6050" --search-only --json
```

### 下载 PDF 到本地

```bash
python ../knowledge-base-search/scripts/fetch_datasheet.py --url "{PDF 链接}" --output "./datasheets/"
```

## 文档获取流程

```
步骤 1: 运行 --search-only 识别厂商 + 生成搜索查询
步骤 2: web_search_exa 搜索文档链接
步骤 3: fetch_markdown 获取文档内容 / navigate_page 浏览器交互
步骤 4: 可选下载 PDF 到本地供 kb-import 导入
```

### 传感器数据手册关键章节

获取文档后优先提取以下内容：

1. **校准参数** → "Calibration" / "Compensation" 章节
2. **I2C/SPI 地址与时序** → "Communication Interface" 章节
3. **寄存器映射** → "Register Map" 章节
4. **精度/噪声规格** → "Electrical Characteristics" 章节
5. **参考驱动** → GitHub 搜索厂商官方 driver

## 搜索示例

```bash
# MCU 参考手册
"RM0090 reference manual STM32F40x STM32F41x site:st.com"

# 传感器数据手册
"BME280 datasheet site:bosch-sensortec.com"
"MPU-6050 datasheet site:invensense.tdk.com"

# 无线芯片
"nRF52840 product specification site:nordicsemi.com"
```

## 使用时机

### 何时激活
- 用户需要芯片或传感器的官方技术文档
- 需要查看寄存器定义、引脚功能、时序参数
- 需要传感器校准算法、补偿公式
- 用户说"查一下这个芯片的资料"、"有没有xxx的手册"

### 何时不激活
- 用户需要的是代码示例或驱动实现（使用 peripheral-driver）
- 用户需要的是通用开发知识而非特定芯片文档

### 边界
- **不下载**受版权保护的完整手册（仅获取必要的技术章节）
- **不修改**用户已有的本地文档
- **不替代**厂商官网的官方文档版本管理
