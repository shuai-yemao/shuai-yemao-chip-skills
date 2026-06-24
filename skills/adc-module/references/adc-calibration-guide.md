# ADC 校准方法详解

## 为什么需要校准

SAR ADC 的偏移误差（Offset Error）和增益误差（Gain Error）是模拟电路固有的。即使同一芯片不同批次、不同温度，误差也不同。校准可将其从 ±2~5 LSB 降至 ±0.5 LSB 内。

## 校准类型与 API 对照

| 校准类型 | 功能 | F1 | F4 | G0/G4/H7 |
|---------|------|----|----|---------|
| 偏移校准 | 消除输入偏移 | `ADC_ResetCalibration` + `ADC_StartCalibration` 标准库 | `HAL_ADCEx_Calibration_Start(&hadc1)` | `HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET)` |
| 线性度校准 | 消除积分非线性 (INL) | 不支持 | 不支持 | `ADC_CALIB_OFFSET_LINEARITY` |

## F4 系列校准

```c
/* 单端模式偏移校准（必须每次上电后执行） */
HAL_ADCEx_Calibration_Start(&hadc1);
```

- 校准值自动注入到 ADC 内部，用户无需保存
- 校准过程中 ADC 应处于空闲状态（未启动）
- 校准耗时大约几十微秒

## H7/G4 系列校准

```c
/* H7 支持两种校准模式 */
// 基础偏移校准（同 F4）
HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET);

// 偏移+线性度校准（推荐 — 补偿 INL 误差）
HAL_ADCEx_Calibration_Start(&hadc1, ADC_CALIB_OFFSET_LINEARITY);
```

**注意事项**：
- 线性度校准增加 ~40μs 校准时间
- 单端和差分模式需要分别校准
- H7 上切换分辨率后需重新校准
- H7 VBAT 通道有自己的独立校准

## 校准值保存与恢复

大多数场景下不需要——每次上电执行一次即可。但如果需要在极短时间内恢复上下文：

```c
// F4: 校准时读回偏移值（可以保存到 RAM）
uint32_t saved_offset = ADC1->DR;  // 校准结束后 DR 中存储偏移值

// 恢复时写入偏移寄存器
// 注意：HAL 不支持手动写校准值，需要操作寄存器
```

## 温度影响

校准值随温度漂移：约 **±0.5 LSB / 10°C**。在宽温范围（-40°C~85°C）工作时：
- 定期在空闲时间重新校准
- 或读取内部温度传感器做软件补偿

## 典型校准流程

```
上电 → HAL_ADC_Init → 校准（HAL_ADCEx_Calibration_Start） → 开始采样
                                                       ↓
                              温度变化 > 20°C? → 停止采样 → 重新校准 → 开始采样
```
