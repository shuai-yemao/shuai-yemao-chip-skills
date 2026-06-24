---
name: freertos-module
version: "1.0.0"
description: "FreeRTOS 嵌入式实时操作系统开发指南。涵盖任务管理（创建/删除/优先级/栈）、队列/信号量/互斥锁/事件组/任务通知、软件定时器、中断安全 API、临界区、tick 管理、栈溢出检测、内存管理方案、调试技巧与常见陷阱。当用户提到 FreeRTOS、任务、队列、信号量、互斥锁、事件组、任务通知、软件定时器、临界区、中断安全 API、RTOS、xTaskCreate、vTaskDelay、xQueueSend、xSemaphoreGive、xEventGroupSetBits、xTaskNotifyGive、FreeRTOSConfig、configTICK_RATE_HZ、栈溢出、vApplicationStackOverflowHook、FreeRTOS 调试、任务优先级、优先级反转、死锁、tick、portYIELD、cmsis_os、FreeRTOS 内存管理、heap_1/2/3/4/5 时使用。"
---

# FreeRTOS 模块开发指南

> API 速查见 `references/freertos-api-quickref.md`（所有 API 的 ISR 安全性/阻塞行为速查表）

## 核心概念

### FreeRTOS 架构

```
Application Tasks
     ↕
FreeRTOS Kernel (tasks.c, queue.c, timers.c, event_groups.c, ...)
     ↕
portable layer (port.c, portmacro.h) — 硬件相关
     ↕
Hardware (Cortex-M NVIC/SysTick/FPU)
```

### 配置入口

```c
// FreeRTOSConfig.h 中的关键配置
#define configUSE_PREEMPTION          1     // 抢占式调度
#define configCPU_CLOCK_HZ           100000000 // HCLK 频率
#define configTICK_RATE_HZ           1000    // 1ms tick (常用)
#define configMAX_PRIORITIES          5      // 优先级数量
#define configMINIMAL_STACK_SIZE      128    // 最小任务栈 (word)
#define configTOTAL_HEAP_SIZE         (10 * 1024)  // 堆大小
#define configUSE_IDLE_HOOK           0      // 空闲任务钩子
#define configUSE_TICK_HOOK           0      // tick 钩子
#define configCHECK_FOR_STACK_OVERFLOW 2    // 栈溢出检测
#define configUSE_MALLOC_FAILED_HOOK  1     // malloc 失败钩子

#define INCLUDE_vTaskDelay            1      // API 裁剪
#define INCLUDE_xSemaphoreTake        1
#define INCLUDE_xQueueSend            1
#define INCLUDE_vTaskDelete           1
// ...
```

## 任务管理

### 任务创建

```c
// 动态创建（栈由 FreeRTOS 从堆分配）
TaskHandle_t xTask1Handle = NULL;

void vTask1(void *pvParameters)
{
    for (;;) {
        // 任务主循环
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void main(void)
{
    xTaskCreate(
        vTask1,             // 任务函数
        "Task1",            // 任务名称
        256,                // 栈大小 (单位: word = 4 字节)
        NULL,               // 参数
        1,                  // 优先级
        &xTaskHandle        // 句柄
    );
    vTaskStartScheduler();  // 启动调度器
}

// 静态创建（栈由用户提供）：
#define STACK_SIZE 256
StackType_t xTaskStack[STACK_SIZE];
StaticTask_t xTaskBuffer;

TaskHandle_t xHandle = xTaskCreateStatic(
    vTask, "Task", STACK_SIZE,
    NULL, 1, xTaskStack, &xTaskBuffer
);
```

### 任务状态

```
Running    ← 正在执行（同一时间只有一个任务）
Ready      ← 就绪，等待调度器选择
Blocked    ← 等待事件/时间（延时、队列、信号量、事件组）
Suspended  ← 手动挂起 (vTaskSuspend)
```

### 任务优先级

