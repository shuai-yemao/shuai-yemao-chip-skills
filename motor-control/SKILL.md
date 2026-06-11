---
name: motor-control
version: "2.1.0"
description: "专业电机控制开发指南——多环级联/并联伺服控制。覆盖 FOC 矢量控制（Clarke/Park/SVPWM）、电流环/速度环/位置环/角度环的级联与并联架构、数字 PID 高级实现（抗积分饱和/微分先行/条件积分/observer）、BLDC/PMSM 有感无感控制、SVPWM 扇区判定与占空比计算、电机参数辨识（Rs/Ld/Lq/Ke）、陷波滤波器设计、系统带宽整定。当用户提到 FOC、矢量控制、电流环、速度环、位置环、角度环、级联控制、并联控制、多环控制、SVPWM、Clarke 变换、Park 变换、DQ 轴、Id Iq、PMSM、BLDC FOC、M/T 法测速、PI 调节器电流环、带宽整定、无感 FOC、滑模观测器、龙伯格观测器、电机参数辨识、电感测量、反电动势常数、陷波滤波器、共振抑制、伺服电机、多环串联、控制环路、TI InstaSPIN、SimpleFOC、ST MCSDK 时使用。新增：电压圆限制、电流零点校准、MTPA、弱磁控制、ADRC 自抗扰控制对比、3-shunt/1-shunt 采样拓扑选型。"
---

# 专业电机控制开发指南

> **实操调参指南**见 `references/pid-tuning-guide.md`：DAC/串口 Dump/GPIO 观测搭建、逐步骤调参流程、Python 自动调参脚本、波形判读速查表。

## 控制环路架构

### 级联控制（标准伺服结构）

```
位置指令 ─→ [位置环] ─→ 速度指令 ─→ [速度环] ─→ 电流指令 ─→ [电流环] ─→ PWM → 电机
                 ↑                       ↑                       ↑
              位置反馈                 速度反馈            Ia/Ib/Ic 采样
```

| 环路 | 带宽 | 控制频率 | 传感器 | 控制器 |
|------|------|---------|--------|--------|
| **电流环** | 1k~5k Hz | 10k~40k Hz | 电流传感器(采样电阻/霍尔) | PI (Iq/Id 独立控制) |
| **速度环** | 50~500 Hz | 1k~10k Hz | 编码器/霍尔/BEMF | PI + 前馈 |
| **位置环** | 10~100 Hz | 200~1k Hz | 编码器/磁编码器 | P/PDFF |

### 并联控制（特殊应用场景）

```
           ┌── [位置环] ──┐
           │              ├── 选择器 → 电流指令 → [电流环] → 电机
指令 ──→ 判断逻辑 ──→ ──→ [速度环] ──→ min/max
           │              │
           └── [电流环] ──┘

并联场景：
- 力位混合控制（机器人柔顺控制）
- 限幅切换（位置到达限位后切入电流限制）
- 多目标协调（速度+扭矩同时约束）
```

### 控制频率选择

```c
// 电流环: PWM 频率的一半或相等
// f_current_loop = f_pwm (单采样单更新)
// f_current_loop = f_pwm / 2 (单采样双更新)

// 速度环: 电流环频率的 1/5 ~ 1/20
// f_speed_loop = f_current_loop / 10

// 位置环: 速度环频率的 1/5 ~ 1/10
// f_pos_loop = f_speed_loop / 5

// 典型值：
// f_pwm = 20kHz
// f_current = 20kHz (同步更新)
// f_speed = 2kHz (每10次电流环执行一次)
// f_pos = 400Hz (每5次速度环执行一次)
```

## FOC 矢量控制核心

### FOC 信号流

```
Ia/Ib/Ic
   ↓ (ADC 采样)
   ↓  低通滤波
   ↓
Ia,Ib (Ic = -Ia-Ib)       θ (编码器/观测器)
   ↓                          ↓
 [Clarke变换] ─→ Iα,Iβ ──→ [Park变换] ─→ Id,Iq
                                              ↓
                                      Id_ref=0, Iq_ref=速度环输出
                                              ↓
                                    [Id PI]  [Iq PI]
                                              ↓
                                      Vd_REF, Vq_REF
                                              ↓
                                    [逆Park变换] ─→ Vα,Vβ
                                                        ↓
                                              [SVPWM] ─→ Ta,Tb,Tc
                                                        ↓
                                              [PWM 比较器] → 6路PWM
```

### Clarke 变换

```c
// 三相静止 → 两相静止 (α-β)
// 输入: Ia, Ib (Ic = -Ia-Ib)
// 输出: Iα, Iβ

void clarke_transform(float ia, float ib, float *i_alpha, float *i_beta)
{
    *i_alpha = ia;
    *i_beta  = (ia + 2.0f * ib) * 0.577350269f;  // 1/√3
}

// 幅度不变 vs 功率不变：
// 幅度不变 (上面公式): Iα = Ia, 适合电流环 PI
// 功率不变: Iα = sqrt(2/3) * Ia, 适合功率计算
```

### Park 变换

```c
// 两相静止 → 两相旋转 (d-q)
// 输入: Iα, Iβ, θ (转子电角度)
// 输出: Id, Iq

void park_transform(float i_alpha, float i_beta, float theta,
                    float *id, float *iq)
{
    float ct = cosf(theta);
    float st = sinf(theta);
    *id =  i_alpha * ct + i_beta * st;
    *iq = -i_alpha * st + i_beta * ct;
}

// 逆 Park 变换 (从 Vd/Vq 回到 Vα/Vβ)：
void inv_park_transform(float vd, float vq, float theta,
                        float *v_alpha, float *v_beta)
{
    float ct = cosf(theta);
    float st = sinf(theta);
    *v_alpha = vd * ct - vq * st;
    *v_beta  = vd * st + vq * ct;
}
```

