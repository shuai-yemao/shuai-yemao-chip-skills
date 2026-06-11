---
name: bootloader-design
description: 嵌入式 Bootloader 设计与开发完整指南。涵盖启动流程架构（硬件初始化 → 完整性校验 → 引导决策 → APP 跳转）、Flash 分区策略（单区/双区 A-B/恢复区/配置区）、固件校验（CRC32/SHA256/ECDSA+RSA 签名验签）、向量表重定位与大跳转（VTOR/MSP/PC 跳转序列）、引导模式（正常/DFU/OEM/恢复/安全启动）、通信协议集成（UART Ymodem/SPI/USB DFU/CAN/以太网/HSPI 外部 Flash）、回滚与容错机制（看门狗超时回退/Bad App 自动恢复/备份区加载）、安全引导链（信任根 → BootROM → Bootloader1 → Bootloader2 → APP 分级验签）、启动时间优化、双芯片架构（WiFi MCU 下载 + 主 MCU 引导）、常见陷阱与调试。当用户提到 Bootloader、引导程序、IAP、In-Application Programming、flash 分区、A-B 分区、双区引导、回滚、版本回退、安全引导、secure boot、签名验签、固件校验、CRC 校验、DFU、Device Firmware Upgrade、Ymodem 升级、UART 升级、USB DFU、引导流程、启动流程、跳转 APP、向量表重映射、APP 跳转、看门狗回退、恢复模式、出厂固件恢复、双芯片 boot、外部 Flash 引导时使用。
version: "1.0.0"
---

# 嵌入式 Bootloader 设计与开发指南

> 与 `flash-module`（Flash 编程/分区/Sector 操作）和 `ota-update-system`（OTA 架构与状态机）互补——本 skill 专注 Bootloader **架构设计、启动流程、引导决策、安全链和调试**。

## 适用场景

- 需要为产品设计启动引导方案
- 需要设计 Flash 分区策略（单区/双区/恢复区）
- 需要实现固件校验（CRC/SHA/签名验签）
- 需要实现 IAP 跳转和向量表重定位

## 必要输入

| 参数 | 说明 |
|------|------|
| MCU 型号 | 影响 Flash 大小、扇区布局、启动模式 |
| Flash 总容量 | 决定分区划分 |
| OTA 方案 | 有/无 OTA（影响是否需要 A-B 分区）|
| 安全需求 | 是否需要安全启动/签名验签 |

## 适用场景

- Bootloader 架构选型（单区/双区 A-B/恢复区）
- Flash 分区布局设计
- 启动引导流程实现（硬件初始化→校验→决策→跳转）
- 固件完整性校验（CRC/SHA/签名）
- 安全引导链（信任根→分级验签）
- 回滚与容错机制设计（看门狗/恢复区/备份）
- 通信协议集成（Ymodem/DFU/CAN/SPI）
- 双芯片引导架构
- Bootloader 调试与故障排查

## 必要输入

- MCU 型号与 Flash 大小
- APP 固件大小
- 是否需要安全引导（签名验签）
- 通信方式（UART/USB/CAN/SPI/以太网）
- 分区策略（单区/双区 A-B/其他）

---

## 1. Bootloader 架构模式

### 架构对比

| 架构 | Flash 占用 | 回滚能力 | 实现复杂度 | 适用场景 |
|------|-----------|---------|-----------|---------|
| **单区 (Single)** | Boot + App(1) | 无回滚 | 最低 | 产品稳定后，仅有线升级 |
| **双区 A-B (Dual Bank)** | Boot + App(A) + App(B) | 硬件级回滚 | 中 | 消费电子、IoT |
| **单区+恢复区 (Single+Recovery)** | Boot + App + Recovery | 软件级回滚 | 中高 | 空间受限但需回滚 |
| **三区 (Safe Dual)** | Boot + App(A) + App(B) + Config | 完整回滚 | 高 | 医疗/车规/工业安全 |

