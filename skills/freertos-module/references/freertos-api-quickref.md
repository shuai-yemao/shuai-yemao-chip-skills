# FreeRTOS API 速查

## 任务

| API | 功能 | ISR 安全 | 阻塞 |
|-----|------|---------|------|
| `xTaskCreate` | 创建任务 | ❌ | ❌ |
| `xTaskCreateStatic` | 创建任务(静态栈) | ❌ | ❌ |
| `vTaskDelete` | 删除任务 | ❌ | ❌ |
| `vTaskDelay` | 相对延时 | ❌ | ✅ |
| `vTaskDelayUntil` | 绝对延时(精确周期) | ❌ | ✅ |
| `vTaskSuspend` | 挂起任务 | ❌ | ❌ |
| `vTaskResume` | 恢复任务 | ❌ | ❌ |
| `xTaskResumeFromISR` | ISR 中恢复任务 | ✅ | ❌ |
| `uxTaskPriorityGet` | 获取优先级 | ✅ | ❌ |
| `vTaskPrioritySet` | 设置优先级 | ❌ | ❌ |
| `uxTaskGetStackHighWaterMark` | 查看栈余量 | ❌ | ❌ |
| `vTaskList` | 列出所有任务(文本) | ❌ | ❌ |
| `vTaskGetRunTimeStats` | 运行时统计 | ❌ | ❌ |
| `xTaskGetTickCount` | 获取 tick 计数值 | ✅ | ❌ |
| `xTaskGetTickCountFromISR` | ISR 中获取 tick | ✅ | ❌ |

## 队列

| API | 功能 | ISR 安全 | 阻塞 |
|-----|------|---------|------|
| `xQueueCreate` | 创建队列 | ❌ | ❌ |
| `xQueueSend` | 发送(尾部) | ❌ | ✅ |
| `xQueueSendToFront` | 发送(头部) | ❌ | ✅ |
| `xQueueSendToBack` | 发送(尾部=Send) | ❌ | ✅ |
| `xQueueReceive` | 接收 | ❌ | ✅ |
| `xQueuePeek` | 查看不移除 | ❌ | ✅ |
| `xQueueSendFromISR` | ISR 中发送 | ✅ | ❌ |
| `xQueueReceiveFromISR` | ISR 中接收 | ✅ | ❌ |
| `xQueueReset` | 重置队列 | ❌ | ❌ |
| `uxQueueMessagesWaiting` | 队列中消息数 | ✅ | ❌ |
| `uxQueueSpacesAvailable` | 队列中空余空间 | ❌ | ❌ |

## 信号量与互斥锁

| API | 功能 | ISR 安全 | 阻塞 |
|-----|------|---------|------|
| `xSemaphoreCreateBinary` | 创建二值信号量 | ❌ | ❌ |
| `xSemaphoreCreateCounting` | 创建计数信号量 | ❌ | ❌ |
| `xSemaphoreCreateMutex` | 创建互斥锁 | ❌ | ❌ |
| `xSemaphoreCreateRecursiveMutex` | 创建递归互斥锁 | ❌ | ❌ |
| `xSemaphoreGive` | 释放 | ❌ | ❌ |
| `xSemaphoreTake` | 获取 | ❌ | ✅ |
| `xSemaphoreGiveFromISR` | ISR 释放 | ✅ | ❌ |
| `xSemaphoreTakeFromISR` | ISR 获取 | ✅ | ❌ |

## 事件组

| API | 功能 | ISR 安全 | 阻塞 |
|-----|------|---------|------|
| `xEventGroupCreate` | 创建事件组 | ❌ | ❌ |
| `xEventGroupSetBits` | 设置事件位 | ❌ | ❌ |
| `xEventGroupSetBitsFromISR` | ISR 设置事件位 | ✅ | ❌ |
| `xEventGroupClearBits` | 清除事件位 | ❌ | ❌ |
| `xEventGroupWaitBits` | 等待事件位 | ❌ | ✅ |
| `xEventGroupGetBits` | 获取事件位 | ✅ | ❌ |
| `xEventGroupGetBitsFromISR` | ISR 获取事件位 | ✅ | ❌ |