### SVPWM (Space Vector PWM)

```c
// 原理：用 8 个开关矢量合成任意方向幅值的电压矢量
// 6 个非零矢量 (V1~V6, 间隔 60°)
// 2 个零矢量 (V0, V7)

// 扇区判定：
int svpwm_sector(float v_alpha, float v_beta)
{
    float v1 = v_beta;
    float v2 = -0.8660254f * v_alpha + 0.5f * v_beta;   // -√3/2, +1/2
    float v3 =  0.8660254f * v_alpha + 0.5f * v_beta;   //  √3/2, +1/2

    int sector = 0;
    if (v1 > 0) sector = 1;
    if (v2 > 0) sector |= 2;
    if (v3 > 0) sector |= 4;

    // sector now in {1,2,3,4,5,6}
    return sector;
}

// 占空比计算（七段式 SVPWM）：
void svpwm_calc(float v_alpha, float v_beta, float vdc,
                float *ta, float *tb, float *tc)
{
    float udc = 1.0f / vdc;
    float x = v_alpha * udc * 0.8660254f;       // √3/2
    float y = (0.5f * v_alpha + 0.8660254f * v_beta) * udc;
    float z = (0.5f * v_alpha - 0.8660254f * v_beta) * udc;

    float t1, t2;
    int sector = svpwm_sector(v_alpha, v_beta);

    // 每个扇区的矢量作用时间
    switch (sector) {
        case 1: t1 = z; t2 = y; break;  // V1(100), V2(110)
        case 2: t1 = y; t2 = -x; break; // V3(010), V2(110)
        case 3: t1 = -z; t2 = x; break; // V3(010), V4(011)
        case 4: t1 = -x; t2 = z; break; // V5(001), V4(011)
        case 5: t1 = x; t2 = -y; break; // V5(001), V6(101)
        case 6: t1 = -y; t2 = -z; break;// V1(100), V6(101)
        default: t1 = 0; t2 = 0;
    }

    // 过调制处理（限幅到 Tpwm）
    float t_sum = t1 + t2;
    if (t_sum > 1.0f) {
        t1 /= t_sum;
        t2 /= t_sum;
    }

    // 七段式占空比插入零矢量
    float t0 = 1.0f - t_sum;
    float t_on = t0 * 0.5f;  // V0 和 V7 均分

    *ta = t_on;
    *tb = t_on;
    *tc = t_on;

    switch (sector) {
        case 1: *tb += t1; *tc += t2; break;
        case 2: *ta += t2; *tc += t1; break;
        case 3: *ta += t1; *tb += t2; break;
        case 4: *tc += t1; *tb += t2; break;
        case 5: *tc += t2; *ta += t1; break;
        case 6: *ta += t2; *tb += t1; break;
    }
}
```

### 电流采样时序

```c
// 关键约束：电流采样必须在 PWM 中心时刻
// 因为此时开关噪声最小，电流最稳定

// PWM 中心对齐模式：
//            ┌────┐         ┌────┐
// TIMx_CCR1  │    │         │    │
//            │    │         │    │
// TIMx_CCR2  │    │         │    │
//            │    │         │    │
// TIMx_CCR3  │    │         │    │
// ───────────┴────┴─────────┴────┴────
//            ↑                 ↑
//        ADC 采样点        ADC 采样点
//        (PWM 中心)

// 当 PWM 在中心对齐模式时：
// 在 TIM 上溢/下溢中断中启动 ADC
// 采样两相电流（第三相 = -(Ia+Ib)）

// CubeMX 配置：
// TIM1: Center-Aligned PWM, Update Interrupt
// ADC: 由 TIM1 TRGO 触发启动
// DMA: 将 ADC 结果传送到电流环输入缓冲

// 采样拓扑选型（3-shunt / 1-shunt / ICS）和零点校准见下文
// "电流采样拓扑与零点校准" 章节
```

## 电流环设计

### Id/Iq 独立 PI 控制

```c
typedef struct {
    float kp;               // 比例增益
    float ki;               // 积分增益
    float integral;         // 积分累计
    float integral_max;     // 积分限幅 (anti-windup)
    float output_max;       // 输出限幅
    float output_min;       // 输出下限
} CurrentPI;

// 电流环 PI 更新（每 PWM 周期执行）
float current_pi_update(CurrentPI *pi, float ref, float measured)
{
    float err = ref - measured;

    // 抗积分饱和 (Clamping)
    float temp_out = pi->kp * err + pi->integral;

    if (temp_out > pi->output_max || temp_out < pi->output_min) {
        // 输出饱和时，只积分往反方向的误差
        // 方法 1: 条件积分
        if ((temp_out > pi->output_max && err < 0) ||
            (temp_out < pi->output_min && err > 0)) {
            pi->integral += pi->ki * err;
        }
    } else {
        pi->integral += pi->ki * err;
    }

    // 积分限幅
    if (pi->integral > pi->integral_max) pi->integral = pi->integral_max;
    if (pi->integral < -pi->integral_max) pi->integral = -pi->integral_max;

    float output = pi->kp * err + pi->integral;

    // 输出限幅
    if (output > pi->output_max) output = pi->output_max;
    if (output < pi->output_min) output = pi->output_min;

    return output;
}
```

### 电流环带宽整定

