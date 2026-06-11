---
name: flash-platformio
description: 当需要通过 PlatformIO 烧录固件到目标板时使用，利用 platformio.ini 中的上传配置自动完成烧录。当用户提到 PlatformIO 烧录、pio run --target upload、pio upload、PlatformIO 下载时使用。
version: "1.0.0"
---

# PlatformIO 烧录

## 适用场景

- `Project Profile` 中标明 `build_system: platformio` 或工作区中存在 `platformio.ini`。
- 用户希望将编译产物烧录到目标板，利用 PlatformIO 内置的上传机制。
- 支持串口、JTAG、DFU 等多种上传协议，由 `platformio.ini` 中的 `upload_protocol` 决定。

## 必要输入

- PlatformIO 工程目录（包含 `platformio.ini`）。
- 可选的环境名称和上传端口。

## 自动探测

- 自动定位 `pio` CLI。
- 解析 `platformio.ini` 中的环境列表和 `upload_protocol`。
- 若未指定环境，使用 `default_envs` 或第一个环境。
- 可列出已连接设备帮助用户确认端口。

## 执行步骤

1. 先阅读 [references/usage.md](references/usage.md)，确认本次操作。
2. 对于常见场景，直接一次调用完成烧录：
   ```bash
   python scripts/pio_flasher.py --flash --project-dir <工程目录> --env <环境名>
   ```
3. 若需指定上传端口：
   ```bash
   python scripts/pio_flasher.py --flash --project-dir <工程目录> --env <环境名> --upload-port {SERIAL_PORT}
   ```
4. 读取脚本输出的烧录结果报告，关注成功/失败状态和证据。
5. 将烧录结果写回 `Project Profile`，推荐下一步 skill。

## 失败分流

- `connection-failure`：设备未连接、串口被占用或权限不足。
- `project-config-error`：板卡配置无效或环境名不存在。
- `upload-failure`：上传过程中出错。

## 输出约定

示例输出格式：

```
烧录成功 ✅
  工程: ESP32_DEV → 环境: esp32dev
  板卡: esp32dev | 平台: espressif32
  固件: firmware.bin (200.0 KB)
  耗时: 15.3 秒
```

- 成功后推荐 `serial-monitor`（查看串口输出）或 `debug-platformio`（在线调试）。
- 失败时输出失败分类和日志证据。

## 边界定义

### 不该激活
- 用户的工程不是 PlatformIO 工程（无 platformio.ini）
- 用户明确需要手动控制烧录参数（地址、接口类型等）而非依赖 platformio.ini 配置
- 用户的板卡 platformio.ini 中 upload_protocol 为自定义脚本（custom）→ 需用户手动执行
- 用户只需要编译不烧录 → 使用 `build-platformio`

### 不该做
- **禁止**在 `platformio.ini` 不存在或环境名无效时猜测配置
- **禁止**修改 platformio.ini 中的 upload_protocol 或 upload_port 配置
- **禁止**在多个串口候选时静默选择（必须列出并确认）

### 不该碰
- **不触碰** platformio.ini：只读取，不修改
- **不触碰** .pio/ 构建缓存目录中的中间文件
- **不触碰** PlatformIO 全局配置（~/.platformio/）

## 交接关系

- 从 `build-platformio` 接收编译成功的工程信息。
- 烧录成功后交给 `serial-monitor`（查看串口输出）或 `debug-platformio`（在线调试）。
