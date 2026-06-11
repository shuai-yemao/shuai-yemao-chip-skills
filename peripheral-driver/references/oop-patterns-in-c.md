# OOP 设计模式在嵌入式 C 中的实现

> 基于《设计模式之美》(王争) + 嵌入式 C 语言实践提炼。
> 解决的核心问题：C 语言没有 class/interface/abstract 语法，如何用 struct + 指针模拟 OOP？

---

## 0. 核心思维模型：3W (What/How/Why)

所有 OOP 决策都必须回答三个问题。**Why 是最重要的，没有 Why 就不应该使用 OOP。**

| 维度 | 问题 | 在代码中体现 |
|------|------|------------|
| **What** | 这个模块/函数/类型是做什么的？ | 函数名、注释第一句 |
| **How** | 它是怎么实现的？ | 注释第二段、函数体 |
| **Why** | **为什么用这个方案而不是别的？** | 注释第三段、设计文档 |

### 反例 vs 正例

```c
// ❌ 反例：只有 What
/* 写 GPIO 引脚 */
void pin_write(void *port, uint16_t pin, uint8_t val);

// ✅ 正例：What + How + Why
/**
 * @brief 写 GPIO 引脚电平
 *
 * 实现: 直接代理到 HAL_GPIO_WritePin。
 *
 * 为什么用 void* 而不是 GPIO_TypeDef*?
 *   让 BSP 层不依赖 STM32 特定的类型定义，
 *   换 GD32/N32 等兼容芯片时不需要改 .h 文件。
 */
static inline void GPIO_Core_WritePin(void *port, uint16_t pin, uint8_t state)
{
    HAL_GPIO_WritePin((GPIO_TypeDef *)port, pin, (GPIO_PinState)state);
}
```

**在代码审查中**：如果看到一个设计决策没有"Why"解释，标记为 P2（文档缺失）。

---

## 1. 接口模式 (Interface Pattern)

### 对应概念
- Java/C++: `interface` 关键字
- Go: `interface{ ... }` 类型
- **C 实现**: 函数指针结构体 (vtable)

### 用途
- 定义行为契约（has-a 关系）
- 解耦调用者和实现者
- 运行时多态

### 示例：传感器接口

```c
// ── 定义接口 (接口 = 一组函数指针) ──
typedef struct {
    int  (*init)(void);
    int  (*read)(uint8_t reg, uint8_t *buf, uint16_t len);
    int  (*write)(uint8_t reg, const uint8_t *buf, uint16_t len);
    void (*deinit)(void);
} Sensor_Interface_t;

// ── 实现 A: DHT22 ──
static int dht22_init(void) { /* DHT22 初始化 */ }
static int dht22_read(uint8_t reg, uint8_t *buf, uint16_t len) { /* ... */ }
const Sensor_Interface_t DHT22_Driver = {
    .init   = dht22_init,
    .read   = dht22_read,
    .write  = NULL,      /* DHT22 是只读传感器 */
    .deinit = NULL,
};

// ── 实现 B: SHT30 ──
static int sht30_init(void) { /* SHT30 初始化 */ }
const Sensor_Interface_t SHT30_Driver = {
    .init   = sht30_init,
    .read   = sht30_read,
    .write  = sht30_write,
    .deinit = sht30_deinit,
};

// ── 调用方: 面向接口编程 ──
void App_ReadTemperature(const Sensor_Interface_t *sensor)
{
    if (sensor->init) sensor->init();
    uint8_t buf[2];
    if (sensor->read) sensor->read(0x00, buf, 2);
    // ...
}
```

### 3W 分析

| 维度 | 说明 |
|------|------|
| What | 定义一个行为契约，多个实现可互换 |
| How | `typedef struct { 函数指针 } 接口名_t;` + 常量实例 |
| Why | 解耦调用者和实现者。换传感器时不用改上层代码。**但注意**：嵌入式环境下函数指针调用有间接跳转开销（~5条指令/call），不适合时间关键路径 |

### 适用场景
- 同一功能有多种实现（传感器、存储器、显示驱动）
- 需要在运行时选择实现
- 测试时需要 mock/stub

---

## 2. 抽象类模式 (Abstract Class Pattern)

### 对应概念
- Java/C++: `abstract class`
- **C 实现**: 包含数据 + 函数指针的结构体（虚方法表）