```c
// CubeMX 中: 优先级值越小优先级越低（与 NVIC 相反）
#define IDLE_PRIORITY     0
#define LOW_PRIORITY      1
#define MEDIUM_PRIORITY   2
#define HIGH_PRIORITY     3
#define ISR_HIGH_PRIORITY 4

// 优先级反转示例：
// 低优先级 (1) 持有互斥锁 → 中优先级 (2) 抢占 → 高优先级 (3) 等锁被中优先级阻断
// 解决：使用优先级继承的互斥锁 (xSemaphoreCreateRecursiveMutex)
```

### 任务栈

```c
// 推荐栈大小经验值：
// 裸机主循环:           128 words (512 bytes)
// 简单任务(无printf):    200 words (800 bytes)
// 带printf/格式化输出:   400 words (1.6 KB)
// 带 LCD 文字输出:       512 words (2 KB)
// 调用深层函数:          需要估算

// 栈溢出检测（configCHECK_FOR_STACK_OVERFLOW = 2）：
void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName)
{
    // 方法 1: 检测栈指针是否越界（较慢但准确）
    // 方法 2: 查看任务栈末尾的标记是否被覆盖
    // 触发时在此断点
    printf("[!] Stack overflow: %s\n", pcTaskName);
    for (;;);
}
```

## 队列

```c
// 创建队列（可容纳 10 个 int 值）
QueueHandle_t xQueue = xQueueCreate(10, sizeof(int));

// 发送（中断安全版）
int data = 42;
xQueueSend(xQueue, &data, portMAX_DELAY);       // 任务中
xQueueSendFromISR(xQueue, &data, NULL);           // 中断中

// 接收
int received;
if (xQueueReceive(xQueue, &received, pdMS_TO_TICKS(1000)) == pdPASS) {
    // 收到数据
} else {
    // 超时
}

// 队列集 (Queue Set) — 同时等待多个队列
QueueSetHandle_t xSet = xQueueCreateSet(5);
xQueueAddToSet(xQueue1, xSet);
xQueueAddToSet(xQueue2, xSet);

QueueSetMemberHandle_t member = xQueueSelectFromSet(xSet, portMAX_DELAY);
uint32_t val;
xQueueReceive(member, &val, 0);
```

## 信号量与互斥锁

### 二值信号量

```c
// 用于 ISR → Task 同步
SemaphoreHandle_t xSem = xSemaphoreCreateBinary();

// ISR 中给出：
void EXTI0_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    xSemaphoreGiveFromISR(xSem, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);  // 如果唤醒了更高优先级的任务
}

// 任务中等待：
void vTask(void *pvParameters)
{
    for (;;) {
        xSemaphoreTake(xSem, portMAX_DELAY);  // 等待信号量
        // 处理事件
    }
}
```

### 计数信号量

```c
// 资源计数器，最大 5 个资源
SemaphoreHandle_t xSem = xSemaphoreCreateCounting(5, 5);  // 初始可用 5 个

// 申请资源：xSemaphoreTake
// 释放资源：xSemaphoreGive
```

### 互斥锁（带优先级继承）

```c
// 互斥锁 vs 二值信号量：
// 互斥锁 = 二值信号量 + 优先级继承（解决优先级反转）
// 互斥锁必须在同一个任务中 take/release（不可在 ISR 中使用）
// 二值信号量可在任意上下文 give，但无优先级继承

SemaphoreHandle_t xMutex = xSemaphoreCreateMutex();

// 访问共享资源
xSemaphoreTake(xMutex, portMAX_DELAY);
// 写共享变量...
xSemaphoreGive(xMutex);

// 递归互斥锁（同一个任务可多次 take，必须相同次数 give）
SemaphoreHandle_t xRMutex = xSemaphoreCreateRecursiveMutex();
xSemaphoreTakeRecursive(xRMutex, portMAX_DELAY);
xSemaphoreGiveRecursive(xRMutex);
```

## 事件组

