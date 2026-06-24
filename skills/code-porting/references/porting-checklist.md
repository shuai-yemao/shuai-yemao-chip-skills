# 移植预检清单模板

> 每次移植任务开始前，逐项填写并确认。标记 [—] 表示不适用可直接跳过。

## 项目信息

| 项目 | 填写 |
|------|------|
| 源芯片 | |
| 目标芯片 | |
| 源 HAL/库版本 | |
| 目标 HAL/库版本 | |
| 源 IDE/工具链 | |
| 目标 IDE/工具链 | |
| 源 RTOS (如有) | |
| 目标 RTOS (如有) | |
| 移植类型 | □ 同系列微调 □ 同厂商重映射 □ 跨厂商重写 □ 跨架构重构 |

## Pre-Layer 0：工程配置

- [ ] 目标芯片 DFP/Cube 包已安装
- [ ] 目标芯片头文件路径已加入编译器 Include 路径
- [ ] 编译器宏定义已更新（`STM32F1xx` → `STM32F4xx` 等）
- [ ] 烧录算法已切换为目标芯片型号
- [ ] 调试器配置已更新（SWD/JTAG 频率适配）

## Layer 1：启动文件与链接脚本

- [ ] startup_xxx.s 已替换为目标系列
- [ ] Stack_Size / Heap_Size 适配目标 SRAM 容量
- [ ] 中断向量表项数与目标 NVIC 通道数匹配
- [ ] 链接脚本内存区域基地址已核对（Flash / SRAM / Peripheral）
- [ ] FPU 使能（硬件浮点目标：`SCB_CPACR` 配置）
- [ ] Cache 使能（CM7：`SCB_EnableICache()` + `SCB_EnableDCache()`）
- [ ] MPU 配置（如需要，CM3/CM4/CM7 可用）
- [ ] 链接脚本 SECTION 顺序：`.isr_vector` → `.text` → `.rodata` → `.data` → `.bss`
- [ ] 堆栈总占用不超过 SRAM 的 80%

**编译验证**：□ 0 Error, 0 Warning

## Layer 2：时钟树

- [ ] HSI/HSE 主时钟源频率匹配目标
- [ ] PLL 分频系数/倍频系数重算（参考 SKILL.md 对照表）
- [ ] AHB/APB1/APB2 预分频器不超过目标上限
- [ ] Flash 等待周期（WS）适配目标频率
- [ ] VCO 频率在目标范围内
- [ ] USB 48MHz 时钟源检查（F4: PLL48CK, H7: PLL3Q, F1: 无）
- [ ] RCC 时钟安全系统（CSS）配置

**编译验证**：□ 0 Error, 0 Warning
**运行时验证**：`HAL_GetTick()` 正常计数

## Layer 3：GPIO

- [ ] 每处 GPIO 端口号核对（PA/PB/PC… 在目标上是否存在）
- [ ] 每处 GPIO 引脚号核对（Pin0~15，含大封装才有的引脚）
- [ ] 复用功能方式核对（F1: AFIO+Remap 宏，F4+: AFRL/AFRH 寄存器）
- [ ] GPIO 时钟使能核对（F1: RCC_APB2Periph, F4+: RCC_AHB1Periph）
- [ ] 输出速度范围核对（F1: 2/10/50MHz, F4+: Low/Med/High/VeryHigh）
- [ ] 上下拉 PULLUP/PULLDOWN 核对（F1 需手动写 BSRR）
- [ ] EXTI 线映射核对
- [ ] 引脚功能冲突检查（目标芯片不同封装引脚减少风险）

**编译验证**：□ 0 Error, 0 Warning
**运行时验证**：LED 闪烁 / GPIO 回环

## Layer 4：外设驱动（逐外设）

### USART
- [ ] 波特率重算（核对 OVER8 位配置）
- [ ] USART 时钟来自 APB1/APB2 确认
- [ ] TX/RX GPIO AF 号核对
- [ ] DMA 请求号核对（如使用）
- [ ] 中断号核对

