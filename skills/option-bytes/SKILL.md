---
name: option-bytes
description: 读取、显示和安全配置 STM32 Option Bytes。支持 RDP 读保护、WRP 写保护、BOR 电压阈值、IWDG 看门狗模式、Boot 源选择、PCROP 保护，所有写操作需用户二次确认。当用户提到 Option Bytes、读保护、RDP、写保护、WRP、BOR、PCROP、量产保护、芯片锁死、Boot 配置、硬件看门狗时使用。
version: "1.0.0"
---

# option-bytes

读取、显示和安全配置 STM32 Option Bytes（选项字节），
支持读保护（RDP）、写保护（WRP）、BOR 电压、看门狗模式、PCROP 等配置。
所有写操作均需用户二次确认，防止误操作锁死芯片。

## 触发条件
- 用户说"Option Bytes"、"读保护"、"RDP"、"写保护"、"WRP"
- 用户需要设置量产保护（防止固件被读取）
- 用户不小心锁死芯片需要解锁
- 用户配置 BOR（掉电复位）阈值
- 需要查看当前 Option Bytes 配置
- 用户说"PCROP"、"专有代码读出保护"
- 用户说"nBoot0"、"Boot 引脚配置"
- 用户说"IWDG 硬件看门狗"、"独立看门狗"
- 用户说"secure boot"、"量产安全"

## ⚠️ 安全警告
- RDP Level 2 一旦写入，芯片将**永久锁定**，无法解除，无法调试
- 解除 RDP 会**全片擦除** Flash，请确认固件已备份
- 写 Option Bytes 失败可能导致芯片无法启动
- 本 skill 不会自动执行写操作，**必须用户明确输入确认码后才执行**

## 参数收集
- `operation`: 操作类型
  - `read` — 读取当前 Option Bytes
  - `unlock` — 解除 RDP（全片擦除！）
  - `set-rdp` — 设置读保护级别
  - `clear-rdp` — 清除读保护
  - `set-wrp` — 设置写保护扇区
  - `set-bor` — 设置掉电复位电压阈值
  - `set-iwdg` — 配置看门狗模式（软件/硬件）
  - `set-boot` — 配置 Boot 源选择
  - `dump` — 导出当前 Option Bytes 到 JSON 文件
  - `custom` — 自定义操作
- `device`: STM32 型号（影响寄存器地址，如 STM32F4、STM32L4、STM32G0、STM32H7）
- `interface`: SWD 或 JTAG（stlink / jlink / cmsis-dap）
- `openocd_cfg`: OpenOCD 配置文件路径
- `bor_level`: BOR 阈值等级 0~3（`set-bor` 操作时使用，0→1.8V, 1→2.1V, 2→2.4V, 3→2.7V）
- `output`: `dump` 操作时的输出 JSON 文件路径

## Option Bytes 字段说明

### RDP（读保护）
| 级别 | 值 | 说明 |
|------|----|------|
| Level 0 | 0xAA | 无保护，可调试读取 |
| Level 1 | 其他 | 禁止通过调试接口读取 Flash，可降级（全片擦除）|
| Level 2 | 0xCC | 永久锁定，不可降级，不可调试 |

### WRP（写保护）
按扇区配置，防止 Flash 被意外写入/擦除。

### BOR（掉电复位电压）
配置芯片在电源电压低于阈值时自动复位，防止低压误操作。

## STM32 各系列完整 Option Bytes 字段表

### STM32F4 系列 Option Bytes
| 位域 | 名称 | 默认值 | 说明 |
|------|------|--------|------|
| [7:0] | RDP | 0xAA | 读保护级别 |
| [8] | nRST_STOP | 1 | 进入 STOP 模式是否复位 |
| [9] | nRST_STDBY | 1 | 进入待机模式是否复位 |
| [11:10] | BOR_LEV | 0x3 | 掉电复位阈值 |
| [12] | WDG_SW | 1 | 独立看门狗软件/硬件模式 |
| [31:16] | nWRP | 0xFFFF | 扇区写保护（0=保护，1=不保护）|

### STM32H7 系列 Option Bytes
| 位域 | 名称 | 说明 |
|------|------|------|
| [7:0] | RDP | 读保护（0xAA=L0, 0xCC=L2）|
| [25] | SECURITY | TrustZone 安全启动使能 |
| [26] | BOOT_UBE | 用户 Flash 安全区 Boot |
| [28] | BCM4/BCM7 | Cortex-M4/M7 Boot 使能（双核）|

### STM32G0 系列 Option Bytes
| 位域 | 名称 | 说明 |
|------|------|------|
| [7:0] | RDP | 读保护 |
| [8] | nBOOT1 | Boot 源配置（配合 BOOT0 引脚）|
| [14] | nBOOT_SEL | BOOT0 信号来源（引脚/Option Bit）|
| [23:16] | BORF_LEV | 掉电复位上升阈值 |
| [25:24] | BORR_LEV | 掉电复位下降阈值 |

## Boot 配置说明

```
STM32 启动源选择（以 STM32F4 为例）
BOOT1(PB2)  BOOT0  启动源
    x          0   Flash（正常运行）
    0          1   系统存储器（内置 Bootloader，用于 ISP 烧录）
    1          1   SRAM（用于调试）

Option Bytes 中 nBOOT_SEL=0 时，Boot0 引脚决定启动源；
nBOOT_SEL=1 时，由 Option Bytes 中的 nBOOT0 位决定，与引脚无关。
```

