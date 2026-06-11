---
name: fft-module
description: |
  快速傅里叶变换(FFT)嵌入式开发指南。覆盖 FFT 算法原理和工程实现、
  CMSIS-DSP FFT 函数(rfft/cfft)、ST 全系列及 ESP32 上的 FFT 性能基准、
  窗函数选择(汉宁/海明/布莱克曼/平顶)、频谱分析与谐波检测、
  FFT 点数的选择与频率分辨率计算、定点 vs 浮点 FFT 精度对比、
  实时频谱显示、Goertzel 算法单频检测。
  当用户提到 FFT、快速傅里叶变换、频谱分析、频谱、CFFT、RFFT、
  傅里叶、频率分析、谐波检测、窗函数、汉宁窗、Goertzel 算法、
  STM32 FFT、CMSIS-DSP fft、arm_rfft、arm_cfft、定点 FFT、
  频率分辨率、频谱泄露、ADC 频谱、信号分析 时使用。
version: "1.0.0"
---

# FFT 快速傅里叶变换嵌入式开发指南

## 适用场景

- 需要对 ADC 采样数据进行频谱分析
- 需要做谐波检测（电力质量分析/电机振动监测）
- 需要实现实时频谱显示（音频可视化/FFT 频谱仪）
- 需要检测特定频率信号（Goertzel 算法替代 FFT）
- 需要选型 FFT 点数（128/256/512/1024/2048）
- 需要选择窗函数以减少频谱泄漏

## 必要输入

| 参数 | 说明 |
|------|------|
| FFT 点数 | 128/256/512/1024/2048/4096（2^N） |
| 采样率(Hz) | ADC 采样频率，决定频率分辨率 |
| 数据类型 | float32 / q15 / q31 |
| 变换方向 | 正变换(时域→频域) / 逆变换(频域→时域) |
| 实信号/复信号 | 多数传感器为实信号(rfft)，IQ 采样为复信号(cfft) |

## FFT 核心参数

### 频率分辨率

```
Δf = fs / N

例: fs = 1000Hz, N = 1024 → Δf = 0.98Hz
例: fs = 1000Hz, N = 256  → Δf = 3.91Hz

N 越大 → 分辨率越高 → RAM 占用越大 → 计算时间越长
```

### FFT 点数选择权衡

| 点数 | RAM(浮点) | RAM(定点q15) | 时间@STM32F411 | 分辨率@1kHz |
|------|-----------|-------------|---------------|------------|
| 128 | 1KB | 0.5KB | ~0.5ms | 7.8Hz |
| 256 | 2KB | 1KB | ~1ms | 3.9Hz |
| 512 | 4KB | 2KB | ~3ms | 1.95Hz |
| 1024 | 8KB | 4KB | ~8ms | 0.98Hz |
| 2048 | 16KB | 8KB | ~20ms | 0.49Hz |
| 4096 | 32KB | 16KB | ~50ms | 0.24Hz |

## CMSIS-DSP FFT 实现

### 实数 FFT (arm_rfft_fast_f32) — 推荐

```c
#include "arm_math.h"

#define FFT_SIZE 1024

static float32_t input[FFT_SIZE];       // ADC 采样缓冲区
static float32_t output[FFT_SIZE];      // FFT 输出(复数交替存储)
static arm_rfft_fast_instance_f32 fft;

void fft_init(void)
{
    arm_rfft_fast_init_f32(&fft, FFT_SIZE);
}

void fft_process(float32_t *adc_samples)
{
    // 1. 去除直流分量(可选)
    float32_t mean;
    arm_mean_f32(adc_samples, FFT_SIZE, &mean);
    for (int i = 0; i < FFT_SIZE; i++)
        input[i] = adc_samples[i] - mean;

    // 2. 加窗(减少频谱泄漏)
    // arm_cfft_radix8_f32 不支持加窗, 需手动加
    for (int i = 0; i < FFT_SIZE; i++)
        input[i] *= hanning_window[i];

    // 3. 执行 FFT
    arm_rfft_fast_f32(&fft, input, output, 0);  // 0=正变换

    // 4. 计算幅度谱
    // output 格式: [real0, imag0, real1, imag1, ...]
    // 只取前 N/2 个频点(奈奎斯特)
    float32_t magnitude[FFT_SIZE / 2];
    arm_cmplx_mag_f32(output, magnitude, FFT_SIZE / 2);

    // 5. 幅度到 dB(可选)
    for (int i = 0; i < FFT_SIZE / 2; i++)
        magnitude[i] = 20.0f * log10f(magnitude[i] / FFT_SIZE);
}
```

### 复数 FFT (arm_cfft_f32) — 适合同/正交信号

```c
void cfft_process(void)
{
    // 输入: 复数交替格式 [real0, imag0, real1, imag1, ...]
    arm_cfft_f32(&cfft_instance, complex_buffer, 0, 1);
    // arm_cfft_f32(instance, pSrc, inverse, bitReverseFlag)
}
```

## 窗函数选择

