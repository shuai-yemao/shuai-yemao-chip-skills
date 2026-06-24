---
name: ozone-module
version: 1.0.0
type: tool
description: SEGGER Ozone 调试器与性能分析器使用指南——覆盖项目配置、源码调试、.jdebug 脚本自动化、Sampling Profiler 性能分析、Code Coverage 代码覆盖率、Power Profiling 功耗分析、Instruction Trace 指令追踪、RTT 集成、RTOS 感知调试。
keywords: [Ozone, SEGGER, J-Link, debugger, performance analyzer, profiling, code coverage, trace, jdebug, automation]
---

# Ozone 调试器与性能分析器

> SEGGER Ozone — 跨平台独立调试器 + 实时性能分析器，支持 ARM Cortex-M/RISC-V 嵌入式应用。

## 场景

| 场景 | 说明 |
|------|------|
| 源码级调试 | 加载任意工具链（GCC/IAR/ARMCC/Clang）的 ELF，进行 C/C++/Rust/汇编级调试 |
| 性能分析 | Sampling Profiler 定位热点函数、CPU 占用率分析 |
| 代码覆盖率 | 无需模拟器，在实机上统计函数/文件/指令级覆盖率 |
| 功耗分析 | 配合 J-Link 读取目标板功耗（50uA 分辨率，100kHz 采样率） |
| 指令追踪 | 配合 J-Trace 实现 ETM 指令流全量记录与回放 |
| RTT 调试 | 集成 SEGGER RTT 实时输出，替代串口日志 |
| RTOS 感知 | FreeRTOS/embOS/ThreadX 等 RTOS 任务状态、栈使用可视化 |
| 自动化测试 | .jdebug 脚本实现一键加载→运行→断点→导出报告 |
| 故障现场分析 | 指令追溯定位 HardFault 触发指令、Snapshot 保存/恢复现场 |

## 输入

| 项目 | 必需 | 说明 |
|------|------|------|
| ELF/HEX 文件 | Y | 目标固件镜像（需含调试符号） |
| MCU 型号 | Y | 如 STM32F407VG, STM32F411CE, ESP32-S3 等 |
| J-Link S/N | N | 多探针时指定序列号 |
| .jdebug 项目脚本 | N | 已有项目文件可直接加载 |
| SVD 文件 | N | CMSIS-SVD 外设寄存器描述（自动从 DFP 加载） |

## 依赖

- **Ozone**: `C:\Program Files\SEGGER\Ozone\Ozone.exe`
- **J-Link**: J-Link V9/V10/V11/V12 或 J-Trace PRO（部分高级功能要求 J-Trace PRO）
- **J-Link 软件**: V6.60f 或更高（建议最新版）
- **ELF 格式**: 支持 ELF（推荐）、HEX、Motorola S-Record
- **SVD**: CMSIS DFP 或手动指定 SVD 文件用于外设寄存器视图

## 步骤

### 1. 快速上手：加载并调试固件

```
1. 打开 Ozone
2. File → New Project Wizard
3. 选择目标 MCU 型号
4. 选择调试探针（J-Link / J-Trace / GDB Server）
5. 选择 ELF 文件（含调试符号的 .elf/.out/.axf）
6. 接口配置：SWD（默认）或 JTAG，速度建议 4MHz
7. 确认 → 项目自动下载并停在 main()
```

### 2. 项目文件 (.jdebug) 结构

Ozone 项目是一个 `.jdebug` 脚本文件（C 语言语法），包含所有配置：

```c
// Project.jdebug
void OnProjectLoad() {
  // 目标配置
  Device.Set("STM32F407VG");
  Linker.SetTargetDevice("STM32F407VG");

  // 探针配置
  JLink.SetDevice("STM32F407VG");
  JLink.SetHostIF("USB");
  JLink.SetSpeed(4000);               // 4 MHz

  // 接口模式
  Target.Connect("SWD");

  // 文件加载
  File.Open("Debug/Project.elf");
}

void OnStartupComplete() {
  // 启动完成后自动执行
  Debug.ReadIntoInstCache();          // 初始化指令缓存（RAM 调试必需）
  RTT.Enable();                       // 启用 RTT
}

void OnTargetHalt() {
  // 目标暂停时执行
}
```

### 3. 事件处理函数速查

