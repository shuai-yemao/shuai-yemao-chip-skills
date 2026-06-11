---
name: gps-module
description: |
  GPS/GNSS 全球导航卫星系统开发指南。覆盖 GNSS 基础（GPS/北斗/GLONASS/Galileo）、
  NMEA-0183 协议解析、UBX 二进制协议、常见模块（NEO-6M/8M/9M/L76K/ATGM336H）、
  多星座融合定位、AGPS 辅助定位、低功耗策略。
  当用户提到 GPS、北斗、GNSS、定位模块、NEO-6M、NEO-8M、NEO-9N、
  L76K、ATGM336H、NMEA、经纬度、海拔、定位调试、室外定位 时使用。
version: "1.0.0"
---

# GPS/GNSS 定位开发指南

## 适用场景

- 需要为设备添加室外定位能力（经纬度/速度/海拔）
- 需要解析 NMEA-0183 协议格式的定位数据
- 需要选型 GNSS 模块（单GPS/多星座/RTK）
- 需要优化定位精度和首次定位时间(TTFF)
- 需要低功耗 GNSS 定位方案

## 必要输入

| 参数 | 说明 |
|------|------|
| GNSS 模块 | NEO-6M/8M/9N / L76K / ATGM336H / ZED-F9P |
| 星座需求 | GPS / 北斗 / GLONASS / Galileo (多星座精度更高) |
| 更新率 | 1Hz(标准) / 5Hz / 10Hz(高动态) |
| 精度要求 | 2-3m(标准) / <1m(RTK 差分) |
| 首次定位(TTFF) | 冷启动~30s / AGPS(辅助)<15s / 热启动<2s |

## NMEA-0183 协议解析

### 常用语句

| 语句 | 内容 | 示例 |
|------|------|------|
| $GPGGA | 定位数据(经纬度/海拔/卫星数) | `$GPGGA,092725.00,3110.45612,N,...` |
| $GPRMC | 推荐最小数据(速度/日期/磁偏角) | `$GPRMC,092725.00,A,3110.45612,N,...` |
| $GPGSA | 活跃卫星(PDOP/HDOP/VDOP精度因子) | `$GPGSA,A,3,01,02,03,04,05,06,...` |
| $GPGSV | 视野中卫星列表 | `$GPGSV,3,1,11,01,67,308,42,02,51,...` |
| $BDGGA | 北斗定位数据（北斗星座） | `$BDGGA,...` |

### GGA 语句解析示例

```
$GPGGA,092725.00,3110.45612,N,12123.45678,E,1,08,0.9,10.5,M,5.6,M,,*47
  │        │           ││           ││ │  │  │   │   │ │  │
  │        │           ││           ││ │  │  │   │   │ │  └─ 差分龄(秒)
  │        │           ││           ││ │  │  │   │   │ └─── 差分站ID
  │        │           ││           ││ │  │  │   │   └───── 椭球高(m)
  │        │           ││           ││ │  │  │   └───────── 海平面高(m)
  │        │           ││           ││ │  │  └─────────── 水平精度因子(HDOP)
  │        │           ││           ││ │  └───────────── 卫星数
  │        │           ││           ││ └──────────────── 定位模式(1=单点,2=差分,4=RTK固定)
  │        │           ││           │└────────────────── 经度(E/W)
  │        │           ││           └─────────────────── 经度值
  │        │           │└─────────────────────────────── 纬度(N/S)
  │        │           └──────────────────────────────── 纬度值
  │        └─────────────────────────────────────────── UTC 时间
  └─────────────────────────────────────────────────── 数据头
```

### 嵌入式 NMEA 解析器框架

```c
typedef struct {
    double  latitude;       // 纬度 (dddmm.mmmm → 十进制度)
    double  longitude;      // 经度
    float   altitude;       // 海拔 (m)
    float   speed_kmh;      // 速度 (km/h)
    float   heading;        // 航向 (度)
    int     satellites;     // 跟踪卫星数
    float   hdop;           // 水平精度因子
    int     fix_quality;    // 定位质量 (0=无效,1=单点,2=差分,4=RTK)
    uint8_t hour, min, sec; // UTC 时间
    uint8_t day, month;     // UTC 日期
    uint16_t year;
} gps_data_t;

// 逐字符解析（在 UART RX 中断或环形缓冲区中调用）
void gps_parse_char(gps_data_t *gps, char c)
{
    static char buffer[100];
    static uint8_t idx = 0;

    if (c == '$') { idx = 0; }       // 帧起始
    buffer[idx++] = c;
    if (c == '\n') {                  // 帧结束
        buffer[idx] = '\0';
        if (strstr(buffer, "$GPGGA"))
            parse_gpgga(gps, buffer);
        if (strstr(buffer, "$GPRMC"))
            parse_gprmc(gps, buffer);
        idx = 0;
    }
}
```

## 平台开发

### STM32 + GNSS 模块（UART 接收 NMEA）