```c
// 电流环带宽由 PI 参数和电机电气时间常数决定
// f_bw_current = Kp / (2π × L)  (假设 Ki = R/L)

// 典型电机参数：
// Ls (相电感): 100µH ~ 10mH
// Rs (相电阻): 0.1Ω ~ 10Ω
// 电气时间常数 τe = Ls / Rs

// 带宽与 PI 参数关系：
void current_pi_tune(CurrentPI *pi, float rs, float ls, float fs)
{
    // fs = 电流环执行频率 (Hz)
    // 目标带宽 = fs / 10 ~ fs / 20

    float bw = fs * 0.1f;  // 目标带宽 1kHz (fs=10kHz 时)

    // 内模控制 (IMC) 法整定：
    pi->kp = bw * ls;            // Kp = bw × L
    pi->ki = bw * rs;            // Ki = bw × R

    // 反向计算确认：
    // 电流环闭环带宽 ≈ Kp / L = (bw × L) / L = bw ✅

    // 实际中 Kp/Ki 需要微调：
    // 加大 Kp → 响应更快，但噪声放大
    // 加大 Ki → 消除稳态误差，但可能引起低频振荡

    pi->output_max = 0.95f;       // 占空比限幅 (95% 保留余量)
    pi->integral_max = pi->output_max * 0.3f;
}
```

### DQ 解耦

```c
// PMSM 在 DQ 坐标系下有交叉耦合：
// Vd = Rs×Id + Ld×dId/dt - ωe×Lq×Iq
// Vq = Rs×Iq + Lq×dIq/dt + ωe(Ld×Id + φf)

// ωe×Lq×Iq 和 ωe(Ld×Id+φf) 是交叉耦合项
// 高速时耦合严重，需要解耦

float vd_decouple(float vd_pi_output, float we, float lq, float iq)
{
    // vd = vd_pi - ωe × Lq × Iq
    return vd_pi_output - we * lq * iq;
}

float vq_decouple(float vq_pi_output, float we, float ld, float id, float flux)
{
    // vq = vq_pi + ωe × (Ld × Id + φf)
    return vq_pi_output + we * (ld * id + flux);
}

// 解耦后编码到 SVPWM 的 Vd/Vq 值
// 不解耦的效果：高速时 Id 会因 Iq 的变化被耦合干扰
// MTPA (最大转矩电流比) 需要精确解耦
```

## 速度环设计

### M/T 法测速

```c
// M 法: 固定时间内计脉冲数 → 适合高速
// T 法: 测相邻脉冲间隔 → 适合低速
// M/T 法: 结合两者 → 全速度范围

typedef struct {
    int32_t last_cnt;       // 上次编码器计数值
    uint32_t last_tick;     // 上次时间 (timer ticks)
    float speed_rpm;        // 滤波后速度
    float filter_alpha;     // 一阶低通系数
} SpeedEstimator;

float mt_speed_estimate(SpeedEstimator *se, int32_t current_cnt,
                        uint32_t current_tick, float ppr, float dt)
{
    int32_t delta_cnt = current_cnt - se->last_cnt;
    uint32_t delta_tick = current_tick - se->last_tick;

    se->last_cnt = current_cnt;
    se->last_tick = current_tick;

    // M/T 法：用脉冲数和时间共同计算
    // n = delta_cnt / (PPR × 4) [转]
    // T = delta_tick / timer_freq [秒]
    // speed_rpm = n / T × 60 = delta_cnt × timer_freq × 60 / (PPR × 4 × delta_tick)

    float speed_raw = (float)delta_cnt * TIMER_FREQ * 60.0f /
                     (ppr * 4.0f * (float)delta_tick);

    // 一阶低通滤波
    se->speed_rpm = se->filter_alpha * speed_raw +
                   (1.0f - se->filter_alpha) * se->speed_rpm;

    return se->speed_rpm;
}
```

### 速度环 PI + 前馈

```c
typedef struct {
    float kp;               // 比例 (刚度和响应)
    float ki;               // 积分 (稳态精度)
    float kff;              // 前馈系数 (减小跟随误差)
    float integral;
    float integral_max;
    float output_max;
} SpeedPI_FF;

float speed_pi_ff_update(SpeedPI_FF *spi, float ref, float measured,
                         float ref_accel)
{
    float err = ref - measured;

    // 积分处理 (anti-windup)
    spi->integral += spi->ki * err;
    if (spi->integral > spi->integral_max) spi->integral = spi->integral_max;
    if (spi->integral < -spi->integral_max) spi->integral = -spi->integral_max;

    // PI + 前馈
    // 前馈项: kff × 速度变化率 (减小加减速时的跟随误差)
    float output = spi->kp * err + spi->integral + spi->kff * ref_accel;

    if (output > spi->output_max) output = spi->output_max;
    if (output < -spi->output_max) output = -spi->output_max;

    return output;  // 输出作为 Iq_ref
}
```

### 速度环带宽整定

```c
// 速度环带宽由机械时间常数决定
// τm = J × Rs / (Kt × Ke)  (机电时间常数)
// 典型带宽: 50~500 Hz

// 经验整定：
// 1. 固定负载下，从 Ki=0 开始
// 2. 增大 Kp 到速度有轻微振荡，然后减小 30%
// 3. 增大 Ki 消除稳态误差（加减速后的速度偏差）
// 4. 加前馈 Kff 减小梯形曲线的拐点误差
// 5. 连接负载后重新微调

// 参数效果：
// Kp 太大 → 速度超调 → 位置过冲
// Ki 太大 → 速度低频振荡
// Kff 太大 → 加减速时前馈过补偿 → 速度超前
```

## 位置环设计

### P/PDFF 控制器

