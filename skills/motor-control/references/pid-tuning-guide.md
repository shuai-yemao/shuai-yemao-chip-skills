# PID 调参与多环伺服控制指南

> 对应 `motor-control` v2.0.0 专业电机控制 SKILL.md 的调参参考。
> 覆盖 FOC 多环级联/并联架构的完整参数整定方法。

## 电流环 PI 整定（IMC 内模控制法）

### IMC 公式

```c
// 内模控制 (Internal Model Control) 整定法
// 适用于 PMSM/BLDC 电流环 Id/Iq PI 参数

// 电机参数：
// Rs — 相电阻 (Ω)
// Ls — 相电感 (H) — 对 PMSM 区分 Ld 和 Lq
// τe = Ls / Rs — 电气时间常数

// IMC 整定公式：
// Kp = bw × Ls
// Ki = bw × Rs
// 其中 bw = 目标电流环带宽 (rad/s)

void current_pi_tune_by_imc(CurrentPI *pi, float rs, float ls, float bw_hz)
{
    float bw_rad = bw_hz * 2.0f * 3.14159f;  // Hz → rad/s
    pi->kp = bw_rad * ls;                     // Kp = bw × L
    pi->ki = bw_rad * rs;                     // Ki = bw × R
}
```

### 带宽选择规则

| 条件 | 带宽上限 | 说明 |
|------|---------|------|
| PWM 频率 f_pwm | f_pwm / 2 | 奈奎斯特限制 |
| 电流采样延迟 | f_pwm / 4 ~ f_pwm / 6 | 考虑 ADC 转换 + 计算延迟 |
| 电气时间常数 τe | 1 / (2π × τe) | L/R 极点限制 |
| 推荐上限 | f_pwm / 10 | 工程安全范围 |

**典型值（f_pwm = 20kHz）：**

```
保守:  bw = 800 Hz   → Kp = 800×2π×Ls,  Ki = 800×2π×Rs
中等:  bw = 1500 Hz  → Kp = 1500×2π×Ls, Ki = 1500×2π×Rs
极限:  bw = 2000 Hz  → Kp = 2000×2π×Ls, Ki = 2000×2π×Rs
```

### Kp/Ki 参数效果

| 参数 | 增大效果 | 过大后果 | 过小后果 |
|------|---------|---------|---------|
| Kp | 响应更快，带宽更高 | 电流振荡，噪声放大 | 响应慢，跟随误差大 |
| Ki | 消除稳态误差 | 低频振荡，相位滞后 | 稳态误差不消除 |
| Kp 固定 + 增大 Ki | 改善 Id=0 跟踪 | 超调，积分饱和 | — |

### 限幅配置

```c
// 电流环输出限幅直接影响 SVPWM 调制比
pi->output_max = 0.95f;          // 占空比限幅 (留过调制余量)
pi->integral_max = 0.3f;         // 积分限幅 = output_max × 0.3
```

## DQ 解耦调参

### 交叉耦合方程

```
Vd = Rs×Id + Ld×dId/dt - ωe×Lq×Iq
Vq = Rs×Iq + Lq×dIq/dt + ωe×(Ld×Id + φf)

交叉耦合项：
  Vd_cross = -ωe × Lq × Iq          ← 随 ωe×Iq 增大
  Vq_cross =  ωe × (Ld×Id + φf)     ← 随 ωe 增大 (反电动势)
```

### 解耦必要性判断

| 条件 | 建议 |
|------|------|
| ωe × Lq × Iq_max < 0.05 × VDC | 可不解耦 |
| 0.05 × VDC < ωe × Lq × Iq_max < 0.2 × VDC | 建议解耦 |
| ωe × Lq × Iq_max > 0.2 × VDC | 必须解耦 |

**实践中：低速（< 10% 额定转速）可以不解耦，高速必须解耦。**

### 解耦参数获取