### 用途
- 代码复用（is-a 关系）
- 定义通用行为框架（模板方法模式）
- 部分实现 + 部分抽象

### 示例：通用的 Logger

```c
// ── "抽象类": Logger ──
typedef struct {
    /* ── 公共数据 ── */
    const char *name;
    uint8_t     enabled;
    uint8_t     level;   /* 0=DEBUG, 1=INFO, 2=ERROR */

    /* ── "虚方法" (由子类实现) ── */
    void (*output)(const char *msg);

    /* ── "子类私有数据" (通过 void* 透传) ── */
    void *priv;
} Logger_t;

// ── "模板方法": 在抽象类中实现公共逻辑 ──
void Logger_Log(Logger_t *logger, uint8_t level, const char *msg)
{
    if (!logger || !logger->enabled) return;
    if (level < logger->level) return;  /* 级别过滤 */
    if (logger->output) logger->output(msg);
}

// ── "子类" A: 串口日志 ──
typedef struct {
    void *huart;   /* UART handle */
} UartLogger_Priv_t;

static void uart_output(const char *msg)
{
    UartLogger_Priv_t *p = /* 从 logger priv 获取 */;
    HAL_UART_Transmit(p->huart, (uint8_t*)msg, strlen(msg), 100);
}

Logger_t UartLogger = {
    .name   = "UART",
    .level  = 1,
    .output = uart_output,
    .priv   = &(UartLogger_Priv_t){ .huart = &huart1 },
};

// ── 使用 ──
Logger_Log(&UartLogger, 1, "System started");  /* 模板方法 */
```

### 3W 分析

| 维度 | 说明 |
|------|------|
| What | 定义公共数据结构 + 部分实现 + 抽象接口，子类继承并实现差异部分 |
| How | struct 包含虚函数表指针 + 公共数据，模板方法操作虚函数 |
| Why | 复用公共逻辑，避免重复代码（如日志级别过滤）。**C 语言中不如接口模式常用**，因为组合通常比继承更好 |

### 适用场景
- 多个变体共享大部分逻辑（模板方法模式）
- 需要同时复用数据和行为

---

## 3. 充血模型 (Rich Domain Model)

### 对应概念
- DDD (Domain-Driven Design) 中的领域模型
- 与"贫血模型"（Anemic Domain）相对
- **C 实现**: 结构体包含数据 + 操作方法 + 业务规则

### 示例：充血 LED vs 贫血 LED

```c
// ── 贫血模型 (Anti-pattern) ──
// 数据和方法分离
typedef struct {
    void *port;
    uint16_t pin;
    uint8_t active_level;
} LED_Data_t;           // 只有数据

void LED_TurnOn(LED_Data_t *led) {
    /* 在另一个文件中实现 */
}

// ── 充血模型 (Rich Model) ──
// 数据和操作在一起
typedef struct LED_Object {
    /* 数据 */
    void     *port;
    uint16_t  pin;
    uint8_t   active_level;
    uint8_t   state;

    /* 行为 (包含业务规则) */
    uint8_t (*validate)(struct LED_Object *self);
} *LED_Handle;

// 行为中包含规则校验
void LED_On(LED_Handle led)
{
    if (led == NULL) return;              // 规则1: NULL 保护
    if (led->state == 1) return;          // 规则2: 防重复点亮
    if (led->validate && !led->validate(led)) return; // 规则3: 自定义校验
    /* 执行电平转换 */
}
```

### 3W 分析

| 维度 | 说明 |
|------|------|
| What | 数据和操作封装在同一结构中，操作包含业务规则校验 |
| How | struct 同时包含成员变量和操作它们的函数（指针或直接函数） |
| Why | **防止无效状态**。贫血模型中，谁都可以直接修改 `led->state` 导致不一致；充血模型确保状态转换受控 |

### 在嵌入式 BSP 中的应用

| 适合充血模型的场景 | 适合贫血模型的场景 |
|------------------|------------------|
| 有复杂状态转换的设备（电机、电源管理） | 简单 GPIO 控制（LED、继电器） |
| 有内部状态机的设备（温控器、充电管理） | 数据透传（UART 缓存） |
| 需要业务规则校验的设备（安全关键） | 纯数据采集（ADC 采样） |

**经验法则**: 如果设备有 3 个以上内部状态，用充血模型。简单 on/off 用贫血模型就够了。