## 任务通知

| API | 功能 | ISR 安全 | 阻塞 |
|-----|------|---------|------|
| `xTaskNotifyGive` | 通知+1(信号量语义) | ❌ | ❌ |
| `vTaskNotifyGiveFromISR` | ISR 通知+1 | ✅ | ❌ |
| `xTaskNotify` | 通知(8种操作) | ❌ | ❌ |
| `xTaskNotifyFromISR` | ISR 通知 | ✅ | ❌ |
| `xTaskNotifyWait` | 等待通知 | ❌ | ✅ |
| `ulTaskNotifyTake` | 等待通知+1(信号量风格) | ❌ | ✅ |
| `xTaskNotifyStateClear` | 清除通知状态 | ❌ | ❌ |

## 软件定时器

| API | 功能 | 阻塞 |
|-----|------|------|
| `xTimerCreate` | 创建定时器 | ❌ |
| `xTimerStart` | 启动定时器 | ✅ (调用者阻塞直到命令队列有空间) |
| `xTimerStop` | 停止定时器 | ✅ |
| `xTimerReset` | 复位定时器 | ✅ |
| `xTimerChangePeriod` | 修改周期 | ✅ |
| `xTimerDelete` | 删除定时器 | ✅ |
| `xTimerIsTimerActive` | 检查是否运行 | ❌ |

## 内存管理

| API | 功能 |
|-----|------|
| `pvPortMalloc` | 从 FreeRTOS 堆分配内存 |
| `vPortFree` | 释放内存 |
| `xPortGetFreeHeapSize` | 获取剩余堆空间 |
| `xPortGetMinimumEverFreeHeapSize` | 获取历史最小堆(碎片指标) |

## 任务通知 vs 信号量 vs 事件组 选型

| 场景 | 推荐方案 | 原因 |
|------|---------|------|
| ISR → 单任务同步 | 任务通知 | 速度最快 (~25% 比信号量快) |
| ISR → 多任务广播 | 二值信号量(每个任务一个) | 通知只能一对一 |
| 资源管理(互斥) | 互斥锁 (Mutex) | 优先级继承防反转 |
| 多事件等待(任意/全部) | 事件组 | 原生支持 |
| 数据传递 | 队列 | 带数据 |
| 多生产者-单消费者 | 计数信号量 + 队列 | 灵活 |
| 后台任务执行 | 软件定时器 | 简单周期调用 |

## 配置裁剪与资源占用

| 特性 | 启用宏 | ROM 增量 | RAM 增量 |
|------|-------|---------|---------|
| 任务通知 | 默认 | ~200B | 4B/任务 |
| 队列 | 默认 | ~1KB | 队列大小相关 |
| 信号量 | 默认 | ~200B | — |
| 互斥锁 | 默认 | ~100B | — |
| 事件组 | `configUSE_EVENT_GROUPS` | ~500B | 12B/事件组 |
| 软件定时器 | `configUSE_TIMERS` | ~800B | 定时器命令队列 |
| 运行时统计 | `configGENERATE_RUN_TIME_STATS` | ~600B | — |
| Co-routine | `configUSE_CO_ROUTINES` | ~400B | — |
| 递归互斥锁 | `configUSE_RECURSIVE_MUTEXES` | ~100B | — |
| Tickless Idle | `configUSE_TICKLESS_IDLE` | ~500B | — |

## 常见 CubeMX 集成问题

```c
// CubeMX FreeRTOS 配置位置：
// Project Manager → Advanced Settings → FreeRTOS Heap
// Pinout → Middleware → FREERTOS → Configuration

// 默认配置问题：
// 1. configTOTAL_HEAP_SIZE 默认 10KB → 大工程需要加大
// 2. configMINIMAL_STACK_SIZE 默认 128 → 带 printf 需要 256+
// 3. configMAX_PRIORITIES 默认 7 → 够用

// CubeMX 生成的任务优先级 vs FreeRTOS 优先级：
// CubeMX 中优先级数值 = 实际 FreeRTOS 优先级
// 不需要做映射
```
