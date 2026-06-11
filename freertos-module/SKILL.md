---
name: freertos-module
version: "1.0.0"
description: "FreeRTOS 嵌入式实时操作系统开发指南。涵盖任务管理（创建/删除/优先级/栈）、队列/队列集/流缓冲区/消息缓冲区、信号量/互斥锁/优先级继承、事件组、任务通知、软件定时器、中断安全 API、临界区、tick 管理/vTaskDelayUntil 积累误差、栈溢出检测、heap_1~5 内存管理、Tickless 低功耗模式 (configUSE_TICKLESS_IDLE)、调试技巧(vTaskList/栈水位)、典型应用场景(ISR 卸载/生产者-消费者/多任务协作/Queue Set)、常见陷阱解析(优先级反转/ISR阻塞/内存碎片)。当用户提到 FreeRTOS、任务、队列、信号量、互斥锁、事件组、任务通知、软件定时器、临界区、中断安全 API、RTOS、xTaskCreate、vTaskDelay、xQueueSend、xSemaphoreGive、xEventGroupSetBits、xTaskNotifyGive、FreeRTOSConfig、configTICK_RATE_HZ、栈溢出、vApplicationStackOverflowHook、FreeRTOS 调试、任务优先级、优先级反转、死锁、tick、portYIELD、cmsis_os、FreeRTOS 内存管理、heap_1/2/3/4/5、流缓冲区、消息缓冲区、StreamBuffer、MessageBuffer、Tickless、低功耗、configUSE_TICKLESS_IDLE、生产者消费者、ISR 卸载、场景、示例 时使用。"
---

# FreeRTOS 模块开发指南

> API 速查见 `references/freertos-api-quickref.md`（所有 API 的 ISR 安全性/阻塞行为速查表）

## 参考资料