| 参数 | 获取方式 | 精度影响 |
|------|---------|---------|
| Ld | 参数辨识测量 | 低估 → 欠解耦 |
| Lq | 参数辨识测量 | 低估 → 欠解耦 |
| φf (永磁磁链) | 由 Ke 换算: φf = Ke / (√3 × pole_pairs) | 低磁链估计 → Vq 过补偿 |
| ωe (电角速度) | θ 差分: ωe = (θ[k] - θ[k-1]) × fs | θ 噪声 → ωe 噪声放大 |

## 速度环 PI + 前馈整定

### 机电时间常数

```
τm = J × Rs / (Kt × Ke)

其中：
  J  = 转子 + 负载转动惯量 (kg·m²)
  Kt = 转矩常数 = 1.5 × pole_pairs × φf (N·m/A)
  Ke = 反电动势常数 (V·s/rad)
  Rs = 相电阻 (Ω)
```

### 经验整定流程

```c
// Step 1: Ki=0, Kff=0, 逐步增大 Kp
//   观察速度响应，直到出现轻微过冲 (~10%)
//   记录此时的 Kp_critical

// Step 2: Kp = Kp_critical × 0.7 (留余量)
//   此时速度响应应无过冲，但可能有稳态误差

// Step 3: 逐步增大 Ki
//   Ki 从 Kp / (10 × τm) 开始
//   观察加减速后的速度恢复时间
//   增大 Ki 直到稳态误差消除，但不要引起低频振荡

// Step 4: 加前馈 Kff
//   Kff 从 0 开始，逐步增大
//   观察梯形加减速时的跟随误差
//   最优时加减速过程误差接近 0
//   Kff 过大 → 加减速时"超前"（速度前冲）

// Step 5: 连接负载后重新 Step 1~4
```

### Kp/Ki/Kff 效果速查

| 参数 | 效果 | 过大 | 过小 |
|------|------|------|------|
| Kp | 刚度 + 响应速度 | 速度超调 + 位置过冲 | 软，跟随误差大 |
| Ki | 稳态精度 + 抗扰 | 低频振荡 (2~10Hz) | 加减速有偏 |
| Kff | 动态跟随精度 | 速度超前/前冲 | 梯形拐点有误差 |

### 速度环带宽范围

| 电机系统 | 带宽范围 | 说明 |
|---------|---------|------|
| 大惯量 (机床主轴) | 10~50 Hz | 机械时间常数大 |
| 中惯量 (机器人关节) | 50~200 Hz | 减速器弹性限制 |
| 小惯量 (伺服电机) | 200~500 Hz | 直驱或小减速比 |
| 超小惯量 (无人机电机) | 500~1000 Hz | 无负载绕线电机 |

## 位置环整定

### 控制器类型对比

| 类型 | 公式 | 特点 |
|------|------|------|
| P-only | output = Kp × err | 简单，有跟随误差 |
| PDFF | output = Kp × err + Kff × vel_ref | 减少跟随误差，平滑 |
| PPV | output = Kp × err + Kff × vel_ref - Kv × vel_measured | 阻尼可控，跟踪最好 |

### PDFF 参数选择

```c
// Kp — 位置环刚度
//   范围: 10~100 (取决于位置分辨率)
//   越大 → 位置恢复越快，但易过冲
//   过大 → 速度环指令超限 → 速度环饱和引起抖动

// Kff — 速度前馈
//   理想值: 1.0 (当外环输出 = 内环速度指令时)
//   实际: 0.8~0.95 (留余量)
//   作用: 跟踪匀速运动时减小跟随误差

// Kv — 速度阻尼 (PPV 结构)
//   范围: 0.1~0.5 × Kp
//   作用: 抑制位置响应过冲
//   增大 → 阻尼更大，响应变慢

// 限幅：
//   output_max = 速度环最大指令 (rpm 或 rad/s)
//   一般设为额定转速的 80%
```

### 轨迹规划参数

| 参数 | 选择依据 | 典型值 |
|------|---------|-------|
| v_max (最大速度) | 电机额定转速 × 安全系数 (0.8) | 3000 rpm (300W伺服) |
| a_max (最大加速度) | 电机最大转矩 / 负载惯量 | 5000 rpm/s |
| jerk (急动度) | 机械系统刚度 | 50000 rpm/s² |
| dt (位置环周期) | 控制频率决定 | 2.5ms (400Hz) |