| 函数 | 触发时机 | 典型用途 |
|------|----------|----------|
| `OnProjectLoad()` | 项目加载时 | 设备/探针/文件配置 |
| `OnStartupComplete()` | 目标启动完成 | 启 RTT/Data Sampling/指令缓存初始化 |
| `OnTargetStart()` | 目标开始运行 | 清除统计 |
| `OnTargetHalt()` | 目标暂停 | 记录 halt 原因 |
| `OnTargetDownload()` | 固件下载后 | 验证下载 |
| `OnSnapshotSave()` | 保存快照时 | 保存外设寄存器状态 |
| `OnSnapshotLoad()` | 加载快照时 | 恢复外设寄存器状态 |

### 4. 性能分析

#### Sampling Profiler（采样分析）
```
View → Code Profile → Start Sampling
```
- 目标运行时周期性采样 PC，统计各函数 CPU 占用率
- 无需 J-Trace，J-Link 即可工作
- 结果按函数/文件/指令分级显示，颜色编码标识热点

#### Code Coverage（代码覆盖率）
```
View → Code Profile → Coverage Mode
```
- 基于指令追踪（需 J-Trace PRO）统计哪些指令/分支被执行过
- 源码窗口以颜色标记：绿色=已覆盖，红色=未覆盖

#### Power Profiling（功耗分析）
```
View → Timeline
```
- 配合 J-Link 为目标供电时，实时读取功耗数据
- 50uA 分辨率，100kHz 采样率
- 功耗曲线与代码执行时序对齐显示

#### High-Speed Sampling（高速数据采样）
```
View → Data Sampling
```
- 100us 分辨率读取目标符号值
- 记录最大值/最小值/均值/变化频率
- 导出 CSV 做进一步分析

### 5. 指令追踪（需 J-Trace PRO）

```
View → Instruction Trace
View → Timeline
```

- **指令追溯**: 目标暂停后回放最近执行的指令，定位 HardFault 触发点
- **Timeline 视图**: 函数调用栈随时间变化图，测量函数耗时
- **流式追踪**（J-Trace PRO）: 全量记录所有执行指令，无缓冲区限制

### 6. RTT 集成

在 `.jdebug` 中启用 RTT：

```c
void OnStartupComplete() {
  RTT.Enable();     // 启用 RTT 通道 0
  // 或指定通道
  RTT.SetBuffer("Terminal", 0, "Up",  1024);
  RTT.SetBuffer("Terminal", 0, "Down", 64);
}
```

Ozone 启动后自动打开 RTT Terminal 窗口显示 `SEGGER_RTT_printf()` 输出。

### 7. RTOS 感知调试

#### FreeRTOS
- Ozone 自动检测 FreeRTOS，无需额外配置
- 在 `View → RTOS` 查看任务列表、栈使用率、状态

#### embOS
- 原生支持，Ozone 检测到 embOS 符号后自动启用

#### 手动配置
若自动检测失败，在 `.jdebug` 中指定：
```c
void OnProjectLoad() {
  RTOS.SetPlugin("FreeRTOS");
}
```

### 8. 命令行与自动化

#### 命令行启动
```bash
Ozone.exe -project Project.jdebug
Ozone.exe -project Project.jdebug -line 123    # 打开时定位到第 123 行
Ozone.exe -project Project.jdebug -cmd "Debug.Log"  # 启动后执行命令
```

#### 自动化测试脚本示例
```c
// autotest.jdebug
void OnProjectLoad() {
  Device.Set("STM32F407VG");
  JLink.SetDevice("STM32F407VG");
  JLink.SetSpeed(4000);
  Target.Connect("SWD");
  File.Open("Debug/Test.elf");
  // 设置断点
  Debug.SetBreakpoint("main");
  Debug.SetBreakpoint("Test_Run");
}

void OnBreakpoint() {
  if (Util.PCIsInFunc("main")) {
    Log("Hit main, continuing...");
    Debug.Go();
  } else if (Util.PCIsInFunc("Test_Run")) {
    Log("Test complete, saving coverage...");
    File.Save("CoverageReport.csv", Util.FormatSprintf(
      "Code Coverage Report\n"));

    // 导出覆盖率
    File.Save("coverage.txt", Target.GetCodeCoverage());
    Log("Coverage saved. Quitting.");
    Exit(0);
  }
}
```

### 9. Snapshot 快照（故障现场保存/恢复）

```c
// 保存快照
Debug.SaveSnapshot("crash.snapshot", "Full");

// 加载快照
Debug.LoadSnapshot("crash.snapshot");
```

支持自定义保存/恢复外设寄存器状态（GPIO 配置等复杂外设需在 `OnSnapshotSave`/`OnSnapshotLoad` 中手动处理）。

