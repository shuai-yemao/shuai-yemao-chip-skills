---
name: dsp-module
description: |
  嵌入式数字信号处理(DSP)开发指南。覆盖 CMSIS-DSP 软件库函数、
  FIR/IIR 数字滤波器设计与实现（直接型/级联型/格型）、
  定点 vs 浮点 DSP 编程、arm_math.h 常用函数速查、
  STM32 M4/M7 DSP指令集(SIMD/MAC)、ESP32 软件 DSP、
  滤波器系数生成(Python+scipy)、PID 控制算法、矩阵运算、统计函数。
  当用户提到 DSP、数字信号处理、CMSIS-DSP、arm_math、FIR 滤波器、
  IIR 滤波器、低通滤波、高通滤波、巴特沃斯、切比雪夫、PID 算法、
  定点 DSP、浮点 DSP、SIMD、MAC 指令、信号处理、滤波算法、
  scipy 生成系数、滤波器设计、噪声滤除 时使用。
version: "1.0.0"
---

# 嵌入式数字信号处理(DSP)开发指南

## 适用场景

- 需要对传感器 ADC 数据进行数字滤波（去噪/平滑/去趋势）
- 需要实现 FIR/IIR 数字滤波器（低通/高通/带通/带阻）
- 需要利用 Cortex-M4/M7 的 DSP 指令集(SIMD/MAC)加速计算
- 需要将 Python/scipy 设计的滤波器系数移植到嵌入式 C
- 需要实现 PID 控制算法、矩阵运算、统计处理
- 需要在 ESP32 等无硬件 DSP 的 MCU 上实现软件 DSP

## 必要输入

| 参数 | 说明 |
|------|------|
| MCU 平台 | STM32F4(M4+F) / STM32H7(M7+DP) / STM32F1(M3无DSP) / ESP32 |
| 采样率(Hz) | ADC 采样频率，决定滤波器截止频率 |
| 滤波器类型 | FIR / IIR(Butterworth/Chebyshev/Bessel) |
| 截止频率 | 低通/高通/带通/带阻 的频率参数 |
| 浮点 vs 定点 | float / q15 / q31 |

## CMSIS-DSP 核心函数速查

### 常用函数分类

| 类别 | 函数 | 说明 |
|------|------|------|
| **滤波** | `arm_fir_f32` / `arm_fir_q15` | FIR 滤波器(浮点/定点) |
| | `arm_biquad_cascade_df1_f32` / `arm_biquad_cascade_df2T_f32` | IIR 双二阶滤波器 |
| | `arm_lms_f32` | 自适应 LMS 滤波器 |
| **变换** | `arm_rfft_fast_f32` / `arm_cfft_f32` | FFT/IFFT（实数/复数） |
| | `arm_dct4_f32` | DCT-IV 变换 |
| **矩阵** | `arm_mat_mult_f32` / `arm_mat_inverse_f32` | 矩阵乘/逆/转置 |
| **统计** | `arm_mean_f32` / `arm_std_f32` / `arm_var_f32` | 均值/标准差/方差 |
| | `arm_max_f32` / `arm_min_f32` | 最大值/最小值 |
| **数学** | `arm_sin_f32` / `arm_cos_f32` / `arm_sqrt_f32` | 快速三角函数/平方根 |
| | `arm_pid_f32` | PID 控制器 |
| **转换** | `arm_float_to_q15` / `arm_q31_to_float` | 浮点 ↔ 定点 |

## FIR 滤波器实现

### Python 设计 + scipy 生成系数

```python
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt

# 设计一个 FIR 低通滤波器
fs = 1000.0          # 采样率 1kHz
fc = 50.0            # 截止频率 50Hz
numtaps = 51          # 滤波器阶数(系数个数)

# 用窗口法设计
coeff = signal.firwin(numtaps, fc, fs=fs, window='hamming')

# 生成 C 数组定义
print(f'#define FIR_NUM_TAPS {numtaps}')
print(f'const float32_t fir_coeffs[FIR_NUM_TAPS] = {{')
for c in coeff:
    print(f'    {c:.10f}f,')
print('};')

# 频率响应验证
w, h = signal.freqz(coeff, worN=8000)
plt.plot(w*fs/(2*np.pi), 20*np.log10(np.abs(h)))
plt.axvline(fc, color='r', linestyle='--')
plt.grid(True)
```

### STM32 CMSIS-DSP FIR 实现

```c
#include "arm_math.h"

#define FIR_NUM_TAPS 51
#define BLOCK_SIZE   32

// Python scipy 生成的系数
const float32_t fir_coeffs[FIR_NUM_TAPS] = {
    -0.0001f, -0.0003f, -0.0005f, /* ... 51 个系数 */  0.0005f, 0.0003f, 0.0001f
};

// FIR 状态缓冲区 (必须为 2*BLOCK_SIZE + FIR_NUM_TAPS - 1)
static float32_t fir_state[BLOCK_SIZE + FIR_NUM_TAPS - 1];
static arm_fir_instance_f32 fir_s;

void fir_init(void)
{
    arm_fir_init_f32(&fir_s, FIR_NUM_TAPS, fir_coeffs, fir_state, BLOCK_SIZE);
}

// 每次送入 BLOCK_SIZE 个采样点，获得 BLOCK_SIZE 个滤波输出
void fir_process(float32_t *input, float32_t *output, uint32_t block_size)
{
    arm_fir_f32(&fir_s, input, output, block_size);
}
```

## IIR 双二阶滤波器