```
单区架构:
┌──────────────────────────────────────┐
│  Bootloader  (32KB)                   │
├──────────────────────────────────────┤
│  App  (剩余全部)                       │
├──────────────────────────────────────┤
│  Config/Flag (1~4KB, 末尾)            │
└──────────────────────────────────────┘

双区 A-B 架构:
┌──────────────────────────────────────┐
│  Bootloader    (32KB)                 │
├──────────────────────────────────────┤
│  App Slot A    (512KB)               │ ← 当前运行
├──────────────────────────────────────┤
│  App Slot B    (512KB)               │ ← 新固件写入目标
├──────────────────────────────────────┤
│  Config/State  (4KB)                 │ ← 引导标志/版本/CRC
└──────────────────────────────────────┘

单区+恢复区:
┌──────────────────────────────────────┐
│  Bootloader    (32KB)                 │
├──────────────────────────────────────┤
│  App           (448KB)               │
├──────────────────────────────────────┤
│  Recovery Mini (64KB)                │ ← 稳定的出厂固件
├──────────────────────────────────────┤
│  Config/State  (4KB)                 │
└──────────────────────────────────────┘
```

---

## 2. 启动引导流程

### 标准启动序列

```text
上电/复位
    │
    ▼
┌─────────────────────────────────────┐
│ 1. 硬件初始化阶段 (Startup)           │
│    ├─ CPU 时钟/Flash 等待周期        │
│    ├─ 栈指针 SP 初始化               │
│    ├─ 全局变量/ BSS 初始化 (可省)     │
│    ├─ 最小外设时钟使能               │
│    └─ 看门狗初始化 (可选，推荐使能)    │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│ 2. 引导决策阶段 (Boot Decision)       │
│    ├─ 读取引导标志 (Config 区)        │
│    ├─ 验证各分区的完整性               │
│    │   ├─ CRC32 校验 (快速)           │
│    │   ├─ SHA256 摘要 (安全但慢)       │
│    │   └─ 数字签名验证 (安全启动必需)   │
│    ├─ 检查外部触发条件                  │
│    │   ├─ GPIO 电平 (强制 DFU 模式)     │
│    │   ├─ 串口收到特定字符              │
│    │   └─ 看门狗标志（上次异常复位）     │
│    └─ 决策结果:                        │
│        ├─ 启动 A 区                    │
│        ├─ 启动 B 区                    │
│        ├─ 启动恢复区                   │
│        └─ 进入 DFU 模式（等待新固件）   │
└─────────────────┬───────────────────┘
                  ▼
┌─────────────────────────────────────┐
│ 3. 跳转阶段 (Jump to APP)            │
│    ├─ 关闭所有使能的中断              │
│    ├─ 禁用外设时钟 (清理状态)         │
│    ├─ 恢复 SysTick 为复位状态         │
│    ├─ 设置主栈指针 MSP ← APP 栈顶     │
│    ├─ 重定位向量表 VTOR ← APP 基址    │
│    ├─ DSB + ISB (确保生效)            │
│    └─ 跳转到 APP Reset_Handler       │
└─────────────────────────────────────┘
```

### 跳转代码（核心）

```c
// ── APP 跳转函数（标准实现）──

typedef void (*app_entry_t)(void);

static void jump_to_app(uint32_t app_addr) {
    // 1. 关闭全局中断
    __disable_irq();

    // 2. 关闭所有外设中断（NVIC 级）
    for (int i = 0; i < sizeof(NVIC->ICER) / sizeof(NVIC->ICER[0]); i++) {
        NVIC->ICER[i] = 0xFFFFFFFF;         // 清除所有使能
        NVIC->ICPR[i] = 0xFFFFFFFF;         // 清除所有挂起
    }

    // 3. 关闭 SysTick（APP 会重新配置）
    SysTick->CTRL = 0;
    // 可选: 清除 PendSV 和 SysTick 挂起
    SCB->ICSR = SCB_ICSR_PENDSVCLR_Msk | SCB_ICSR_PENDSTCLR_Msk;

    // 4. 重置 SCB 寄存器为默认值（避免 APP 依赖 Bootloader 的配置）
    SCB->VTOR = 0;  // 由 APP 的 SystemInit 重新设置
    // 或者直接设为目标地址:
    SCB->VTOR = app_addr;

    // 5. 清除 MPU 配置（如果 Bootloader 用了 MPU）
    #ifdef __MPU_PRESENT
    MPU->CTRL = 0;
    MPU->RNR  = 0;
    MPU->RBAR = 0;
    MPU->RASR = 0;
    #endif

    // 6. 内存屏障
    DSB();
    ISB();

    // 7. 读取 APP 向量表
    uint32_t app_stack  = *(volatile uint32_t*)app_addr;      // 栈顶
    uint32_t app_entry  = *(volatile uint32_t*)(app_addr + 4); // Reset_Handler 地址

    // 8. 设置 MSP 并跳转
    __set_MSP(app_stack);       // 关键：用 APP 的栈顶，而非 Bootloader 的
    DSB();
    ISB();

    app_entry_t jump = (app_entry_t)app_entry;
    jump();                     // 永不返回
}

// ── 调用 ──
jump_to_app(APP_A_ADDR);
```