```c
typedef struct {
    float kp;               // 位置环增益
    float kff;              // 速度前馈
    float kv;               // 速度阻尼
    float output_max;       // 最大速度输出 (限幅)
} PositionController;

float position_pdff_update(PositionController *pc,
                           float pos_ref, float pos_measured,
                           float vel_ref)
{
    float err = pos_ref - pos_measured;

    // PDFF: Pseudo-Derivative Feedback with Feed-forward
    // 输出 = Kp × (pos_ref - pos_measured) + Kff × vel_ref - Kv × vel_measured
    // (Kv × vel_measured 需要外部传入或估算)

    float output = pc->kp * err + pc->kff * vel_ref;

    if (output > pc->output_max) output = pc->output_max;
    if (output < -pc->output_max) output = -pc->output_max;

    return output;  // 输出作为速度环的 speed_ref
}

// 位置环 P 与 PDFF 对比：
// P-only:  简单，但有超调和跟随误差
// PDFF:    减小跟随误差，平滑
// PPV (P+前馈+速度阻尼): 最好的跟踪性能
```

### 运动轨迹规划

```c
// 梯形轨迹 (Trapezoidal)
typedef struct {
    float v_max;        // 最大速度
    float a_max;        // 最大加速度
    float d_max;        // 最大减速度 (通常 = a_max)
    float v_start;      // 起始速度
    float v_end;        // 结束速度
} TrapezoidalProfile;

// 计算梯形轨迹的每个周期的目标位置/速度
void trap_profile_calc(TrapezoidalProfile *tp, float target_pos,
                       float current_pos, float current_vel,
                       float dt, float *pos_ref, float *vel_ref)
{
    float remaining = target_pos - current_pos;
    float dir = (remaining > 0) ? 1.0f : -1.0f;
    float dist = fabsf(remaining);

    // 判断是否需要减速
    float decel_dist = current_vel * current_vel / (2.0f * tp->a_max);
    // 若为梯形则分为三段：加速(in progress, 执行), 匀速(执行), 减速(执行)
    // 实时实现：用有限状态机控制三段
  
    // S 形轨迹 (S-Curve): 加速度连续变化，急动度(Jerk)受限
    // 比梯形更平滑，减少机械冲击
    // 分 7 段：加加速→匀加速→减加速→匀速→加减速→匀减速→减减速
}

// 简化 S 形轨迹实现（使用 Jerk 限制）：
float s_curve_velocity(float target_vel, float current_vel,
                       float jerk, float dt)
{
    float dv = jerk * dt;
    if (current_vel + dv > target_vel)
        return target_vel;
    return current_vel + dv;
}
```

## 高级 PID 技术

### 微分先行 (PI-D)

```c
// 传统 PID: u = Kp×e + Ki×∫e + Kd×de/dt
// 问题: 设定值突变时微分项会产生巨大冲击 (derivative kick)

// PI-D: 微分只作用在测量值上
// u = Kp×e + Ki×∫e - Kd×d(measured)/dt

typedef struct {
    float kp, ki, kd;
    float integral;
    float prev_measured;   // 前次测量值（微分用）
    float integral_max;
    float output_max;
    float tau;             // 微分低通滤波 (1/2πfc)
} PID_PID;

float pid_pid_update(PID_PID *pid, float ref, float measured, float dt)
{
    float err = ref - measured;

    // 积分 (条件积分 Anti-windup)
    pid->integral += pid->ki * err * dt;
    if (pid->integral > pid->integral_max) pid->integral = pid->integral_max;
    if (pid->integral < -pid->integral_max) pid->integral = -pid->integral_max;

    // 微分: 对测量值求导 + 低通滤波
    // 低通: d_measured = (prev_d + tau/dt × d_measured_raw) / (1 + tau/dt)
    float d_measured = (measured - pid->prev_measured) / dt;
    // 简化：实际中常用一阶低通 + 限幅
    pid->prev_measured = measured;

    float output = pid->kp * err + pid->integral - pid->kd * d_measured;

    if (output > pid->output_max) output = pid->output_max;
    if (output < -pid->output_max) output = -pid->output_max;

    return output;
}
```

### 双自由度 PID (2DOF PID)

```c
// 设定值加权 PID:
// u = Kp×(b×ref - measured) + Ki×∫(ref-measured) + Kd×(c×ref - measured)

// b: 设定值加权系数 (0~1)
// c: 微分设定值加权系数 (0~1)
// b=1, c=0 → PI-D (标准)
// b=0, c=0 → I-PD (无过冲)
// b=0.7, c=0 → 折中

typedef struct {
    float kp, ki, kd;
    float b, c;               // 设定值加权
    float integral;
    float prev_measured;
    float output_max;
} PID_2DOF;

float pid_2dof_update(PID_2DOF *pid, float ref, float measured, float dt)
{
    float err = ref - measured;
    float p_err = pid->b * ref - measured;  // 比例用加权误差
    float d_err = pid->c * ref - measured;  // 微分用加权误差

    // P
    float p_term = pid->kp * p_err;

    // I (条件积分)
    pid->integral += pid->ki * err * dt;
    if (pid->integral > pid->output_max * 0.3f)
        pid->integral = pid->output_max * 0.3f;
    if (pid->integral < -pid->output_max * 0.3f)
        pid->integral = -pid->output_max * 0.3f;

    // D (测量值微分)
    float d_measured = (measured - pid->prev_measured) / dt;
    pid->prev_measured = measured;
    float d_term = -pid->kd * d_err;  // 微分只作用在加权设定值 - 测量值

    float output = p_term + pid->integral + d_term;

    if (output > pid->output_max) output = pid->output_max;
    if (output < -pid->output_max) output = -pid->output_max;

    return output;
}

// 调节建议：
// b=1.0: 最快响应, 有过冲
// b=0.7: 折中
// b=0.5: 慢响应, 无过冲
// b=0.0: I-PD, 无过冲但响应最慢
```

