---
name: peripheral-driver
description: 当需要为外部设备（传感器、存储器、显示屏等）开发 BSP 驱动时使用。提供开源驱动搜索策略、质量评估、代码适配工具和常见设备适配要点。当用户提到外设驱动、传感器驱动、BSP、设备驱动、SPI 驱动、I2C 驱动、驱动移植、添加新外设时使用。
version: "1.0.0"
---

# 外设驱动开发（基于开源库适配）

## 适用场景

- 需要为外部设备（传感器、存储器、显示屏等）开发 BSP 驱动
- 想找到成熟的开源驱动库并适配到项目的 BSP 架构中
- 已有开源驱动代码，需要重命名、整理、注入 HAL handle 以符合项目规范
- 设备较简单，不需要开源库，需要生成 BSP 骨架文件快速起步
- 需要对现有 BSP 代码做面向对象封装

## 依赖

- Python 3.8+（仅标准库，无外部包依赖）
- 目标设备的开源驱动库（搜索时需联网）
- STM32 HAL 工程（生成的 BSP 代码需要 HAL 环境）

## BSP 层定位（分层架构中的位置）

`peripheral-driver` skill 产生的代码对应分层架构中的 **BSP 层**（板级外设驱动层）。

架构参考：`embedded-architect/references/layered-architecture-model.md`

```mermaid
flowchart LR
    APP[APP 业务逻辑] --> OS[OS RTOS内核]
    OS --> BSP[BSP 板级外设 ← 本 skill]
    BSP --> CORE[Core MCU外设封装]
    CORE --> DRV[Driver 硬件抽象/HAL]
```

### BSP 层编码规则

| 规则 | 说明 |
|------|------|
| **接口隔离** | BSP 驱动**只能调用 Core 层 API**（如 `I2C_Read/Write`、`UART_Send`），不能直接调 HAL 或操作寄存器 |
| **禁止跨层** | BSP 文件不能 `#include` Driver 层头文件（`stm32f4xx_hal.h`） |
| **业务语义** | BSP 函数名要体现器件功能（`MPU6050_ReadTemperature`），而不是总线操作（`I2C_ReadBytes`） |
| **板级相关** | 同一芯片的不同板卡需独立 BSP 适配（引脚不同） |
| **换芯片无关** | BSP 层代码在换 MCU 系列时无需修改（因为 Core 层接口不变） |

### 面向对象模式（BSP 层推荐）

```c
// ── 1. 封装：头文件只暴露接口，隐藏实现细节 ──
// BSP/Inc/mpu6050.h
void MPU6050_Init(void);
float MPU6050_ReadTemperature(void);
void MPU6050_ReadAccel(float *x, float *y, float *z);

// BSP/Src/mpu6050.c
static uint8_t i2c_addr = 0x68;  // 私有，外部不可见

// ── 2. 多态：同一接口不同传感器 ──
typedef struct {
    void (*init)(void);
    float (*read_temperature)(void);
    float (*read_humidity)(void);
} SensorDriver_t;

const SensorDriver_t DHT22_Driver = { DHT22_Init, DHT22_ReadTemp, DHT22_ReadHum };
const SensorDriver_t SHT30_Driver = { SHT30_Init, SHT30_ReadTemp, SHT30_ReadHum };
```

### BSP 层典型文件结构

```
BSP/
├── Inc/
│   ├── mpu6050.h          # 公开接口声明
│   ├── w25q128.h          # 公开接口声明
│   └── ssd1306.h          # 公开接口声明
├── Src/
│   ├── mpu6050.c          # 实现（只调 Core 层 I2C API）
│   ├── w25q128.c          # 实现（只调 Core 层 SPI API）
│   └── ssd1306.c          # 实现（只调 Core 层 I2C/SPI API）
└── docs/
    └── device-adaptation.md  # 器件适配要点（本 skill 的参考文档）
```

---

- 需要为外部设备（AT24C02、MPU6050、SSD1306 等）开发 BSP 驱动。
- 想找到成熟的开源驱动库并适配到项目的 BSP 架构中。
- 已有开源驱动代码，需要重命名、整理、注入 HAL handle 以符合项目规范。
- 设备较简单，不需要开源库，需要生成 BSP 骨架文件快速起步。

## 必要输入

- 目标设备名称（如 `AT24C02`、`MPU6050`）。
- 通信总线类型（I2C / SPI / UART / 1-Wire / GPIO）。
- HAL handle 名称（如 `hi2c1`、`hspi2`），通常来自 CubeMX 生成的代码。
- 可选：设备 I2C 地址、已下载的开源驱动目录路径。

## 自动探测

- 脚本 `--scan` 模式自动分析输入目录中的 C/H 文件，识别函数签名、HAL 调用模式、命名风格和 include 依赖。
- `--list-devices` 模式列出 `device-adaptation.md` 中已记录的设备和推荐库。
- 如果目标设备在 `device-adaptation.md` 中有记录，直接提供推荐库和适配要点。

## 执行步骤

1. 确认目标设备和总线类型。如果设备在 [references/device-adaptation.md](references/device-adaptation.md) 中有记录，直接参考推荐库和适配要点。
2. 阅读 [references/search-and-evaluate.md](references/search-and-evaluate.md)，按搜索策略在 GitHub/Gitee 上寻找候选开源驱动库。
3. 按评估清单对候选库打分，选择最合适的库。如果没有合适的库，跳到步骤 6。
4. 下载选定的开源库代码到本地临时目录。
5. 运行 `--scan` 分析开源代码，查看适配建议报告：
   ```bash
   python3 scripts/bsp_adapter.py --scan ./downloaded_driver/
   ```