### 跳转陷阱

| 陷阱 | 现象 | 解决 |
|------|------|------|
| IRQ 未关闭 | 跳转后进入未知 ISR 或 HardFault | 跳转前 `__disable_irq()` + 清所有 ICER |
| MSP 未更新 | 栈溢出或 SPI 异常 | `__set_MSP(app_stack)` 必须在跳转前 |
| D-Cache 未清理 (M7) | APP 代码读取旧数据 | `SCB_CleanInvalidateDCache()` + `SCB_InvalidateICache()` |
| MPU 配置遗留 | APP 无法访问受 Bootloader 保护的区域 | 跳转前禁用 MPU |
| 外设时钟未关 | 外设在 APP 重置前保持状态，导致误触发 | 逐个关闭已使能的外设时钟 |
| VTOR 未切换 | 中断向量指向 Bootloader 区 | APP 的 SystemInit 或显式设置 VTOR |

---

## 3. 固件校验

### 校验方法对比

| 方法 | 强度 | 速度 | Flash 占用 | 防篡改 | 用途 |
|------|------|------|-----------|--------|------|
| CRC32 | 低 | 极快 | 4 bytes | 不可靠 | 传输校验/快速完整性 |
| SHA256 | 高 | 中 | 32 bytes | 可靠 | 固件完整性验证 |
| ECDSA | 极高 | 慢（验签） | 64 bytes | 不可伪造 | 安全启动必须 |
| RSA-2048 | 极高 | 很慢 | 256 bytes | 不可伪造 | 安全启动 |

### CRC32 校验

```c
// 优点: 硬件 CRC 外设可加速，适合快速完整性检测
// 缺点: 可被伪造 → 不能作为安全校验

// 用硬件 CRC 计算（STM32F4/F7/H7 内置 CRC 单元）:
uint32_t calc_crc32(uint32_t *data, uint32_t len_words) {
    CRC->CR = CRC_CR_RESET;                    // 复位 CRC 计算单元
    for (uint32_t i = 0; i < len_words; i++) {
        CRC->DR = data[i];                     // 逐字输入
    }
    return CRC->DR;                            // 读取结果
}

// 在固件头中预留 CRC32 字段
// 先填 CRC 字段为 0，计算全固件 CRC，再回填
// Bootloader 读出固件头中的 CRC，重新计算对比
```

### SHA256 + 签名验签（安全启动）