```c
// 适用于：一个任务等待多个事件（任意/全部）
// 事件位: 每个 bit 代表一个事件

EventGroupHandle_t xEventGroup = xEventGroupCreate();

#define BIT_TEMP_READY    (1 << 0)
#define BIT_HUMID_READY   (1 << 1)
#define BIT_ALARM          (1 << 2)

// 任务等待 TEMP_READY 或 HUMID_READY（任意一个）
void vTask(void *pvParameters)
{
    EventBits_t bits = xEventGroupWaitBits(
        xEventGroup,
        BIT_TEMP_READY | BIT_HUMID_READY,  // 等待的 bit
        pdTRUE,         // 等待到后自动清除
        pdFALSE,        // 任意一个满足就返回 (true=全部满足)
        portMAX_DELAY
    );

    if (bits & BIT_TEMP_READY) handle_temp();
    if (bits & BIT_HUMID_READY) handle_humid();
}

// ISR 中设置事件位
xEventGroupSetBitsFromISR(xEventGroup, BIT_TEMP_READY, NULL);
```

## 任务通知

```c
// 任务通知比信号量/事件组更快（直接操作 TCB，不经过队列）
// 每个任务有 32 位通知值 + 8 种操作模式

// 发送通知：
xTaskNotifyGive(xTaskHandle);  // 通知值 +1（类似二值信号量）
// 或：
xTaskNotify(xTaskHandle, 0x01, eSetBits);  // 设 bit 0（类似事件组）

// 接收通知：
uint32_t ulNotifiedValue;
xTaskNotifyWait(0, ULONG_MAX, &ulNotifiedValue, portMAX_DELAY);

// 限制：
// - 只能一对一通知（不能广播）
// - 接收方必须在 Blocked 状态等待
// - 通知值只能存一个值
```

## 软件定时器

```c
// 软件定时器基于 FreeRTOS 的 Timer Daemon 任务
// 精度受 tick 周期限制（默认 1ms）

// 创建：
TimerHandle_t xTimer = xTimerCreate(
    "Timer",                    // 名称
    pdMS_TO_TICKS(1000),        // 周期 (1s)
    pdTRUE,                     // 自动重载 (pdFALSE = 单次)
    NULL,                       // 定时器 ID
    vTimerCallback              // 回调函数
);

void vTimerCallback(TimerHandle_t xTimer)
{
    // 在定时器守护任务上下文中执行
    // 回调中不可使用阻塞 API（vTaskDelay, xQueueReceive 等）
    // 回调应快速执行，不可长时间运行
}

// 启动/停止：
xTimerStart(xTimer, 0);
xTimerStop(xTimer, 0);

// 修改周期：
xTimerChangePeriod(xTimer, pdMS_TO_TICKS(500), 0);
```

## 中断管理

### ISR 中可用的 FreeRTOS API

```c
// ISR 中使用带 FromISR 后缀的 API
// FromISR 函数需要传递 BaseType_t *pxHigherPriorityTaskWoken
// 如果 After function, xHigherPriorityTaskWoken = pdTRUE → 调用 portYIELD

void EXTI0_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;

    // 允许：
    xQueueSendFromISR(xQueue, &data, &xHigherPriorityTaskWoken);
    xSemaphoreGiveFromISR(xSem, &xHigherPriorityTaskWoken);
    xTaskNotifyGiveFromISR(xTaskHandle, &xHigherPriorityTaskWoken);
    xEventGroupSetBitsFromISR(xEventGroup, BIT_0, &xHigherPriorityTaskWoken);

    // 禁止（会导致断言或死锁）：
    // ❌ xQueueReceive / xSemaphoreTake / xTaskDelay / vTaskDelay
    // ❌ xSemaphoreGive(xMutex)  — 互斥锁不可在 ISR 中使用

    // 在中断末尾：
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}
```

### 临界区

