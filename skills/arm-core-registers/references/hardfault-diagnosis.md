# HardFault 诊断速查

## 故障分析四步流程

```
触发 HardFault
  → Step 1: 读取 SCB->HFSR (0xE000ED2C)
     ├─ bit1 (VECTTBL): 取向量表地址异常 → 查 VTOR 配置
     └─ bit30 (FORCED): 上层异常 escalation
           → Step 2: 读取 SCB->CFSR (0xE000ED28)
              ├─ [24:31] USFAR: 用法 fault
              │    bit16 (UNDEFINSTR): 未定义指令
              │    bit17 (INVSTATE): 切到 ARM 状态（Cortex-M 不支持）
              │    bit18 (INVPC): EXC_RETURN 无效
              │    bit19 (NOCPG): 无协处理器
              │    bit8 (DIVBYZERO): 除零（需置位 CCR.DIV_0_TRP）
              ├─ [16:23] BFSR: 总线 fault
              │    bit12 (BFARV): BFAR 有效 → 读 SCB->BFAR
              │    bit1 (LSPERR): 浮点 lazy 保存出错
              │    bit0 (IBUSERR): 指令预取总线错误
              ├─ [8:15] MMFSR: 存储管理 fault
              │    bit7 (MMARV): MMAR 有效 → 读 SCB->MMAR
              │    bit4 (MSTKERR): 异常入栈时 MPU 违例
              │    bit0 (IACCVIOL): 指令区 MPU 违例
              └─ [0:7] (保留)
  → Step 3: 读取 SCB->BFAR/MMAR → 获取违法地址
  → Step 4: 退出异常 → 恢复现场
```

## J-Link Commander 读取

```
mem32 0xE000ED28 1    // CFSR
mem32 0xE000ED2C 1    // HFSR
mem32 0xE000ED38 1    // BFAR/MMAR（共享地址）
mem32 0xE000ED34 1    // MMAR（仅 M3 使用）
```

## CFSR 位域解码速查

| 位域 | 偏移 | 含义 | 常见原因 |
|------|------|------|---------|
| IACCVIOL | 0 | 指令访问违例 | 函数指针跳转到非法地址 |
| DACCVIOL | 1 | 数据访问违例 | 空指针解引用 |
| MSTKERR | 4 | 异常入栈 MPU 违例 | 栈溢出/SP 越界 |
| MUNSTKERR | 3 | 异常出栈 MPU 违例 | 返回时栈空间损坏 |
| IBUSERR | 0 | 指令预取总线错误 | 函数指针指向未初始化的外存 |
| PRECISERR | 1 | 精确数据总线错误 | 访问未使能时钟的外设寄存器 |
| IMPRECISERR | 2 | 非精确数据总线错误 | 写缓冲延迟报错（Cortex-M7 常见） |
| BFARV | 3 | BFAR 有效标志 | 读 BFAR 获取违法地址 |
| UNDEFINSTR | 0 | 未定义指令 | Flash 内容损坏/指令取指错误 |
| INVSTATE | 1 | 无效状态 | 用 LSB=0 的地址跳转（应 LSB=1 表示 Thumb） |
| INVPC | 2 | 无效 PC 加载 | EXC_RETURN 值异常 |
| NOCPG | 3 | 无协处理器 | 使用了未实现的协处理器指令 |
| UNALIGNED | 4 | 未对齐访问 | 未使能 CCR.UNALIGN_TRP 时不会触发 |
| DIVBYZERO | 5 | 除零错误 | 需先置位 CCR.DIV_0_TRP |

## HFSR (0xE000ED2C)

| 位 | 名称 | 说明 |
|----|------|------|
| 31 | DEBUGEVT | 调试事件（硬件断点/跟踪点等） |
| 30 | FORCED | 上层异常 escalation（MMFault/BusFault/UsageFault 未处理） |
| 1 | VECTTBL | 取向量表出错 |

## 栈回溯寄存器

HardFault 入栈时自动压入的 8 个寄存器（从 SP→高地址）：

| 偏移 | 寄存器 | 说明 |
|------|--------|------|
| SP+0x00 | R0 | 参数/返回值 |
| SP+0x04 | R1 | 参数 |
| SP+0x08 | R2 | 参数 |
| SP+0x0C | R3 | 参数 |
| SP+0x10 | R12 | 临时 |
| SP+0x14 | LR | 返回地址（异常前） |
| SP+0x18 | PC | 故障指令地址 ← 最关键的线索 |
| SP+0x1C | xPSR | 程序状态寄存器 |

J-Link Commander 读取故障 PC：

```
// HardFault 入栈后，MSP 指向这 8 个寄存器
// PC 在 SP+0x18 位置
mem32 <MSP+0x18> 1    // 读故障 PC
// 然后用 disasm 反汇编该地址附近指令
disasm <PC_value> 10
```

## 常见 HardFault 根因速查

| 现象 | CFSR 典型值 | 根因 | 修复 |
|------|------------|------|------|
| 跑飞后 HardFault | 0x010000 (INVSTATE) | 函数指针低位为 0 | 确保函数指针 LSB=1 |
| 动一下就 HardFault | 0x000100 (IBUSERR) | 跳转到未初始化 Flash 或 Boot 配置错误 | 检查 VTOR/Boot0 引脚 |
| 访问外设时 HardFault | 0x000200 (PRECISERR) | 外设时钟未使能 | `__HAL_RCC_xxx_CLK_ENABLE()` |
| FreeRTOS 下随机 HardFault | 0x008000 (MSTKERR) | 任务栈溢出 | 增加 `configMINIMAL_STACK_SIZE` |
| 无符号除零 | 0x010100 (DIVBYZERO+INVSTATE) | 启用了 DIV_0_TRP 且执行了除零 | 确保除数非零或清除 CCR.DIV_0_TRP |
| 浮点运算后 HardFault | 0x000200 (LSPERR) | FPU lazy stacking 出错 | 检查 FPU 栈空间或禁用 lazy stacking |

## 预防性检查

在 HardFault_Handler 中读取并保存故障信息到 RTC 备份寄存器或保留 RAM：

```c
void HardFault_Handler(void)
{
    uint32_t cfsr = SCB->CFSR;
    uint32_t hfsr = SCB->HFSR;
    uint32_t bfar = SCB->BFAR;

    // 保存到备份 SRAM（如果可用）或 RTC 备份寄存器
    BACKUP_SRAM[0] = cfsr;
    BACKUP_SRAM[1] = hfsr;
    BACKUP_SRAM[2] = bfar;

    // 读取栈帧中的 PC
    uint32_t *sp;
    asm volatile("MRS %0, MSP" : "=r"(sp));
    uint32_t fault_pc = sp[6];  // R14 偏移 6 个字 → PC

    BACKUP_SRAM[3] = fault_pc;

    while(1);
}
```

> **注意**：J-Link halt 后读 SCB/CFSR 获得到的是**复位值**——这些寄存器在复位时被清零。必须在 HardFault_Handler 入口处立即读取，不能在 halt 之后读。
