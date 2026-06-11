# BSP 面向对象驱动 — 使用与维护指南

> **目标读者**: 接手 OOP 风格 BSP 驱动代码的嵌入式工程师。
> **核心问题**: OOP in C 用不透明句柄隐藏了实现细节，新接手的人看不到"内部是什么"。
> **解决思路**: 本文档记录所有 OOP BSP 驱动的通用设计模式，各驱动特有的内容写在对应 .h 文件头部。

---

## 1. 为什么 BSP 驱动要用 OOP？

### 问题对比

```c
// ── 面向过程: 所有信息在眼前, 但耦合度高 ──
#define LED_PORT GPIOC
#define LED_PIN  GPIO_PIN_13

void LED_Init(void) {
    HAL_GPIO_WritePin(LED_PORT, LED_PIN, GPIO_PIN_RESET);
}

// ── 面向对象: 隐藏细节, 但开发者看不到内部 ──
LED_Handle hled = LED_Register(GPIOC, GPIO_PIN_13, 1);
LED_On(hled);

// 问题: hled 里面是什么？LED_On 对 GPIO 做了什么？
```

### 选择 OOP 的理由

| 需求 | 面向过程的问题 | OOP 的解决 |
|------|---------------|-----------|
| 多个 LED | 定义 N 组宏 + 复制 N 份函数 | 一个注册表, 任意实例 |
| 换 MCU | 所有 HAL_GPIO_WritePin 要改 | Core 层桥接, BSP 不变 |
| 低/高电平亮 | 有的板子要改逻辑 | active_level 参数配置 |
| 极端资源受限 | 宏更省 | 8 实例静态数组 = 固定 RAM |

**代价就是可读性降低** — 本文档的初衷。

### 适用判断

```
该设备需要多个实例?                       → OOP (注册表模式)
该设备未来可能换 MCU 系列?                → OOP (Core 层桥接)
这个驱动可能被其他项目复用?                → OOP (封装)
只是简单控制一个引脚(如板载 LED)?          → 宏定义 + 过程式更直接
```

> **经验法则**: 项目中 LED 超过 2 个, 或者该器件会在不同板子上复用 → OOP。
> 板载指示灯(1 个, 永不换板) → 宏定义 + 过程式更清晰。

---

## 2. OOP BSP 驱动的通用结构

### 文件布局

```
BPS/<device>/
├── bsp_<device>.h        # 公开接口 (不透明句柄 + 函数声明)
└── bsp_<device>.c        # 私有实现 (struct 定义 + Core 桥接 + 注册表)
```

### 每个文件的"阅读入口"

```c
// ═══════════════════════════════════════════════════════════════
// bsp_led.h — 你要看的是:
//   1. 函数列表 (On/Off/Toggle/Blink)
//   2. 参数说明 (特别是 active_level 的含义)
//   3. 返回值 (NULL 表示注册失败)
// ═══════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════
// bsp_led.c — 你要看的是:
//   1. struct LED_Object 定义 (里面有什么字段)
//   2. GPIO_Core_* 桥接函数 (如何访问硬件)
//   3. s_led_registry[] (全局注册表)
//   4. priv_hw_write (有效电平转换逻辑)
// ═══════════════════════════════════════════════════════════════
```

---

## 3. 核心概念逐项说明

### 3.1 不透明句柄 (Opaque Handle)

```c
// bsp_led.h (公开):
typedef struct LED_Object *LED_Handle;
// 外部只能看到: LED_Handle 是一个指针
// 看不到: 里面有什么字段

// bsp_led.c (私有):
struct LED_Object {
    void     *port;          // GPIO 端口地址, 如 (void*)GPIOC
    uint16_t  pin;           // GPIO 引脚号, 如 GPIO_PIN_13
    uint8_t   active_level;  // 1=高电平亮, 0=低电平亮
    uint8_t   state;         // 当前逻辑状态 (1=亮, 0=灭)
    uint8_t   in_use;        // 1=已注册, 0=空闲
};
```