```c
// 方式 1: 调度器加锁（禁止任务切换，不禁中断）
// 适合保护多个任务之间的共享变量
taskENTER_CRITICAL();
// 访问共享变量...
taskEXIT_CRITICAL();

// 方式 2: 中断加锁（禁止所有中断 + 任务切换）
// 适合 ISR 和任务共享的变量
taskENTER_CRITICAL_FROM_ISR();
// 访问共享变量...
taskEXIT_CRITICAL_FROM_ISR(0);

// 临界区注意事项：
// 1. 临界区应尽量短（μs 级）
// 2. 临界区内不可调用阻塞 API
// 3. 临界区嵌套安全（FreeRTOS 内嵌计数）
```

## Tick 与时间管理

### tick 配置

```c
// configTICK_RATE_HZ = 1000  → 1ms tick
// configTICK_RATE_HZ = 100   → 10ms tick（省电，精度更低）

// 延时函数对比：
vTaskDelay(pdMS_TO_TICKS(100));    // 阻塞 100 tick（最少 100ms）
vTaskDelayUntil(&xLastWakeTime, pdMS_TO_TICKS(100));  // 精确周期（消除积累误差）
```

### vTaskDelay 积累误差

```c
// ❌ 有积累误差：
void vTask(void *pvParameters)
{
    for (;;) {
        do_something();
        vTaskDelay(pdMS_TO_TICKS(100));  // do_something 耗时 + 100ms
    }
    // 实际周期 = elapsed_ms + 100ms → 逐渐漂移
}

// ✅ 无积累误差（vTaskDelayUntil）：
void vTask(void *pvParameters)
{
    TickType_t xLastWakeTime = xTaskGetTickCount();
    for (;;) {
        do_something();
        vTaskDelayUntil(&xLastWakeTime, pdMS_TO_TICKS(100));
    }
    // 始终每 100ms 触发一次，忽略 do_something 耗时
}
```

## 内存管理

### heap 方案对比

| 方案 | 适用场景 | 释放 | 碎片 | 大小 |
|------|---------|------|------|------|
| heap_1 | 不删除任务 | 不支持 | 无 | 最小 |
| heap_2 | 大小相近的分配 | 支持 | 有 | 小 |
| heap_3 | 标准 malloc/free 包装 | 支持 | 取决于 libc | — |
| heap_4 | 通用（合并相邻空闲块） | 支持 | 少 | 适中 |
| heap_5 | 多不连续内存区 | 支持 | 少 | 大 |

```c
// heap_4 最常用：HeapRegion 只需定义起始地址 + 大小
// configTOTAL_HEAP_SIZE → 总堆大小

// heap_5 多区域示例：
const HeapRegion_t xHeapRegions[] = {
    { (uint8_t *)0x20000000, 0x18000 },  // SRAM1: 96KB
    { (uint8_t *)0x20018000, 0x8000 },   // SRAM2: 32KB
    { NULL, 0 }  // 终止
};
vPortDefineHeapRegions(xHeapRegions);
```

## 调试技巧

```c
// 1. 任务列表
// 在断点处调用 vTaskList 或 vTaskGetRunTimeStats：
char infoBuffer[1024];
vTaskList(infoBuffer);
printf("Task\tState\tPrio\tStack\tNum\n");
printf("%s\n", infoBuffer);

// 2. 栈余量监控
UBaseType_t stack_hwm = uxTaskGetStackHighWaterMark(xTaskHandle);
printf("Stack remaining: %u words\n", stack_hwm);
// 定期检查，若 < 20 → 接近溢出

// 3. 运行时统计（需 configGENERATE_RUN_TIME_STATS = 1）
// 在 CubeMX 中使能后：
vTaskGetRunTimeStats(infoBuffer);
printf("Task\tCPU%%\tTime\n%s\n", infoBuffer);

// 4. 断言定位
// configASSERT 宏触发 HardFault：
// #define configASSERT(x) if(!(x)) { taskDISABLE_INTERRUPTS(); for(;;); }
// 在 HardFault_Handler 中查看 LR=0xFFFFFFF9 → 任务栈
```

## 常见陷阱