### Observer 增强

```c
// 扰动观测器 (Disturbance Observer — DOB)
// 估测外部负载扰动，前馈补偿
// 原理：J×dω/dt = Te - Tload - B×ω
//       Tload_est = Te - J×dω/dt - B×ω

typedef struct {
    float J;                // 转动惯量 (kg·m²)
    float B;                // 粘滞摩擦系数
    float Te_prev;          // 上次电磁转矩
    float omega_prev;       // 上次速度 (rad/s)
    float Tload_est;        // 负载转矩估计
    float g;                // 观测器增益 (低通截止频率)
} DOB;

void dob_update(DOB *dob, float te, float omega, float dt)
{
    // 预估负载转矩
    float domega_dt = (omega - dob->omega_prev) / dt;
    float tload_raw = te - dob->J * domega_dt - dob->B * omega;

    // 低通滤波（一阶）
    dob->Tload_est += dob->g * dt * (tload_raw - dob->Tload_est);

    dob->Te_prev = te;
    dob->omega_prev = omega;
}

// 前馈补偿：
// Iq_ref = Iq_from_speed_PI + Tload_est / Kt
// 效果：突加负载时，速度跌落更小，恢复更快
```

## 电流环/速度环/位置环多环级联完整配置

```c
// 完整多环控制结构
typedef struct {
    // 电流环 (最高频, 10k~40kHz)
    CurrentPI pi_d;             // Id 轴 PI
    CurrentPI pi_q;             // Iq 轴 PI
    float vd, vq;               // DQ 轴电压指令
    float v_alpha, v_beta;      // αβ 轴电压
    float ta, tb, tc;           // 三相占空比

    // 坐标变换 + SVPWM
    float theta;                // 转子电角度

    // 速度环 (1k~10kHz)
    SpeedPI_FF speed_pi;
    float speed_ref;
    float speed_measured;

    // 位置环 (200~1kHz)
    PositionController pos_ctrl;
    float pos_ref;
    float pos_measured;

    // 电机参数
    float rs, ls, ld, lq, flux; // 电阻/电感/磁链
    float pole_pairs;           // 极对数
} MotorControl;

// 电流环 ISR (每 PWM 周期调用)
void current_loop_isr(MotorControl *mc)
{
    // 1. 读取 ADC 电流采样
    float ia = adc_get_phase_a();
    float ib = adc_get_phase_b();

    // 2. Clarke → Park
    float i_alpha, i_beta;
    clarke_transform(ia, ib, &i_alpha, &i_beta);
    float id, iq;
    park_transform(i_alpha, i_beta, mc->theta, &id, &iq);

    // 3. 电流 PI
    mc->vd = current_pi_update(&mc->pi_d, 0.0f, id);     // Id_ref=0
    mc->vq = current_pi_update(&mc->pi_q, mc->speed_ref, iq);

    // 3b. DQ 解耦 (高速时)
    float we = mc->speed_measured * mc->pole_pairs;
    mc->vd = vd_decouple(mc->vd, we, mc->lq, iq);
    mc->vq = vq_decouple(mc->vq, we, mc->ld, id, mc->flux);

    // 4. 逆 Park → SVPWM
    inv_park_transform(mc->vd, mc->vq, mc->theta,
                       &mc->v_alpha, &mc->v_beta);
    svpwm_calc(mc->v_alpha, mc->v_beta, VDC,
               &mc->ta, &mc->tb, &mc->tc);

    // 5. 更新占空比 (更新 TIM CCR)
    set_pwm_duty(mc->ta, mc->tb, mc->tc);
}

// 速度环 (每 N 次电流环调用一次)
void speed_loop_isr(MotorControl *mc)
{
    // 1. 测速
    mc->speed_measured = mt_speed_estimate(&se, encoder_cnt, timer_tick,
                                           ENCODER_PPR, dt);

    // 2. 速度 PI + 前馈
    mc->speed_ref = speed_pi_ff_update(&mc->speed_pi,
                                       mc->pos_ref,  // 来自位置环
                                       mc->speed_measured,
                                       0);  // 前馈加速度
    // speed_ref = Iq_ref
}

// 位置环 (每 M 次速度环调用一次)
void position_loop_isr(MotorControl *mc)
{
    // 1. 读取编码器位置
    mc->pos_measured = encoder_get_position();

    // 2. 位置 PDFF
    mc->pos_ref = position_pdff_update(&mc->pos_ctrl,
                                        mc->pos_target,
                                        mc->pos_measured,
                                        0);  // vel_ref
    // pos_ref = speed_ref
}
```

## 电流采样拓扑与零点校准

### 采样拓扑选型

| 拓扑 | 采样电阻数 | 精度 | 成本 | 最小脉宽限制 | 适用场景 |
|------|-----------|------|------|-------------|---------|
| **三电阻 (3-shunt)** | 3 | 最高 | 高 | 无 | 伺服、高精度 FOC |
| **单电阻 (1-shunt)** | 1 | 中等 | 低 | 有 (需规避) | 风机、水泵、小家电 |
| **隔离电流传感器 (ICS)** | 0 | 高 | 最高 | 无 | 大功率、高压 |

```c
// 三电阻采样：每相一个采样电阻，需要 3 路 ADC + 运放
// 采样点在 PWM 中心对齐时，三相电流均可直接读取

// 单电阻采样：母线单电阻，通过 PWM 开关状态重构三相电流
// 需要在每个 PWM 周期内两次采样不同相
// 限制：在扇区边界附近存在"非观测区"，需特殊处理

// ICS (如 ACS712/LA25-NP)：直接测量相电流，无共模问题
// 成本最高，精度最好，常用于工业伺服
```