```python
# Python scipy 设计 IIR 低通 (Butterworth, 4阶)
fs = 1000.0
fc = 50.0
sos = signal.butter(4, fc, 'low', fs=fs, output='sos')
# sos 是 (2阶数 × 6) 的矩阵 → 每个 2 阶有 6 个系数
# [b0 b1 b2 a0 a1 a2]

# 转成 C 数组
print(f'#define IIR_NUM_STAGES {sos.shape[0]}')
for stage in range(sos.shape[0]):
    b0, b1, b2, a0, a1, a2 = sos[stage]
    print(f'// Stage {stage}: b0={b0:.8f}, b1={b1:.8f}, b2={b2:.8f}')
    print(f'//            a1={a1:.8f}, a2={a2:.8f}')
```

```c
// CMSIS-DSP IIR 级联实现
#include "arm_math.h"

#define IIR_NUM_STAGES 2       // 4 阶 = 2 个双二阶
#define BLOCK_SIZE    32

static float32_t iir_state[4 * IIR_NUM_STAGES];  // 状态变量
static arm_biquad_casd_df1_inst_f32 iir_s;

// Python 生成的系数 (a0=1 归一化)
const float32_t iir_coeffs[5 * IIR_NUM_STAGES] = {
    // Stage 0: b0, b1, b2, a1, a2
    1.0f, -1.6f, 1.0f,  1.5f, -0.6f,
    // Stage 1: b0, b1, b2, a1, a2
    1.0f,  0.5f, 0.1f,  0.8f, -0.3f,
};

void iir_init(void)
{
    arm_biquad_cascade_df1_init_f32(&iir_s, IIR_NUM_STAGES,
                                     iir_coeffs, iir_state);
}

void iir_process(float32_t *input, float32_t *output, uint32_t block_size)
{
    arm_biquad_cascade_df1_f32(&iir_s, input, output, block_size);
}
```

## 性能对比

| 滤波器 | STM32F103(72MHz) | STM32F411(100MHz) | STM32H743(480MHz) | ESP32(240MHz) |
|--------|-----------------|-------------------|-------------------|---------------|
| FIR 51阶, 每采样 | ~5μs | ~1.5μs | ~0.3μs | ~2.5μs(软件) |
| IIR 4阶, 每采样 | ~2μs | ~0.6μs | ~0.1μs | ~1μs(软件) |
| 1024点 FFT | ~40ms | ~8ms | ~1ms | ~15ms |

**关键差异**：
- M4/M7 有硬件 FPU + DSP 指令(SMAC/UMAAL) → FIR 计算 1 MAC/cycle
- M3 无 FPU + 无 DSP 指令 → 纯软件浮点，慢 10-20x
- M7 双精度 FPU → double 运算与 float 几乎同速
- ESP32 无 DSP 指令 → CMSIS-DSP 不可用，需用 ESP-DSP 库或纯 C

## PID 控制器

```c
// CMSIS-DSP PID 控制器
float32_t pid_process(float32_t setpoint, float32_t measurement)
{
    static arm_pid_instance_f32 pid;
    static int initialized = 0;

    if (!initialized) {
        // Ziegler-Nichols 整定或经验参数
        pid.Kp = 2.0f;
        pid.Ki = 0.5f;
        pid.Kd = 0.1f;
        arm_pid_init_f32(&pid, 1);  // 1 = 重置积分累加
        initialized = 1;
    }

    float32_t error = setpoint - measurement;
    return arm_pid_f32(&pid, error);
}
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 滤波器不收敛 | IIR 极点超出单位圆 | 检查 scipy butter/cheby1 稳定性，增加截止频率 |
| FIR 毛刺(起始) | 状态缓冲区未清零 | arm_fir_init 时确保 state 内存已清零 |
| 相位失真 | FIR 线性相位被破坏 | 确认系数对称，使用 `firwin` 默认对称 |
| CMSIS-DSP 编译错误 | 未启用 FPU/DSP 指令 | GCC: `-mfpu=fpv4-sp-d16 -mfloat-abi=hard` |
| ESP32 arm_math 不存在 | 无 CMSIS-DSP | 用 ESP-DSP 库或纯 C 实现 |

## 平台差异

| 平台 | DSP 库 | FPU | 典型 FIR(51阶) |
|------|--------|-----|---------------|
| STM32F4 | CMSIS-DSP | 单精度 | ~1.5μs/采样 |
| STM32F7/H7 | CMSIS-DSP | 双精度 | ~0.3μs/采样 |
| STM32F1/G0 | 无(需软件) | 无 | ~50μs/采样(软件浮点) |
| ESP32 | ESP-DSP(部分) | 单精度 | ~2.5μs/采样 |
| GD32F4 | CMSIS-DSP(兼容) | 单精度 | ~2μs/采样 |

## 边界定义

- **不覆盖** FFT（快速傅里叶变换）→ 使用 `fft-module`
- **不覆盖** 高级控制算法（MPC/卡尔曼滤波/状态观测器）
- **不覆盖** 音频编解码（MP3/AAC/Opus）
- **不覆盖** 图像处理（OpenMV/OpenCV）
- 定点 DSP(q15/q31) 需要额外注意溢出问题

## 交接关系

- 互补：`fft-module`（频率域分析，与 FIR/IIR 时域滤波互补）
- 下游：`adc-module`（DSP 输入端：ADC 采样数据）
- 下游：`motor-control`（PID 控制器、电流环/速度环 DSP）
- 参考：`chip-architecture`（DSP 指令集支持选型）
