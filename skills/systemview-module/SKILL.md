---
name: systemview-module
version: 1.0.0
type: tool
description: SEGGER SystemView 实时记录与可视化分析工具指南——覆盖目标端移植、RTT 连续录制、Timeline 任务调度分析、CPU 负载统计、中断/API 事件追踪、DataPlot 数据波形、多核可视化、录制文件 (.SVDat/.bin) 的保存与加载。
keywords: [SystemView, SEGGER, J-Link, RTOS, real-time, recording, tracing, timeline, profiling, FreeRTOS, embOS]
---

# SEGGER SystemView 实时记录与可视化分析

> SEGGER SystemView — 嵌入式系统实时行为记录与可视化分析工具，比传统调试器更深入洞察系统运行时行为。

## 场景

| 场景 | 说明 |
|------|------|
| RTOS 任务调度分析 | 查看任务切换时序、优先级抢占关系、任务执行时间分布 |
| 中断延迟排查 | 确认 ISR 触发频率、执行耗时、是否存在多余或过频繁的中断 |
| CPU 负载统计 | 各任务/ISR 占用 CPU 百分比，定位性能瓶颈 |
| 系统启动流程分析 | 录制从复位到 main 再到任务创建的全过程 |
| 死锁/优先级反转调试 | 结合 Timeline 和 Events 列表定位资源竞争 |
| 裸机中断分析 | 无 RTOS 系统下录制中断活动和用户事件 |
| 多核通信可视化 | 多核系统下核间通信事件时序对齐查看 |
| 功耗关联分析 | 将事件记录与功耗曲线关联（配合 Power Profiling） |
| 现场保存复现 | 录制保存为 `.SVDat` 文件，脱离硬件离线分析 |

## 输入

| 项目 | 必需 | 说明 |
|------|------|------|
| MCU 型号 | Y | 如 STM32F407VG, STM32F411CE 等 |
| 目标端集成 | Y | 工程中需包含 SystemView 目标模块 + RTT |
| RTOS 类型 | N | 支持的 RTOS 开箱即用（FreeRTOS/embOS/Zephyr 等），裸机也可 |
| J-Link 探针 | N | 连续录制需 J-Link + RTT，单次/事后模式无需 |
| .SVDat 文件 | N | 已有录制文件可直接加载离线分析 |

## 依赖