**为什么这样做？**
- 防止外部代码直接修改端口/引脚/状态
- 换 MCU 时, 只需改 .c 中的 struct (比如 `void *port` → `GPIO_TypeDef *port`)
- 对外接口不变, 其他文件不用动

**新接手的人要知道**:
> `LED_Handle` 指向的对象在静态数组 `s_led_registry[]` 中。
> 它是全局存在的, 不需要 `malloc/free`。
> 句柄是永久的, 除非调用 `LED_Unregister()`。

### 3.2 Core 层桥接 (Core Layer Bridge)

```c
// bsp_led.c 头部 (标为"待迁移到 Core 层"):
static inline void GPIO_Core_WritePin(void *port, uint16_t pin, uint8_t state)
{
    HAL_GPIO_WritePin((GPIO_TypeDef *)port, pin, (GPIO_PinState)state);
}

static inline uint8_t GPIO_Core_ReadPin(void *port, uint16_t pin)
{
    return (uint8_t)HAL_GPIO_ReadPin((GPIO_TypeDef *)port, pin);
}
```

**为什么这样做？**
- BSP 层不直接调 HAL → 这是分层架构的铁律
- 换 MCU 时 (如 STM32F4 → GD32F4): 只改这里几行, bsp_led.c 的 On/Off/Toggle 逻辑不动

**新接手的人要知道**:
> 这 3 个 `static inline` 函数就是 BSP 和硬件的唯一接口。
> 不管你用什么 MCU, 只要把这里 3 个函数实现换掉, 整个 LED 驱动就移植完成了。
> 正式项目中这里应该是一个独立的 `gpio_core.h` 文件。

### 3.3 静态注册表 (Static Registry)

```c
// bsp_led.c (全局):
#define LED_REGISTRY_MAX  8

static struct LED_Object s_led_registry[LED_REGISTRY_MAX];

// LED_Register() 内部:
uint8_t slot = priv_find_free_slot();  // 找空闲槽位
s_led_registry[slot] = ...;           // 填入设备信息
return &s_led_registry[slot];         // 返回句柄
```

**为什么这样做？**
- 嵌入式系统禁止 `malloc` (MISRA Dir 4.12)
- 8 个 LED = 8 × 约 12 字节 = 96 字节固定 RAM
- 数组方式: 运行时无分配失败风险

**新接手的人要知道**:
> - 最多 8 个 LED (改 `LED_REGISTRY_MAX` 可调整)
> - `LED_Register` 返回 NULL 表示满了
> - 所有句柄都指向这个数组, 没有动态内存
> - `LED_AllOff()` 遍历这个数组

### 3.4 有效电平转换 (Active Level)

```c
// 用户注册时指定:
LED_Register(GPIOC, GPIO_PIN_13, 1);  // 高电平亮 (STM32 核心板)
LED_Register(GPIOB, GPIO_PIN_0,  0);  // 低电平亮 (某些模块)

// 内部转换:
static void priv_hw_write(struct LED_Object *led, uint8_t state)
{
    // 根据 active_level 将逻辑 state(1/0) 映射为物理电平
    uint8_t pin_state = led->active_level ? state : !state;
    // active_level=1, state=1 → pin_state=1 (高电平)
    // active_level=0, state=1 → pin_state=0 (低电平 → 拉低点亮)
    GPIO_Core_WritePin(led->port, led->pin, pin_state);
    led->state = state;  // 记住逻辑状态
}
```

**为什么这样做？**
- 不同板子 LED 点亮电平不同 (有些接 VCC, 有些接 GND)
- 没有这个抽象 → 每个板子要改代码
- 用参数配置 → 换板子只改注册那行

**新接手的人要知道**:
> 调用 `LED_On(hled)` 不一定是输出高电平。
> 如果注册时 `active_level=0`, 那么 `LED_On()` 输出的是低电平。
> 你不需要关心电平, 只需要关心"亮/灭"这个逻辑状态。

---

## 4. 常见误解 (FAQ)

### Q: `LED_Handle` 是指针还是整数？
A: 指针。指向 `s_led_registry[]` 中的元素。不是文件描述符, 不是索引号。

