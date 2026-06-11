# APB ×2 规则详解与 PSC/ARR 计算表

## APB ×2 规则

### 根本原因

STM32 定时器时钟来自 APB，但不是直接使用 APB 时钟。具体规则：

```
if (APB Prescaler == 1) {
    TIM_CLK = APB_CLK;           // 不分频
} else {
    TIM_CLK = APB_CLK × 2;       // 分频≠1 时定时器时钟翻倍
}
```

**目的**：保证无论 APB 分频多少，TIM_CLK 都等于 HCLK（或接近 HCLK）。

### CubeMX 确认方法

在 CubeMX 中：**Clock Configuration** 页面 →
- 点击 APB1/APB2 后面的时钟数值 → 弹出的对话框中会显示 TIMx 时钟
- 或者生成代码后看 `SystemClock_Config()` 函数的注释

### 常见系列实际值

| MCU | HCLK | APB1 Presc | APB1 | TIM on APB1 | APB2 Presc | APB2 | TIM on APB2 |
|-----|------|-----------|------|------------|-----------|------|------------|
| STM32F103C8 | 72MHz | /2 | 36MHz | **72MHz** | /1 | 72MHz | **72MHz** |
| STM32F411CE | 100MHz | /2 | 50MHz | **100MHz** | /1 | 100MHz | **100MHz** |
| STM32F407VG | 168MHz | /4 | 42MHz | **84MHz** | /2 | 84MHz | **84MHz** |
| STM32H743 | 480MHz | /4 | 120MHz | **240MHz** | /4 | 120MHz | **240MHz** |
| STM32G474 | 170MHz | /2 | 85MHz | **170MHz** | /2 | 85MHz | **170MHz** |

### 代码中获取 TIM_CLK

```c
// 获取特定 TIM 实例的时钟频率
uint32_t get_timer_clock(TIM_TypeDef *TIMx)
{
    if (TIMx == TIM1 || TIMx == TIM8 || TIMx == TIM9 || TIMx == TIM10 || TIMx == TIM11) {
        return HAL_RCC_GetPCLK2Freq();               // APB2 上的 TIM
    } else {
        // APB1 Prescaler ≠ 1 时 ×2
        if ((RCC->CFGR & RCC_CFGR_PPRE1) != 0) {
            return HAL_RCC_GetPCLK1Freq() * 2;
        } else {
            return HAL_RCC_GetPCLK1Freq();
        }
    }
}
```

## PSC/ARR 计算

### 公式
```
目标频率 f_target = TIM_CLK / (PSC + 1) / (ARR + 1)
```

**PSC 选择策略**：
1. 先让 `PSC + 1` 足够大使 `ARR + 1` 在 16bit (0~65535) 或 32bit (0~4294967295) 范围内
2. 如果 ARR 超出范围 → 增大 PSC
3. 如果 ARR 太小（<10）→ 减小 PSC（提高计数精度）

### 完整速查表（TIM_CLK=100MHz）

| 目标频率 | 目标周期 | PSC | ARR | 误差 |
|---------|---------|-----|-----|------|
| 100 MHz | 10 ns | 0 | 0 | 0% |
| 10 MHz | 100 ns | 0 | 9 | 0% |
| 1 MHz | 1 μs | 0 | 99 | 0% |
| 100 kHz | 10 μs | 0 | 999 | 0% |
| 50 kHz | 20 μs | 1 | 999 | 0% |
| 10 kHz | 100 μs | 9 | 999 | 0% |
| 1 kHz | 1 ms | 99 | 999 | 0% |
| 100 Hz | 10 ms | 999 | 999 | 0% |
| 10 Hz | 100 ms | 9999 | 999 | 0% |
| 1 Hz | 1 s | 9999 | 9999 | 0% |

### 速查表（TIM_CLK=72MHz，F103 典型值）

| 目标频率 | PSC | ARR | 实际周期 | 误差 |
|---------|-----|-----|---------|------|
| 1 kHz | 71 | 999 | 1.000 ms | <0.1% |
| 100 Hz | 719 | 999 | 10.00 ms | <0.1% |
| 10 kHz | 7 | 899 | 100 μs | 0% |
| 50 Hz (舵机) | 71 | 19999 | 20.00 ms | <0.1% |

## 32bit 定时器优势

TIM2/TIM5 是 32bit（F4/H7）。长周期场景优势明显：

| 场景 | 16bit (PSC=65535, ARR=65535) | 32bit (PSC=65535, ARR=4294967295) |
|------|-----------------------------|-----------------------------------|
| 100MHz 时钟 | 最大周期 ≈ 42.9 ms | 最大周期 ≈ 78 小时 |
| 100kHz 时钟 | 最大周期 ≈ 42.9 s | 不适用（PSC 太大） |

**实用技巧**：用 32bit TIM（TIM2/TIM5）做长时间测量，不需要额外处理溢出。