---

## 4. 反模式清单 (Anti-patterns)

### 反模式 1: 结构体暴露

```c
// ❌ 结构体在 .h 中暴露
// bsp_led.h
typedef struct {
    void *port;
    uint16_t pin;
} LED_t;
// 任何人都可以: led->pin = 0xFF;  ← 绕过所有检查

// ✅ 不透明句柄
// bsp_led.h
typedef struct LED_Object *LED_Handle;
// bsp_led.c
struct LED_Object { void *port; uint16_t pin; };
```

### 反模式 2: Getter/Setter 泛滥

```c
// ❌ 暴露所有内部数据
uint8_t LED_GetState(LED_Handle led);
void    LED_SetState(LED_Handle led, uint8_t state);  // 为什么要暴露setter？
void    LED_SetPin(LED_Handle led, uint16_t pin);      // 运行时改引脚？疯了？

// ✅ 只暴露有意义的行为
void    LED_On(LED_Handle led);
void    LED_Off(LED_Handle led);
void    LED_Toggle(LED_Handle led);
uint8_t LED_GetState(LED_Handle led);  // getter 可以保留（只读查询）
```

### 反模式 3: 全局状态/工具类

```c
// ❌ 全局配置散落在各处
#define LED_DEFAULT_BLINK_MS  200    // led.h
#define LED_MAX_COUNT           8    // led.c

// ✅ 配置集中在 System 层
// system_conf.h
#define SYS_LED_BLINK_PERIOD_MS  200
#define SYS_LED_MAX_INSTANCES      8
```

### 反模式 4: 数据和方法分离

```c
// ❌ 类似 Java 贫血模型的 Service/Data 分离
// led_data.h  — 只有结构体
// led_service.c — 所有操作
// 问题: 两个人可以同时修改同一个 LED 的数据

// ✅ 数据操作在一起
// bsp_led.h — 句柄
// bsp_led.c — 结构体定义 + 所有操作
```

---

## 5. 设计决策树

选择设计模式时按这个树决策：

```
该功能需要多个实例?
├─ 是 → 需要运行时多态?
│       ├─ 是 → 接口模式 (vtable)
│       └─ 否 → 注册表模式 (静态数组)
└─ 否 → 有复杂状态机?
        ├─ 是 → 充血模型 (状态+行为一体)
        └─ 否 → 面向过程 (函数+宏)

该功能可能换 MCU?
├─ 是 → Core 层桥接 (BSP→Core→Driver)
└─ 否 → 直接调 HAL (简单场景)

该功能跨项目复用?
├─ 是 → OOP (不透明句柄+接口)
└─ 否 → 面向过程 (更直接)

RAM 极受限 (< 4KB)?
├─ 是 → 面向过程 + 宏 (最小开销)
└─ 否 → OOP (96 字节注册表可接受)
```

---

## 6. 类识别方法论 (从需求到代码)

从博客文章的鉴权案例提炼的方法，适用于嵌入式驱动设计：

```
Step 1: 罗列所有功能点 (要尽可能小)
  - 例 (LED): 点亮、熄灭、翻转、闪烁一次、闪烁N次、设置闪烁模式

Step 2: 识别名词和动词
  - 名词 → 候选类: LED, BlinkMode
  - 动词 → 候选方法: On(), Off(), Toggle(), Blink()

Step 3: 按共享数据分组
  - 操作 port/pin/state 的功能 → 归入 LED 类
  - 操作闪烁参数的 → 归入 BlinkMode

Step 4: 设计交互关系
  - LED "has-a" BlinkMode (组合)
  - BlinkMode 是接口，Normal/Fast/Double 是实现 (多态)

Step 5: 组装并提供入口
  - LED_Register() 作为工厂
  - LED_On/Off/Toggle 作为公共 API
```

---

## 7. 推荐阅读

| 来源 | 内容 | 适用 |
|------|------|------|
| 《设计模式之美》王争 | 面向对象/设计原则/设计模式/重构 | 所有 OOP 决策 |
| 博客 Part 1 | 3W 模型、四大特性、接口vs抽象类 | 代码评审 |
| 博客 Part 2 | 贫血vs充血、DDD 实战、类识别方法论 | 架构设计 |
| `oop-usage-guide.md` | OOP 驱动的使用和维护 | BSP 开发人员 |
