---
name: mqtt-module
description: |
  MQTT 物联网通信协议开发指南。覆盖 MQTT 协议基础（发布/订阅/主题/QoS）、
  MQTT v3.1.1 vs v5.0 差异、会话管理与遗愿(Last Will)、
  ESP32 ESP-MQTT 开发、STM32 + MQTT 客户端移植（paho MQTT-C）、
  MQTT over TLS 安全连接、桥接与云平台对接（阿里云IoT/华为云/AWS IoT）。
  当用户提到 MQTT、物联网通信、发布订阅、消息队列、遥测传输、
  MQTT 客户端、paho MQTT、ESP-MQTT、阿里云 IoT、华为云 IoT、
  AWS IoT Core、MQTT 上云、QoS、保留消息、遗嘱消息 时使用。
version: "1.0.0"
---

# MQTT 物联网通信协议开发指南

## 适用场景

- 需要在嵌入式设备和云平台之间建立 MQTT 通信
- 需要选型 MQTT 客户端库（ESP-MQTT / paho MQTT-C / lwMQTT）
- 需要对接云平台（阿里云 IoT / 华为云 IoT / AWS IoT Core）
- 需要配置 MQTT 连接参数（QoS、KeepAlive、Clean Session）
- 需要 MQTT over TLS 安全连接
- 需要调试 MQTT 断连、丢消息、离线消息问题

## 必要输入