### 电流零点校准

```c
// FOC 对电流采样零偏极其敏感 — 必须在每次上电时校准
// 零偏误差直接导致 Id/Iq 中有直流偏置 → 转矩脉动

#define CALIBRATION_SAMPLES  1024

typedef struct {
    float iu_offset;
    float iv_offset;
    float iw_offset;    // 三电阻需要第三相
} CurrentOffset;

void current_offset_calibrate(CurrentOffset *off)
{
    // 电机静止状态下采集（PWM 已使能但无输出）
    float iu_sum = 0, iv_sum = 0;

    for (int i = 0; i < CALIBRATION_SAMPLES; i++) {
        iu_sum += adc_read_phase_u();
        iv_sum += adc_read_phase_v();
    }

    off->iu_offset = iu_sum / CALIBRATION_SAMPLES;
    off->iv_offset = iv_sum / CALIBRATION_SAMPLES;

    // 三相平衡时，第三相偏置 = -(Iu + Iv)
    off->iw_offset = -(off->iu_offset + off->iv_offset);
}

// 校准后的电流读数：
float get_phase_u(CurrentOffset *off)
{
    return adc_read_phase_u() - off->iu_offset;
}

// 注意：运放温漂会导致零偏随时间变化
// 高精度应用需运行时定期重新校准或加入跟踪算法
```

## 电压圆限制 (Circle Limitation)

```c
// ST MCSDK §3.10 — PI 输出的 Vd/Vq 矢量幅值必须限制
// SVPWM 最大可合成电压 = VDC / √3 (六边形内切圆)
// 超出此范围 → 过调制 → 电流波形畸变

typedef struct {
    float vdc;              // 母线电压
    float max_modulation;   // 最大调制比 = VDC / √3
    float vd_ref;           // 限制后的 Vd
    float vq_ref;           // 限制后的 Vq
} CircleLimiter;

void circle_limitation(CircleLimiter *cl, float vd, float vq)
{
    float v_mag = sqrtf(vd * vd + vq * vq);
    float v_max = cl->vdc * 0.577350269f;  // VDC / √3

    if (v_mag > v_max) {
        // 幅值超限，等比例缩小 (保持角度不变)
        float scale = v_max / v_mag;
        cl->vd_ref = vd * scale;
        cl->vq_ref = vq * scale;
    } else {
        cl->vd_ref = vd;
        cl->vq_ref = vq;
    }

    // 注意：必须限制在逆 Park 变换之前
    // inv_park(cl->vd_ref, cl->vq_ref, θ, &va, &vb)
}

// 电流环 ISR 中的完整流程：
// 1. Clarke + Park
// 2. PI 控制 → Vd, Vq
// 3. DQ 解耦
// 4. 圆限制 (★ 新增)
// 5. 逆 Park
// 6. SVPWM
```

## MTPA 最大转矩电流比

```c
// 仅对 IPMSM (Ld ≠ Lq) 有意义
// SPMSM (Ld = Lq) 保持 Id=0 即 MTPA

// MTPA 原理：利用磁阻转矩 (Ld-Lq) 分量
// Te = 1.5 × pn × [φf × Iq + (Ld-Lq) × Id × Iq]
//          ─────────   ───────────────
//          永磁转矩    磁阻转矩 (IPMSM 额外项)

// MTPA 曲线上的 Id/Iq 关系：
// Id_mtpa = (φf - √(φf² + 4×(Ld-Lq)²×Iq²)) / (2×(Ld-Lq))

float id_mtpa_calc(float iq_ref, float flux, float ld, float lq)
{
    float delta_l = ld - lq;            // 凸极率
    if (fabsf(delta_l) < 0.0001f)
        return 0.0f;                    // SPMSM: Id=0

    float iq_sq = iq_ref * iq_ref;
    float sqrt_term = flux * flux + 4.0f * delta_l * delta_l * iq_sq;

    return (flux - sqrtf(sqrt_term)) / (2.0f * delta_l);
}

// 使用：d 轴 PI 的目标值不再是 0
// Id_ref = id_mtpa_calc(iq_ref, flux, ld, lq);
// mc->vd = current_pi_update(&mc->pi_d, Id_ref, id);

// 注意：
// MTPA 仅在恒转矩区有效，进入弱磁区后需与弱磁协调
// IPMSM (Ld < Lq) 使用正 Id → MTPA 曲线在负 Id 区
// SPMSM (Ld ≈ Lq) MTPA 退化为 Id=0，无需计算
```

## 弱磁控制 (Flux Weakening)

