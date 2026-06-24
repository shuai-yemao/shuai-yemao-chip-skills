---
name: cellular-module
description: |
  蜂窝通信（4G/NB-IoT/Cat-M）开发指南。覆盖蜂窝网络选型对比、
  4G Cat-1/Cat-M/NB-IoT 差异与应用场景、SIM7xxx/BC95/EC20 模块 AT 指令开发、
  TCP/IP 协议栈管理、MQTT over LTE、低功耗 PSM/eDRX 模式、
  信号质量监测与异常排查。
  当用户提到 4G、NB-IoT、Cat-M、蜂窝通信、SIM7000、SIM7600、
  BC95、BC26、EC20、4G DTU、LTE 模块、AT 指令拨号、MQTT 上云时使用。
version: "1.0.0"
---

# 蜂窝通信（4G/NB-IoT/Cat-M）开发指南

## 适用场景

- 需要为嵌入式设备添加蜂窝网络（4G/NB-IoT）通信能力
- 需要选型蜂窝方案（4G Cat-1 / Cat-M / NB-IoT）
- 需要通过 AT 指令控制 4G/NB-IoT 模块
- 需要使用蜂窝网络发送传感器数据到云平台
- 需要优化蜂窝设备的功耗（PSM/eDRX 模式）

## 必要输入

| 参数 | 说明 |
|------|------|
| 蜂窝制式 | 4G Cat-1 / Cat-M (LTE-M) / NB-IoT / 2G 后备 |
| 模块型号 | SIM7xxx(SIMCom) / BCxx(移远) / ECxx(移远) |
| SIM 卡 | 运营商 + APN + 鉴权信息 |
| 通信方式 | TCP / UDP / MQTT / HTTP 直连或透传 |
| 功耗需求 | 实时在线 / PSM(省电) / eDRX(扩展不连续接收) |

## 蜂窝方案对比

| 制式 | 速率(下行) | 时延 | 功耗 | 覆盖 | 适用场景 |
|------|-----------|------|------|------|---------|
| 4G Cat-1 | ~10Mbps | ~50ms | 高~400mA | 广 | 实时通信/视频/OTA |
| LTE-M (Cat-M1) | ~1Mbps | ~100ms | 中~200mA | 中 | 移动追踪/可穿戴 |
| NB-IoT | ~200kbps | ~1-10s | 低~50mA | 深(室内/地下) | 水表/烟感/停车位 |
| 2G(GPRS) | ~50kbps | 高 | 中 | 极广(关闭中) | 遗留系统 |

**选型决策**：
- 需要语音/视频 → Cat-1
- 移动设备、需切换基站 → Cat-M
- 固定位置、深覆盖 → NB-IoT
- 低成本低速 → NB-IoT（模块成本最低）

## AT 指令核心集

### 模块初始化与网络注册

```c
// SIM7xxx / BC26 / EC20 AT 命令流程
AT                          // 同步波特率，返回 OK
ATE0                        // 关闭回显
AT+CPIN?                    // 检查 SIM 卡，返回 +CPIN: READY
AT+CREG?                    // 网络注册状态(0=未注册,1=注册,5=漫游)
AT+CSQ                      // 信号质量(0~31), >=10 可通信
AT+CPSI?                    // 小区信息（移动联通电信）
AT+CGDCONT=1,"IP","CMNET"  // 设置 APN（CMNET/UNINET/CTNET）
AT+CGATT=1                  // 附着 PS 域
AT+NETOPEN                  // 打开 TCP/IP 栈（部分模块需要）
```

### TCP/UDP 通信

```c
// 建立 TCP 连接并发送数据
AT+QIOPEN=1,0,"TCP","host.com",8888,0,0    // 打开Socket
// 返回: +QIOPEN: 0,0
AT+QISEND=0,5                              // 发送 5 字节
> HELLO
// 返回: SEND OK

// UDP 无连接发送
AT+QISEND=0,5,"udp://host.com:8888"
> HELLO
```

### MQTT over LTE

现代 4G 模块内建 MQTT 协议支持（无需额外 MQTT 客户端）：

```c
// SIM7600 MQTT 示例
AT+CMQTTSTART?              // 确认 MQTT 客户端状态
AT+CMQTTACCQ=0,"client_id"  // 分配 MQTT 客户端
AT+CMQTTCONNECT=0,"tcp://mqtt.host.com:1883",60,1
AT+CMQTTTOPIC=0,5           // 设置主题
> topic
AT+CMQTTPAYLOAD=0,10        // 设置消息体
> 0123456789
AT+CMQTTPUB=0,0,0           // 发布消息
AT+CMQTTSUB=0,5             // 订阅主题
> topic
```