## 2DOF PID 调参指南

### PID 结构对比

```
标准 PID:  u = Kp×e + Ki×∫e + Kd×de/dt
           e = ref - measured
           → 设定值突变时比例项和微分项均跳变

PI-D:      u = Kp×e + Ki×∫e - Kd×d(measured)/dt
           → 微分只作用在测量值，设定值突变无微分冲击

I-PD:      u = -Kp×measured + Ki×∫e - Kd×d(measured)/dt
           → 比例和微分都不含设定值，过冲最小

2DOF PID:  u = Kp×(b×ref - measured) + Ki×∫e + Kd×(c×ref - measured)
           b = 设定值加权系数 (0~1)
           c = 微分设定值加权系数 (0~1)
```

### b/c 参数选择

| b | c | 等效结构 | 响应特点 | 适用场景 |
|---|----|---------|---------|---------|
| 1.0 | 0 | PI-D | 最快响应，有 ~10% 过冲 | 电流环 |
| 0.7 | 0 | 折中 | 响应快，~5% 过冲 | 速度环 |
| 0.5 | 0 | 平滑 | 慢响应，几乎无过冲 | 位置环 |
| 0.0 | 0 | I-PD | 无过冲，响应最慢 | 对过冲敏感的应用 |
| 1.0 | 1.0 | 标准 PID | 最快但有微分冲击 | 不推荐 (除非需要) |

### 整定推荐

```
第一步: 按标准 PID 调好 Kp/Ki/Kd
第二步: 根据过冲容忍度选择 b
第三步: 固定 c=0 (PI-D 模式)
第四步: 如需更好的跟踪性能，逐步增大 Kff (前馈)
```

## 扰动观测器 (DOB) 整定

### 原理

```
J × dω/dt = Te - Tload - B × ω
Tload_est = Te - J × dω/dt - B × ω

其中：
  Te = 1.5 × pole_pairs × (φf × Iq + (Ld-Lq)×Id×Iq)
  J  = 总惯量 (kg·m²)
  B  = 粘滞摩擦系数
```

### 观测器增益 g 选择

```c
// DOB 本质上是一个一阶低通滤波器
// 截止频率 f_cut = g / (2π)

// g 太小 → 观测缓慢，扰动补偿延迟大
// g 太大 → 噪声耦合进前馈，速度抖动

// 经验法则：
// g = 2π × f_speed_loop × 0.5    (保守：速度环带宽的一半)
// g = 2π × f_speed_loop × 1.0    (中等：等于速度环带宽)
// g = 2π × f_speed_loop × 2.0    (激进：速度环带宽的两倍)

f_cut = 速度环带宽 × (0.5 ~ 2.0)
```

### DOB 带宽选择指南

| 场景 | 推荐带宽 | 说明 |
|------|---------|------|
| 恒速负载 (传送带) | 5~10 Hz | 慢变负载，低通强 |
| 周期性负载 (压缩机) | 基频 × 2~5 | 需抑制特定频率 |
| 冲击负载 (机械手抓取) | 速度环带宽 × 1~2 | 快速响应 |
| 高噪声 (编码器精度低) | 2~5 Hz | 防止噪声耦合 |

### 惯量 J 辨识方法

```c
// 方法：加减速辨识
// 1. 在恒定转矩 Te 下加速
// 2. 记录 dω/dt
// 3. J = Te / (dω/dt)  (忽略 B 项的低速近似)

// 更准确：
// 以不同加速度多次运行，最小二乘法拟合：
// Te = J × dω/dt + B × ω
// 多组 (Te, dω/dt, ω) → 线性回归 → J, B
```

## 陷波滤波器设计

### 扫频法找共振频率

```c
// 步骤：
// 1. 系统闭环运行在额定速度的 30%
// 2. 在 Iq_ref 上叠加正弦扫描信号
//    幅值: 5~10% 额定转矩
//    频率: 10Hz ~ 2000Hz (对数扫频)
// 3. 测量速度响应幅值
// 4. 找到幅值突变的频率 = 共振频率

// 软件实现：
for (f = 10; f <= 2000; f *= 1.1f) {
    float amplitude = 0.05f * IQ_NOMINAL;
    inject_sine(f, amplitude, DURATION_MS);
    float response = measure_speed_response(f);
    log_data(f, response);
    // 响应幅值 > 输入幅值 × 2 → 共振点
}
```