| 参数 | 说明 |
|------|------|
| MQTT Broker | 云平台 / 私有 Mosquitto / EMQX |
| 端口 | 1883(TCP) / 8883(TLS) / 443(WS) |
| 客户端 ID | 全局唯一标识 |
| 认证 | 用户名密码 / X.509 证书 / Token |
| 主题(Topic) | 发布/订阅的主题名，支持通配符(+/#) |

## MQTT 协议基础

### 协议架构

```
传感器节点 (Publisher)             云平台/AWS IoT (Broker)
  │                                      │
  │── PUBLISH topic/data QoS 1 ─────────>│
  │                                      │── PUBLISH to subscribers
  │<── PUBACK (QoS 1 确认) ─────────────│
  │                                      │
  │                                      │── PUBLISH topic/command QoS 0
  │<── (无确认，QoS 0 ) ─────────────────│
  │                                      │
控制面板 (Subscriber)
  │<── PUBLISH topic/data ──────────────│
```

### 连接报文结构

```
CONNECT (客户端 → 服务器)
├─ Protocol Name: "MQTT" / "MQIsdp"
├─ Protocol Level: 4(MQTT 3.1.1) / 5(MQTT 5.0)
├─ Connect Flags: Clean Session / Will / QoS / Retain / Password / Username
├─ Keep Alive: 60s (建议 30-120s)
├─ Client ID: "esp32_sensor_01"
├─ [Will Topic/Message]
├─ [Username]
├─ [Password]

CONNACK (服务器 → 客户端)
├─ Session Present: true/false
└─ Return Code: 0(接受) / 1-5(拒绝原因)
```

### MQTT v3.1.1 vs v5.0

| 特性 | v3.1.1 | v5.0 |
|------|--------|------|
| 会话过期 | 同 Clean Session | 可设置 Session Expiry Interval |
| 原因码 | 仅 CONNACK | 所有 ACK 带原因码 |
| 用户属性 | 无 | 自定义键值对 |
| 内容类型 | 无 | Content Type 指示 payload 格式 |
| 订阅选项 | 简单订阅 | 订阅标识符+选项 |

**建议**：大多数嵌入式场景用 v3.1.1 足够，v5.0 适合需要细粒度控制的高级场景。

## 平台开发

### ESP32 — ESP-MQTT（内建，推荐）

```c
#include "mqtt_client.h"

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                                int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;
    switch (event->event_id) {
        case MQTT_EVENT_CONNECTED:
            esp_mqtt_client_subscribe(client, "/sensor/temp", 1);
            break;
        case MQTT_EVENT_DATA:
            printf("TOPIC=%.*s, DATA=%.*s\n",
                   event->topic_len, event->topic,
                   event->data_len, event->data);
            break;
        case MQTT_EVENT_DISCONNECTED:
            // 自动重连（内建）
            break;
    }
}

void mqtt_app_start(void)
{
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = "mqtt://mqtt.eclipseprojects.io:1883",
        .credentials.client_id = "esp32_sensor_01",
        .session.keepalive = 60,
        .session.disable_clean_session = false,
    };
    esp_mqtt_client_handle_t client = esp_mqtt_client_init(&mqtt_cfg);
    esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event_handler, client);
    esp_mqtt_client_start(client);
}
```

### STM32 + paho MQTT-C（开源库移植）

```c
// 使用 paho.mqtt.c 的 MQTTClient 层
// 需要实现网络传输层（通过 lwIP 或 AT TCP 命令）

#include "MQTTClient.h"

// 网络传输接口
int network_read(MQTTClient *c, unsigned char *buf, int len, int timeout_ms) { /* TCP recv */ }
int network_write(MQTTClient *c, unsigned char *buf, int len, int timeout_ms) { /* TCP send */ }

void mqtt_task(void *arg)
{
    MQTTClient client;
    Network network;
    MQTTPacket_connectData data = MQTTPacket_connectData_initializer;

    NetworkInit(&network);
    // 通过 lwIP 建立 TCP 连接
    networkConnect(&network, "mqtt.host.com", 1883);
    MQTTClientInit(&client, &network, 3000, sendBuf, sizeof(sendBuf), recvBuf, sizeof(recvBuf));

    data.clientID.cstring = "stm32_sensor";
    data.keepAliveInterval = 60;
    MQTTConnect(&client, &data);

    // 订阅/发布
    MQTTSubscribe(&client, "sensor/temp", QOS1, messageArrived);
    MQTTPublish(&client, "sensor/temp", payload, &payload_len, QOS1, 0);
}
```

### QOS 行为对比

| QoS | 可靠性 | 开销 | 适用场景 |
|-----|--------|------|---------|
| 0 (最多一次) | 不确认 | 最低 | 传感器定期上报(可丢) |
| 1 (至少一次) | 需 ACK，可能重复 | 中 | 大多数传感器数据 |
| 2 (正好一次) | 四次握手，无重复 | 最高 | 计费/控制指令 |

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| CONNACK 返回拒绝 | 客户端 ID 冲突/认证失败 | 检查 Client ID 唯一性，核对用户名密码 |
| 频繁断连 | Keep Alive 太短/网络不稳定 | 增加到 60-120s，启用自动重连 |
| 收不到消息 | 主题不匹配/QoS 不兼容 | 检查通配符订阅，确认 Broker 持久会话 |
| 消息重复 | QoS=1 正常行为 | 应用层做幂等处理(UUID 去重) |
| 内存不足 | 消息缓冲区太大 | 减小 最大包大小，用 QoS 0 减少缓存 |
| TLS 连接失败 | 证书链验证不通过 | 检查 CA 证书，确认服务器域名匹配 |

## MQTT over TLS

```c
// ESP32 MQTT+TLS 配置
esp_mqtt_client_config_t mqtt_cfg = {
    .broker.address.uri = "mqtts://xxx.iot.aliyun.com:8883",
    .broker.verification.certificate = (const char *)root_ca_pem_start,
    .credentials.client_id = "client_id",
    .credentials.username = "device_name",
    .credentials.authentication.password = "device_secret",
};
```

## 平台差异

| 平台 | MQTT 库 | TLS | 特点 |
|------|---------|-----|------|
| ESP32 | ESP-MQTT(内建) | mbedTLS | 开箱即用，支持自动重连 |
| ESP32+AT | AT+MQTTCONNCFG | 模块侧 | 通过 UART AT 命令 |
| STM32+lwIP | paho MQTT-C | mbedTLS | 需移植网络层 |
| STM32+ESP8266 | 串口 AT | 透传 | 低成本 WiFi+MQTT |
| STM32+4G | 模块内建 | 模块侧 | AT 命令如 `AT+CMQTTCONNECT` |
| Linux | mosquitto / paho | OpenSSL | 功能最全 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| ESP-MQTT 连接失败 | Broker 地址不可达或 DNS 解析失败 | 检查网络连通性，用 IP 直连测试 |
| mbedTLS SSL 握手失败 | 证书错误或不匹配 | 核对 CA、设备证书、私钥 |
| 发布 QoS 1 不收到 PUBACK | Broker 端异常 | 检查 Broker 日志，降低 QoS 到 0 |
| 包超限 | 消息体 > 最大包限制 | 调整 `MQTT_MAX_PACKET_SIZE` |
| MQTT 任务栈溢出 | 回调处理太重 | 回调中仅取数据，处理放主循环 |

## 边界定义

### 不该激活
- 用户需要的是 TCP/UDP 裸数据传输（非 MQTT 协议）→ 使用 TCP socket
- 用户需要的是 HTTP REST API（非 MQTT 发布订阅）
- 用户需要搭建 MQTT Broker 服务器（Mosquitto/EMQX）→ 服务器端配置

### 不该做
- **禁止**在无 Keep Alive 且无遗嘱消息(Last Will)时连接（断线后 Broker 不知道）
- **禁止**使用 Client ID 不唯一（导致互踢）
- **禁止**在 QoS 1/2 中不处理重复消息（应用层应幂等）
- **禁止**在 TLS 连接中使用自签名证书不验证（中间人攻击风险）

### 不该碰
- **不触碰** MQTT Broker 的配置（Mosquitto/EMQX 服务器端）
- **不触碰**云平台 IoT 产品的创建和管理（阿里云/华为云/亚马逊后台）
- **不触碰** TLS 证书的 PKI 体系管理

## 交接关系

- 下层：`wifi-module`（MQTT over WiFi 典型方案）
- 下层：`cellular-module`（MQTT over 4G/NB-IoT 方案）
- 下层：`uart-module`（AT 命令 MQTT 模块底层）
- 互补：`ble-module`（BLE + MQTT 网关桥接）
- 参考：`chip-architecture`（MQTT 方案选型）