> 本指南基于 **FreeRTOS V10.4.x LTS**（兼容 V9.0.0 ~ V10.6.x），
> 所有 API 签名和行为以 [FreeRTOS.org 官方文档](https://www.freertos.org/) 为准。

| 资源 | 链接 |
|------|------|
| 官方文档首页 | https://www.freertos.org/ |
| API 参考索引 | https://www.freertos.org/a00106.html |
| 任务通知文档 | https://www.freertos.org/RTOS-task-notifications.html |
| 流/消息缓冲区 | https://www.freertos.org/RTOS-stream-buffer.html |
| 低功耗 Tickless | https://www.freertos.org/low-power-tickless-rtos.html |
| 栈溢出检测 | https://www.freertos.org/Stacks-and-stack-overflow-checking.html |
| 内存管理指南 | https://www.freertos.org/a00111.html |
| 官方 GitHub | https://github.com/FreeRTOS/FreeRTOS |
| FreeRTOS+TCP | https://www.freertos.org/FreeRTOS-Plus/FreeRTOS_Plus_TCP/ |
| 官方论坛 | https://forums.freertos.org/ |

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

## 流缓冲区 (Stream Buffer)

> 从 FreeRTOS V10.0.0 引入。流式字节流传输，发送方写入字节流，接收方逐个字节或批量读取。
> 适用于 ISR → Task 的连续数据流场景（如 UART 接收、ADC 采样数据流）。

```c
// 创建：指定缓冲区大小 + 触发级别
// 发送方写入达到触发级别后才唤醒接收任务（避免频繁上下文切换）
StreamBufferHandle_t xStreamBuffer = xStreamBufferCreate(
    256,       // 缓冲区总大小（字节）
    10         // 触发级别：至少 10 字节才通知接收方
);

// 发送（任务中）：
size_t xBytesSent = xStreamBufferSend(
    xStreamBuffer,
    pvData,       // 数据指针
    xDataLength,  // 发送长度
    0             // 阻塞时间（ISR 中传 0，满则丢弃）
);

// ISR 发送（UART Rx 中断中填入接收 FIFO）：
BaseType_t xHigherPriorityTaskWoken = pdFALSE;
size_t xSent = xStreamBufferSendFromISR(
    xStreamBuffer, pvData, xDataLength,
    &xHigherPriorityTaskWoken
);
portYIELD_FROM_ISR(xHigherPriorityTaskWoken);

// 接收（任务中批量取出）：
uint8_t ucBuffer[64];
size_t xBytesReceived = xStreamBufferReceive(
    xStreamBuffer,
    ucBuffer,       // 接收缓冲区
    sizeof(ucBuffer),
    portMAX_DELAY   // 等待直到有数据
);

// 接收（非阻塞查询，适合轮询模式）：
size_t xBytesReceived = xStreamBufferReceive(
    xStreamBuffer, ucBuffer, sizeof(ucBuffer), 0
);

// 查询可用字节数 / 剩余空间：
size_t xAvailable = xStreamBufferBytesAvailable(xStreamBuffer);
size_t xSpacesLeft = xStreamBufferSpacesAvailable(xStreamBuffer);

// 复位：
xStreamBufferReset(xStreamBuffer);

// 特点：
// - 纯字节流，无消息边界
// - 触发级别(Trigger Level)机制：收方不会因 1 字节频繁唤醒
// - 比队列更省 RAM（无元素元数据开销，按实际字节存储）
// - 不支持多个接收方同时读取
// - 不支持队列集的 SelectFromSet

// 典型用途：UART DMA 接收 + 流缓冲区 → 协议解析任务
// ISR 中将数据塞入流缓冲区，解析任务在触发级别处被唤醒
```

## 消息缓冲区 (Message Buffer)

> 从 FreeRTOS V10.0.0 引入。基于流缓冲区构建，但以 **可变长消息** 为单位收发。
> 每条消息自动携带长度前缀，接收方按整条消息取出，保留消息边界。

```c
// 创建：
MessageBufferHandle_t xMsgBuf = xMessageBufferCreate(512);

// 发送（按消息，自动加 4 字节长度前缀）：
size_t xSent = xMessageBufferSend(
    xMsgBuf,
    pvData,       // 消息内容
    xDataLength,  // 消息长度（可变）
    0
);

// 接收（按消息，必须提供足够大的缓冲区）：
uint8_t ucMsgBuf[128];
size_t xReceived = xMessageBufferReceive(
    xMsgBuf,
    ucMsgBuf,       // 接收缓冲区
    sizeof(ucMsgBuf),
    portMAX_DELAY
);

// 查看下一条消息长度（预分配缓冲区用）：
size_t xNextMsgLen = xMessageBufferReceiveLength(xMsgBuf);
// 注：xMessageBufferReceiveLength 不是官方 API —— 实际需用
// xMessageBufferReceive + 指定接收缓冲区 0 长度查错
// 推荐做法：用足够大的固定缓冲区接收

// ISR 版：
BaseType_t xHigherPriorityTaskWoken = pdFALSE;
xMessageBufferSendFromISR(xMsgBuf, pvData, xDataLength,
                          &xHigherPriorityTaskWoken);
xMessageBufferReceiveFromISR(xMsgBuf, ucBuf, sizeof(ucBuf),
                             &xHigherPriorityTaskWoken);

// 特点：
// - 保留消息边界，接收方一次读出完整一条
// - 每条消息额外 4 字节长度前缀（不可见）
// - 适用于变长帧传递（命令帧、传感器多类型数据）
// - 底层基于 StreamBuffer，行为类似队列但更节省 RAM

### 队列 vs 流缓冲区 vs 消息缓冲区 选型

| 特性 | 队列 (Queue) | 流缓冲区 (Stream) | 消息缓冲区 (Message) |
|------|-------------|-------------------|---------------------|
| 数据单元 | 固定大小元素 | 可变长字节流 | 可变长消息 |
| 消息边界 | 元素天然边界 | 无，自行分帧 | 自动保留 |
| RAM 开销 | 每元素 1x 大小 | 无元数据 | 4B/消息前缀 |
| 触发级别 | 元素数量 | 字节数 | 不适用 |
| 多接收方 | 支持（1:N） | 不支持（1:1） | 不支持（1:1） |
| QueueSet | 支持 | 不支持 | 不支持 |
| 适用场景 | 固定长度命令帧 | UART/SPI 连续流 | 变长协议帧 |
| 速度 | 中等（memcpy） | 最快 | 较快（memcpy + 长度） |

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

## 低功耗 Tickless 模式

> FreeRTOS 的 Tickless Idle 模式 (`configUSE_TICKLESS_IDLE = 1`) 允许芯片在空闲期间
> **停止 SysTick 中断**，进入深度睡眠，用低功耗定时器（如 LPTIM、RTC）代替 tick 计数。
> 典型应用：电池供电产品（秒级/分钟级唤醒间隔可省电 90%+）。

### 基本原理

```
正常模式 (Full Tick):
    tick ─┼─┼─┼─┼─┼─┼─┼─┼─→  1ms 一次 SysTick 中断
         ┌─────────────┐
         │  无任务运行  │  ← 空闲任务依然被 1ms tick 唤醒
         └─────────────┘

Tickless 模式:
    tick ─┼─┼───┬──────┼─┼─→  空闲期间停止 tick，用 LPTIM 计数
         ┌─────┘      └─────┐
         │  STOP/Sleep 模式  │  ← 节省 tick 中断耗电
         └──────────────────┘
```

### 配置

```c
// FreeRTOSConfig.h
#define configUSE_TICKLESS_IDLE         1       // 使能 tickless
// 可选自定义实现（预定义符号）：
// #define configPRE_SLEEP_PROCESSING(x)     // 进入睡眠前回调
// #define configPOST_SLEEP_PROCESSING(x)    // 唤醒后回调
```

### 实现方式

| 方式 | 宏设定 | 说明 | 适用平台 |
|------|--------|------|---------|
| 默认 | `configUSE_TICKLESS_IDLE = 1` | 使用 SysTick 的 CLR 值计算休眠时间，精度受 SysTick 分辨率限制 | STM32 通用 |
| 自定义 | 自行实现 `vPortSuppressTicksAndSleep` | 用独立低功耗定时器（LPTIM、RTC）替代 SysTick，休眠期间可进入 STOP 模式 | 低功耗产品 |

### STM32 HAL 配合要点

```c
// 方法 1: HAL 自动模式（CubeMX 生成）
// 在 CubeMX → FreeRTOS → Config parameters → Tickless idle 打勾
// CubeMX 自动生成:
//   #define configUSE_TICKLESS_IDLE         1
//   #define configEXPECTED_IDLE_TIME_BEFORE_SLEEP 2  // 空闲 >2 tick 才休眠

// HAL_Delay 冲突！！！
// ⚠️ Tickless 模式下 SysTick 停止，HAL_Delay 基于 HAL_IncTick 计数会暂停
// 处理方式：
// 1. 启用 HAL_Delay 补丁: configUSE_TICKLESS_IDLE 设为 2（自动补全 HAL tick）
// 2. 或重写 HAL_GetTick 使用 LPTIM 计数
// 3. 或不再使用 HAL_Delay（推荐），改用 vTaskDelay

// 方法 2: 自定义低功耗定时器（深度睡眠用 LPTIM）
// 使能 LPTIM 时钟 → 配置 LPTIM 为 PWM 模式 → 替换 tick 源
// 复杂度高，不建议首次使用 Tickless 时尝试

// 方法 3: RTC 唤醒
// 适用于分钟级唤醒间隔
// 空闲时 RTC 闹钟唤醒 → 补 tick → 继续调度
// 需要自定义 configPRE_SLEEP_PROCESSING / configPOST_SLEEP_PROCESSING
```

### STM32 平台功耗对比

| 模式 | 电流 (典型) | Tickless 适用 | 说明 |
|------|------------|--------------|------|
| 运行 (Run) | ~10-50 mA | 否 | 正常工作 |
| 睡眠 (Sleep) | ~5-10 mA | 是 | 内核停止，外设运行 |
| 停止 (Stop) | ~10-100 μA | 是（需 LPTIM） | 可 LPTIM 周期性唤醒 |
| 待机 (Standby) | ~1-2 μA | 否 | 仅 RTC 唤醒 |

### 常见问题

| # | 现象 | 根因 | 解决 |
|---|------|------|------|
| 1 | Tickless 下串口丢数据 | SysTick 停止，`HAL_GetTick` 不准 | 禁用 UART 超时的 `HAL_GetTick` 依赖 |
| 2 | vTaskDelay 不唤醒 | LPTIM 时钟配置错误 | 检查 LPTIM 时钟源（LSI/LSE） |
| 3 | 进入 Stop 后无法唤醒 | 未使能唤醒中断源 | 检查 EXTI/LPTIM 唤醒中断配置 |
| 4 | 功耗未明显降低 | 空闲时间不够长（<2 tick） | 降低 `configEXPECTED_IDLE_TIME_BEFORE_SLEEP` |
| 5 | debug 无法连接 | Stop 模式下调试器掉线 | 调试时禁用 Tickless，或使用 DBGMCU 保持调试时钟 |

> Tickless 模式下调试困难，建议先确认功能正常后再开启。
> 开发阶段：`configUSE_TICKLESS_IDLE = 0` → 调通功能 → `= 1` 验证低功耗。

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
| 11 | tickless 下串口丢数据 | SysTick 停 HAL_GetTick 不准 | 禁用 HAL_Delay 或使用补丁 |
| 12 | 任务通知误唤醒 | 多个 ISR 通知同一个任务 | 改用信号量或事件组 |

## 典型应用场景

### 场景 1: ISR 卸载 — UART 接收 + 协议解析

```
ISR(UART Rx) ──xQueueSendFromISR──→ 协议解析任务 ──xQueueSend──→ 业务处理任务
    IRQ级别                       优先级 2                    优先级 1
                                  (高优、短)                  (低优、耗时)
```

```c
// UART ISR — 只放数据，尽快退出
void USART1_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    uint8_t byte = USART1->DR & 0xFF;
    xQueueSendFromISR(xUartQueue, &byte, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}

// 协议解析任务 — 帧组装、校验
void vParseTask(void *pvParameters)
{
    uint8_t byte;
    uint8_t frame[256];
    uint8_t idx = 0;

    for (;;) {
        if (xQueueReceive(xUartQueue, &byte, portMAX_DELAY) == pdPASS) {
            frame[idx++] = byte;
            if (idx >= 2 && frame[idx-1] == '\n') {  // 收到换行 = 帧结束
                // 校验、解析
                xQueueSend(xCmdQueue, frame, 0);
                idx = 0;
            }
            if (idx >= sizeof(frame)) idx = 0;  // 防溢出
        }
    }
}
```

### 场景 2: 生产者-消费者（ADC 采集 + 滤波 + 发送）

```
Timer ISR ──xStreamBufferSendFromISR──→ 采集任务 ──xQueueSend──→ 发送任务
(定时触发ADC)   (原始数据流)          (滑动平均滤波)          (打包发送)
```

```c
// 采集任务 — 从流缓冲区取原始值，滑动平均后发送
void vAcquireTask(void *pvParameters)
{
    uint16_t raw;
    uint32_t sum = 0;
    uint8_t count = 0;
    const uint8_t WINDOW = 16;

    for (;;) {
        // 从流缓冲区读取一个采样值（阻塞直到数据到达）
        xStreamBufferReceive(xAdcStream, &raw, sizeof(raw), portMAX_DELAY);

        sum += raw;
        count++;
        if (count >= WINDOW) {
            uint16_t filtered = sum / WINDOW;
            xQueueSend(xFilteredQueue, &filtered, 0);
            sum = 0;
            count = 0;
        }
    }
}

// 发送任务
void vSendTask(void *pvParameters)
{
    uint16_t val;
    for (;;) {
        xQueueReceive(xFilteredQueue, &val, portMAX_DELAY);
        printf("[DATA] %u\n", val);
    }
}
```

### 场景 3: 多任务协作 — 传感器采集 → 处理 → 上报

```
采集任务 ──xQueueSend──→ 处理任务 ──xQueueSend──→ 上报任务
(Prio 3)               (Prio 2)               (Prio 1)
采集传感器原始值         单位换算、校准          打包 MQTT 上报
```

```c
// 事件组协调 — 全部传感器就绪后才开始处理
#define BIT_TEMP_READY  (1 << 0)
#define BIT_HUM_READY   (1 << 1)
#define BIT_PRESS_READY (1 << 2)

// 温度采集任务
void vTempTask(void *pvParameters)
{
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        int16_t temp = read_temperature();
        xQueueSend(xTempQueue, &temp, 0);
        xEventGroupSetBits(xEventGroup, BIT_TEMP_READY);
    }
}