```c
// 当电机转速超过额定转速时，反电动势接近母线电压
// 通过注入负 Id 电流"削弱"永磁磁场，降低反电动势
// 代价：Id 增大 → 铜耗增加 → 效率下降

// 弱磁控制目标：维持 Vd² + Vq² ≤ (VDC/√3)²

typedef struct {
    float vdc;                  // 母线电压
    float v_max_sq;             // 最大电压平方
    float id_fw_ref;            // 弱磁 Id 目标值
    float id_fw_max;            // 最大弱磁电流 (负值)
    float ki_fw;                // 弱磁 PI 积分增益
} FluxWeakening;

void flux_weakening_update(FluxWeakening *fw, float vd, float vq, float dt)
{
    // 判断是否进入弱磁区
    float v_sq = vd * vd + vq * vq;

    if (v_sq > fw->v_max_sq) {
        // 电压超限 → 需要弱磁
        // PI 调节器：根据电压超调量生成负 Id
        float err = sqrtf(v_sq) - sqrtf(fw->v_max_sq);
        fw->id_fw_ref -= fw->ki_fw * err * dt;

        // 限幅
        if (fw->id_fw_ref < fw->id_fw_max)
            fw->id_fw_ref = fw->id_fw_max;
        if (fw->id_fw_ref > 0)
            fw->id_fw_ref = 0;  // 弱磁必须是负 Id
    } else {
        // 电压未超限 → 缓慢退出弱磁
        fw->id_fw_ref *= 0.999f;
        if (fw->id_fw_ref > 0)
            fw->id_fw_ref = 0;
    }
}

// 完整 Id 目标值：
// Id_ref = Id_mtpa + Id_fw
//          ───────   ────
//          MTPA 项   弱磁项 (负值)

// 注意：
// 弱磁区转矩输出能力下降
// 高速弱磁时需降低最大 Iq 限幅
// 退磁保护：不允许 Id 超过永磁体退磁电流
```

## ADRC 自抗扰控制 (备选方案)

```c
// TI InstaSPIN-MOTION 使用 ADRC 替代传统 PI
// 核心思想：将系统内扰(参数变化)和外扰(负载)统一为"总扰动"
// 用扩张状态观测器(ESO)实时估计并补偿

// 相比 DOB 的优势：
// - 单参数整定 (带宽)，不依赖电机参数
// - 对惯量变化、摩擦变化更鲁棒
// - 全速度范围一组参数可用

// ADRC 速度环简化实现：
typedef struct {
    float bw;               // 观测器带宽 (单参数)
    float z1, z2;           // ESO 状态: z1=速度估计, z2=总扰动估计
    float u_prev;           // 上次控制量
    float h;                // 采样周期
} ADRC_Speed;

float adrc_speed_update(ADRC_Speed *adrc, float omega_ref,
                        float omega_meas, float u_max)
{
    // ESO (扩张状态观测器)
    float e = adrc->z1 - omega_meas;
    adrc->z1 += adrc->h * (adrc->z2 - 2 * adrc->bw * e + adrc->u_prev);
    adrc->z2 -= adrc->h * adrc->bw * adrc->bw * e;

    // 状态误差反馈 + 扰动补偿
    float u0 = adrc->bw * (omega_ref - adrc->z1);

    // 控制量 = u0 - 扰动估计 / b0
    // b0 = 控制增益 (≈ Kt/J)
    float u = u0 - adrc->z2 / B0;

    // 限幅
    if (u > u_max) u = u_max;
    if (u < -u_max) u = -u_max;

    adrc->u_prev = u;
    return u;  // 输出作为 Iq_ref
}

// ADRC vs DOB 选型：
// ADRC: 单参数整定，对模型不敏感，但计算量稍大
// DOB:  需要 J 参数，计算量小，适合已知惯量的系统
```

### 电阻测量

```c
// 方法：注入直流电压，测量稳态电流
float measure_resistance(void)
{
    // 给 D 轴注入小电压 (Vd), Q 轴置 0
    // 保持转子不转
    float vd_test = 0.1f * VDC;  // 10% 占空比
    float vq_test = 0.0f;

    // 等待电流稳定 (~ 电气时间常数 × 5)
    // Id_stable = Vd_test / Rs

    float id_stable = get_stable_current();
    float rs = vd_test / id_stable;

    return rs;  // 相电阻
}
```

### 电感测量

```c
// 方法：注入高频电压信号，测量电流响应斜率
float measure_inductance_ls(void)
{
    // 给 D 轴注入阶跃电压
    // di/dt = Vd / Ld (在电流上升段)

    float id_before = get_current_id();
    apply_voltage_step(VD_TEST);
    delay(100);  // µs
    float id_after = get_current_id();

    float didt = (id_after - id_before) / dt_test;
    float ld = VD_TEST / didt;

    return ld;  // D 轴电感
}
```

### 反电动势常数 (Ke)

```c
// 方法：外力拖动电机到已知转速，测量开路电压
float measure_ke(float speed_rpm)
{
    // 让电机空转（无电流驱动）
    // 测量线电压 Vll_peak

    float vll = measure_line_voltage();
    float ke = vll / speed_rpm;  // V/RPM

    // 或用 SI 单位：
    // flux_linkage = Vll_peak / (ωe × √3)
    // ωe = speed_rpm × pole_pairs × π / 30

    return ke;
}
```

## 陷波滤波器（机械共振抑制）

```c
// 机械共振：由传动系统弹性（皮带/减速器）引起
// 表现为特定频率的速度/电流振荡
// 频率范围：100Hz~2kHz

// 二阶 IIR 陷波滤波器：
// H(z) = (1 - 2×cos(ω0)×z^-1 + z^-2) / (1 - 2×r×cos(ω0)×z^-1 + r²×z^-2)

typedef struct {
    float b0, b1, b2;      // 分子系数
    float a1, a2;          // 分母系数
    float x1, x2;          // 输入历史
    float y1, y2;          // 输出历史
} NotchFilter;

void notch_init(NotchFilter *nf, float f0, float bw, float fs)
{
    // f0: 陷波中心频率 (Hz)
    // bw: 带宽 (Hz), 越小陷波越窄
    // fs: 采样率 (Hz)

    float w0 = 2.0f * 3.14159f * f0 / fs;
    float r = 1.0f - 3.14159f * bw / fs;  // 极点半径 (0<r<1)

    float cos_w0 = cosf(w0);
    float r2 = r * r;

    nf->b0 = 1.0f;
    nf->b1 = -2.0f * cos_w0;
    nf->b2 = 1.0f;
    nf->a1 = -2.0f * r * cos_w0;
    nf->a2 = r2;

    nf->x1 = nf->x2 = 0;
    nf->y1 = nf->y2 = 0;
}

float notch_process(NotchFilter *nf, float input)
{
    // 直接 II 型
    float output = nf->b0 * input + nf->b1 * nf->x1 + nf->b2 * nf->x2
                 - nf->a1 * nf->y1 - nf->a2 * nf->y2;

    nf->x2 = nf->x1;
    nf->x1 = input;
    nf->y2 = nf->y1;
    nf->y1 = output;

    return output;
}

// 使用：
// 1. 运行 FFT 扫频找出共振频率（扫频 10~1000Hz 电机响应）
// 2. 配置陷波滤波器
// 3. 将陷波器串入速度环输出 (Iq_ref)
```