> **关于 `.jsnap` 格式**：Ozone 使用 `.snapshot` 格式保存快照（压缩二进制格式，含 Flash/RAM/寄存器/Trace/日志），**不能直接读取 `.jsnap` 文件**。
> `.jsnap` 是 J-Link Commander (`JLink.exe`) 的 `save` 命令输出的原生快照格式，两者不兼容。
> Ozone 的 `.snapshot` 文件只能由 Ozone 自身读写，且要求加载时的 ELF 文件与保存时的版本二进制一致。

### 10. 控制台命令速查

| 命令 | 说明 |
|------|------|
| `Debug.Go()` | 运行目标 |
| `Debug.Halt()` | 暂停目标 |
| `Debug.StepOver()` | 单步跳过 |
| `Debug.StepInto()` | 单步进入 |
| `Debug.StepOut()` | 单步跳出 |
| `Debug.SetBreakpoint("FuncName")` | 设置函数断点 |
| `Debug.SetBreakpoint(0x08001000)` | 设置地址断点 |
| `Debug.DeleteAllBreakpoints()` | 清除所有断点 |
| `Target.ReadU32(Addr)` | 读 32 位内存 |
| `Target.WriteU32(Addr, Value)` | 写 32 位内存 |
| `Target.GetReg("R0")` | 读寄存器 |
| `Target.SetReg("R0", 0x1234)` | 写寄存器 |
| `RTT.Enable()` | 启用 RTT |
| `File.Save("path", content)` | 保存文件 |
| `Util.Log(msg)` | 输出日志到控制台 |
| `Exit(code)` | 退出 Ozone |

## 错误处理

| 现象 | 根因 | 解决 |
|------|------|------|
| "Could not connect to J-Link" | USB 驱动问题/探针未插 | 检查 USB 连接，运行 JLink.exe 确认识别 |
| "Could not find device" | 工程 MCU 型号与目标不符 | 核对 Device.Set() 中的型号 |
| "Error reading target device" | SWD 速度过高/干扰 | 降低 JLink.SetSpeed() (4000→1000) |
| "Cannot load ELF file" | ELF 不兼容/格式错误 | 确认 ELF 为 ARM/RISC-V 格式，带调试符号 |
| "No source available" | ELF 不含调试符号/源码路径错 | 检查 `-g` 编译选项，附加源码搜索路径 |
| "RTT not found" | 目标未初始化 RTT | 确认有 SEGGER_RTT_Init() 调用，RTT.Enable() 在启动完成后 |
| "Trace data not available" | 无 ETM/无 J-Trace | Sampling Profiler 不需要 J-Trace，Code Coverage 需要 |

## 输出

| 输出 | 格式 | 说明 |
|------|------|------|
| Code Profile 报告 | CSV / 内嵌显示 | CPU 占用率按函数/文件/指令分级 |
| Coverage 报告 | CSV / 内嵌显示 | 覆盖率统计，红色/绿色代码标记 |
| Power Profile | Timeline 图形 | 功耗曲线与代码执行对齐 |
| Instruction Trace | 列表 + 源码关联 | 指令级执行历史回放 |
| Timeline | Mermaid 式时序图 | 函数调用栈随时间变化 |
| Snapshot | .snapshot 文件 | 故障现场完整保存 |
| Data Sampling | CSV / 统计面板 | 符号值采样数据，含最值/均值/频率 |

## 边界

- **不处理**：固件编译、烧录（由 build-keil/build-cmake/flash-keil 处理）
- **不处理**：J-Link 驱动安装/固件升级（由 flash-jlink 的 JLink Commander 处理）
- **不处理**：RTT 应用层移植（由 segger-rtt-module 处理）
- **Trace**：Code Coverage / Instruction Trace / Timeline 功能需要 J-Trace PRO（J-Link 不支持）
- **Power Profiling**：需要 J-Link 为目标供电（非独立供电场景）
- **Simulator**：Ozone V3.40+ 支持第三方探针和模拟器，但功能可能受限
- **RTOS 感知**：仅支持已启用 RTOS 插件的内核（FreeRTOS/embOS/ThreadX/Micrium 等）

## 交接关系

| 相邻 skill | 关系 |
|-----------|------|
| `segger-rtt-module` | Ozone 集成 RTT 输出，该 skill 负责 RTT 应用层移植 |
| `flash-jlink` | Ozone 依赖 J-Link，该 skill 负责 J-Link 驱动验证 |
| `embedded-debugger-framework` | Ozone 是五层诊断模型中的调试工具，该 skill 提供诊断方法论 |
| `arm-core-registers` | Ozone 实时查看内核寄存器，该 skill 提供寄存器速查参考 |
| `cmbacktrace-debug` | HardFault 定位可先用 CmBacktrace 自动分析，再用 Ozone 指令追溯确认 |