```c
// 硬件配置: UART 9600 8N1
// 软件配置: 串口 DMA 环形缓冲区接收 NMEA 语句

// UART RX 回调（DMA+IDLE 变长接收）
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart->Instance == USART1) {
        // 缓冲区接收完一帧 NMEA 数据
        for (uint16_t i = 0; i < Size; i++) {
            gps_parse_char(&gps_data, rx_buffer[i]);
        }
        HAL_UARTEx_ReceiveToIdle_DMA(huart, rx_buffer, sizeof(rx_buffer));
    }
}

// 主循环读取定位结果
void main_loop(void)
{
    if (gps_data.fix_quality > 0) {
        printf("LAT: %.6f, LON: %.6f, ALT: %.1fm, SAT: %d\n",
               gps_data.latitude, gps_data.longitude,
               gps_data.altitude, gps_data.satellites);
    } else {
        printf("Waiting for GPS fix...\n");
    }
    HAL_Delay(1000);
}
```

### ESP32 + GNSS 模块

```c
// ESP-IDF: 使用 UART 驱动 + NMEA 解析器
#include "driver/uart.h"
#include "minmea.h"  // 轻量 NMEA 解析库

void gps_task(void *arg)
{
    uart_config_t uart_config = {
        .baud_rate = 9600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
    };
    uart_param_config(UART_NUM_1, &uart_config);
    uart_driver_install(UART_NUM_1, 1024, 0, 0, NULL, 0);

    uint8_t data[256];
    while (1) {
        int len = uart_read_bytes(UART_NUM_1, data, sizeof(data)-1, 20/portTICK_PERIOD_MS);
        if (len > 0) {
            data[len] = '\0';
            // 用 minmea 库解析
            const char *p = (const char *)data;
            while (*p) {
                if (*p == '$') {
                    // minmea 自动识别语句类型
                    minmea_sentence_rmmc rmc;
                    if (minmea_parse_rmmc(&rmc, p)) {
                        float lat = minmea_tocoord(&rmc.latitude);
                        float lon = minmea_tocoord(&rmc.longitude);
                        ESP_LOGI("GPS", "%.4f, %.4f", lat, lon);
                    }
                }
                p++;
            }
        }
    }
}
```

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 无定位(00) | 冷启动未完成/天线不匹配 | 室外首次需 30-60s 冷启动，检查天线 |
| 只有 2D 定位 | 卫星数不足(<4颗) | 等待或移至开阔地 |
| 定位漂移 | 多径效应/低 SNR | 开启多星座，在代码中加 HDoP 阈值过滤 |
| 首次定位慢 | 星历过期/无 AGPS | 启用 AGPS(辅助数据下载)，或备份星历 |
| NMEA 解析乱码 | 波特率不匹配 | 核对模块默认波特率(常见 9600/115200) |
| 掉电后定位慢 | 电池后备 RAM 无电 | 给 V_BCKP 供电(保持星历)，或存 Flash |

## 平台差异

| 方案 | 模块 | 接口 | 星座 | 精度 |
|------|------|------|------|------|
| STM32+UART | NEO-6M(M8N) | UART 9600 | GPS/GLONASS | 2.5m |
| STM32+UART | L76K | UART | GPS+北斗 | 2.0m |
| STM32+UART | ATGM336H | UART | GPS+北斗+GLONASS | 2.0m |
| STM32+UART | ZED-F9P | UART/USB | 多星座+RTK | 0.025m |
| ESP32+UART | NEO-8M/9N | UART | GPS+北斗 | 2.0m |
| ESP32+UART | L76K | UART+I2C | GPS+北斗 | 2.0m |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 无 NMEA 数据 | 模块与 MCU 通信异常 | 检查 UART RX 接线，确认波特率 9600 |
| $xxGGA 中 fix=0 | 未定位 | 室外空旷处等待，检查天线 |
| $xxGGA 中 fix=1 但坐标误差大 | 卫星数少或 HDoP 高 | 设置 `hdop < 2.0` 才认为有效定位 |
| TTFF 过长 (>60s) | 星历过期（超过4小时）| 需要 AGPS 或备份星历 |
| 频繁输出无效帧 | 电源纹波大或干扰 | 检查模块供电去耦 |
| 功耗过高 | 持续搜星模式 | 到达定位后切换到 1Hz 或 Standby |

## 边界定义

### 不该激活
- 用户需要的是室内定位（WiFi/BLE/IMU 融合定位）→ 不在本 skill 范围
- 用户只需要基站定位（无 GNSS 硬件）
- 用户需要的是高精度 RTK 基站架设（ZED-F9P 差分基准站）

### 不该做
- **禁止**在无定位有效标志(fix > 0)时使用经纬度数据
- **禁止**在没有足够卫星数(< 4颗)时算 3D 位置
- **禁止**在 HDoP > 2.5 时使用定位数据（漂移过大）

### 不该碰
- **不触碰** GNSS 模块的波特率配置（修改后可能无法恢复）
- **不触碰**天线设计（陶瓷天线/有源天线选型）
- **不触碰**坐标系统转换（WGS84 到 GCJ-02 需单独库）

## 交接关系

- 上游：`uart-module`（NMEA 数据 UART 接收，DMA+IDLE 变长）
- 互补：`cellular-module`（AGPS 辅助数据通过蜂窝网络下载）
- 互补：`lowpower-design`（GNSS 低功耗模式管理）
- 参考：`chip-architecture`（GNSS 模块选型）