6. 执行适配（二选一）：
   - **有开源库**：运行 `--adapt` 将代码适配到 BSP 规范：
     ```bash
     python3 scripts/bsp_adapter.py \
       --adapt ./downloaded_driver/ \
       --device <device_name> --handle <hal_handle> \
       --output ./Hardware/bsp_<device>/
     ```
   - **无合适库**：运行 `--scaffold` 生成 BSP 骨架文件：
     ```bash
     python3 scripts/bsp_adapter.py \
       --scaffold --device <device_name> --bus <bus_type> \
       --handle <hal_handle> --addr <i2c_addr> \
       --output ./Hardware/bsp_<device>/
     ```
7. 将生成的 BSP 文件集成到 `main.c` 的 USER CODE 区域，参考脚本输出的集成指南。
8. 编译验证，交给 `build-*` skill。

### OOP 骨架生成（推荐）

对于 GPIO 类设备（LED、继电器、蜂鸣器等），支持 `--oop` 标志生成面向对象风格的 BSP 代码：

```bash
python3 scripts/bsp_adapter.py \
  --scaffold --device led --bus gpio --handle NULL \
  --output ./Hardware/bsp_led/ \
  --oop
```

**OOP 模式与默认模式对比**：

| 维度 | 默认模式 | OOP 模式 (`--oop`) |
|------|---------|-------------------|
| 封装 | struct 暴露在 .h | 不透明句柄 (struct 在 .c) |
| 跨层 | 直接调 HAL | Core 层 GPIO 桥接 |
| 方法 | 泛型 ReadData/WriteData | 语义化 On/Off/Toggle |
| 实例管理 | 单实例 | 静态注册表 (最多 8 实例) |
| 有效电平 | 硬编码高电平亮 | active_level 参数可配 |
| NULL 安全 | 无检查 | 全方法 NULL 保护 |

> **⚠️ OOP 可读性说明**: 不透明句柄隐藏了实现细节, 新接手的人看不到"内部是什么"。
> 因此 OOP 驱动需要比过程式代码多 3~5 倍的注释来解释"为什么这样做"。
> 生成的 OOP 代码已内置完整的中文设计决策注释。
> 完整的 OOP 使用与维护指南见: `references/oop-usage-guide.md`

参考实现：[bsp_led.c 示例](file:///D:/zhuomian/KEIL+Arduino+Vscode/Keil+STM32cubeMx/STM32F411CEU6/EmbeddedProject-Folder-Template-main/04_Software/01_Source_Code/06_LED_V1/BPS/LED/bsp_led.c)

> **流水线集成**: 使用 `--oop` 生成 BSP 后，运行 `add-peripheral` 流水线会自动触发 OOP 合规检查步骤 (`oop-check`)。

驱动架构设计和实现最佳实践参考 [stm32-hal-development/references/peripheral-driver-guide.md]({USER_HOME}/work/open-git/em_skill/skills/stm32-hal-development/references/peripheral-driver-guide.md)。

## 失败分流

- 当搜索不到任何可用的开源驱动库时，使用 `--scaffold` 生成骨架并提示用户参考规格书手动实现。
- 当开源库使用裸寄存器操作或非 STM32 平台 API 时，返回 `project-config-error`，建议手动适配通信层。
- 当开源库许可证为 GPL 或无许可证时，提醒用户许可证风险，建议寻找替代库或自行实现。
- 当适配后编译失败时，交给 `build-*` skill 处理构建错误。

## 平台说明

- 自带脚本使用 Python 标准库（`os`、`re`、`pathlib`、`argparse`），无额外依赖。
- 生成的 C 代码遵循 STM32 HAL BSP 规范，兼容 GCC、IAR、Keil 工具链。
- 路径格式遵循 [platform-compatibility.md]({USER_HOME}/work/open-git/em_skill/shared/platform-compatibility.md)。

## 输出约定

- `--scan` 输出适配建议报告：检测到的函数、HAL 调用、命名风格、适配难度评估。
- `--adapt` 输出适配后的 BSP 文件和 `main.c` 集成指南。
- `--scaffold` 输出符合 BSP 模板规范的骨架文件。
- `--list-devices` 输出已记录设备的推荐库和适配难度。
- 所有模式的详细用法见 [references/usage.md](references/usage.md)。

## 边界定义

### 不该激活
- 用户只需要查阅 MCU 内置外设（GPIO、UART、SPI、I2C、TIM）的 HAL 用法 → 使用 `stm32-hal-development`
- 用户的目标平台不是 STM32（而是 ESP32、nRF、GD32 等非 HAL 平台）
- 用户需要的是驱动手动实现（不需搜索开源库）→ 直接使用 `stm32-hal-development` 的 BSP 模板
- 用户只是问"有没有 XX 传感器的驱动"而不需要实际适配到工程

### 不该做
- **禁止**下载和使用 GPL 许可证的开源库（可能污染商业项目）
- **禁止**在无许可证评估的情况下直接推荐开源库并集成
- **禁止**在适配过程中修改开源库的核心算法逻辑（仅修改通信层和命名）
- **禁止**自动覆盖用户已有的 BSP 文件

### 不该碰
- **不触碰**非目标设备的 BSP 文件
- **不触碰** CubeMX 生成的外设初始化代码（main.c 中的 USER CODE 区域之外）
- **不触碰**第三方开源库的 LICENSE 文件

## 交接关系

- 上游：`stm32-hal-development`（提供方法论和 BSP 模板）。
- 下游：`build-cmake`、`build-iar`、`build-keil`（编译验证）。