### 陷波器参数选择

| 参数 | 选择规则 | 说明 |
|------|---------|------|
| f0 (中心频率) | 等于扫频找到的共振频率 | 精确到 ±5Hz |
| bw (带宽) | 共振峰的半高宽 (FWHM) | 越窄越精准 |
| r (极点半径) | r = 1 - π × bw / fs | 0 < r < 1，接近 1 窄 |

**典型带宽经验值：**

| 共振类型 | 共振峰 Q 值 | 建议 bw | r (fs=10kHz) |
|---------|------------|---------|-------------|
| 结构共振 (刚性) | 高 (Q>10) | 5~10 Hz | 0.997~0.999 |
| 皮带共振 | 中 (Q=3~10) | 10~30 Hz | 0.991~0.997 |
| 柔性联轴器 | 低 (Q=1~3) | 30~80 Hz | 0.975~0.991 |

### 陷波器放置位置

```
最佳位置：串联在速度环输出 (Iq_ref 前)

   速度 PI → [陷波滤波器] → Iq_ref → [电流环]
               ↑
        只滤除共振频率

注意：
- 陷波器会引入额外的相位延迟
- 多个陷波器串联 → 相位累积 → 可能降低稳定裕度
- 最多串联 2~3 个陷波器
```

## 系统参数辨识完整流程

### Step 1: 电阻 Rs 测量

```c
// 条件: 转子锁住或不转
// 方法: D 轴注入直流电压，测量稳态电流

// Vd = 0.1 × VDC (10% 母线电压)
// 等待 5 × τe (电气时间常数) 使电流稳定
// Rs = Vd / Id_stable

// 精度: ~5% (受死区效应和 MOSFET 压降影响)
// 改善: 多个电压点测量后线性回归
```

### Step 2: 电感 Ld/Lq 测量

```c
// Ld 测量:
//   D 轴注入电压阶跃 Vd_test
//   转子对齐 (θ=0)
//   测量电流上升斜率 di/dt
//   Ld = Vd_test / (di/dt)

// Lq 测量:
//   D 轴注入电流偏置 (Id_bias, 约 10% 额定)
//   转子对齐后注入高频小信号
//   或使用旋转测量法 (需外力拖动)

// 注意：
//   Ld/Lq 随电流饱和而变化
//   在不同 Id/Iq 工作点测量 → Ld/Lq 查表
//   内置式 PMSM (IPMSM): Lq > Ld, 相差 ~2~3 倍
//   表贴式 PMSM (SPMSM): Ld ≈ Lq
```

### Step 3: 反电动势常数 Ke / 磁链 φf 测量

```c
// 方法 A: 外力拖动法
//   外力驱动电机到已知转速 (如 1000 RPM)
//   测量开路线电压 Vll_peak (示波器 or ADC)
//   Ke = Vll_peak / speed_rpm  (V/RPM)
//   磁链: φf = Vll_peak / (ωe × √3)

// 方法 B: 自测法 (无外力)
//   空载运行电机到某速度
//   突然关断 PWM，记录反电动势衰减
//   在电流 = 0 的时刻测量电压
//   (需快速 ADC + 精确时序)

// 注意：
//   Ke 随温度升高而降低 (永磁体退磁)
//   每升高 10°C → Ke 下降约 0.1~0.2%
//   热态和冷态 Ke 可差 5~10%
```

### Step 4: 惯量 J 辨识

```c
// 使用前文的加减速法
// 也可用 FFT 扫频方法：
//   注入正弦 Iq_ref，扫描 1~100 Hz
//   测量速度响应幅值和相位
//   拟合传递函数获取 J 和 B

// 传递函数模型：
// G(s) = ω(s) / Te(s) = 1 / (J×s + B)
// 在频率 ω0 处: |G| = 1/√(J²×ω0² + B²)
// 低频时: |G| ≈ 1/B
// 高频时: |G| ≈ 1/(J×ω0)
```

