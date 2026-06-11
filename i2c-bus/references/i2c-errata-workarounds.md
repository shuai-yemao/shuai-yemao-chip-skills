# STM32 I2C Errata 与解决方案

## F1 系列已知 Errata（与 I2C 相关）

| Errata ID | 描述 | 影响 | 解决方案 |
|-----------|------|------|---------|
| 2.9.2 | 在某些条件下 BTF 标志不置位 | 多字节传输卡死 | 用 TXE/RXNE 替代 BTF 判断 |
| 2.9.3 | START 条件在总线忙时可能产生 | 通信异常 | 必须在操作前检查 BUSY 位 |
| 2.9.5 | NOSTRETCH=0 时从机模式有额外 SCL 脉冲 | 时序违规 | 设 NOSTRETCH=1 并从软件处理时钟延展 |
| 2.9.8 | 88kHz 附近时钟不稳定 | 通信出错 | 避免 88kHz，用 100kHz 或 400kHz |

## 总线死锁完全恢复方案

### 软件复位（SWRST）
```c
/* 使用 I2C_CR1 的 SWRST 位复位 I2C 状态机 */
void i2c_sw_reset(I2C_TypeDef *I2Cx)
{
    I2Cx->CR1 |= I2C_CR1_SWRST;
    __NOP(); __NOP();
    I2Cx->CR1 &= ~I2C_CR1_SWRST;
}
```

### 如果 SWRST 不生效（硬件死锁）
参见 SKILL.md 中的 `i2c_bus_recover()` 9 脉冲法。

## NACK 处理的正确模式

Master 在读最后一个字节时主动发 NAK+STOP——这是 **正常流程**，不是错误。

HAL 的 `HAL_I2C_ErrorCallback` 在 NAK 时也会被调用。判断方法：

```c
void HAL_I2C_ErrorCallback(I2C_HandleTypeDef *hi2c)
{
    uint32_t err = HAL_I2C_GetError(hi2c);
    if (err & HAL_I2C_ERROR_AF) {
        // ─ 如果这是最后字节后的 NAK → 正常，不做特殊处理
        // ─ 如果这是中间字节的 NAK → 从机异常，需要恢复
    }
}
```
