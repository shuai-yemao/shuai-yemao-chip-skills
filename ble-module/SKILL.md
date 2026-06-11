---
name: ble-module
description: |
  蓝牙低功耗(BLE)通信开发指南。覆盖 BLE 协议栈架构(GAP/GATT/SMP/L2CAP)、
  广播/扫描/连接/配对全流程、STM32WB/ESP32/Nordic nRF52 多平台 BLE 开发、
  蓝牙服务与特征值设计、低功耗优化、常见调试方法。
  当用户提到 BLE、蓝牙、低功耗蓝牙、Bluetooth Low Energy、蓝牙通信、
  STM32WB、ESP32 BLE、nRF52840、蓝牙配网、iBeacon、Eddystone 时使用。
version: "1.0.0"
---

# BLE 蓝牙低功耗开发指南

## 适用场景

- 需要在嵌入式设备和手机/网关之间建立 BLE 无线通信
- 需要设计蓝牙服务和特征值（Service/Characteristic）
- 需要选型 BLE 芯片方案（STM32WB / ESP32 / nRF52）
- 需要调试 BLE 连接断开、配对失败、广播不可见等问题
- 需要优化 BLE 设备功耗（广播间隔/连接间隔/唤醒策略）

## 必要输入

| 参数 | 说明 |
|------|------|
| BLE 芯片/模块 | STM32WB / ESP32 / nRF52 / BLE 串口模块 |
| 角色 | Peripheral(从)/Central(主)/Broadcaster/Observer |
| 服务 UUID | 自定义 128-bit 或标准 16-bit |
| 广播间隔 | 20ms~10.28s（影响功耗和发现速度）|

## BLE 协议栈核心概念

### 协议栈分层

```
APP (应用层)         ← 自定义服务/特征值
  |
GATT (通用属性)      ← 服务/特征值/属性协议
  |
GAP (通用访问)       ← 广播/扫描/连接/绑定
  |
SMP (安全管理)       ← 配对/绑定/加密
  |
L2CAP (逻辑链路)     ← 数据分片/重组
  |
HCI (主机控制器)     ← 命令/事件/数据
  |
Link Layer (链路层)  ← 37个物理信道(3广播+37数据)
```

### GATT 服务结构

```
Service (UUID: 0x180F 电池服务)
├── Characteristic (UUID: 0x2A19 电池电量)
│   ├── Properties: Read/Notify
│   ├── Value: 0~100 (%)
│   └── Descriptor: CCCD (0x2902) — 使能/禁止 Notify
│
└── Characteristic (UUID: 自定义 128-bit)
    ├── Properties: Write
    └── Value: 自定义数据
```

### 广播数据格式

```
AD Structure 1 (Length + AD Type + Data)
  ├─ Length: 1 byte
  ├─ AD Type: Flags(0x01) / 16-bit UUID(0x02) / 128-bit UUID(0x06)
  │           Name(0x08/0x09) / Tx Power(0x0A) / Service Data(0x16)
  └─ Data: N bytes

AD Structure 2
  ...
```

## 平台开发

### STM32WB — 双核架构

| 核 | 角色 | SDK |
|----|------|-----|
| Cortex-M4 (主核) | 应用逻辑 | STM32Cube_FW_WB |
| Cortex-M0+ (射频核) | BLE 协议栈+射频 | 固件更新通过 FUS |

**API 流程**：
```c
// 1. 初始化
SystemPower_Config();
BLE_Init();

// 2. 注册服务
aci_gatt_add_service(UUID_SERVICE, ..., &serviceHandle);
aci_gatt_add_char(serviceHandle, UUID_CHAR, CHAR_PROP_NOTIFY,
                  ATT_C_VALUE, 0, &charHandle);

// 3. 开始广播
aci_gap_set_discoverable(ADV_IND, 0, 1000, 0, ...);

// 4. 发送通知
aci_gatt_update_char_value(serviceHandle, charHandle, offset,
                           dataSize, data);
```

### ESP32 — 双核 + BLE/WiFi 共存