### Q: 我可以保存多个 `LED_Handle` 吗？
A: 可以。句柄就是普通指针, 可以复制、存数组、传参:
```c
LED_Handle h1 = LED_Register(GPIOC, GPIO_PIN_13, 1);
LED_Handle h2 = h1;          // 同一个 LED 的第二个引用
LED_On(h2);                  // 效果和 LED_On(h1) 一样
```

### Q: `LED_Unregister()` 后句柄还能用吗？
A: 不能。函数内部 `memset(led, 0, sizeof(*led))` 清空了对象。再用就是野指针。

### Q: 为什么不用 `malloc` 动态分配？
A: MISRA C:2012 Dir 4.12 禁止动态内存分配。嵌入式系统堆碎片会导致无法预料的"用完就崩"。

### Q: 用 OOP 跑 72MHz 的 F103 会不会太慢？
A: 不会。`LED_On()` 最终就是 1 次寄存器写入。OOP 带来的额外开销只有:
- 1 次 NULL 检查 (2 条指令)
- 1 次 active_level 条件判断 (3 条指令)
- 1 次函数调用 (BL 指令)
总共不到 10 条 CPU 指令, 约 0.14μs @ 72MHz。

### Q: 为什么要在 .c 里写 `GPIO_Core_WritePin` 而不是直接调 HAL？
A: 这是分层架构铁律 — BSP 层不能直接调 Driver/HAL 层。这样做:
- 换 MCU 时 BSP 不用改 (只需改 Core 层)
- 代码审查时可以快速定位: "BSP 里唯一的 HAL 调用在这里"
- 符合 embedded-architect 的 7 层架构 (BSP → Core → Driver)

---

## 5. 调试技巧

### 5.1 查看注册表状态

用 JLink Commander 或 GDB 查看 `s_led_registry`:

```
# JLink:
mem32 <地址> 8    # 查看 s_led_registry 前 8 个 word

# GDB:
p s_led_registry
p s_led_registry[0].state
```

### 5.2 判断 LED_On 是否生效

如果 LED 不亮:
1. `LED_GetState(hled)` → 返回 1? (软件层面已"点亮")
2. 如果返回 1 → 硬件问题: 引脚、电平、LED 坏
3. 如果返回 0 → 软件问题: 句柄为 NULL? 注册失败?

### 5.3 注册表溢出

```c
LED_Handle h = LED_Register(...);
if (h == NULL) {
    printf("[ERR] LED 注册表已满! 当前 %d 个\n", LED_GetCount());
    // 增大 LED_REGISTRY_MAX 或排查泄漏
}
```

---

## 6. 架构合规检查清单

每次修改 BSP OOP 驱动后核查:

- [ ] **不透明句柄**: .h 中 `typedef struct Xxx_Obj *XXX_Handle`, .c 中定义 `struct Xxx_Obj {...}` 
- [ ] **无跨层**: .c 中没有 `#include "stm32f4xx_hal.h"` (通过 Core 桥接间接调用)
- [ ] **静态注册表**: 使用 `static struct` 数组, 无 `malloc`
- [ ] **NULL 检查**: 每个 public 函数第一行检查 `if (!handle) return;`
- [ ] **有效电平**: `Create/Register` 函数有 `active_level` 参数
- [ ] **初始化状态**: 创建后设备处于"关闭/熄灭"安全状态
- [ ] **析构清理**: `Destroy/Unregister` 函数 `memset` 清空对象
- [ ] **头文件独立**: .h 只包含 `<stdint.h>`, 不包含 HAL 头文件
- [ ] **语义命名**: 函数名体现业务语义 (`On/Off/Toggle`), 非总线操作 (`ReadData/WriteData`)
- [ ] **注释完整**: 每个函数有 Doxygen 注释块, 说明参数和返回值

---

## 7. 参考实现

- `06_LED_V1/BPS/LED/bsp_led.c` — OOP LED 驱动参考实现
- `bsp_adapter.py --oop` — OOP 骨架自动生成
- `embedded-architect/references/layered-architecture-model.md` — 7 层分层架构定义
- `embedded-reviewer/SKILL.md` — OOP 合规审查 7 项检查
