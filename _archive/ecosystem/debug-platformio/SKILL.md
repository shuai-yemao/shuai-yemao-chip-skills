---
name: debug-platformio
description: 当需要通过 PlatformIO 内置调试功能对目标板进行 GDB 调试时使用，支持下载暂停、附加和崩溃现场分析。当用户提到 PlatformIO 调试、pio debug、PlatformIO GDB、PIO 在线调试时使用。
version: "1.0.0"
---

# PlatformIO 调试

## 适用场景

- `Project Profile` 中标明 `build_system: platformio` 或工作区中存在 `platformio.ini`。
- 用户需要对目标板进行在线调试（单步、断点、查看寄存器和变量）。
- 需要分析崩溃现场（HardFault 寄存器、调用栈）。

## 必要输入

- PlatformIO 工程目录（包含 `platformio.ini`）。
- 可选的环境名称和调试模式。

## 自动探测

- 自动定位 `pio` CLI。
- 解析 `platformio.ini` 中的 `debug_tool` 配置。
- PlatformIO 自动管理调试服务器（OpenOCD/pyOCD/J-Link GDB Server），无需手动配置。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次操作。
2. 探测调试环境：
   ```bash
   python scripts/pio_debugger.py --detect --project-dir <工程目录> --env <环境名>
   ```
3. 执行调试：
   ```bash
   python scripts/pio_debugger.py --project-dir <工程目录> --env <环境名> --mode download-and-halt
   ```

## 调试模式

- `download-and-halt`：下载固件到目标板，暂停在入口点，输出寄存器和回溯信息。
- `attach-only`：附加到正在运行的目标，不下载固件，输出当前状态。
- `crash-context`：暂停目标，读取寄存器、完整回溯和 Cortex-M Fault 寄存器（CFSR/HFSR/MMFAR/BFAR）。

## 失败分流

- `connection-failure`：调试器未连接或设备无响应。
- `debug-not-supported`：板卡不支持调试或未配置 debug_tool。
- `debug-failure`：调试会话异常终止。

## 输出约定

示例输出格式：

```
调试完成 ✅
  工程: ESP32_DEV → 环境: esp32dev
  板卡: esp32dev | 调试工具: esp-prog
  模式: download-and-halt
  关键观察: 5 条（寄存器、回溯帧）
```

## 边界定义

### 不该激活
- 工程不是 PlatformIO 工程（无 platformio.ini）
- 工程中使用的是 OpenOCD/GDB 直接调试 → 优先用 `debug-gdb-openocd`
- 用户只需要烧录 → 使用 `flash-platformio`
- platformio.ini 中未配置 debug_tool（板卡不支持调试）

### 不该做
- **禁止**修改 platformio.ini 中的 debug_tool 或 debug_init_break 配置
- **禁止**在板卡不支持调试时静默跳过（必须报 debug-not-supported）
- **禁止**在 crash-context 模式中修改目标板状态（仅读取寄存器）

### 不该碰
- **不触碰** platformio.ini：只读取，不修改
- **不触碰** PlatformIO 自动管理的调试服务器配置

## 交接关系

- 从 `build-platformio` 接收编译成功的工程信息。
- 调试发现问题后可回交给 `build-platformio` 修改代码重新编译。
