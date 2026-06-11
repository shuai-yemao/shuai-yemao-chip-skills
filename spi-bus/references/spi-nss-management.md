# SPI NSS 管理全面对比

## 硬件 NSS vs 软件 NSS vs GPIO 手动控制

| 特性 | 硬件 NSS 输出 | 硬件 NSS 输入 | 软件 NSS (SSM=1) | GPIO 手动 (推荐) |
|------|-------------|-------------|----------------|----------------|
| 引脚配置 | AF 推挽 | 浮空输入 | AF 推挽（功能被旁路） | GPIO 推挽输出 |
| SSM 位 | 0 | 0 | 1 | 1 |
| SSOE 位 | 1 | 0 | 无关 | 无关 |
| 控制方式 | SPI 硬件在 SPE=1 时持续拉低 | 外部主机控制 | SSI 位控制内部 NSS | GPIO BSRR 直接控制 |
| CS 间脉冲 | 无（除非 NSSP=ENABLE 在新系列上） | 无（外部控制） | 无 | 完全可控 |
| 多从机 | ❌ 硬件 NSS 只驱动一个 CS | ✅ 外部解码器 | 需要额外 GPIO | ✅ 每个 CS 一个 GPIO |
| 推荐度 | ❌ 不推荐 | 仅多主机仲裁场景 | 可以但多余 | ✅ **唯一推荐** |

## 硬件 NSS 在各系列上的具体行为

### STM32F1/F4（SPI V1）
- `SPI_NSS_Hard` + `SSOE=1`：SPE=1 时 NSS 持续低电平
- SPE=0 时 NSS **三态（高阻）**——不是推挽高电平！外部必须加上拉
- 事务之间无法自动释放 → 多从机不可用
- **结论**：ST 在 F1/F4 上推荐 GPIO 手动控制

### STM32H7/G4（SPI V2）
- 引入了 `NSSP` (NSS Pulse Mode) 位：每个帧后自动产生 NSS 脉冲
- `MasterKeepIOState`：SPE=0 后 NSS 保持最后状态，不自三态
- 硬件 NSS 在 H7 上实际可用，但配置复杂（需同时设 NSSP、MasterSSIdleness、MasterInterDataIdleness）
- **结论**：技术可用但推荐 GPIO 手动控制以保持代码兼容性

## CS 间时序参数

| 参数 | 描述 | 最小值 |
|------|------|--------|
| tCSS (CS setup) | CS 拉低到第一个 SCK 边沿 | 至少半个 SCK 周期 |
| tCSH (CS hold) | 最后一个 SCK 边沿到 CS 释放 | 至少半个 SCK 周期 |
| tCSD (CS deselect) | CS 释放到下一次拉低 | 至少一个 SCK 周期 |

```c
/* 保守延时（低速 < 10MHz 时足以） */
#define CS_SETUP_DELAY_US  (1)
#define CS_HOLD_DELAY_US   (1)

CS_LOW();
delay_us(CS_SETUP_DELAY_US);
SPI_TransmitReceive(...);
delay_us(CS_HOLD_DELAY_US);
CS_HIGH();
```
