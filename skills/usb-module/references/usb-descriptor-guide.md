# USB 描述符配置指南

## 描述符层次结构

```
Device Descriptor
  └─ Configuration Descriptor
       ├─ Interface Descriptor (0)  — CDC Control
       │    ├─ Header Functional Descriptor
       │    ├─ ACM Functional Descriptor
       │    └─ Union Functional Descriptor
       ├─ Interface Descriptor (1)  — CDC Data
       │    └─ Endpoint Descriptor (EP1_IN, Bulk)
       │    └─ Endpoint Descriptor (EP1_OUT, Bulk)
       └─ Interface Descriptor (2)  — HID
            ├─ HID Descriptor
            └─ Endpoint Descriptor (EP2_IN, Interrupt)
```

## 设备描述符

```c
// usbd_desc.c — 修改 VID/PID/序列号
#define USBD_VID                      0x0483  // ST 官方 VID
#define USBD_PID                      0x5740  // 自定义 PID
#define USBD_LANGID_STRING            0x409   // English (US)
#define USBD_SERIAL_NUMBER_STRING      "123456789ABCDEF"

// 字符串描述符（最多 64 字节）：
// USBD_MANUFACTURER_STRING
// USBD_PRODUCT_STRING
// USBD_CONFIGURATION_STRING
// USBD_INTERFACE_STRING
```

## 报告描述符（HID）

### 键盘描述符（默认）

```c
// 标准键盘：
0x05, 0x01,       // Usage Page (Generic Desktop)
0x09, 0x06,       // Usage (Keyboard)
0xA1, 0x01,       // Collection (Application)
0x05, 0x07,       //   Usage Page (Key Codes)
0x19, 0xE0,       //   Usage Minimum (224)
0x29, 0xE7,       //   Usage Maximum (231)
0x15, 0x00,       //   Logical Minimum (0)
0x25, 0x01,       //   Logical Maximum (1)
0x75, 0x01,       //   Report Size (1)
0x95, 0x08,       //   Report Count (8)
0x81, 0x02,       //   Input (Data,Var,Abs)
// ... modifiers, OEM keys
0xC0              // End Collection
```

### 自定义 HID 发送/接收

```c
// 自定义 64 字节报告：
0x06, 0x00, 0xFF,    // Usage Page (Vendor Defined 0xFF00)
0x09, 0x01,          // Usage (Vendor Usage 1)
0xA1, 0x01,          // Collection (Application)
0x15, 0x00,          //   Logical Min (0)
0x25, 0xFF,          //   Logical Max (255)
0x75, 0x08,          //   Report Size (8 bits)
0x95, 0x40,          //   Report Count (64 bytes)
0x09, 0x01,          //   Usage (Vendor Usage 1)
0x81, 0x02,          //   Input (Data,Var,Abs)
0x09, 0x01,          //   Usage (Vendor Usage 1)
0x91, 0x02,          //   Output (Data,Var,Abs)
0xC0                 // End Collection
// 总长度 = 18 字节
```

### 鼠标描述符

```c
0x05, 0x01,       // Usage Page (Generic Desktop)
0x09, 0x02,       // Usage (Mouse)
0xA1, 0x01,       // Collection (Application)
0x09, 0x01,       //   Usage (Pointer)
0xA1, 0x00,       //   Collection (Physical)
0x05, 0x09,       //     Usage Page (Button)
0x19, 0x01,       //     Usage Min (1)
0x29, 0x03,       //     Usage Max (3)
0x15, 0x00,       //     Logical Min (0)
0x25, 0x01,       //     Logical Max (1)
0x95, 0x03,       //     Report Count (3)
0x75, 0x01,       //     Report Size (1)
0x81, 0x02,       //     Input (Data,Var,Abs)
0x95, 0x01,       //     Report Count (1)
0x75, 0x05,       //     Report Size (5)
0x81, 0x03,       //     Input (Const,Var,Abs)
0x05, 0x01,       //     Usage Page (Generic Desktop)
0x09, 0x30,       //     Usage (X)
0x09, 0x31,       //     Usage (Y)
0x16, 0x00, 0x80, //     Logical Min (-32767)
0x26, 0xFF, 0x7F, //     Logical Max (32767)
0x75, 0x10,       //     Report Size (16)
0x95, 0x02,       //     Report Count (2)
0x81, 0x06,       //     Input (Data,Var,Rel)
0xC0,             //   End Collection
0xC0              // End Collection
// 鼠标报告：7 字节（3button + 5padding + 2×16bit 坐标）
```

## 端点配置

### CDC 端点分配（典型）

| 端点 | 方向 | 类型 | 包大小 | 描述 |
|------|------|------|--------|------|
| EP0 | IN/OUT | Control | 64 | 控制端点 |
| EP1_IN | IN | Interrupt | 8 | CDC 通知（串口状态） |
| EP2_IN | IN | Bulk | 64 | CDC 数据发送 |
| EP2_OUT | OUT | Bulk | 64 | CDC 数据接收 |

### 复合设备端点分配

```c
// CDC + MSC 复合设备需要至少 4 个端点（不含 EP0）：
// EP1_IN Int CDC 通知
// EP2_IN Bulk CDC 数据
// EP2_OUT Bulk CDC 数据
// EP3_IN Bulk MSC 数据
// EP3_OUT Bulk MSC 数据

// F4 OTG FS 最多 4 IN + 4 OUT 端点
// F4 OTG HS 最多 6 IN + 6 OUT 端点
// 复合设备端点数量需仔细规划
```

## USB 标准请求

```c
// bmRequestType = (direction << 7) | (type << 5) | recipient
// direction:  0=Host→Dev, 1=Dev→Host
// type:       0=Standard, 1=Class, 2=Vendor
// recipient:  0=Device, 1=Interface, 2=Endpoint, 3=Other

// 标准设备请求（USB 2.0 第 9 章）：
#define GET_DESCRIPTOR       0x06
#define SET_ADDRESS          0x05
#define SET_CONFIGURATION    0x09
#define GET_CONFIGURATION    0x08
#define GET_INTERFACE        0x0A
#define SET_INTERFACE        0x0B
#define CLEAR_FEATURE        0x01
#define SET_FEATURE          0x03
```

## 常见 USB 错误码

| Windows 错误 | 描述 | 常见原因 |
|-------------|------|---------|
| Code 10 | 设备无法启动 | 描述符错误/电源不足 |
| Code 28 | 驱动未安装 | ST 虚拟串口驱动缺失 |
| Code 43 | 设备停止工作 | 枚举过程中出错/F4 VBUS 检测 |
| Code 43 + 未知USB设备 | 时钟频率偏差 > 0.25% | HSI48 未校准/PLLQ 输出非 48MHz |
| Linux dmesg: `Invalid EP 0x81` | 端点描述符中地址无效 | 端点地址 bit7 (IN方向) 设置错误 |