// 处理任务 — 等所有传感器数据到齐再做融合
void vFusionTask(void *pvParameters)
{
    for (;;) {
        xEventGroupWaitBits(xEventGroup,
            BIT_TEMP_READY | BIT_HUM_READY | BIT_PRESS_READY,
            pdTRUE, pdTRUE, portMAX_DELAY);
        // 三个传感器数据都到齐了
        // 读取各队列数据做融合...
        SensorData_t fused = fuse_data();
        xQueueSend(xReportQueue, &fused, 0);
    }
}
```

### 场景 4: 优先级继承实战

```c
// ⚠️ 问题场景：优先级反转导致高优任务错过时序
// 低优先级(1) 持有互斥锁 → 被中优先级(2) 抢占 → 高优先级(3) 等锁被(2) 阻断
// 现象：高优先级任务延迟执行，导致时序错过

// ✅ 解决：用带优先级继承的互斥锁
// 当高优先级任务等锁时，低优先级任务「临时继承」高优先级
// 避免被中优先级任务抢占

SemaphoreHandle_t xSpiMutex = xSemaphoreCreateMutex();  // 带优先级继承

// 访问共享 SPI 总线
void spi_transaction(uint8_t *data, uint16_t len)
{
    xSemaphoreTake(xSpiMutex, portMAX_DELAY);  // 请求锁
    // 高优先级任务等锁时，当前持有者临时提升优先级
    // → 不会被中优先级任务打断
    HAL_SPI_TransmitReceive(&hspi1, data, data, len, 100);
    xSemaphoreGive(xSpiMutex);
}

