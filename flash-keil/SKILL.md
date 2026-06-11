---
name: flash-keil
description: 当需要通过 Keil MDK 烧录编译产物到目标 MCU 时使用。支持 .hex/.axf 文件通过 J-Link 烧录。与 build-keil 配合形成完整的 Keil 编译→烧录工作流。当用户提到 Keil 烧录、MDK 下载、UV4 烧录、J-Link 配合 Keil、编译后烧录、flash-keil 时使用。
version: "1.0.0"
---

# Keil MDK 固件烧录

通过 Keil MDK 构建系统烧录编译产物到目标 MCU，支持 .hex/.axf 文件。
与 `build-keil` 配合形成完整的 Keil 编译→烧录工作流。

## 适用场景

- 已通过 `build-keil` 完成编译，需要烧录产物到目标板验证
- 有一份已编译好的 .hex/.axf 文件需要烧录
- 需要验证烧录结果（校验模式）
- 需要指定 J-Link 探针或烧录地址

## 必要输入

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--project` | .uvprojx 工程文件路径 | 必填（自动扫描时可选）|
| `--target` | 工程 Target 名 | 自动检测 |
| `--hex` | 直接指定 hex 文件（跳过工程解析） | 可选 |
| `--device` | MCU 型号 | 从工程自动解析 |
| `--jlink-sn` | J-Link 序列号（多探针时必填） | 自动选唯一探针 |
| `--addr` | 烧录起始地址（.bin 文件必填） | 自动从 .hex 解析 |

## 依赖

- Windows 平台
- J-Link 驱动（`JLink.exe` 在 PATH 中）
- J-Link 调试器硬件已连接目标板
- Keil MDK 生成的 .uvprojx 工程文件

## 执行步骤

### Step 0 环境检查
```bash
JLinkExe -version
```
确认 J-Link 驱动可用，否则提示安装 SEGGER J-Link Software。

### Step 1 工程解析（自动模式）
```bash
python scripts/keil_flasher.py --project app.uvprojx --target "Release"
```
自动解析工程输出目录，定位 .hex/.axf 文件。

### Step 2 直接指定 hex（跳过工程解析）
```bash
python scripts/keil_flasher.py --hex Build/app.hex --device STM32F411CE
```

### Step 3 指定 J-Link 探针
```bash
python scripts/keil_flasher.py --project app.uvprojx --jlink-sn 69701612
```

### Step 4 编译后直接烧录
```bash
python ../build-keil/scripts/keil_builder.py --project app.uvprojx --target "Release"
python scripts/keil_flasher.py --project app.uvprojx --target "Release"
```

## 失败分流

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| JLink.exe not found | J-Link 驱动未安装 | 安装 SEGGER J-Link Software |
| No hex/axf found | 工程未编译或输出路径错误 | 先运行 build-keil 编译 |
| Cannot connect to target | J-Link 未连接或 SWD 引脚冲突 | 检查接线、供电、Option Bytes |
| Flash download failed | 保护位或地址冲突 | 检查 RDP/PCROP，尝试全片擦除 |
| Verification failed | 烧录后校验不一致 | 检查时钟配置、供电稳定性 |

## 输出约定

烧录成功后输出：
- 固件文件路径
- 目标 MCU 型号
- 烧录接口与速度
- 烧录耗时（秒）
- Flash 写入状态（成功/校验通过）

## 边界定义

### 不该激活
- 用户没有 J-Link 探针（使用 ST-Link/OpenOCD）→ 使用 `flash-openocd`
- 用户使用 PlatformIO 平台 → 使用 `flash-platformio`
- 用户使用 ESP-IDF 平台 → 使用 `flash-idf`
- 用户只需要编译不烧录 → 使用 `build-keil`

### 不该做
- **禁止**在未确认目标 MCU 型号时执行烧录
- **禁止**未经用户确认执行全片擦除
- **禁止**对带读保护（RDP Level 1/2）的芯片静默烧录
- **禁止**使用 `--jlink-sn` 时探针序列号与实际不匹配

### 不该碰
- **不触碰** Option Bytes（RDP/WRP/BOR 等系统配置）
- **不触碰** Bootloader 分区
- **不触碰** 非当前探针的其他 J-Link 连接
- **不触碰** 固件源文件

## 交接关系

- 上游：`build-keil`（编译 → 烧录）
- 下游：`serial-monitor` / `rtt-monitor`（烧录后查看日志）
- 烧录失败时：`option-bytes`（检查保护位）
