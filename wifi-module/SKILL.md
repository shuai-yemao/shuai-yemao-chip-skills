---
name: wifi-module
description: |
  WiFi 无线通信开发指南。覆盖 WiFi 协议基础（Station/AP/混杂模式）、
  ESP32 ESP-IDF WiFi 开发、STM32W/AT 命令 WiFi 模块、WiFi 配网方式、
  网络连接管理（TCP/UDP/TLS）、WiFi 低功耗策略。
  当用户提到 WiFi、无线网络、无线通信、ESP32 WiFi、ESP8266、
  AT 命令连 WiFi、WiFi 配网、SmartConfig、AirKiss、ESP-Now 时使用。
version: "1.0.0"
---

# WiFi 无线通信开发指南

## 适用场景

- 需要为嵌入式设备添加 WiFi 联网能力
- 需要选型 WiFi 方案（ESP32 SoC / AT 模块 / STM32W）
- 需要实现 WiFi 配网/重连/状态管理
- 需要调试 WiFi 断开、丢包、延迟问题
- 需要 TCP/UDP/TLS 网络通信

## 必要输入

| 参数 | 说明 |
|------|------|
| WiFi 方案 | SoC(ESP32) / AT模块(ESP8266/WizFi) / STM32W |
| 模式 | Station(STA) / AP / STA+AP |
| 网络 | SSID + 密码 + 安全类型(WPA2/WPA3/Open) |
| 传输 | TCP / UDP / TLS / HTTP 客户端或服务端 |

## WiFi 协议基础

### 工作模式

```
Station (STA)           ← 连接路由器，最常用
  └─ 扫描 → 认证 → 关联 → DHCP获取IP

AP (Soft-AP)            ← 自身做热点
  └─ 手机直连设备，用于配网阶段

STA + AP                ← 同时连接外网 + 提供热点
  └─ ESP32 典型配网模式
```

### 连接生命周期

```
Disconnected
  ↓ Wi-Fi scan / 保存的AP
Connecting
  ↓ Authentication / Association
  ↓ 4-way handshake (WPA2)
Got IP (DHCP)
  ↓
Connected
  ↓ Link loss / Beacon timeout
Disconnected (重连)
```

## 平台开发

### ESP32 — 最成熟的嵌入式 WiFi SoC

```c
// ESP-IDF WiFi Station 模式
void wifi_init_sta(void)
{
    esp_netif_init();
    esp_event_loop_create_default();
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    // 注册事件回调
    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &got_ip_handler, NULL);

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = CONFIG_ESP_WIFI_SSID,
            .password: "{REDACTED}",
        },
    };
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
    esp_wifi_start();
    esp_wifi_connect();
}
```

### AT 命令 WiFi 模块（ESP8266/WizFi/MW31）

| 命令 | 功能 |
|------|------|
| `AT+CWJAP="SSID","pwd"` | 连接 AP |
| `AT+CIFSR` | 查询 IP |
| `AT+CIPSTART="TCP","host",port` | 建立 TCP 连接 |
| `AT+CIPSEND=<len>` | 发送数据 |
| `AT+CIPCLOSE` | 关闭连接 |

**STM32 + AT 命令架构**：
- `uart-module` skill 覆盖 UART 底层
- 主控发送 AT 命令并解析响应
- 注意模块启动延迟（ESP8266 冷启动约 2-3 秒）

## WiFi 配网方式

| 方式 | 描述 | 适用 |
|------|------|------|
| SmartConfig | 手机 App 编码 SSID 到 WiFi 包 | ESP32 原生支持 |
| AirKiss | 微信的 SmartConfig 变体 | ESP8266/ESP32 |
| Soft-AP | 设备做热点，手机连上配置 | 通用 |
| BLE 配网 | 手机通过 BLE 发送 WiFi 凭据 | BLE+WiFi 共存 |
| HTTP 配网 | 设备做 AP，浏览器打开配置页 | 通用 |

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 连接失败 | SSID/密码错误，或信道不匹配 | 扫描确认 AP 存在，核对凭据 |
| 频繁断开 | Beacon timeout/信号弱 | 检查天线、供电；减小 DTIM |
| DHCP 超时 | 路由器 DHCP 池满 | 设置静态 IP 后备 |
| 吞吐量低 | TCP window 小/Payload 大 | 调整 TCP MSS，启用 Nagle |
| 功耗高 | WiFi 保持连接时电流大 | 用 Modem-sleep(ESP32 保持连接) |

## 平台差异

| 平台 | SDK | TCP/IP 栈 | 特色 |
|------|-----|-----------|------|
| ESP32 | ESP-IDF | lwIP 深度定制 | 最成熟，WiFi+BT共存 |
| ESP8266 | ESP8266 RTOS SDK | lwIP | 低成本，单核 |
| STM32W | STM32CubeWBA | 集成 | 双核(无线核) |
| STM32+AT | 串口 AT 指令 | 模块端 | 主控负担最小 |
| WizFi360 | AT 指令 | 模块端 | 工业级，-40~85C |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| WiFi 初始化失败 | 射频被占用/BT 冲突 | 检查 WiFi/BT 共存配置 |
| 连接超时 | AP 不可达/认证失败 | 检查信号强度、WPA 配置 |
| DNS 解析失败 | 路由器/DNS 服务器问题 | 配置静态 DNS 后备 |
| 内存不足 | lwIP 堆内存耗尽 | 增加 `LWIP_MEM_SIZE`、减小 TCP 连接数 |

## 边界定义

### 不该激活
- 用户需要的是 WiFi 配网 App（手机端）开发 → 非嵌入式范围
- 用户需要的是 WiFi 路由器固件开发（OpenWRT 等）→ Linux 内核级
- 用户只需要以太网有线连接 → 使用以太网 MAC + PHY 方案

### 不该做
- **禁止**在未配网时循环扫频（增加功耗和信道干扰）
- **禁止**在 TLS 中使用自签名证书不验证
- **禁止**在 AP 模式下暴露不安全的配置界面
- **禁止**连续快速重连（应加退避策略）

### 不该碰
- **不触碰**路由器/AP 的配置（仅配置设备端）
- **不触碰**射频 FCC/CE 认证测试
- **不触碰**网络防火墙和路由规则

## 交接关系

- 上游：`uart-module`（AT 命令模块底层通信）
- 互补：`mqtt-module`（WiFi + MQTT 云连接典型方案）
- 互补：`ble-module`（BLE+WiFi 共存/混合配网）
- 参考：`chip-architecture`（WiFi SoC 选型）