```c
// ── 固件签名流程（上位机/CI 中执行）──
// openssl ecparam -genkey -name prime256v1 -out boot_private.pem
// openssl ec -in boot_private.pem -pubout -out boot_public.pem
// 签名: openssl dgst -sha256 -sign boot_private.pem -out firmware.sig firmware.bin

// ── Bootloader 验签（MCU 端）──
// 需要集成 mbedTLS 或自研 ECC 验签代码
#include "mbedtls/pk.h"
#include "mbedtls/sha256.h"
#include "mbedtls/ecdsa.h"

int verify_firmware(uint8_t *fw_data, uint32_t fw_len,
                    uint8_t *signature, uint32_t sig_len,
                    uint8_t *public_key, uint32_t key_len) {
    mbedtls_pk_context pk;
    mbedtls_pk_init(&pk);

    // 解析公钥
    int ret = mbedtls_pk_parse_public_key(&pk, public_key, key_len);
    if (ret != 0) return -1;

    // 计算固件 SHA256
    uint8_t hash[32];
    mbedtls_sha256(fw_data, fw_len, hash, 0);  // 0=SHA256

    // ECDSA 验签
    ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256,
                            hash, 0, signature, sig_len);
    mbedtls_pk_free(&pk);
    return (ret == 0) ? 0 : -1;
}
```

### 固件头格式设计

```c
// 推荐的固件头（放在固件最前面，Bootloader 先读头再做决策）
typedef struct __attribute__((packed)) {
    uint32_t magic;             // 魔数 0xDEADBEAF (或板级唯一 ID)
    uint32_t image_size;        // 固件大小（不含头）
    uint32_t firmware_version;  // 版本号 (0x01020003 = v1.2.3)
    uint32_t hardware_id;       // 板型 ID (防止刷错固件事)
    uint32_t crc32;             // 固件数据 CRC32
    uint8_t  sha256[32];        // 固件数据 SHA256
    uint8_t  signature[64];     // ECDSA P-256 签名 (可选)
    uint32_t signature_size;    // 签名大小 (0=无签名)
    uint32_t timestamp;         // 编译时间戳
    uint32_t reserved[4];       // 保留，填充到 128 字节对齐
    // ── 固件数据紧接其后 ──
} firmware_header_t;

#define FIRMWARE_MAGIC    0xDEADBEAF
#define HEADER_SIZE       sizeof(firmware_header_t)
```

---

## 4. 引导决策与状态管理

### 引导标志区 (Config)

```c
// 引导标志存储在固定 Flash 扇区末尾 (4KB 扇区)
// 关键: 使用 2 份备份 + 累加器策略，防写入中断导致状态丢失

typedef struct __attribute__((packed)) {
    uint32_t magic;               // 0xCFCFCFCF 表示有效
    uint32_t boot_count;          // 启动次数（看门狗回退计数）
    uint32_t current_slot;        // 当前槽位: 0=A, 1=B, 2=Recovery
    uint32_t try_boot_count;      // 新固件尝试启动次数
    uint32_t firmware_status;     // 0=未知, 1=OK, 2=FAILED, 3=PENDING
    uint32_t firmware_version;    // 当前运行固件版本
    uint32_t upgrade_pending;     // 有升级待处理
    uint32_t crc32;               // 本结构体 CRC
} boot_config_t;

// 状态迁移:
// 升级开始时: firmware_status = PENDING, 启动尝试次数+1
// APP 正常启动: 主动调用 boot_set_status(OK)
// 看门狗复位: 启动计数器+1，超过阈值 → 标记 FAILED → 回滚
```

### 引导决策流程图

```text
                ┌──────────┐
                │  复位     │
                └────┬─────┘
                     ▼
          ┌──────────────────┐
          │ 读取 Config 区    │
          │ 检测复位原因      │
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │ 升级挂起?         │───是──→ ┌─────────────┐
          └────────┬─────────┘         │ 验证新固件   │
                   ▼ 否                │ (CRC/SHA/签名)│
          ┌──────────────────┐         └──────┬──────┘
          │ GPIO DFU 触发?    │───是──→       │
          └────────┬─────────┘                ▼
                   ▼ 否              ┌──────────────────┐
          ┌──────────────────┐    ┌─→│ 校验通过?         │
          │ 看门狗复位标志?   │───┤  └────────┬─────────┘
          └────────┬─────────┘   │           ▼
                   ▼             │    ┌──────────────────┐
          ┌──────────────────┐   │ 是 │ 标记 OK, 跳转新区   │
          │ 主槽位完整性校验   │   └──→│ N 次计数器=0       │
          └────────┬─────────┘   │    └──────────────────┘
                   ▼             │
          ┌──────────────────┐   │ 否 ┌──────────────────┐
          │ 校验通过?         │───┤   │ 回滚到另一区      │
          └────────┬─────────┘   └──→│ 标记旧区 OK       │
                   ▼ 否              └──────────────────┘
          ┌──────────────────┐
          │ 尝试备用槽       │
          │ (B区/Recovery)   │
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │ 都失败 → DFU 模式 │
          │ 等待固件下载      │
          └──────────────────┘
```

