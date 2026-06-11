# Workflow 流水线 Skill 用法

## 基础用法

```bash
# 探测环境（检查各 skill 脚本是否存在）
python scripts/workflow_runner.py --detect

# 列出可用 workflow
python scripts/workflow_runner.py --list

# 编译 + 烧录 + 串口监控（PlatformIO）
python scripts/workflow_runner.py --run build-flash-monitor --build-system platformio --project /path/to/project

# 编译 + 烧录 + GDB 调试（Keil）
python scripts/workflow_runner.py --run build-flash-debug --build-system keil --project /path/to/project.uvprojx

# 编译 + 烧录 + 串口监控（CMake + OpenOCD）
python scripts/workflow_runner.py --run build-flash-monitor --build-system cmake --project /path/to/source --flash-interface stlink --flash-target stm32f4x

# 指定串口和波特率
python scripts/workflow_runner.py --run build-flash-monitor --build-system platformio --project /path --port {SERIAL_PORT} --baud 115200

# 指定构建目标
python scripts/workflow_runner.py --run build-flash-monitor --build-system platformio --project /path --target esp32dev

# 手动指定产物路径（跳过自动推断）
python scripts/workflow_runner.py --run build-flash-debug --build-system cmake --project /path --artifact /path/build/app.elf

# 仅打印命令，不实际执行
python scripts/workflow_runner.py --run build-flash-monitor --build-system platformio --project /path --dry-run

# 详细输出
python scripts/workflow_runner.py --run build-flash-monitor --build-system keil --project /path -v
```

## 参数说明

### 模式参数

| 参数 | 说明 |
| --- | --- |
| `--detect` | 探测环境，检查各 skill 脚本 |
| `--list` | 列出可用 workflow |
| `--run` | 执行指定 workflow |
| `--dry-run` | 仅打印命令 |

### 构建参数

| 参数 | 说明 |
| --- | --- |
| `--build-system` | 构建系统：keil、cmake、platformio |
| `--project` | 工程路径 |
| `--target` | 构建目标/环境/预设 |

### 烧录参数

| 参数 | 说明 |
| --- | --- |
| `--artifact` | 固件产物路径（可选，自动推断） |
| `--flash-interface` | OpenOCD 接口（如 stlink） |
| `--flash-target` | OpenOCD 目标（如 stm32f4x） |

### 监控参数

| 参数 | 说明 |
| --- | --- |
| `--port` | 串口（如 {SERIAL_PORT}） |
| `--baud` | 波特率 |

## 可用 Workflow

| 名称 | 步骤 | 说明 |
| --- | --- | --- |
| `build-flash-monitor` | 编译 → 烧录 → 串口监控 | 完整开发验证流程 |
| `build-flash-debug` | 编译 → 烧录 → GDB 调试 | 编译后直接进入调试 |

## 构建系统脚本映射

| 构建系统 | 编译 | 烧录 | 调试 | 监控 |
| --- | --- | --- | --- | --- |
| keil | keil_builder.py | keil_flasher.py | gdb_debugger.py | serial_monitor.py |
| cmake | cmake_builder.py | openocd_flasher.py | gdb_debugger.py | serial_monitor.py |
| platformio | platformio_builder.py | pio_flasher.py | pio_debugger.py | serial_monitor.py |

## 跨 Skill 边界冲突检查

### 独立检查模式

在正式执行流水线前，可单独运行冲突检查验证所有 skill 组合是否合法：

```bash
# 检查 keil 流水线
python scripts/workflow_runner.py --check --run build-flash-monitor --build-system keil

# 检查 cmake 流水线
python scripts/workflow_runner.py --check --run build-flash-debug --build-system cmake

# 检查 platformio 流水线
python scripts/workflow_runner.py --check --run build-flash-monitor --build-system platformio
```

### 自动检查（默认行为）

执行 `--run` 时自动运行冲突检查。检查失败（error 级别）会阻断流水线执行。

如需跳过检查（仅限调试场景，不推荐）：
```bash
python scripts/workflow_runner.py --run build-flash-monitor --build-system cmake --project /path --skip-conflict-check
```

### 检查维度与阻断级别

| 维度 | 阻断级别 | 说明 |
|------|---------|------|
| 构建系统未知 | **error** | build_system 不在 SCRIPT_MAP 中 |
| 步骤映射缺失 | **error** | steps 中有 SCRIPT_MAP 未覆盖的步骤 |
| PlatformIO + OpenOCD 调试 | **error** | debug-platformio 与 debug-gdb-openocd 不兼容 |
| Keil 跨平台 | warning | 非 Windows 平台执行 Keil 流程 |
| ESP32 + J-Link 探针 | warning | 提示确认 J-Link 固件支持 ESP32 |
| debug 无 build 前置 | warning | debug 步骤之前无 build（可能缺少 .elf） |

### 规则来源注释

CROSS_SKILL_RULES 中每条规则标注了来源 skill，如：
- `# 来源: flash-jlink SKILL.md "不该激活 → 用户的目标板是 ESP32/ESP8266 系列"`
- `# 来源: debug-platformio SKILL.md 与 debug-gdb-openocd SKILL.md 边界定义`

## 返回码

- `0`：流水线全部完成 / 冲突检查通过
- `1`：某步骤失败、参数错误、或冲突检查失败