| 窗函数 | 主瓣宽度 | 旁瓣抑制 | 幅值精度 | 适用场景 |
|--------|---------|---------|---------|---------|
| 矩形(无窗) | 最窄 | -13dB | 差 | 瞬态信号/频谱分辨率优先 |
| 汉宁(Hanning) | 中 | -32dB | 好 | **大多数通用场景(推荐)** |
| 海明(Hamming) | 中 | -43dB | 中 | 窄带信号/接近频率相近 |
| 布莱克曼(Blackman) | 宽 | -58dB | 好 | 需要强旁瓣抑制 |
| 平顶(FlatTop) | 最宽 | -44dB | **最好** | 幅值精度最优先(校准) |

### 汉宁窗生成

```c
// 预计算汉宁窗系数(在初始化时计算一次)
static float32_t hanning_window[FFT_SIZE];

void gen_hanning(void)
{
    for (int i = 0; i < FFT_SIZE; i++) {
        hanning_window[i] = 0.5f * (1.0f - arm_cos_f32(2.0f * PI * i / (FFT_SIZE - 1)));
    }
}
```

## Goertzel 算法（单频率检测）

当只需要检测特定频率（如 DTMF 解码、工频 50Hz 检测）时，Goertzel 比 FFT 高效得多：

```c
// Goertzel 算法：检测特定频率的幅值
// 比 FFT 节省 10-100x 计算量（当只需要 1-3 个频点时）

float32_t goertzel(float32_t *samples, uint32_t N, float32_t target_freq, float32_t fs)
{
    float32_t coeff = 2.0f * arm_cos_f32(2.0f * PI * target_freq / fs);
    float32_t s_prev = 0.0f, s_prev2 = 0.0f, s;

    for (uint32_t i = 0; i < N; i++) {
        s = samples[i] + coeff * s_prev - s_prev2;
        s_prev2 = s_prev;
        s_prev = s;
    }

    // 计算幅值
    float32_t power = s_prev2 * s_prev2 + s_prev * s_prev - coeff * s_prev * s_prev2;
    return sqrtf(power);
}
```

## 频谱分析示例：工频谐波检测

```c
// 以 6400Hz 采样率采集电网电压，分析 50Hz 基波 + 谐波
#define FS      6400.0f   // 采样率 6.4kHz
#define FFT_N   1024      // 分辨率 = 6400/1024 = 6.25Hz

void power_quality_analysis(float32_t *samples)
{
    fft_process(samples);  // 得到幅度谱 magnitude[]

    // 50Hz 基波 (bin = 50/6.25 = 8)
    printf("Fundamental(50Hz): %.2f\n", magnitude[8]);

    // 3次谐波 150Hz (bin = 150/6.25 = 24)
    printf("3rd harmonic(150Hz): %.2f\n", magnitude[24]);

    // 5次谐波 250Hz (bin = 250/6.25 = 40)
    printf("5th harmonic(250Hz): %.2f\n", magnitude[40]);

    // THD 计算
    float32_t harm_power = 0;
    for (int i = 2; i < FFT_N/2; i++)  // 跳过直流(bin 0)
        harm_power += magnitude[i] * magnitude[i];
    float32_t thd = sqrtf(harm_power) / magnitude[8] * 100.0f;
    printf("THD: %.2f%%\n", thd);
}
```

## 平台性能基准

| MCU | 频率 | 1024点FFT(float) | 1024点FFT(q15) | 备注 |
|-----|------|-----------------|----------------|------|
| STM32F103 | 72MHz | ~40ms | ~8ms | 无FPU, 定点q15可用 |
| STM32F303 | 72MHz | ~12ms | ~3ms | M4 FPU |
| STM32F411 | 100MHz | ~8ms | ~2ms | M4F, 常见性价比 |
| STM32H743 | 480MHz | ~1ms | ~0.3ms | M7, DSP+FPU最强 |
| STM32G474 | 170MHz | ~5ms | ~1.2ms | M4, 数学加速器 |
| ESP32 | 240MHz | ~15ms | — | 无CMSIS-DSP, 用ESP-DSP |
| ESP32-S3 | 240MHz | ~10ms | — | 向量指令加速 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| FFT 结果全零 | 输入数据未填充或全零 | 检查 ADC 采样是否正常 |
| 频谱镜像对称 | 用 cfft 处理实信号 | 实信号用 rfft(只输出半幅频谱) |
| 频谱泄漏严重 | 未加窗或窗函数不合适 | 加汉宁窗，或选择更多旁瓣抑制的窗 |
| 频率分辨率不够 | FFT 点数太小 | 增大 FFT 点数或降低采样率 |
| FFT 时间超采样间隔 | 计算时间 > 采样时间 | 减小 FFT 点数或用定点 q15 |

## 边界定义

- **不覆盖** FIR/IIR 数字滤波器设计 → 使用 `dsp-module`
- **不覆盖** 音频编解码（MP3/AAC/Opus）
- **不覆盖** 图像傅里叶变换（2D FFT 属于图像处理）
- **不覆盖** 小波变换(Wavelet)
- 定点 q15/q31 FFT 需要注意饱和和精度损失
- FFT bin 之间的频率值需要用插值法估算

## 交接关系

- 上游：`adc-module`（FFT 输入端：ADC 采样数据采集）
- 互补：`dsp-module`（时域 FIR/IIR 滤波 + 频域 FFT 频谱分析互补）
- 下游：`lvgl-module`（实时频谱显示 GUI 实现）
- 下游：`timer-module`（定时触发 ADC 采样，控制采样率）
- 参考：`chip-architecture`（DSP/FPU 指令集支持选型）
