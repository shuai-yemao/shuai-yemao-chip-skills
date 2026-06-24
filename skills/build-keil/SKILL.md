---
name: build-keil
description: 当需要通过 Keil MDK 命令行编译嵌入式工程，调用自带脚本解析工程文件、执行构建并定位固件产物时使用。当用户提到 Keil 编译、MDK 编译、UV4 编译、ARMCC、ARMCLANG、build Keil、编译报错、固件编译时使用。
version: "1.0.0"
---

# 构建 Keil MDK 工程

通过 Keil MDK 命令行工具（UV4.exe）编译嵌入式工程，自动解析 .uvprojx 工程文件，执行构建并定位固件产物。

## 适用场景

- 需要通过命令行编译 Keil MDK 工程（非手动点 IDE 按钮）
- 需要集成到自动化流水线（工作流/GitHub Actions）
- 编译报错需要定位文件行号
- 需要查看特定 Target 的编译结果

## 必要输入

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--project` | .uvprojx 工程文件路径 | 必填（自动扫描时可选）|
| `--target` | 工程 Target 名 | 从工程文件解析 |
| `--uv4-path` | UV4.exe 路径 | 自动检测 |
| `--list-targets` | 列出所有可用 Target | 可选（仅列举不编译）|
| `--log` | 编译日志输出路径 | 控制台输出 |

## 依赖

- Windows 平台（Keil MDK 仅 Windows）
- UV4.exe（ARMCC/ARMCLANG 编译器）
- Keil MDK 工程文件 .uvprojx
- 有效的 Keil MDK License

## 执行步骤

### Step 0 环境检查
```bash
# 检查 UV4.exe 可用性
python scripts/keil_builder.py --detect
```

### Step 1 编译工程
```bash
python scripts/keil_builder.py --project app.uvprojx --target "TargetName"
```

### Step 2 列出可用 Target
```bash
python scripts/keil_builder.py --project app.uvprojx --list-targets
```

### Step 3 指定 UV4 路径（自动检测失败时）
```bash
python scripts/keil_builder.py --project app.uvprojx --uv4-path "G:/keil5/core/UV4/UV4.exe"
```

### Step 4 编译后查看产物
编译成功后在输出目录查找 .hex/.axf 文件，供 `flash-keil` 使用。

## 失败分流

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| UV4.exe not found | Keil MDK 未安装或路径未配置 | 确认安装路径，通过 `--uv4-path` 指定 |
| Build error(s) | 编译报错，含具体文件:行 | 定位报错位置，分析根因后修复 |
| Target not found | 指定 Target 名称不匹配 | 用 `--list-targets` 列出所有可用 Target |
| License error | Keil MDK 授权过期或未激活 | 检查 FlexNet/License 状态 |
| ARMCC not available | ARM Compiler 5 未安装 | 安装 ARMCC 或切换到 ARMCLANG |
| .uvprojx not found | 路径指向非工程文件 | 确认 .uvprojx 文件路径正确 |
| Cannot open project | 工程文件格式异常或编码问题 | 检查 .uvprojx XML 格式完整性 |
| Unlicensed tool | 评估模式限制（代码 > 32KB） | 激活有效 License |

## 输出约定

编译成功后输出：
- 编译耗时（秒）
- 错误/警告计数
- 固件产物路径（.hex/.axf）
- 各 Target 的编译状态

## 边界定义

### 不该激活
- 用户需要 IAR 编译 → 使用 `build-iar`
- 用户需要 CMake + GCC 编译 → 使用 `build-cmake`
- 用户需要 PlatformIO 编译 → 使用 `build-platformio`
- 用户需要 ESP-IDF 编译 → 使用 `build-idf`
- 用户只需要烧录不需编译 → 使用 `flash-keil`

### 不该做
- **禁止**修改工程文件（.uvprojx / .uvoptx）
- **禁止**在编译失败时报错但不清除中间产物（避免缓存不一致）
- **禁止**修改编译器选项或优化级别
- **禁止**删除或移动用户的源文件

### 不该碰
- **不触碰** Keil MDK 安装目录和 License 文件
- **不触碰** 非当前工程的其他 .uvprojx
- **不触碰** 用户的源码文件（只读）
- **不触碰** Target 板的 Flash/RAM（编译阶段）

## 交接关系

- 下游：`flash-keil`（编译 → 烧录）
- 辅助：`map-analyzer`（编译后分析 .map 文件）
- 报错时：`arm-core-registers` / `mcu-peripheral-registers`（编译不报错但运行异常时查寄存器）
- 工作流中：`workflow`（全自动编译→烧录→监控流水线）

## 相关脚本

| 脚本 | 功能 |
|------|------|
| `scripts/keil_builder.py` | 编译工程、扫描产物、环境探测 |
| `scripts/keil_reg_reader.py` | 通过 J-Link 读取内存/外设寄存器 |
| `scripts/keil_rtt_analyzer.py` | 解析 J-Link RTT 日志 |
| `scripts/keil_map_analyzer.py` | 由 `map-analyzer` skill 提供 |