## 启动策略与状态机

```c
typedef enum {
    MOTOR_IDLE,
    MOTOR_ALIGN,        // 转子对齐 (给 D 轴电流固定转子)
    MOTOR_OPENLOOP,     // 开环强拖 (无感启动)
    MOTOR_CLOSELOOP,    // 闭环运行
    MOTOR_FAULT
} MotorState;

// 无感 BLDC 启动流程：
// IDLE → ALIGN (500ms) → OPENLOOP (加速到 ~5% 额定转速)
//      → CLOSELOOP (切换到观测器闭环)

void motor_start(MotorState *state)
{
    switch (*state) {
        case MOTOR_IDLE:
            // 给 D 轴正电流对齐转子
            set_id_ref(ID_ALIGN);
            *state = MOTOR_ALIGN;
            break;

        case MOTOR_ALIGN:
            // 等待对齐完成
            if (align_timer > ALIGN_TIME_MS) {
                // 切换到开环强拖
                *state = MOTOR_OPENLOOP;
            }
            break;

        case MOTOR_OPENLOOP:
            // 开环 V/F 控制，缓慢升频
            openloop_speed += ACCEL_RATE * dt;
            if (openloop_speed > SWITCH_SPEED) {
                // 切换至闭环
                *state = MOTOR_CLOSELOOP;
            }
            break;

        case MOTOR_CLOSELOOP:
            // FOC 闭环正常运行
            break;
    }
}
```

## 常见陷阱

| 编号 | 现象 | 根因 | 解决 |
|------|------|------|------|
| 1 | 电流环振荡 | PI 参数过大或电流采样噪声 | 减小 Kp，加低通滤波，检查采样时序 |
| 2 | 电机高速啸叫 | PWM 频率在可听范围内 | 提到 20kHz+ |
| 3 | 满速上不去 | SVPWM 过调制极限 | 检查 VDC 和 SVPWM 调制比 (最大 0.577) |
| 4 | 电流采样全 0 | ADC 采样点不在 PWM 中心 | 确认 TIM TRGO 触发 ADC 的时序 |
| 5 | DQ 解耦失效 | 电角度误差或 PI 饱和 | 检查 θ 角精度和解耦系数符号 |
| 6 | 机械共振啸叫 | 传动系统弹性模态 | 加陷波滤波器 |
| 7 | 速度环低频抖动 | 积分饱和引起 | 加条件积分 (Anti-windup Clamping) |
| 8 | 位置过冲 | Kp 太大或前馈不足 | 减小 Kp 或 PDFF 改用 PPV 结构 |
| 9 | 突加负载速度跌落大 | 无扰动补偿 | 加 DOB 扰动观测器 |
| 10 | 无感启动失败 | 开环强拖升频太快 | 减小 ACCEL_RATE 或增加 ALIGN 时间 |
| 11 | 电流采样偏置导致转矩脉动 | 上电未做零点校准 | 每次启动执行 current_offset_calibrate |
| 12 | 高速转矩不足或失步 | 未开启弱磁控制 | 加入 Flux Weakening 控制 |
| 13 | 死区时间导致电流波形畸变 | MOSFET 死区补偿不足 | 添加死区补偿算法或减小死区 |

## 边界定义

- **不覆盖具体三相逆变器硬件设计**（MOSFET 选型/栅极驱动/自举电容/死区补偿）— 属电力电子领域
## 平台差异

| 平台 | PWM 生成 | 编码器接口 | ADC 采样 | FOC 方案 |
|------|---------|-----------|---------|---------|
| STM32(G4) | HRTIM/高级TIM | TIM 编码器模式 | 3-shunt 注入组+ADC | ST MCSDK |
| STM32(F4) | 高级TIM | TIM 编码器模式 | ADC 规则组+DMA | ST MCSDK |
| STM32(F1) | 高级TIM | TIM 编码器模式 | ADC+TIM 触发 | 自定义 |
| ESP32 | MCPWM | PCNT 外设 | ADC+DMA | ESP-MDF(简单电机)|
| SimpleFOC | 任意 TIM | 任意编码器 | 任意 ADC | SimpleFOC 库 |

注：ESP32 的 MCPWM 和 PCNT 是专用电机控制外设，配置方式与 STM32 TIM 完全不同。

- **不覆盖 ST MCSDK / TI InstaSPIN / SimpleFOC 库的使用** — 这些是成熟 SDK，本 skill 提供原理性指导
- **不覆盖电机有限元分析 (FEA)** — 需 Ansys/JMAG 等专用工具
- **不覆盖安全功能安全 (ISO 13849 / IEC 61800)** — 伺服驱动器功能安全标准
- 与 `timer-module` 互补：PWM 生成/编码器计数/死区由 timer-module 覆盖
- 与 `adc-module` 互补：电流采样需要高速 ADC + DMA 触发
