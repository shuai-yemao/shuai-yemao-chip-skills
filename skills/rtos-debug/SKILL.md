---
name: rtos-debug
description: RTOS 感知调试工具，支持 FreeRTOS/ThreadX/RT-Thread。通过 GDB+OpenOCD 查看任务列表、栈水印、堆状态、死锁分析、HardFault 寄存器解析。当用户调试 FreeRTOS/ThreadX/RT-Thread、遇到死锁/栈溢出/看门狗复位/优先级反转/HardFault、需要查看任务列表或堆分析时使用。
version: "1.0.0"
---

# rtos-debug

RTOS 感知调试工具，支持 FreeRTOS / ThreadX / RT-Thread。
通过 GDB + OpenOCD 获取任务列表、栈使用情况、信号量/队列状态，
辅助定位死锁、栈溢出、优先级反转等 RTOS 级 Bug。

## 触发条件
- 用户调试 FreeRTOS / ThreadX / RT-Thread 项目
- 用户遇到任务死锁、栈溢出、看门狗复位
- 用户需要查看当前所有任务状态
- 用户遇到 vTaskSwitchContext 断言失败
- 用户说"任务列表"
- 用户说"堆分析"
- 用户说"优先级反转"
- 用户说"HardFault 排查"

## 参数收集
- rtos: RTOS 类型，freertos / threadx / rtthread（默认 freertos）
- elf: 固件 .elf 文件路径（必填，含调试符号）
- openocd_cfg: OpenOCD 配置文件路径
- device: MCU 型号
- interface: SWD 或 JTAG
- analysis: 分析模式，all（默认）/ tasks / heap / deadlock / hardfault（按需分析）
- save_report: 是否保存分析报告到文件（默认 false）
- rtos_port: FreeRTOS 移植类型（ARM_CM4F / ARM_CM3 / ARM_CM0，影响栈帧解析）

## 执行流程

### Step 1 检查调试符号
确认 .elf 文件包含 DWARF 调试信息：
```bash
arm-none-eabi-readelf -S firmware.elf | grep debug
```