// 三个任务使用同一个 SPI 总线外设：
// vHighPrioTask (3) — 传感器读取，每次调用 spi_transaction
// vMidPrioTask  (2) — UI 刷新，不需要 SPI，但抢占了 vLowPrioTask
// vLowPrioTask  (1) — 日志输出，有时调用 spi_transaction
```

### 场景 5: 任务通知替代信号量（高性能 ISR → Task）

```c
// 场景：高速 PWM 捕获 ISR → 计算任务
// 每秒触发 10000 次，用信号量太重

TaskHandle_t xCalcTaskHandle;
volatile uint32_t gCapCount = 0;

// ISR
void TIMx_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    gCapCount = TIMx->CCR1;    // 捕获值
    vTaskNotifyGiveFromISR(xCalcTaskHandle, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}

// 任务 — 使用 ulTaskNotifyTake（信号量语义）
void vCalcTask(void *pvParameters)
{
    uint32_t last_count = 0;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);  // 等待通知
        // 计算频率
        uint32_t freq = gCapCount - last_count;
        last_count = gCapCount;
        // ... 更新显示
    }
}
```

### 场景 6: 多队列多等待 — Queue Set

```c
// 场景：一个命令处理任务同时等待多个输入源
// - 串口命令队列
// - 按键事件队列
// - 超时事件