---

## 5. 回滚与容错

### 看门狗回滚机制

```c
// ── 核心思路 ──
// Bootloader 使能 IWDG，跳转前喂狗一次
// APP 必须在指定时间内喂狗
// 如果 APP 崩溃/死机 → IWDG 复位 → Bootloader 检测到启动计数器+1
// 如果失败次数 > 阈值 → 回滚到旧固件

#define MAX_BOOT_ATTEMPTS  3   // 3 次失败后回滚

void bootloader_main() {
    // 1. 从 Config 区读取当前状态
    boot_config_t cfg = read_boot_config();

    // 2. 检测看门狗复位
    if (RCC->CSR & RCC_CSR_IWDGRSTF) {
        cfg.boot_count++;
        RCC->CSR |= RCC_CSR_RMVF;          // 清除复位标志

        if (cfg.boot_count >= MAX_BOOT_ATTEMPTS) {
            cfg.firmware_status = STATUS_FAILED;
            cfg.boot_count = 0;
            cfg.try_boot_count = 0;
            // 回滚到上一版本
            if (cfg.current_slot == SLOT_A) {
                cfg.current_slot = SLOT_B;
            } else {
                cfg.current_slot = SLOT_A;
            }
            save_boot_config(&cfg);
        }
    } else {
        cfg.boot_count = 0;                 // 正常复位 → 清零计数
    }

    // 3. 使能 IWDG: LSI=32kHz, 预分频=256, 重载=1250 → 约 10 秒
    IWDG->KR = 0x5555;                     // 解锁
    IWDG->PR = IWDG_PR_PR_2;               // 256 分频
    IWDG->RLR = 1250;                      // 10s 超时
    IWDG->KR = 0xCCCC;                     // 启动
    // 跳转前喂一次狗
    IWDG->KR = 0xAAAA;

    // 4. 跳转到 APP（APP 内部定期喂狗）
    jump_to_app(cfg.current_slot == SLOT_A ? APP_A_ADDR : APP_B_ADDR);
}

// ── APP 端 ──
void app_main() {
    // APP 启动后先标记自身 OK（通过写入 Config 区）
    boot_set_status(STATUS_OK);

    // 主循环中喂狗
    while (1) {
        IWDG->KR = 0xAAAA;
        // ... 正常任务
    }
}

// 如果 APP 在 10 秒内没有喂狗 → IWDG 复位 → Bootloader 重试
// 3 次重置后回滚 → 保证死机后能恢复
```

### 回滚策略总览

```c
// 策略 A: A-B 双区回滚（硬件级，推荐）
//   新固件写入 B 区 → 标记 PENDING → 跳转 B 区
//   B 区运行成功 → 标记 OK, A 区变为备用
//   B 区运行失败 → 回跳 A 区（A 区未修改）
//   优点: 回滚零风险，A 区始终是好的

// 策略 B: 单区 + 备份回滚（软件级）
//   新固件写入 A 区 → 标记 PENDING → 启动
//   失败 → 从外部 Flash/恢复区复制出厂固件到 A 区
//   优点: 省 Flash, 缺点: 恢复时间长, 备份区需事先写入

// 策略 C: 三区安全回滚（车规级）
//   App A: 当前稳定版
//   App B: 新固件
//   Recovery: 最小出厂固件（不可改写）
//   失败 → 回 App A → 仍失败 → 回 Recovery
```

---

## 6. 通信协议集成

### UART Ymodem（最常用的 Bootloader 协议）