### SPI
- [ ] CPOL/CPHA 时序模式确认
- [ ] NSS 管理方式确认（硬件/软件/GPIO）
- [ ] SPI 时钟分频重算（核对 APB 总线频率变化）
- [ ] TX/RX GPIO AF 号核对
- [ ] DMA 请求号核对（如使用）

### I2C
- [ ] I2C 时序配置（F1: CCR + TRISE, F4+: TIMINGR）
- [ ] 时钟延展使能/禁止确认
- [ ] 目标芯片 I2C 版本（F1: v1 BUSY bug, F4+: v2）
- [ ] SCL/SDA GPIO 配置（Open-Drain + 外部上拉）
- [ ] 中断/DMA 或轮询模式选择

### TIM
- [ ] PSC/ARR 重算（核对 APB 时钟 ×1/×2 规则）
- [ ] 时钟源核对（TIMx 挂载在 APB1 还是 APB2）
- [ ] 捕获/比较通道重映射核对
- [ ] 高级定时器刹车（BRK）配置核对

### ADC
- [ ] fADC 时钟频率核对（不超过目标上限）
- [ ] 采样周期重算（目标 ADC 时序参数不同）
- [ ] 通道映射核对（ADC_INx 各系列不同）
- [ ] 校准流程确认（各系列差异：G4 有差分校准）

### DMA
- [ ] DMA 控制器架构核对（F1: 7ch, F4: stream, H7: MDMA+BDMA）
- [ ] 请求映射完全重做（不同系列差异大）
- [ ] 数据对齐（F4+ FIFO 阈值设置）
- [ ] 中断号与优先级核对

**编译验证**：□ 0 Error, 0 Warning
**运行时验证**：每个外设 loopback 测试

## Layer 5：中断

- [ ] 每处 IRQn 编号核对目标芯片
- [ ] NVIC 优先级分组配置（F1: 固定 4 位抢占）
- [ ] EXTI ISR 范围核对（EXTI0~4 固定，EXTI5~9 共享 EXTI9_5_IRQn）
- [ ] SysTick 优先级配置（FreeRTOS 要求最低）
- [ ] PendSV/SVCall 优先级确认
- [ ] 中断嵌套属性（ARMCC `__irq`, GCC `__attribute__((interrupt))`）

**编译验证**：□ 0 Error, 0 Warning
**运行时验证**：每个中断触发并进入对应 ISR

## Layer 6：RTOS（涉及时）

- [ ] configCPU_CLOCK_HZ 更新为目标频率
- [ ] configTOTAL_HEAP_SIZE 不超过目标 SRAM
- [ ] FreeRTOSConfig.h 中 CPU 相关的宏更新
- [ ] 临界区保护核对（__disable_irq / __enable_irq）
- [ ] 栈大小重算（目标可能有不同 FPU 寄存器压栈）
- [ ] FPU 启用（CM4F/CM7 需要 configENABLE_FPU=1）
- [ ] 任务优先级分配重新评估

**编译验证**：□ 0 Error, 0 Warning
**运行时验证**：task 调度正常，无 HardFault

## Layer 7：业务逻辑与回归测试

- [ ] 外设宏定义全部通过宏间接引用（不硬编码外设名）
- [ ] HAL_Delay 参数更新（新的 SysTick 频率）
- [ ] 时序相关硬编码更新（如软件延时循环、超时值）
- [ ] 存储器地址硬编码更新（如外部 SRAM/Flash 地址）
- [ ] 浮点运算验证（CM3 无 FPU vs CM4F/CM7 有 FPU）
- [ ] 功耗模式核对（如使用 STOP/STANDBY）

**功能测试**：
- [ ] 功能等价性：移植后输出与移植前一致
- [ ] 性能基线：CPU 占用率、外设吞吐量不劣化
- [ ] 边界条件：极端输入是否产生相同行为
- [ ] 回归：关联模块功能测试

## 文档化

- [ ] 移植过程记录（所有修改点文档化）
- [ ] 已知差异清单（不可移植的特性、行为差异）
- [ ] 编译选项记录（新旧对比）
- [ ] 烧录/调试配置记录