## 量产安全配置流程

```
推荐量产 Option Bytes 配置流程：
Step 1  烧录固件并验证功能正常
Step 2  设置 BOR Level（防低压运行，推荐 Level 2）
Step 3  配置 WRP（保护 Bootloader 扇区，扇区 0 通常为 Bootloader）
Step 4  最后设置 RDP Level 1（若需防读取）
        ⚠️ RDP 必须最后设置，设置后调试接口受限
Step 5  绝不设置 RDP Level 2（除非确定永不需要更新固件）
```

## 执行流程

### Step 1 读取当前 Option Bytes
```bash
openocd -f interface/stlink.cfg -f target/stm32f4x.cfg \
  -c "init" \
  -c "reset halt" \
  -c "stm32f4x options_read 0" \
  -c "shutdown"
```

输出格式化显示：
```
═══════════ STM32 Option Bytes ═══════════
RDP Level    : 0 (无读保护)
nRST_STOP    : 1 (进入STOP模式不复位)
nRST_STDBY   : 1 (进入待机模式不复位)
IWDG_SW      : 1 (独立看门狗由软件控制)
BOR Level    : 3 (VBOR~2.7V)
WRP Sectors  : 无
══════════════════════════════════════════
```

### Step 2 操作前确认（写操作必须）
对任何写操作，输出确认提示并要求用户输入确认码：
```
⚠️  即将执行：设置 RDP Level 1（读保护）
    目标芯片：STM32F407VG
    影响：调试接口将无法读取 Flash
    若需恢复，需全片擦除（固件丢失）

    请输入确认码 CONFIRM-RDP1 以继续，或按 Ctrl+C 取消：
```

### Step 3 执行操作
用户确认后执行 OpenOCD 命令，捕获输出验证成功。

### Step 4 验证回读
操作完成后自动回读 Option Bytes，确认配置已生效。

## OpenOCD 命令参考

### STM32F4 系列
```
stm32f4x options_read 0          # 读取
stm32f4x options_write 0 0x...   # 写入（慎用）
stm32f4x unlock 0                 # 解锁（清除 RDP，全片擦除）
```

### STM32L4 系列
```
stm32l4x option_read 0 0x40022020
stm32l4x option_write 0 0x40022020 0x...
```

### STM32H7 系列
```
stm32h7x options_read 0          # 读取
stm32h7x options_write 0 0x...   # 写入（慎用）
stm32h7x unlock 0                 # 解锁（清除 RDP，全片擦除）
```

## 错误处理
| 错误 | 原因 | 处理 |
|------|------|------|
| OpenOCD 无法连接 | 读保护已启用 | 提示通过专用解锁流程清除（需全片擦除）|
| 写入超时 | 供电不稳定 | 检查 VDD 和 VBAT 供电 |
| 验证失败 | 写入值与回读不符 | 重试或检查芯片损坏 |
| `RDPKEY incorrect` | STM32L5/H5 系列需要提供 RDP 解锁密钥 | 查阅芯片手册获取正确密钥 |
| `nSWBOOT0 mismatch` | Boot0 引脚与 Option Bytes 配置冲突 | 检查 nBOOT_SEL 设置是否与硬件匹配 |
| `Option bytes not readable` | 芯片在 PCROP 或 RDP2 状态 | 无法通过调试接口读取，需硬件解除保护 |

## 边界定义

### 不该激活
- 用户讨论的是非 STM32 芯片（ESP32、GD32、nRF 等），这些芯片有各自独立的保护机制
- 用户只是想了解"Option Bytes 是什么"这类纯概念性问题，无实际硬件操作需求
- 用户没有明确提到任何 Option Bytes 相关关键词（RDP、WRP、BOR、读保护、写保护、PCROP）
- 工程中无 OpenOCD 可用的调试探针（如仅 Windows+Keil 环境且未安装 OpenOCD）

### 不该做
- **严禁**在用户未输入确认码的情况下执行任何写操作（RDP、WRP、BOR、IWDG）
- **严禁**设置 RDP Level 2 前不展示永久不可逆的严重警告
- **严禁**在用户未确认已备份固件的情况下执行 unlock（全片擦除）
- **严禁**猜测 Option Bytes 寄存器值和位域含义，必须对照芯片参考手册
- **严禁**在目标板运行中（非 halt 状态）写入 Option Bytes
- **严禁**跨系列套用 OpenOCD 命令（如对 STM32G0 使用 stm32f4x 命令）

### 不该碰
- **不触碰** Flash 用户数据区：Option Bytes 操作仅影响系统配置区，不得读写用户 Flash
- **不触碰** Boot 引脚物理状态：不修改 nBOOT_SEL 和 BOOT0 引脚配置与硬件跳线冲突的组合
- **不触碰** PCROP 保护区域：不解密、不绕过、不尝试读取 PCROP 保护中的代码
- **不触碰** 其他非 STM32 目标板的调试接口

## 输出约定
- 当前 Option Bytes 完整状态（格式化表格）
- 操作执行结果（成功/失败）
- 操作后回读验证结果

## 交接关系

- 上游：量产前配置流程，应在固件烧录验证后进行
- 下游：`gang-flash`（量产烧录前配置 Option Bytes 保护）
- 烧录失败时：`flash-jlink` / `flash-keil` 提示检查 RDP 保护位
- 互补：`firmware-sign`（固件签名 + 读保护组合使用）
- **不可逆操作前必须用户确认**（RDP Level 2、unlock 全片擦除）