```c
// Ymodem 流程:
// 发送端                 接收端 (Bootloader)
//   │                        │
//   │  ── Sender Start ──→  C (CRC 模式请求)
//   │  ←─── 文件名 + 大小 ─── │
//   │  ── 数据块 (128B) ──→   │
//   │  ── 数据块 (128B) ──→   │  写 Flash
//   │    ...                  │
//   │  ── EOT ──────────→    │
//   │  ←─── ACK ───────────  │
//   │  ── 空的结束包 ────→   │  EOT 后发一个空包
//   │                        │
//   └── 传输完成 ──────────→  │  验证 + 跳转

// Key: 边接收边写 Flash，不能全部收到再写（RAM 不够）
uint32_t flash_write_addr = APP_B_ADDR;
uint32_t bytes_received = 0;

while (1) {
    packet_t pkt = ymodem_receive(timeout_ms);
    if (pkt.type == PKT_DATA) {
        // 按页写入 Flash（STM32F4 页大小 2KB/16KB 不等）
        flash_program_page(flash_write_addr, pkt.data, pkt.len);
        flash_write_addr += pkt.len;
        bytes_received += pkt.len;
        ymodem_ack();
    } else if (pkt.type == PKT_EOT) {
        ymodem_ack();
        // 接收结束包（空的）
        packet_t end = ymodem_receive(1000);
        if (end.type == PKT_DATA && end.len == 0) {
            ymodem_ack();
            break;  // 传输完成
        }
    } else if (pkt.type == PKT_ERROR || pkt.type == PKT_TIMEOUT) {
        // 重试 N 次后进入 DFU 等待
        retry_count++;
        if (retry_count > MAX_RETRY) {
            enter_dfu_mode();
        }
    }
}

// 完成后验证
if (verify_firmware(APP_B_ADDR, bytes_received) == 0) {
    boot_set_status(STATUS_PENDING);  // 标记待验证
    jump_to_app(APP_B_ADDR);
} else {
    boot_set_status(STATUS_FAILED);
    jump_to_app(APP_A_ADDR);          // 回滚
}
```

### USB DFU 协议

```
USB DFU 类协议 (USB Device Class Spec for DFU):
  ┌─────────────────────┐
  │ DFU_DNLOAD          │ ← 主机发送固件数据
  │ DFU_UPLOAD          │ ← 主机读取固件数据（备份/验证）
  │ DFU_GETSTATUS       │ ← 主机轮询状态
  │ DFU_CLRSTATUS       │ ← 清除错误
  │ DFU_ABORT           │ ← 终止当前操作
  │ DFU_DETACH          │ ← 请求设备重启到 DFU 模式
  └─────────────────────┘

实现方式:
  1. 使用 STM32 USB DFU Bootloader (芯片内置，不可改)
  2. 自实现 USB DFU (基于 ST USB Device 库 + DFU 类)
  3. DfuSe 文件格式支持 (.dfu 文件)
```

### 通信协议对比

| 协议 | 速度 | 可靠性 | MCU 资源 | 适用场景 |
|------|------|--------|---------|---------|
| UART Ymodem | 115200bps | CRC 校验，有重传 | 极低 | 有线串口升级，最常用 |
| USB DFU | 12Mbps (FS) | USB CRC 硬件保证 | 中 (USB 库) | 消费电子，用户友好 |
| SPI Slave | 10+Mbps | 主机控制 | 低 | 双芯片架构 |
| CAN (UDS) | 250k~1Mbps | CAN 硬件 CRC | 中 (CAN 栈) | 车载/工业 |
| 以太网 HTTP | 100Mbps | TCP 保证 | 高 (LWIP) | 有网络连接设备 |

---

## 7. 安全引导链

### 分级安全引导