## 级联环路带宽分配

### 带宽比规则

```
电流环带宽 > 速度环带宽 × 5~10
速度环带宽 > 位置环带宽 × 5~10

原因：内环响应必须远快于外环，否则外环的指令
      内环来不及跟随 → 系统不稳定
```

### 标准分配表 (f_pwm = 20kHz 为例)

| 带宽配置 | 电流环 | 速度环 | 位置环 | 特点 |
|---------|--------|--------|--------|------|
| 保守 | 1000 Hz | 100 Hz | 20 Hz | 稳定，响应慢 |
| 标准 | 1500 Hz | 200 Hz | 40 Hz | 通用伺服 |
| 激进 | 2000 Hz | 500 Hz | 100 Hz | 高速高精度 |
| 极限 | 3000 Hz | 1000 Hz | 200 Hz | 需高 PWM 频率 |

### 稳定性检查

```c
// 电流环闭环带宽 ≈ Kp / (2π × L)
// 速度环闭环带宽 ≈ Kt × Kp_speed / (2π × J)
// 位置环闭环带宽 ≈ Kp_pos / (2π)

// 检查：电流环带宽 > 5 × 速度环带宽?
//       速度环带宽 > 5 × 位置环带宽?
// 不满足 → 降低外环带宽 或 提高内环带宽
```

## 采样与定时整定

### PWM 中心对齐采样

```
    ┌────┐         ┌────┐         ┌────┐
    │    │         │    │         │    │
    │    │         │    │         │    │
    │    │         │    │         │    │
────┴────┴─────────┴────┴─────────┴────┴────
    ↑    ↑              ↑
  上溢  ADC采样       下溢
        (电流环 ISR)

ADC 触发点: 在 PWM 计数器 = 0 或 = ARR/2 时
原因: 此时开关管导通状态稳定，电流噪声最小
```

### ADC 触发延迟计算

```c
// ADC 采样延迟组成：
// 1. ADC 采样时间 (采样周期数 × ADC 时钟周期)
//    1.5~601.5 个周期，取决于采样率配置
// 2. ADC 转换时间 (12bit = 12 个周期)
// 3. DMA 传输时间 (2 个字 = 2 × AHB 时钟周期)
// 4. 电流环计算时间 (Clarke + Park + PI + InvPark + SVPWM)

// 总延迟 ≈ ADC 时间 + DMA 时间 + 计算时间
// 典型值: 3~10 µs (f_pwm=20kHz, Ts=50µs 时占比 6~20%)

// 延迟过大 → 电流采样滞后 → 等效带宽降低
// 优化：用 DMA 双缓冲 + 乒乓模式流水线
```

## 参数整定检查清单

### 调试前

- [ ] 母线电压 VDC 测量正确
- [ ] 电流传感器偏置已校准 (Id = Iq = 0 时 ADC 读数为 0)
- [ ] 编码器/霍尔方向与电机旋转方向一致
- [ ] PWM 死区时间设置正确 (通常 0.5~2 µs)
- [ ] 电流环执行频率已知 (f_current_loop = ?)

### 调试中

- [ ] 电流环无振荡 (示波器观察 Iq/Id 波形)
- [ ] Id 稳定跟踪 0 (或 MTPA 目标值)
- [ ] DQ 解耦开启后高速电流无交叉耦合现象
- [ ] 速度环无低频抖动 (2~10 Hz 振荡)
- [ ] 位置环无过冲 (阶跃响应 overshoot < 5%)
- [ ] 加减速过程跟随误差在可接受范围

### 调试后

- [ ] 扫频确认无机械共振
- [ ] 全速度范围稳定运行 (低速无抖动，高速无啸叫)
- [ ] 满载运行温升在正常范围
- [ ] 参数已保存到非易失存储器

## 调试观测手段搭建

### 方案 A：DAC 实时输出（看电流环，推荐）

用 STM32 内部 DAC（或 PWM+RC 滤波模拟 DAC）在示波器上实时观察电流、环路输出，不限制更新率。