| 组件 | 说明 |
|------|------|
| NimBLE (推荐) | 主机协议栈，资源占用小，API 现代 |
| Bluedroid | 经典蓝牙 + BLE，功能全但资源占用大 |
| ESP-BLE-MESH | 蓝牙 Mesh 组网 |

**API 流程 (NimBLE)**：
```c
// 1. 初始化
nimble_port_init();
ble_gatt_count = ARRAY_SIZE(gatt_svr_svcs);
ble_services_count = 1;

// 2. GAP 事件回调
ble_gap_event_listener();

// 3. GATT 服务定义
static const struct ble_gatt_svc_def gatt_svr_svcs[] = {
    { .type = BLE_GATT_SVC_TYPE_PRIMARY,
      .uuid = &service_uuid.u,
      .characteristics = (struct ble_gatt_chr_def[]) {{
          .uuid = &char_uuid.u,
          .access_cb = data_access_cb,
          .flags = BLE_GATT_CHR_F_NOTIFY,
      }}},
};

// 4. 广播
ble_gap_adv_start(...)
```

### Nordic nRF52 — 专业 BLE SoC

| SDK | 特点 |
|-----|------|
| nRF5 SDK | 传统，文档全，BLE 功能最稳定 |
| nRF Connect SDK (Zephyr) | 现代，支持多协议 |

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 手机搜不到设备 | 广播参数错误/射频匹配未调 | 检查广播间隔、Tx Power、天线匹配 |
| 连接频繁断开 | 连接间隔不匹配/电源不稳 | 减小连接间隔、检查供电去耦 |
| 数据收发丢包 | MTU 太小/ATT Buffer 不足 | 协商 MTU(默认23→最大517) |
| 配对失败 | IO Capabilities 不匹配 | 检查配对参数中的 IO 能力 |
| 功耗过高 | 广播间隔太短/未进入休眠 | 拉长广播间隔、用睡眠模式 |

## 平台差异

| 平台 | SDK | BLE 角色 | 特点 |
|------|-----|---------|------|
| STM32WB | Cube_FW_WB | Peripheral/Central | 双核，BLE+802.15.4 |
| ESP32 | NimBLE/Bluedroid | Peripheral/Central | BLE+WiFi 共存 |
| nRF52 | nRF5 SDK/Zephyr | 全角色 | BLE 专业芯片，功耗最优 |
| CH32V307 | CH32 BLE Stack | Peripheral | RISC-V + BLE |
| 透传模块 | AT 指令 | 仅Peripheral | 成本最低，灵活性差 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| GAP 广播失败 | 射频外设被占用/WiFi 冲突 | 检查 BT/WiFi 共存配置 |
| GATT 写入失败 | 特征值权限不匹配 | 核对属性 Read/Write/Notify 设置 |
| 加密配对不通过 | 密钥交换失败 | 检查 IO Capabilities、OOB 数据 |
| BLE 协议栈 Panic | HCI 命令异常 | 重新初始化协议栈 |

## 边界定义

### 不该激活
- 用户需要的是经典蓝牙（SPP/耳机/音频）→ 非 BLE，需使用经典蓝牙方案
- 用户只需要串口透传（HC-05/HC-06 模块）→ 使用 `uart-module` + AT 指令即可
- 用户需要蓝牙 Mesh 组网 → 需使用 ESP-BLE-MESH 或 nRF Mesh SDK

### 不该做
- **禁止**在射频核心初始化未完成前发送 BLE 命令
- **禁止**在连接间隔过短(< 30ms)时发送大数据包（导致丢包）
- **禁止**在广播数据中暴露安全凭据

### 不该碰
- **不触碰**天线匹配电路设计（需射频专业知识）
- **不触碰**蓝牙认证测试（BQB/CE/FCC 认证）
- **不触碰**手机端 App 的 BLE 扫描逻辑（仅负责嵌入式端）

## 交接关系

- 上游：`uart-module`（BLE 透传模块底层通信）
- 互补：`lowpower-design`（BLE 设备功耗优化）
- 下位：`wifi-module`（BLE+WiFi 共存方案）
- 参考：`chip-architecture`（BLE 芯片选型）