| 编号 | 现象 | 根因 | 解决 |
|------|------|------|------|
| 1 | HardFault 后定位不到原因 | 栈溢出（检测未开启） | 开启 `configCHECK_FOR_STACK_OVERFLOW = 2` |
| 2 | 高优先级任务不运行 | 低优先级任务未释放信号量 | 检查优先级反转 — 改用互斥锁 |
| 3 | ISR 中调用 xSemaphoreTake 死机 | ISR 中用了阻塞 API | 改用 FromISR 版 API |
| 4 | vTaskDelay 不准，越来越慢 | vTaskDelay 累计执行时间误差 | 改用 `vTaskDelayUntil` |
| 5 | xQueueSend 一直返回 errQUEUE_FULL | 队列满且接收任务未运行 | 增大队列或检查接收任务优先级 |
| 6 | 互斥锁在 ISR 中使用 → 断言 | 互斥锁不可在 ISR 中使用 | 改用二值信号量 |
| 7 | 软件定时器回调执行慢 | 回调中调用了阻塞 API | 定时器回调只做标志，耗时的留在任务中 |
| 8 | malloc 返回 NULL | 堆空间不足/碎片化 | 增大堆或用 heap_4 + 静态分配 |
| 9 | 任务不按优先级运行 | 同优先级任务轮转，时间片不够 | 提优先级；降低同优先级任务数 |
| 10 | 临界区内死锁 | 临界区中调用了阻塞 API | 临界区只做快速操作 |

## 系列差异

| 特性 | F1 (Cortex-M3) | F4 (M4F) | H7 (M7) |
|------|---------------|---------|---------|
| SysTick 时钟 | HCLK/8 | HCLK | HCLK |
| BASEPRI 屏蔽 | 支持 | 支持 | 支持 |
| FPU 自动保存 | 无 | 需使能 LSP | 需使能 LSP |
| configMAX_SYSCALL_INTERRUPT_PRIORITY | 5 (推荐) | 5 (推荐) | 5 (推荐) |

```c
// H7 FPU 上下文保存设置（CubeMX 自动配置）：
// #define configUSE_TASK_FPU_SUPPORT  1  // 保存/恢复 FPU 寄存器
// FPU 上下文切换增加 ~100 words 栈开销
```

## 边界定义

## 平台差异

FreeRTOS 本身跨平台，但不同芯片的移植层有细微差异：

| 平台 | Tick 源 | 最大优先级 | 内存管理 | 特色 |
|------|---------|-----------|---------|------|
| STM32(HAL) | SysTick(1ms) | 可配(默认 32) | heap_4 | `HAL_IncTick` 配合 |
| ESP-IDF | LAC timer(1ms) | 25 | heap_4 + 多堆 | 深度定制 FreeRTOS |
| GD32 | SysTick | 同 STM32 | heap_4 | 与 STM32 基本一致 |
| CH32V(RISC-V) | 机器定时器 | 可配 | heap_4 | mtime/mtimecmp 替代 SysTick |

**ESP-IDF FreeRTOS 差异**（常见踩坑）：
- `vTaskDelay` 单位: 1 tick = 10ms (configTICK_RATE_HZ=100)，非 STM32 默认的 1ms
- `xTaskCreatePinnedToCore` 创建时需要指定运行核
- 中断优先级: ESP32 中断分成 1-5 级，`portMAX_INTERRUPT_PRIORITY` 行为不同
- `esp_timer` 是硬件定时器，不占用 FreeRTOS 定时器组

- **不覆盖 cmsis_os v1/v2 封装层** — 那是 HAL 层 API，本 skill 直接使用原生 FreeRTOS API
- **不覆盖 Amazon FreeRTOS (AFR)/FreeRTOS+TCP** — 高级网络套件，单独立项
- **不覆盖低功耗 tickless 模式** (`configUSE_TICKLESS_IDLE`) — 需要外部定时器
- 与 `rtos-debug` 互补：本 skill 覆盖**开发阶段**配置；`rtos-debug` 覆盖**运行中**的调试分析
- 与 `embedded-code-reviewer-framework` 互补：后者审查 RTOS 代码的安全性