### Step 2 启动 OpenOCD（带 RTOS 感知）
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "init" -c "reset halt"
```
OpenOCD 会自动识别 FreeRTOS 任务列表（通过 pxCurrentTCB 符号）。

### Step 3 连接 GDB 并加载 RTOS 脚本
```bash
arm-none-eabi-gdb -x rtos_debug.gdb firmware.elf
```

GDB 脚本 rtos_debug.gdb 内容：
```
target remote :3333
monitor reset halt
set print pretty on
# FreeRTOS: 打印任务列表
info threads
# 打印当前任务TCB
print *pxCurrentTCB
# 查看任务堆栈水印
call uxTaskGetStackHighWaterMark(pxCurrentTCB)
```

### Step 4 分析任务状态
自动执行以下分析：
1. 列出所有任务（名称、状态、优先级、栈剩余）
2. 检测栈使用率 > 80% 的任务（溢出风险）
3. 检测处于 Blocked 状态超过预期的任务（死锁嫌疑）
4. 打印就绪队列和延迟任务列表

### Step 5 输出报告

```
═══════════ RTOS 任务状态 (FreeRTOS) ═══════════
任务名称        状态      优先级  栈剩余  栈使用率
─────────────────────────────────────────────
IDLE            Running    0     312B    38%
TaskComm        Blocked    3     128B    ⚠️87%  ← 栈溢出风险！
TaskSensor      Ready      2     512B    50%
TaskDisplay     Suspended  1     256B    25%
─────────────────────────────────────────────
⚠️  警告: TaskComm 栈剩余仅 128B，建议增大栈空间
```

## 常见 RTOS Bug 诊断

### 栈溢出
- 症状：随机崩溃、HardFault、IDLE 任务异常
- 诊断：检查 configCHECK_FOR_STACK_OVERFLOW，查看任务栈水印
- 修复：增大任务 usStackDepth 参数

### 死锁
- 症状：所有任务 Blocked，系统冻结
- 诊断：检查每个 Blocked 任务等待的资源
- 修复：统一锁的获取顺序，启用互斥锁超时

### 优先级反转
- 症状：高优先级任务被低优先级任务阻塞
- 诊断：查看 Blocked 任务等待的互斥锁持有者
- 修复：启用优先级继承（configUSE_MUTEXES = 1）

## HardFault 分析

HardFault 通常由非法内存访问、除零、未对齐访问或栈溢出引发。

### 读取 Fault 状态寄存器
```gdb
# 读取 CFSR 寄存器（Configurable Fault Status Register）
monitor reg CFSR
# 读取 BFAR（Bus Fault Address Register）
monitor reg BFAR
# 读取 MMFAR（MemManage Fault Address Register）
monitor reg MMFAR
# 解析栈帧（LR=0xFFFFFFF9 表示使用 MSP）
info frame
x/8xw $sp
```

### CFSR 位字段含义
| 位域 | 名称 | 含义 |
|------|------|------|
| [0]  | IACCVIOL | 指令访问违例（MemManage） |
| [1]  | DACCVIOL | 数据访问违例（MemManage） |
| [8]  | IBUSERR  | 指令总线错误（BusFault） |
| [9]  | PRECISERR | 精确数据总线错误，BFAR 有效 |
| [10] | IMPRECISERR | 非精确总线错误 |
| [16] | UNDEFINSTR | 未定义指令（UsageFault） |
| [17] | INVSTATE | 无效状态（EPSR.T=0 执行 Thumb） |
| [24] | DIVBYZERO | 除零错误 |
| [25] | UNALIGNED | 非对齐访问 |

### LR 值与栈指针对照
- `LR = 0xFFFFFFF9`：返回到 Thread 模式，使用 MSP
- `LR = 0xFFFFFFFD`：返回到 Thread 模式，使用 PSP（任务栈）
- `LR = 0xFFFFFFF1`：返回到 Handler 模式，使用 MSP

## 堆内存分析

### FreeRTOS 堆状态查询
```gdb
print xFreeBytesRemaining
print xMinimumEverFreeBytesRemaining
call vPortGetHeapStats(...)
```

- `xFreeBytesRemaining`：当前剩余堆字节数
- `xMinimumEverFreeBytesRemaining`：历史最小剩余堆（泄漏检测指标），若持续缩小则存在内存泄漏

### heap_5 多段堆查询
```gdb
# 查看 HeapRegion 配置
print xHeapRegions
# 查看链表头
print xStart
print pxEnd
```

## RT-Thread 专项命令

### 查找内核对象
```gdb
# 按名称查找对象（thread / semaphore / mutex / event / mailbox / messagequeue / mempool / timer）
call rt_object_find("object_name", RT_Object_Class_Thread)
```

### 当前线程信息
```gdb
# 获取当前运行线程指针
call rt_thread_self()
# 打印线程控制块
print *rt_current_thread
```

### 系统节拍
```gdb
# 获取当前系统节拍计数
call rt_tick_get()
print rt_tick
```

### RT-Thread 线程状态枚举
| 值 | 宏名 | 含义 |
|----|------|------|
| 0x00 | RT_THREAD_INIT | 初始态 |
| 0x01 | RT_THREAD_READY | 就绪 |
| 0x02 | RT_THREAD_SUSPEND | 挂起/阻塞 |
| 0x03 | RT_THREAD_RUNNING | 运行 |
| 0x04 | RT_THREAD_BLOCK | 阻塞（同 SUSPEND） |
| 0x05 | RT_THREAD_CLOSE | 关闭 |
| 0x06 | RT_THREAD_STAT_MASK | 状态掩码 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| pxCurrentTCB 符号不存在 | 未链接 FreeRTOS 或编译缺 -g | 确认 FreeRTOS 源码已编译链接，且编译带调试符号 |
| RTOS 未被 OpenOCD 识别 | OpenOCD 版本过旧或配置缺失 | 检查 OpenOCD 版本，手动加载 `rtos/FreeRTOS.cfg` |
| 任务列表为空 | vTaskStartScheduler() 未调用 | 确认系统启动流程中调用了调度器启动函数 |
| Cannot access memory | 目标板已复位 | 重新执行 `monitor reset halt` 后重试 |
| No symbol table | .elf 编译时未加 -g | 重新编译带调试信息后再连接 |
| GDB connection refused | OpenOCD 未启动或端口被占用 | 检查 :3333 端口是否可用，确认 OpenOCD 进程运行中 |
| RTOS type detection failed | 非标准符号命名 | 通过 `--rtos` 参数显式指定 RTOS 类型 |
| Stack high watermark unavailable | FreeRTOS 配置缺 configUSE_TRACE_FACILITY | 在 FreeRTOSConfig.h 中启用该宏 |

## 边界定义

### 不该激活
- 用户的项目不是基于 RTOS（裸机/bare-metal）→ RTOS 感知调试无符号可查
- 用户只需要通用的 GDB 断点/单步调试（非 RTOS 特定分析）→ 使用 `debug-gdb-openocd`
- 用户的 .elf 文件不含调试符号（编译未加 -g）→ 无法解析 RTOS 数据结构
- 用户的项目使用的是未支持的 RTOS（如 Zephyr、embOS、TI-RTOS、Azure RTOS 但非 ThreadX 分支）

### 不该做
- **禁止**对不含 .elf 符号的 HEX/BIN 文件执行 RTOS 调试
- **禁止**修改目标板的 RTOS 内核变量（如修改 pxCurrentTCB、任务栈大小）
- **禁止**在目标板运行中执行可能破坏任务上下文的 GDB 命令

### 不该碰
- **不触碰** RTOS 内核源码：只读取符号，不修改
- **不触碰** OpenOCD 的 RTOS 配置文件：通过 GDB 脚本访问，不修改 OpenOCD 配置
- **不触碰** 目标板的系统节拍（SysTick）配置

## 输出约定

RTOS 调试完成后输出：
- 任务列表（名称/状态/优先级/栈剩余/栈使用率）
- 栈溢出风险警告（栈使用率 > 80% 的任务）
- 死锁嫌疑任务检测
- HardFault 寄存器解析结果（CFSR/HFSR/BFAR）
- 堆内存分析（剩余/最小剩余/Fragmentation）
- 保存为分析报告（可选）

## 交接关系

- 上游：`debug-gdb-openocd`（启动 GDB 会话后调用此 skill）
- 下游：`freertos-module`（发现 RTOS 配置问题后调整 FreeRTOSConfig）
- 辅助：`arm-core-registers`（CFSR/HFSR 进一步寄存器级分析）
- 当需要检查 RTOS 源码配置时：`freertos-module`
