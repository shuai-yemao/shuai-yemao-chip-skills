# ADC 时钟树与转换时序计算

## 时钟树导航

```
              ┌──────────────┐
              │   SYSCLK     │ (HSI/HSE/PLL)
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │   AHB Prescaler │
              │  (1, 2, 4, ..., 512) │
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │   APBx Bus   │
              │ (APB2 for ADC)│
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │ ADC Prescaler │  ← CubeMX: "ADC Clock" / "Clock Prescaler"
              │ (2, 4, 6, 8) │
              └──────┬───────┘
                     │
              ┌──────▼───────┐
              │   ADC_CLK     │
              │  ≤ 最大限制值   │
              └──────────────┘
```

## 各系列 ADC 时钟配置

### F4 系列
```c
// ADC_CCR 寄存器配置分频
// ADC_PRESC_DIV2 = 84/2 = 42MHz (超限！)
// ADC_PRESC_DIV4 = 84/4 = 21MHz (超限！)
// ADC_PRESC_DIV6 = 84/6 = 14MHz ✅ (APB2=84MHz 时)
// ADC_PRESC_DIV8 = 84/8 = 10.5MHz ✅

hadc1.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV6;  // F4
```

### H7 系列
```c
// H7 ADC Clock 来自：AHB 时钟经过独立分频器
// ADC_CCR: CKMODE[1:0] + PRESC[3:0]
// 支持高达 72MHz ADC 时钟
// 分辨率可配置为 8/10/12/14/16bit

hadc1.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV1;  // 异步时钟模式
```

### G4 系列
```c
// G4 支持最高 70MHz ADC 时钟
// 使用 PLL 输出作为 ADC 专用时钟 (PLLADC1CLK)
hadc1.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV1;
```

## 转换时间速查表

### 给定 fADC 下的单通道转换时间 (12bit)

| fADC | 采样周期 1.5 | 7.5 | 13.5 | 28.5 | 71.5 | 239.5 |
|------|-------------|-----|------|------|------|-------|
| 12 MHz | 1.17μs | 1.67μs | 2.17μs | 3.42μs | 7.0μs | 21.0μs |
| 14 MHz | 1.00μs | 1.43μs | 1.86μs | 2.93μs | 6.0μs | 18.0μs |
| 35 MHz | 0.40μs | 0.57μs | 0.74μs | 1.17μs | 2.4μs | 7.2μs |
| 70 MHz | 0.20μs | 0.29μs | 0.37μs | 0.59μs | 1.2μs | 3.6μs |

### 最大采样率估算

```
fS_max = fADC / (SMP + 12.5)

示例（F4, fADC=14MHz, SMP=1.5）:
fS_max = 14M / (1.5 + 12.5) = 14M / 14 = 1 MSps

示例（G4, fADC=70MHz, SMP=1.5）:
fS_max = 70M / (1.5 + 12.5) = 70M / 14 = 5 MSps
```

## 注入组额外时间

注入组转换时间 = 规则组时间 + 注入序列同步开销（约 2~4 fADC 周期）

## Nyquist 检查

```
采样率 fS 必须 > 2 × 最高信号频率 fmax

推荐：
- 工业传感器 (温度/压力): fS ≥ 10Hz 即可
- 音频: fS ≥ 44.1kHz
- 电机电流: fS ≥ 10kHz
- 振动分析: fS ≥ 2 × 最高振动频率
- 电网同步: fS ≥ 2 × 50/60Hz = 120Hz 实际 > 1kHz 推荐
```