QueueHandle_t xUartCmdQ, xKeyEventQ;
QueueSetHandle_t xQueueSet = xQueueCreateSet(5);
xQueueAddToSet(xUartCmdQ, xQueueSet);
xQueueAddToSet(xKeyEventQ, xQueueSet);

void vCmdProcTask(void *pvParameters)
{
    for (;;) {
        QueueSetMemberHandle_t activated =
            xQueueSelectFromSet(xQueueSet, pdMS_TO_TICKS(5000));

        if (activated == NULL) {
            // 超时 — 做心跳或看门狗喂狗
            reset_watchdog();
        } else if (activated == xUartCmdQ) {
            CmdFrame_t cmd;
            xQueueReceive(xUartCmdQ, &cmd, 0);
            process_cmd(&cmd);
        } else if (activated == xKeyEventQ) {
            KeyEvent_t evt;
            xQueueReceive(xKeyEventQ, &evt, 0);
            process_key(&evt);
        }
    }
}
```

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

本 skill 聚焦 **原生 FreeRTOS API 的开发、配置与调试**，下列相关领域由其他 skill 覆盖：

- **cmsis_os v1/v2 封装层** — 那是 HAL 层 API，本 skill 使用原生 FreeRTOS API，cmsis_os 适配由 `stm32-hal-development` 覆盖
- **Amazon FreeRTOS (AFR)/FreeRTOS+TCP** — 高级网络套件，单独立项
- **运行中 FreeRTOS 调试分析**（任务状态/CPU占用率/死锁检测）— 由 `rtos-debug` skill 覆盖
- **RTOS 代码安全审查**（ISR 安全/竞态/DMA 缓冲区/可重入性）— 由 `embedded-reviewer` skill 覆盖

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
- 与 `rtos-debug` 互补：本 skill 覆盖**开发阶段**配置；`rtos-debug` 覆盖**运行中**的调试分析
- 与 `embedded-reviewer` 互补：后者审查 RTOS 代码的安全性