```text
信任根 (Root of Trust):
  ┌─────────────────────────────────────────┐
  │ BootROM (芯片固件, 不可更改)              │
  │ 验证 Bootloader1 签名                    │
  └────────────────┬────────────────────────┘
                   ▼
  ┌─────────────────────────────────────────┐
  │ Bootloader1 (第一阶段引导, ~4KB)          │
  │ 验证 Bootloader2 签名                    │
  │ 初始化 DDR/Flash 控制器                   │
  └────────────────┬────────────────────────┘
                   ▼
  ┌─────────────────────────────────────────┐
  │ Bootloader2 (主引导, ~64KB)              │
  │ 验证 APP 签名                            │
  │ 支持 DFU 模式/通信协议                    │
  └────────────────┬────────────────────────┘
                   ▼
  ┌─────────────────────────────────────────┐
  │ APP (用户固件)                           │
  │ 可选的运行时验证                          │
  └─────────────────────────────────────────┘
  → 每一级只信任上一级的签名验证结果
  → 任何一级验签失败 → 进入恢复模式/DFU
```

### 签名验签集成

```c
// Bootloader 侧: 验签（使用 mbedTLS）
// 公钥以 const 数组形式编译进 Bootloader
// Bootloader 自身签名在烧录时一次性地验证

static const uint8_t boot_public_key[] = {
    // 由 openssl ec -in boot_private.pem -pubout -outform DER 导出
    // 以 C 数组形式嵌入
    0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2A, 0x86, ...
};

int boot_verify_app(uint32_t app_addr) {
    firmware_header_t *hdr = (firmware_header_t*)app_addr;

    // 必须在 Bootloader 烧录阶段就已嵌入公钥
    // 公钥的 Hash 存储在 OTP/efuse 中防篡改
    return ecdsa_verify(
        boot_public_key, sizeof(boot_public_key),
        (uint8_t*)(app_addr + sizeof(firmware_header_t)),
        hdr->image_size,
        hdr->signature
    );
}
```

### Flash 防篡改

| 措施 | 实现 | 说明 |
|------|------|------|
| RDP Level 2 (STM32) | Option Bytes 设置 | 永久禁用调试接口，不可回退 |
| WRP 写保护 | 保护 Bootloader 扇区 | Bootloader 自身不可被擦写 |
| PCROP 专有代码保护 | 保护 Bootloader 代码区 | 防止读取 Bootloader 代码 |
| 公钥 OTP 存储 | OTP 区域一次性写入 | 公钥写入后不可更改 |
| Secure Boot (M33) | TrustZone 硬件隔离 | 认证安全世界和正常世界 |

---

## 8. 双芯片引导架构

```text
WiFi/BT MCU (ESP32)                   主 MCU (STM32)
┌─────────────────┐                  ┌──────────────────┐
│  OTA 服务器      │     SPI/         │  Bootloader      │
│  HTTPS 下载      │────UART─────────→│  验签/跳转        │
│  完整/差分包     │     Flash        │                  │
│  下载完成后:     │                  │  Shared Flash:   │
│  写入 Shared     │                  │  ┌────────────┐  │
│  Flash 分区      │                  │  │  New FW    │  │
│  通知主 MCU      │────GPIO IRQ─────→│  │  Status    │  │
│                  │                  │  └────────────┘  │
└─────────────────┘                  └──────────────────┘

流程:
  1. ESP32 通过 HTTPS 下载新固件
  2. 写入共享 Flash (SPI 或 QuadSPI)
  3. 设置状态标志 (共享内存或 SPI Flash 状态区)
  4. 触发 GPIO 中断通知 STM32
  5. STM32 Bootloader 读取共享 Flash → 验证签名
  6. 拷贝到内部 Flash 或直接从外部 Flash 引导
  7. 标记完成 → 通知 ESP32 结果
  8. 双方回滚机制保持同步
```

---

## 9. 启动时间优化