```c
// STM32 DAC 配置（PA4=DAC1_OUT1, PA5=DAC1_OUT2）
// 两路 DAC 通道实时输出 Id_fb 和 Iq_fb

static void dac_output_curves(float id, float iq)
{
    // 将 float 映射到 0~4095 (DAC 12bit)
    // Id=0 → DAC=2048 (中点)，±5A → 0~4095
    #define SCALE_A  (4095.0f / 10.0f)

    uint16_t dac_id = (uint16_t)(id * SCALE_A + 2048.0f);
    uint16_t dac_iq = (uint16_t)(iq * SCALE_A + 2048.0f);

    // 硬件写 DAC 数据寄存器（在电流环 ISR 末尾调用）
    DAC1->DHR12R1 = dac_id;   // CH1 → Id_fb
    DAC1->DHR12R2 = dac_iq;   // CH2 → Iq_fb
}

// 示波器连接：CH1=PA4(Id), CH2=PA5(Iq)
// 给 Iq 阶跃指令，看 CH2 上升沿即可评价电流环带宽
```

### 方案 B：高速 RAM 缓存 + 串口 Dump（看速度环）

```c
// 在电流环 ISR 中按分频记录数据到 RAM
// 串口收到 dump 命令时批量输出 CSV

#define LOG_CAPACITY  4096

typedef struct {
    float id, iq;
    float vd, vq;
    float speed_ref, speed_fb;
    float pos_ref, pos_fb;
} LogEntry;

LogEntry log_buf[LOG_CAPACITY];
volatile uint16_t log_head = 0;

// 电流环 ISR 末尾调用（每 N 次记录 1 次）
static void log_push(float id, float iq, float vd, float vq,
                     float sref, float sfb)
{
    if (log_head < LOG_CAPACITY) {
        log_buf[log_head].id = id;
        log_buf[log_head].iq = iq;
        log_buf[log_head].vd = vd;
        log_buf[log_head].vq = vq;
        log_buf[log_head].speed_ref = sref;
        log_buf[log_head].speed_fb = sfb;
        log_head++;
    }
}

// 串口命令: dump → 输出 CSV
void cmd_dump(void)
{
    printf("[LOG] %d entries @ %d Hz\n", log_head, CURRENT_LOOP_HZ / 10);
    for (uint16_t i = 0; i < log_head; i++) {
        printf("%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n",
            log_buf[i].id, log_buf[i].iq,
            log_buf[i].vd, log_buf[i].vq,
            log_buf[i].speed_ref, log_buf[i].speed_fb);
    }
    printf("[LOG] done\n");
    log_head = 0;
}
```

### 方案 C：GPIO 脉冲测时（零成本看 ISR 时序）

```c
#define DBG_PIN    GPIO_PIN_0  // PA0
#define DBG_PORT   GPIOA

// 电流环 ISR 入口/出口打脉冲
// 逻辑分析仪抓 PA0，高电平宽度 = ISR 执行时间

void current_loop_isr(void)
{
    DBG_PORT->BSRR = DBG_PIN;              // 上升沿

    // ... 电流环完整计算 ...

    DBG_PORT->BRR = DBG_PIN;               // 下降沿
}

// 再加一个 PA1 标记 Iq 阶跃时刻：
// PA0 宽度 = ISR 执行时间（应 < PWM 周期的 50%）
// PA1 上升沿到 PA0 下降沿 = Iq 指令到电流到达的延迟
```

### 方案 D：Python 自动调参脚本（主机侧）

