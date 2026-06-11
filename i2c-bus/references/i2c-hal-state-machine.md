# HAL I2C 状态机与 Bug 汇总

## HAL I2C 状态枚举

```c
typedef enum {
  HAL_I2C_STATE_RESET     = 0x00,  // 未初始化
  HAL_I2C_STATE_READY     = 0x20,  // 就绪，可发起新传输
  HAL_I2C_STATE_BUSY      = 0x24,  // 忙（未指定方向）
  HAL_I2C_STATE_BUSY_TX   = 0x28,  // 忙-发送中
  HAL_I2C_STATE_BUSY_RX   = 0x34,  // 忙-接收中
  HAL_I2C_STATE_LISTEN    = 0x38,  // 从机监听中
  HAL_I2C_STATE_BUSY_TX_LISTEN = 0x3A,
  HAL_I2C_STATE_BUSY_RX_LISTEN = 0x3E,
  HAL_I2C_STATE_ABORT     = 0x60,  // 中止中
  HAL_I2C_STATE_ERROR     = 0xE0   // 错误状态
} HAL_I2C_StateTypeDef;
```

## 状态机卡死模式速查

- **0x24 (BUSY)**：最常见。前一次传输的回调未调用/被跳过
- **0x28 (BUSY_TX)**：TX ISR 被触发但状态机不同步
- **0x34 (BUSY_RX)**：从机 RX DMA 一直开启但主机不发送
- **0x3E (BUSY_RX_LISTEN)**：F103 从机模式下运行 30+ 分钟后出现
- **0x60 (ABORT)**：传输被中止，需要主动 `HAL_I2C_Init()` 恢复

## HAL 版本已知问题

| HAL 版本 | MCU 系列 | Bug | 修复方式 |
|---------|---------|-----|---------|
| 1.x | F1 | Slave 模式 LISTEN 后 BERR/OVR 不恢复 | 手动 `__HAL_I2C_CLEAR_FLAG` + 重新 `EnableListen_IT` |
| 1.12+ | L4 | Mem_Write 后 STOPF 清除但 AF 未清除 | 手动清除 AF 或修改 HAL 源码 |
| 1.14+ | G0/G4 | 中断标志在状态机不同步时永远不清 | 中断 handler 中检测所有标志并清除 |
| H7 v1.x | H7 | Lock/Unlock 的 ISR res不起 | 降低中断优先级或修改 HAL 源码加双检查 |