### PSM/eDRX 低功耗模式

```c
// NB-IoT PSM 模式配置
AT+CPSMS=1,,,"00100100","00100010"  // TAU=180s, Active=36s
// T3324: Active Timer (PSM 活动时间)
// T3412: TAU Timer (周期性位置更新)

// eDRX 配置
AT+CEDRXS=1,5,"1001"  // eDRX 周期 = 20.48s
```

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 模块无响应 | 串口波特率不匹配或模块未启动 | 检查 UART 电平，模块冷启动需 5-10s |
| SIM 卡错误 | 卡未插好或 PIN 锁 | 检查物理连接，`AT+CPIN?` 确认状态 |
| 网络注册失败 | 信号弱或无归属网络 | 检查 CSQ，确认 APN 和频段 |
| TCP 连接失败 | 域名解析/DNS 问题 | 用 IP 直连测试，确认 DNS 配置 |
| 频繁离线 | 信号不稳定或 PSM 周期太短 | 增大 TAU/Active Timer，检查 CSQ |
| 功耗过高 | 未进入 PSM/C-DRX 模式 | 检测数据上报间隔，配置 PSM/eDRX |
| NB-IoT 数据延迟 | 非实时在线 | NB-IoT 设计为秒级延迟，可接受 |

## NB-IoT 入网与数据传输时序

```
模块上电 → 搜网(1-3s) → 附着(2-5s) → 入网 → 数据发送(0.5s) → PSM(断电)
                                                    ↓
                                              eDRX 窗口监听
                                              └─ 有下行？→ 接收 → PSM
                                              └─ 无下行？→ PSM
```

## 平台差异

| 方案 | 控制方式 | 协议栈位置 | 典型模块 |
|------|---------|-----------|---------|
| STM32+4G模块 | AT 指令(串口) | 模块端 | SIM7600/EC20 |
| STM32+NB-IoT | AT 指令(串口) | 模块端 | BC95/BC26/M5311 |
| ESP32+4G | AT 指令+ESP-MQTT | 模块端(透传) | SIM7000 |
| 4G DTU | 串口透传 | DTU 端 | 工业 DTU |
| Linux+4G | PPP/RNDIS 拨号 | 系统端 | EC20/Quectel |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| AT 超时无响应 | 模块未开机或波特率错 | 冷启动后等待 5-10s 重试 |
| +CME ERROR | 命令参数错误 | 检查命令格式，参考模块 AT 手册 |
| TCP 断开 | 网络异常/保活超时 | 启用心跳(Keep-Alive)，自动重连 |
| PSM 不生效 | 运营商不支持或配置错误 | 确认基站支持 PSM，检查定时器参数 |
| 发送失败(无网络) | 信号丢失 | 缓存数据，CSQ>=10 时重发 |

## 边界定义

### 不该激活
- 用户需要的是短距离无线通信（WiFi/BLE/LoRa）→ 使用对应 skill
- 用户只需要局域网 TCP/IP 通信（已有以太网/WiFi）→ 使用 `mqtt-module` 或 TCP socket
- 用户没有 SIM 卡或蜂窝模块硬件

### 不该做
- **禁止**在模块未注册网络时发送数据
- **禁止**在无 CSQ 检查时持续重连（浪费功耗）
- **禁止**在 PSM 模式下期望实时下行可达
- **禁止**忽略运营商频段配置（国内移动/联通/电信频段不同）
- **禁止**频繁 TAU 更新（增加网络信令负载和功耗）

### 不该碰
- **不触碰** SIM 卡 PIN 码管理（物理安全由用户负责）
- **不触碰**运营商资费套餐和流量计费
- **不触碰**基站侧配置（移动/联通/电信网络参数）

## 交接关系

- 上游：`uart-module`（AT 命令模块底层串口通信）
- 上层：`mqtt-module`（蜂窝网络上的 MQTT 应用协议）
- 对比：`wifi-module`（蜂窝 vs WiFi 方案选型对比）
- 对比：`lora-module`（NB-IoT vs LoRa 对比）
- 参考：`chip-architecture`（蜂窝芯片/模块选型）