```python
#!/usr/bin/env python3
"""FOC 自动调参助手 — 串口控制 + 数据采集 + 波形分析"""
import serial, time, numpy as np
import matplotlib.pyplot as plt

SERIAL_PORT = '{SERIAL_PORT}'
BAUD = 115200

def write_cmd(ser, cmd):
    ser.write(f'{cmd}\r\n'.encode())

def read_until(ser, marker, timeout=2):
    """读串口直到遇到 marker"""
    data = []
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline().decode(errors='ignore').strip()
        if marker in line:
            break
        if line:
            data.append(line)
    return data

def capture_dump(ser):
    """触发 dump 并返回 numpy 数组"""
    write_cmd(ser, 'dump')
    lines = read_until(ser, 'done')
    csv_lines = [l for l in lines if l and not l.startswith('[')]
    if len(csv_lines) < 5:
        return None
    return np.loadtxt(csv_lines, delimiter=',')

def analyze_step_response(data, sample_rate=2000):
    """计算阶跃响应指标"""
    iq = data[:, 1]                     # Iq_fb 列
    t = np.arange(len(iq)) / sample_rate
    # 稳态值取最后 20%
    steady = iq[-int(len(iq)*0.2):].mean()
    # 找到首次进入 ±5% 稳态带的时间
    band = abs(steady) * 0.05 if abs(steady) > 0.01 else 0.001
    settled = np.where(np.abs(iq - steady) > band)[0]
    settle_time = t[settled[-1]] if len(settled) > 0 else t[-1]
    # 超调量
    peak = np.max(iq[:int(len(iq)*0.5)])
    overshoot = (peak - steady) / steady * 100 if steady != 0 else 0
    return dict(t=t, iq=iq, steady=steady,
                settle_time_ms=settle_time*1000,
                overshoot_pct=overshoot)

def sweep_param(ser, loop_id, pname, values, test_cmd):
    """扫一组参数值，返回最优结果"""
    results = []
    for val in values:
        write_cmd(ser, f'{loop_id}.{pname}={val}')
        time.sleep(0.05)
        write_cmd(ser, test_cmd)
        time.sleep(0.3)
        data = capture_dump(ser)
        if data is None or len(data) < 20:
            continue

        m = analyze_step_response(data)
        # 评分：综合评价值越小越好
        score = m['overshoot_pct'] * 0.6 + m['settle_time_ms'] * 0.4

        print(f'  {pname}={val:.4f}: '
              f'settle={m["settle_time_ms"]:.1f}ms '
              f'overshoot={m["overshoot_pct"]:.1f}% '
              f'score={score:.1f}')
        results.append((score, val, m, data))

    if not results:
        return None
    results.sort(key=lambda x: x[0])
    best = results[0]

    # 画最优结果的波形
    plt.figure()
    plt.plot(best[3][:,0], label='Id')
    plt.plot(best[3][:,1], label='Iq')
    plt.axhline(best[2]['steady'], color='gray', ls='--')
    plt.legend(); plt.grid(); plt.title(f'Best: {pname}={best[1]:.4f}')
    plt.savefig(f'best_{pname}.png')
    plt.show()

    return best[1]

# === 执行流程 ===
if __name__ == '__main__':
    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0.05)
    time.sleep(1)

    # Step 1: 扫电流环 Q 轴 Kp
    print('=== 电流环 Kp 扫描 ===')
    best_kp = sweep_param(ser, 2, 'kp',
                          np.arange(0.02, 0.25, 0.02),
                          'test current')
    if best_kp:
        write_cmd(ser, f'2.kp={best_kp:.4f}')

    # Step 2: 扫电流环 Ki
    print('=== 电流环 Ki 扫描 ===')
    best_ki = sweep_param(ser, 2, 'ki',
                          np.arange(5, 60, 5),
                          'test current')
    if best_ki:
        write_cmd(ser, f'2.ki={best_ki:.4f}')

    # Step 3: 扫速度环 Kp
    print('=== 速度环 Kp 扫描 ===')
    best_sp = sweep_param(ser, 3, 'kp',
                          np.arange(0.5, 6.0, 0.5),
                          'test speed')

    write_cmd(ser, 'save')
    print('Done — parameters saved to flash')
    ser.close()
```

## 波形判读速查表