```c
// Bootloader 目标: 从复位到跳转 APP 控制在 100ms 以内

// 优化点 1: 最小化外设初始化
void bootloader_early_init(void) {
    // 只使必须的时钟:
    RCC->AHB1ENR = RCC_AHB1ENR_GPIOCEN;        // 只使能 DFU 按键 GPIO
    // 不初始化: ADC/DAC/TIM/SPI/I2C/USB/UART（Ymodem 需要才 init UART）

    // Flash 等待周期（快速设置）
    FLASH->ACR = FLASH_ACR_LATENCY_3WS |        // 根据主频设置等待周期
                 FLASH_ACR_PRFTEN;               // 预取缓冲使能
}

// 优化点 2: 快速校验策略
// 不用 SHA256（200KB 固件算 ~50ms）
// 用 CRC32 硬件加速（200KB 固件算 ~2ms）
// 或只校验固件头 128 字节（~0.01ms）
// 签名校验只在第一次启动新固件时执行

// 优化点 3: 校验结果缓存
// 将校验结果写入 Config 区，下次复位直接读缓存
// 只有 Config 中的版本号 > 上次记录的版本号才重新校验

// 优化点 4: 链接器优化
// Bootloader 全放 ITCM (H7) 或 RamFunc (F4)
// 避免 Flash 等待周期
```

---

## 10. 调试与故障排查

### 常见问题

| 症状 | 最可能根因 | 解决 |
|------|-----------|------|
| 跳转后 HardFault | MSP 设置错误或 VTOR 未切换 | 检查 `__set_MSP` + VTOR + DSB/ISB |
| 跳转后中断不触发 | NVIC 中断未全部关闭 | 跳转前清所有 ICER + ICPR |
| 新固件重复启动回滚 | APP 未调用喂狗或未标记 OK | APP 启动后调 `boot_set_status(OK)` + 定期喂狗 |
| 固件校验失败 | Flash 写入时断电/页不对齐 | 增加写入完整性和重试机制 |
| Ymodem 传输超时 | 波特率不匹配或 RTS/CTS 流控 | 固定 115200 8N1，无流控 |
| 升级后变砖 | 分区地址写错或跳转地址不对 | 检查链接脚本分区地址 |
| IWDG 连续复位 | APP 太忙来不及喂狗 | 在 SysTick 或低优先级中断中喂狗 |
| Config 区损坏 | 写入时断电 | 使用 2 份备份 + 读写前校验 |

### Bootloader 调试指示灯

```c
// 推荐 Bootloader 使用 LED 指示状态:
// 1 次闪烁: 正常启动 APP
// 2 次闪烁: 进入 DFU 模式
// 3 次闪烁: 固件校验失败
// 4 次闪烁: 回滚执行中
// 快闪: 固件下载中

// 串口打印（如果 UART 已初始化）:
// [BL] Boot v1.0.0 starting...
// [BL] Config: slot=A, status=OK, ver=2.0.3
// [BL] CRC verify: PASS (0xA3B2C1D0)
// [BL] Signature verify: PASS
// [BL] Jumping to APP @ 0x08020000...
```

---

## 边界定义

### 不该激活
- 用户只需要 Flash 扇区写入/擦除操作（非 Bootloader 设计）→ 使用 `flash-module`
- 用户已经在使用 MCUboot / TinyUSB DFU 等成熟框架，需要的是配置而非设计
- 用户没有具体的 MCU 型号，纯概念性讨论

### 不该做
- **禁止**在多 Bank MCU 上未经确认直接配置双区 Boot
- **禁止**在安全引导链中省略信任根验证步骤
- **禁止**在 Bootloader 中引入阻塞式调用（影响跳转时序）
- **禁止**在向量表重定位时不验证新向量表的有效性

### 不该碰
- **不触碰**用户原有 Flash 分区的数据（除非升级操作）
- **不触碰**芯片 Option Bytes（RDP/WRP 配置）
- **不触碰**量产烧录工具链的配置

## 交接关系

- 上游：`flash-module`（Flash 编程/分区操作基础）
- 下游：`ota-update-system`（OTA 架构设计）
- 辅助：`option-bytes`（RDP/WRP 保护配置）
- 验证：`watchdog-module`（看门狗回退机制）

## 参考文档

- STM32 AN2557 — 通过 USART 实现 IAP
- STM32 AN3155 — USB DFU 协议
- STM32 AN2606 — STM32 系统内存 Bootloader
- STM32 AN3969 — IAP 使用 Ymodem 协议
- ARM ELF 规范 — 向量表结构
- mbedTLS 文档 — ECDSA 验签
- Ymodem 协议规范 (RFC)
- USB DFU 规范 (USB-IF)
