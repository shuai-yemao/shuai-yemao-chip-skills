---
name: flash-jlink
description: 使用 J-Link 调试探针烧录嵌入式固件。支持 .hex/.bin/.elf，SWD/JTAG 接口，自动生成 Commander 脚本，多探针 SN 选择，目标板供电，全片擦除，仅校验模式。当用户提到 J-Link 烧录、JLinkExe、Segger、nRF52840、nRF5340、GD32 烧录时使用。
version: "1.0.0"
---

# flash-jlink

使用 J-Link 调试探针烧录嵌入式固件（支持 .hex / .bin / .elf）。
调用 JLinkExe 命令行工具，自动生成烧录脚本并执行，支持 SWD / JTAG 接口，内建自动重试与多探针管理。

## 触发条件
- 用户提到使用 J-Link 烧录固件
- 用户提到 JFlash、JLinkExe、Segger 烧录
- 当前工程探针配置为 J-Link
- 用户提到 "nRF 烧录"（如 nRF52840、nRF5340 等 Nordic 芯片）
- 用户提到 "GD32"（兆易创新 GD32 系列 MCU）
- 用户提到 "多核芯片烧录"（如 nRF5340 双核、STM32H7 双核等）

## 使用前提
- 已安装 SEGGER J-Link Software（JLinkExe 在 PATH 中）
- J-Link 探针已连接目标板

## 参数收集
在执行前必须确认以下参数（可从工程文件自动推断）：
- `device`: 目标 MCU 型号（如 STM32F103C8、nRF52840）
- `interface`: 调试接口 SWD 或 JTAG（默认 SWD）
- `speed`: 接口速度 kHz（默认 4000）
- `firmware`: 固件文件路径（.hex/.bin/.elf）
- `addr`: 烧录起始地址（.bin 文件必填，.hex/.elf 自动解析）
- `erase`: 烧录前是否全片擦除（默认 false，避免误删 Bootloader 等数据，确有需要时才启用）
- `verify_only`: 仅校验不烧录（true 时只执行 verify/verifybin，不写入 Flash）
- `sn`: 多 J-Link 并联时指定探针序列号（对应 -SelectEmuBySN，不填则自动选唯一在线探针）
- `power`: 是否通过 J-Link 向目标板供 3.3V（true 时脚本开头插入 `power on`，对应 -SetVTarget 3300，仅部分探针型号支持）

## 执行流程

### Step 0 枚举已连接 J-Link
```bash
JLinkExe -ListEmulatorsId
```
- 若返回 **0 个探针** → 报错，见"No emulator found"处理方案。
- 若返回 **1 个探针** → 自动使用，无需用户干预。
- 若返回 **≥2 个探针** → 打印序列号列表，要求用户通过 `--sn` 指定目标探针序列号后再继续。

### Step 1 验证工具
```bash
JLinkExe -version
```
失败则提示用户安装 SEGGER J-Link Software。

### Step 2 生成烧录脚本
根据固件格式生成 JLink commander 脚本（以全擦、供电、指定 SN 为例）：
```
power on
si SWD
speed 4000
device STM32F103C8
connect
h
erase
loadfile firmware.hex
r
go
exit
```
- 若 `erase=false`（默认），省略 `erase` 行。
- 若 `verify_only=true`，用 `verifybin` / `verify` 替换 `loadfile` / `loadbin`，并省略 `erase`。
- 若 `power=false`（默认），省略 `power on` 行。

### Step 3 执行烧录
```bash
# 不指定 SN
JLinkExe -nogui 1 -commandfile flash_script.jlink

# 指定探针序列号（多 J-Link 并联场景）
JLinkExe -nogui 1 -SelectEmuBySN 123456789 -commandfile flash_script.jlink
```

### Step 4 结果判断
- 输出包含 "Flash download: Bank 0" 或 "O.K." → 烧录/校验成功
- 输出包含 "ERROR" / "Could not connect" → 按错误分级处理
- 烧录成功后输出耗时（秒）及 Flash 写入速度（KB/s）

## 错误处理
| 错误 | 原因 | 解决方案 |
|------|------|---------|
| Could not connect | 接线/供电问题 | 检查 SWD 线序，确认目标板供电 |
| Wrong device | MCU 型号不匹配 | 重新确认 device 参数 |
| Flash timeout | Flash 算法不支持 | 更新 J-Link SDK 或换 OpenOCD |
| Protected device | 读写保护 | 提示用户先解除保护（不可自动执行）|
| RTT: Failed to connect | 目标板时钟配置异常 | 检查目标板系统时钟初始化是否正确，确认 HSE/PLL 配置，或降低接口速度后重试 |
| Firmware file not found | 固件路径含中文或空格 | 将固件文件移至纯英文、无空格的路径下再重试 |
| No emulator found | J-Link 未被系统识别 | 检查 USB 连接是否牢固，并确认已安装 SEGGER J-Link USB 驱动（Windows 可在设备管理器中查看）|

## 边界定义

### 不该激活
- 用户的目标板是 **ESP32/ESP8266** 系列 → 应使用 `flash-idf` / `flash-platformio`
- 用户没有 J-Link 探针（如使用 ST-Link、DAP-Link、CMSIS-DAP）→ 应使用 `flash-openocd`
- 用户明确提到 Keil MDK 的"Download"按钮 → 应使用 `flash-keil`
- 用户只需要**查询** J-Link 信息而不执行烧录（如 `--list` 枚举探针）→ 轻量场景，仅枚举不烧录
- 用户未连接目标板硬件（仅做离线分析或代码审查）

### 不该做
- **禁止**在未确认目标 MCU 型号的情况下生成烧录命令
- **禁止**未经用户确认即执行全片擦除（`erase` 默认为 false）
- **禁止**对带读保护（RDP Level 1/2）的芯片静默执行烧录，必须先提示用户解除保护
- **禁止**使用 `--power` 供电时跳过目标板电流检测（过大电流可能损坏 J-Link）
- **禁止**对 .bin 文件在无 `--addr` 参数时猜测烧录地址（0x08000000 也不是通用值）

### 不该碰
- **不触碰** Option Bytes：烧录 flash 区域，不修改 RDP/WRP/BOR 等系统配置
- **不触碰** Bootloader 分区：除非用户明确指定地址覆盖
- **不触碰** 非当前 SN 指定探针的其他 J-Link 连接
- **不触碰** 固件源文件：只读取，绝不修改

## 输出约定
烧录成功后汇报：
- 固件文件路径
- 目标 MCU 型号
- 烧录接口与速度
- Flash 写入字节数
- 烧录耗时（秒）
- Flash 写入速度（KB/s）

## 交接关系

- 上游：`build-keil` / `build-cmake` / `build-platformio`（烧录前需先编译）
- 下游：`serial-monitor` / `rtt-monitor`（烧录后查看日志验证运行状态）
- 烧录失败时：`option-bytes`（检查 RDP 保护位）
- 工作流中：`workflow`（编译→烧录→监控全自动流水线）