| 波形特征 | 根因 | 调参操作 |
|---------|------|---------|
| 响应慢（上升沿缓） | Kp 太小 | ↑ Kp |
| 超调大（尖峰高） | Kp 太大 | ↓ Kp |
| 达不到目标值（有静差） | Ki 太小 | ↑ Ki |
| 低频振荡（波动周期 ~100ms） | Ki 太大 | ↓ Ki |
| 高频毛刺（粗锯齿） | 采样噪声/Kp 过大 | 加滤波或 ↓ Kp |
| 设定值突变时尖峰 | 微分冲击 | 换 PI-D 或减 b 系数 |
| 加减速时偏差大 | Kff 不足 | ↑ Kff |
| 特定频率共振声/振荡 | 机械模态 | 加陷波滤波器 |
| 低速抖动 | 编码器分辨率不够 | ↑ 滤波系数或 M/T 法 |
| Iq 能跟上 Id 跟不上 | D 轴电感差异 | 分开整定 Id/Iq PI 参数 |

## 逐步骤详细调参流程

### Step A：电流环粗调（转子锁定或空载）

```
目标: 找到电流环稳定工作的 Kp/Ki 范围
观测: DAC CH2 = Iq_fb，给 Iq 阶跃

Step A1: Ki=0，从 Kp=0.02 开始
Step A2: 给 0.1A 阶跃，示波器看 Iq 是否响应
  - 无响应 → ↑ Kp 直到看到上升沿
  - 有高频振荡 → ↓ Kp 直到稳定
  - 记录 "临界振荡 Kp_crit"（刚刚开始振的值）
Step A3: Kp = Kp_crit × 0.6 (安全余量)
Step A4: 逐步增大 Ki (从 5 开始)
  - 观察稳态误差是否消除
  - 出现低频振荡 → ↓ Ki
Step A5: 最终检查
  - 阶跃上升时间 < 5 个 PWM 周期
  - 超调 < 5%
  - 稳态误差 < 1%
  - 无振荡

注意事项：
- Id=0 是锁定转子不动的关键
- D 轴和 Q 轴的 Kp 可以不同（如果 Ld ≠ Lq）
- IQ 限幅先设小（30%），防止过流
```

### Step B：速度环调参（松开转子，空载）

```
目标: 速度响应快且无过冲
观测: 串口 dump 2kHz 数据 → Python 绘图

Step B1: Ki=0, Kff=0，Kp=0.5
Step B2: 给 10% 额定转速阶跃
Step B3: 逐步增大 Kp
  - Kp 太小 → 速度缓慢爬升，达不到目标
  - Kp 合适 → 快速但是平滑到达，轻微过冲
  - Kp 太大 → 明显过冲 + 震荡
  记录最佳 Kp（刚刚出现过冲 ~10%，退回 30%）
Step B4: 加 Ki（从 Kp × 0.01 开始）
  - 消除加减速后的稳态偏差
  - Ki 太大 → 低频振荡 (2~10Hz)
Step B5: 加 Kff
  - 给梯形加减速，看拐点处的跟随误差
  - Kff 偏小 → 减速时速度"落后"
  - Kff 偏大 → 加速时速度"超前"
Step B6: 接额定负载后重新 Step B2~B5
```

### Step C：位置环调参（编码器模式）

```
目标: 位置阶跃无过冲
观测: 串口 dump 位置/速度

Step C1: Kp_pos = 10, Kff=0.8
Step C2: 给 90° 阶跃
  - 过冲 → ↓ Kp_pos
  - 响应慢 → ↑ Kp_pos
Step C3: 加前馈 Kff
  - 匀速跟踪误差大 → ↑ Kff
Step C4: 需要更平滑 → 用 PDFF 或 PPV 结构

参数范围经验值：
  P-only:   Kp = 10~100
  PDFF:     Kp = 10~50, Kff = 0.8~0.95
  PPV:      Kp = 10~50, Kff = 0.8~0.95, Kv = 0.1~0.5×Kp
```

## 调参黄金法则

```
1. 从内到外：电流环 → 速度环 → 位置环
   （前一个环没调稳，绝不碰后一个）
2. 一次只改一个参数：先定 Kp 再定 Ki
3. 每次改动都 Dump 存数据，方便回退
4. 阶跃信号是最有用的测试
5. 空载和带载分开调
6. Kp 决定响应速度，Ki 消除稳态误差——各自独立
7. 做完一组调参后用 save 持久化，防止掉电丢失
```