- **SystemView**: `C:\Program Files\SEGGER\SystemView\SystemView.exe`
- **J-Link 软件**: V6.60f 或更高（连续录制必需）
- **目标端源码**: [SEGGER GitHub - SystemView](https://github.com/SEGGERMicro/SystemView)
  - `SEGGER_SYSVIEW.c` / `.h` — 核心记录模块
  - `SEGGER_SYSVIEW_Config_<OS>.c` — RTOS 特定配置
  - `SEGGER_RTT.c` / `.h` — RTT 传输通道
- **ROM**: ~2 KB，**RAM**: ~600 Bytes（连续录制模式）
- **CPU 开销**: 200MHz Cortex-M4 上 10000 events/s 时 < 1%

## 步骤

### 1. 目标端集成

#### 1.1 复制源码到工程

从 [SEGGER GitHub](https://github.com/SEGGERMicro/SystemView) 或 `C:\Program Files\SEGGER\SystemView\Src\` 复制以下文件到工程：

```
Config/
  SEGGER_SYSVIEW_Config_FreeRTOS.c   // FreeRTOS 配置
  SEGGER_SYSVIEW_Config_embOS.c      // embOS 配置
  SEGGER_SYSVIEW_Config.c            // 通用/裸机配置
SEGGER/
  SEGGER_RTT.c
  SEGGER_RTT.h
  SEGGER_SYSVIEW.c
  SEGGER_SYSVIEW.h
  SEGGER_SYSVIEW_Conf.h
  SEGGER_SYSVIEW_ConfDefaults.h
  SEGGER_SYSVIEW_Int.h
```

#### 1.2 配置 SEGGER_SYSVIEW_Conf.h

```c
// SEGGER_SYSVIEW_Conf.h
#define SYSVIEW_APP_NAME        "MyProject"
#define SYSVIEW_DEVICE_NAME     "STM32F407VG"
#define SYSVIEW_TIMESTAMP_FREQ  168000000  // CPU 核心频率（Hz）
#define SYSVIEW_RTT_CHANNEL     1          // RTT 通道号（默认 1）
#define SYSVIEW_MAX_RESERVED_EVENTS 16     // 保留事件槽位
```

#### 1.3 FreeRTOS 集成

在 `SEGGER_SYSVIEW_Config_FreeRTOS.c` 中：

```c
void SEGGER_SYSVIEW_Conf(void) {
  SEGGER_SYSVIEW_Init(
    SYSVIEW_TIMESTAMP_FREQ,
    SYSVIEW_TIMESTAMP_FREQ / 1000,       // 时间戳频率
    &SEGGER_SYSVIEW_OS_API_FreeRTOS      // FreeRTOS API
  );
  SEGGER_SYSVIEW_Start();                // 启动录制
}
```

在 `main()` 中，创建完任务后调用：

```c
int main(void) {
  HAL_Init();
  SystemClock_Config();

  // 必须在 FreeRTOS 调度器启动后、但尽快调用
  SEGGER_SYSVIEW_Conf();

  // 创建任务...
  xTaskCreate(vTask1, "Task1", 256, NULL, 1, NULL);
  xTaskCreate(vTask2, "Task2", 256, NULL, 2, NULL);

  vTaskStartScheduler();
}
```

> **注意**：`SEGGER_SYSVIEW_Conf()` 必须在调度器启动后调用（即 `vTaskStartScheduler()` 之后），否则 FreeRTOS API 钩子尚未就绪。

#### 1.4 裸机/无 OS 集成

```c
#include "SEGGER_SYSVIEW.h"

void SEGGER_SYSVIEW_Conf(void) {
  SEGGER_SYSVIEW_Init(
    168000000,
    168000000 / 1000,
    0     // 无 OS API
  );
}

// 在 ISR 中手动记录中断事件
void EXTI0_IRQHandler(void) {
  SEGGER_SYSVIEW_RecordEnterISR();
  // ... ISR 处理 ...
  SEGGER_SYSVIEW_RecordExitISR();
}

// 用户自定义事件（如模块执行时间）
void MyModule_Process(void) {
  SEGGER_SYSVIEW_OnUserStart(0);  // 用户事件 ID 0
  // ... 模块处理 ...
  SEGGER_SYSVIEW_OnUserStop(0);
}
```

#### 1.5 记录 API 函数

| 函数 | 说明 |
|------|------|
| `SEGGER_SYSVIEW_Init(TimerFreq, TimeBaseFreq, pOSAPI)` | 初始化系统视图模块 |
| `SEGGER_SYSVIEW_Start()` | 开始录制事件 |
| `SEGGER_SYSVIEW_Stop()` | 停止录制事件 |
| `SEGGER_SYSVIEW_RecordEnterISR()` | 记录进入中断 |
| `SEGGER_SYSVIEW_RecordExitISR()` | 记录退出中断 |
| `SEGGER_SYSVIEW_OnUserStart(UserId)` | 用户事件开始计时 |
| `SEGGER_SYSVIEW_OnUserStop(UserId)` | 用户事件结束计时 |
| `SEGGER_SYSVIEW_SendTaskInfo(TaskInfo)` | 发送任务信息 |
| `SEGGER_SYSVIEW_Printf(Format, ...)` | 打印终端消息到 SystemView |

### 2. 录制操作

#### 2.1 连续录制（J-Link RTT）

```
1. 打开 SystemView
2. File → Record → Start Recording
3. 选择 MCU 型号
4. 配置 J-Link 连接：
   - 目标接口: SWD（默认）或 JTAG
   - 速度: ≥ 4 MHz（建议）
   - RTT Control Block: 默认自动扫描
5. 点击 OK → 开始实时录制
6. SystemView 自动读取 RTT 缓冲区并实时更新 Timeline
7. 停止：File → Stop Recording
```

> SystemView 可以与 Ozone/Keil 等调试器**同时连接**到同一目标（并行调试），但需保持 RTT 读取频率足够快。

#### 2.2 单次录制（非 RTT 模式）

```
1. 目标端配置单次录制模式
2. 运行目标直到缓冲区满
3. 暂停目标（调试器 halt）
4. 手动导出 RTT 缓冲区数据：
   - 读取 _SEGGER_RTT.aUp[1].pBuffer 地址
   - 读取 _SEGGER_RTT.aUp[1].WrOff 字节数
   - 导出为 .SVDat 或 .bin 文件
5. 在 SystemView 中 File → Load Recording 打开
```

#### 2.3 事后分析（Post-Mortem）

```
1. 目标端配置循环缓冲模式（默认）
2. 系统事件持续写入缓冲区，溢出时覆盖最旧数据
3. 故障发生后 halt 目标
4. 读取 RTT 附件缓冲区（含 wraparound 处理）：
   - 从 pBuffer + WrOff 到 buffer_end → 文件前半部分
   - 从 pBuffer 到 pBuffer + RdOff - 1 → 文件后半部分
5. 保存为 .bin 文件，SystemView 加载
```

### 3. 数据分析

#### Timeline 窗口
```
View → Timeline
```
- 每一行 = 一个上下文（任务/ISR/空闲）
- 颜色标识不同上下文，ISR 事件特殊标记
- 缩放/滚动查看细节，选中事件同步到 Events 和 CPU Load

#### Events 列表
```
View → Events List
```
- 显示所有录制事件的时间戳、类型、详情
- 事件过滤：可分别显示/隐藏 ISR、任务、API 调用、用户事件
- 上下文跳转：跳转到上一个/下一个同上下文事件

#### CPU Load 窗口
```
View → CPU Load
```
- 各任务/ISR 占用的 CPU 时间百分比
- 峰值/均值统计
- 识别 CPU 占用率最高的热点

#### Contexts 窗口
```
View → Contexts
```
- 每个上下文的统计信息：名称、类型、优先级、执行次数、总耗时
- 中断 ID 显示（如 SysTick = ID #15）

#### DataPlot 窗口（数据波形）
```
View → Data Plot
```
- 可视化用户定义变量（传感器数据、状态值等）
- 与 Timeline 同步，查看值随时间变化
- 窗口同步：选中某个时间点，所有窗口跳到同一位置

#### System 信息
```
File → System Information
```
- 录制概览：事件总数、峰值/平均事件频率
- 任务/中断/定时器统计汇总

### 4. 录制文件 (.SVDat) 管理

```
File → Save Recording    → 保存当前录制为 .SVDat
File → Load Recording    → 加载已有 .SVDat 或 .bin 文件
File → Recent Files      → 快速打开最近录制
```

- `.SVDat` = SystemView 原生格式（压缩二进制）
- `.bin` = 原始 RTT 缓冲区转储（也可加载）
- 离线分析：加载后无需连接 J-Link，无需目标硬件
- 保存时可附加元信息：标题、作者、描述

### 5. 支持多核录制

SystemView 支持多核系统中每个核心独立录制：
- 各核上下文分组显示
- 核间通信事件可视化
- 通过核复选框切换显示/隐藏

### 6. 命令行模式

```bash
SystemView.exe                         # 启动 GUI
SystemView.exe -record "config.svconf" # 自动加载配置并开始录制
SystemView.exe "recording.SVDat"       # 直接加载录制文件
```

## 错误处理

| 现象 | 根因 | 解决 |
|------|------|------|
| "No RTT Control Block found" | RTT 未初始化或地址扫描失败 | 确认 `SEGGER_RTT_Init()` 已调用；手动指定 RTT CB 地址 |
| "No SystemView data received" | 目标端 SYSVIEW 模块未启动 | 确认 `SEGGER_SYSVIEW_Conf()` 和 `SEGGER_SYSVIEW_Start()` 已调用 |
| "Target not connected" | J-Link 连接失败 | 检查 USB/驱动，确认 SWD 速度合适 |
| Timeline 显示空白 | 录制缓冲区太小或没事件 | 增大 `SYSVIEW_MAX_RESERVED_EVENTS` 或 RTT 上行缓冲区 |
| RTT 数据溢出 | 事件产生速度 > RTT 读取速度 | 提高调试接口速度（≥ 4MHz），增大 RTT 缓冲区 |
| FreeRTOS 无任务显示 | `SEGGER_SYSVIEW_Conf()` 在调度器启动前调用 | 必须在 `vTaskStartScheduler()` 之后调用 |
| 时间戳不准 | `SYSVIEW_TIMESTAMP_FREQ` 与 CPU 主频不匹配 | 核对 CPU 核心时钟频率配置 |
| SystemView 与调试器冲突 | SWD 共享冲突 | SystemView 和调试器不能同时占用 SWD 读取 RTT；先停止调试器再录 |

## 输出

| 输出 | 格式 | 说明 |
|------|------|------|
| Timeline 时序图 | 可视化窗口 | 上下文（任务/ISR）随时间变化的执行序列 |
| CPU Load 统计 | 百分比/柱状图 | 各任务/ISR 占用的 CPU 时间 |
| Events 事件列表 | 表格 | 带时间戳的事件详细记录 |
| Contexts 统计 | 表格 | 各上下文执行次数、总耗时、优先级 |
| DataPlot 波形 | 图形 | 用户变量随时间变化曲线 |
| System 信息 | 汇总面板 | 事件总数、频率、录制参数 |
| 录制文件 | .SVDat / .bin | 可保存、加载、分享（离线分析） |

## 边界

- **不处理**：源码级调试（由 Ozone 处理）
- **不处理**：代码覆盖率/指令追踪（由 Ozone/J-Trace 处理）
- **不处理**：功耗曲线（由 Ozone Power Profiling 处理）
- **不支持**：系统不提供 RTT 或无法读取内存时，只能单次/事后模式
- **时间戳精度**：最低 1 CPU cycle（取决于 `SYSVIEW_TIMESTAMP_FREQ` 配置）
- **连续录制**：仅限 J-Link RTT 支持的设备（Cortex-M 全系列 + Renesas RX）
- **RTOS 支持**：embOS/uC-OS-III/Micrium/FreeRTOS/NuttX/Zephyr/ThreadX 开箱即用。其他 RTOS 需手动添加钩子
- **裸机**：仅记录 ISR 活动和用户事件，无任务调度信息

## 交接关系

| 相邻 skill | 关系 |
|-----------|------|
| `segger-rtt-module` | SystemView 依赖 RTT 传输通道，该 skill 负责 RTT 移植和缓冲区配置 |
| `ozone-module` | Ozone 处理源码级调试和高级性能分析，SystemView 提供 RTOS 时序分析 |
| `freertos-module` | FreeRTOS + SystemView 集成时需理解 FreeRTOS 调度机制 |
| `embedded-debugger-framework` | 诊断方法论中 SystemView 用于"状态机"层系统行为分析 |
| `interrupt-optimization` | SystemView 发现中断频次/执行时间问题后，用该 skill 优化 |
