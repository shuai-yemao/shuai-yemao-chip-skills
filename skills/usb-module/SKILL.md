---
name: usb-module
version: "1.0.0"
description: "STM32 USB 配置、开发与故障排查。涵盖 USB 架构（Device/OTG/HS）、时钟配置（48MHz）、CDC 虚拟串口、HID 设备、MSC 大容量存储、USB 主机模式、OTG ID/VBUS 管理、DMA 与双缓冲、常见问题调试。当用户提到 USB、USB CDC、USB 虚拟串口、USB HID、USB MSC、USB OTG、USB 主机、USB 复合设备、USB 时钟、USB DP DM、USB 枚举失败、USB 无法识别、USB 描述符、USB 端点配置、USB DMA、STM32 USB、USB HS、ULPI、USB 调试时使用。"
---

# USB 模块开发指南

> 描述符参考见 `references/usb-descriptor-guide.md`（设备/配置/HID/CDC/MSC 描述符模板）

## USB 架构概览

### 各系列 USB 外设

| 系列 | USB 外设 | 模式 | 最大端点 | 特点 |
|------|---------|------|---------|------|
| F1 (F103) | USB_OTG_FS | Device Only | 8 | 无内置 D+ 上拉，需软件控制 |
| F1 互联型 | USB_OTG_FS/HS | OTG | 8 FS / 9 HS | 有 HS (需 ULPI) |
| F4 (F407) | USB_OTG_FS/HS | OTG | 4 IN + 4 OUT | FS 带内置 PHY，HS 需 ULPI |
| F4 (F411) | USB_OTG_FS | OTG | 4 IN + 4 OUT | 仅 FS，无 HS |
| H7 | USB_OTG_FS/HS | OTG | 8 | FS 内置 PHY，HS ULPI |
| G4 | USB_OTG_FS/PD | Device/DRD | 8 | 支持 UCPD(USB-C PD) |

### USB 模式对比

| 模式 | HAL 前缀 | 描述 | 典型应用 |
|------|---------|------|---------|
| Device | `HAL_PCD_*` | 作为从设备连到主机 | CDC虚拟串口、HID设备 |
| Host | `HAL_HCD_*` | 作为主机连接外设 | 读U盘、接USB键盘 |
| OTG | `HAL_OTG_*` | 可在Host/Device间切换 | 双角色设备 |

## USB 时钟配置

### 关键约束：48MHz

```c
// USB 外设需要精确的 48MHz 时钟
// 偏差必须 < 0.25%（USB 2.0 FullSpeed 要求）

// F4 时钟方案：
// HSE (8MHz) → PLL → 48MHz 输出到 USB
// 或用 HSI48 (F411: 内部专用 48MHz RC 振荡器)

// F411 使用 HSI48（推荐）：
void usb_clock_init(void)
{
    // 使能 HSI48
    RCC->CR2 |= RCC_CR2_HSI48ON;
    while (!(RCC->CR2 & RCC_CR2_HSI48RDY));

    // 选择 HSI48 为 USB 时钟
    RCC->DCKCFGR2 |= RCC_DCKCFGR2_CK48MSEL;  // HSI48 selected

    // 使能 USB 时钟
    __HAL_RCC_USB_OTG_FS_CLK_ENABLE();
}

// F4 通用：用 PLL 输出 48MHz
// 需保证 PLLQ 输出 = 48MHz
// 例如 HSE=8MHz, N=336, M=8, P=2, Q=7 → PLLQ=48MHz
// HAL_RCC_OscConfig 中设置 PLLQ = 7
```

### 常见时钟问题

```
症状：USB 枚举失败（Windows 显示 "Unknown Device"）
根因：时钟偏差 > 0.25%

排查：
1. 测量 DP/DM 信号上的帧起始包 (SOF) 周期：应为 1ms
2. 如果偏差大，检查 HSE 是否稳定
3. F411 用 HSI48 时检查 HSI48 校准值
4. 确认 RCC_CFGR 的 OTGFSSEL 位已正确设置
```

## USB Device 应用

### CDC (Virtual COM Port) — 最常用

```c
// CubeMX 配置：
// USB_OTG_FS → Mode: Device_Only
// Middleware → USB_DEVICE → Class: Communication Device Class (CDC)

// 初始化顺序：
MX_USB_OTG_FS_PCD_Init();
MX_USB_DEVICE_Init();

// 发送数据（在任意位置调用）：
uint8_t data[] = "Hello USB!\r\n";
CDC_Transmit_FS(data, sizeof(data));  // 非阻塞，中断发送

// 接收数据回调（usbd_cdc_if.c）：
static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len)
{
    // Buf = 接收到的数据
    // Len = 数据长度
    USBD_CDC_SetRxBuffer(&hUsbDeviceFS, Buf);
    USBD_CDC_ReceivePacket(&hUsbDeviceFS);  // 准备下一次接收
    return USBD_OK;
}

// 重要：CDC_Transmit_FS 的缓冲区生命周期
// 发送完成前不可修改发送缓冲区的数据
// 使用双缓冲或等待 CDC_TransmitCplt_FS 回调
```

### HID (Human Interface Device)

```c
// CubeMX 配置：Class → Human Interface Device (HID)

// 自定义 HID 报告描述符（usbd_hid.c 中修改）：
// 默认是键盘描述符，可改为自定义报告

// 发送报告（最大长度由描述符定义）：
uint8_t report[64];
HID_ReportDesc_FS[0] = 0x06, 0x00, 0xFF;  // Usage Page (Vendor)
// ... 自定义描述符
USBD_HID_SendReport(&hUsbDeviceFS, report, sizeof(report));

// 接收报告（中断端点 OUT）：
// 在 USBD_HID_EP0_RxReady / USBD_HID_DataOut 中处理
```

### MSC (Mass Storage Class) — U盘模拟

```c
// CubeMX 配置：Class → Mass Storage Class (MSC)

// 需要实现存储介质读写：
// usbd_storage_if.c 中的 6 个接口：
int8_t STORAGE_Read_FS(uint8_t lun, uint8_t *buf, uint32_t blk_addr, uint16_t blk_len);
int8_t STORAGE_Write_FS(uint8_t lun, uint8_t *buf, uint32_t blk_addr, uint16_t blk_len);
int8_t STORAGE_GetMaxLun_FS(void);
// ... 等

// 典型实现：将片上 Flash 或外部 SPI Flash 模拟为 U 盘
// 需管理 512 字节扇区映射
// 注意：PC 访问时会频繁读写，Flash 磨损需注意
```

### 复合设备 (Composite)

```c
// 单个 USB 设备同时实现 CDC + MSC 或 CDC + HID
// CubeMX → USB_DEVICE → Class: Communication Device Class + ... 
// 需要自定义描述符管理多个 Interface

// 注意：
// 1. 每个 Interface 独立端点
// 2. 端点号不能冲突
// 3. 描述符中 Interface Association Descriptor (IAD) 用于绑定
```

## USB Host 应用

```c
// CubeMX 配置：USB_OTG_FS → Mode: Host_Only 或 OTG
// Middleware → USB_HOST → Class: Mass Storage Host / HID Host

// 主机模式初始化：
MX_USB_OTG_FS_HCD_Init();
MX_USB_HOST_Init();

// 外设连接回调（usb_host.c）：
void USBH_UserProcess(USBH_HandleTypeDef *phost, uint8_t id)
{
    switch(id) {
        case HOST_USER_CONNECTION:
            // 设备连接
            break;
        case HOST_USER_DISCONNECTION:
            // 设备断开
            break;
        case HOST_USER_CLASS_ACTIVE:
            // 类驱动就绪，可以开始通信
            break;
    }
}
```

## 端点 (Endpoint) 配置

```c
// USB 端点 = 主机和设备之间的通信管道
// 每个端点有：方向 (IN/OUT)、类型 (Control/Bulk/Isochronous/Interrupt)、最大包大小

// F4 OTG FS 端点分配：
// EP0: 双向控制端点 (64 字节)
// EP1_IN: 设备发往主机 (CDC 数据 IN)
// EP1_OUT: 主机发往设备 (CDC 数据 OUT)
// EP2_IN: 设备发往主机 (CDC 通知 IN)

// 最大包大小约束：
// FS (Full Speed): 控制=64, 批量=64, 中断=64, 同步=1023
// HS (High Speed): 控制=64, 批量=512, 中断=1024, 同步=1024

// 缓冲区分配（USB SRAM，不是系统 SRAM）：
// F4 OTG: 1.25KB 专用 USB SRAM，按端点分配
// 分配在 usbd_conf.c 中：
// #define USBD_RX_BUFF_SIZE    512  // 接收缓冲（所有端点共享）
// #define USBD_TX_BUFF_SIZE    512  // 发送缓冲（所有端点共享）
```

## USB DMA 与双缓冲

```c
// F4/H7 OTG 支持 DMA 模式（不是外设 DMA，是 USB 内部的 DMA 引擎）

// CubeMX 配置：USB_OTG_FS → DMA Settings → Add
// 或寄存器级使能：
USB_OTG_FS->GAHBCFG |= USB_OTG_GAHBCFG_DMAEN;

// DMA 模式要求：
// 1. 缓冲区地址必须 4 字节对齐
// 2. 缓冲区必须在 SRAM 中
// 3. 传输大小必须是 4 的倍数

// 双缓冲（IN 端点，提高吞吐）：
// 使用 USB_OTG_DIEPDMA 和 USB_OTG_DIEPDMA 的 MPS 设置
// 当端点使能了两倍包缓冲，DMA 可以在用户处理一个包时接收下一个
```

## 常见陷阱

| 编号 | 现象 | 根因 | 解决 |
|------|------|------|------|
| 1 | 枚举失败 "Unknown Device" | USB 时钟 ≠ 48MHz | 检查 HSI48/PLLQ 配置 |
| 2 | D+ 一直低电平（无上拉） | F1 需软件控制 DP 上拉 | F1: `GPIO_SetPullUp(DP_PIN, ENABLE)` |
| 3 | CDC 发送卡死/不完成 | 发送缓冲正在使用中 | 用发送完成回调做同步 |
| 4 | USB 插入时 HardFault | USB 中断优先级高于临界区 | 降低 USB 中断优先级 |
| 5 | 接收数据错位 | DMA 模式下缓冲区未 4 字节对齐 | `ALIGN_4` 声明缓冲区 |
| 6 | Windows 描述符请求失败 | 描述符长度声明与实际不符 | 核对报告描述符长度 |
| 7 | OTG 角色切换失败 | ID 引脚中断未配置 | 使能 ID 引脚 EXTI 中断 |
| 8 | 主机枚举 USB 设备失败 | VBUS 未使能 | `HAL_HCD_Start()` 中使能 VBUS |
| 9 | 复合设备只识别一个接口 | 缺少 Interface Association Descriptor | 添加 IAD 到描述符 |

## USB 调试技巧

```c
// 1. 查看 USB 寄存器状态
// 查询 OTG_FS_GINTSTS（全局中断状态）和 OTG_FS_GINTMSK
// 查询 OTG_FS_DIEPINTx / OTG_FS_DOEPINTx（端点中断）

// JLink Commander:
//   mem32 0x50000000 16    // USB_OTG_FS 全局寄存器 (F4)
//   mem32 0x50000E00 16    // DIEPCTL0~DIEPCTL3 (F4)

// 2. 常见调试方法
// - USB 协议分析仪（最准确）
// - Windows USBView 查看描述符
// - Logic analyzer 抓 DP/DM 信号
// - 软件 HID 报告 + 上位机读取验证

// 3. STM32CubeMonitor-USB
// ST 官方 USB 监控工具，可看枚举过程和端点通信
```

## 系列差异速查

| 特性 | F1 | F4 | G4 | H7 |
|------|-----|-----|-----|-----|
| USB PHY | 内置 (FS) | 内置 (FS) / 外置ULPI(HS) | 内置 (FS) | 内置 (FS) / ULPI(HS) |
| D+ 上拉 | 软件控制 | 硬件自动 | 硬件自动 | 硬件自动 |
| VBUS 检测 | 无(Device only) | PA9 (VBUS) | PA9/PA10 | PA9/PA10 |
| USB SRAM | 1KB | 1.25KB | 1KB | 4KB |
| DMA 模式 | 无 | 有 | 有 | 有 |
| LPM | 无 | 有 | 有 | 有 |
| BC 1.2 | 无 | 无 | 有 | 有 |
| UCPD | 无 | 无 | 有 | 无 |

## 边界定义

## 平台差异

详见 `chip-architecture`（MCU 芯片架构与开发方式对比）。

| 平台 | USB 外设 | CDC 实现 | 时钟要求 |
|------|---------|---------|---------|
| STM32F1 | USB Device FS | 自定义 CDC | 48MHz(从 PLL 分频) |
| STM32F4 | OTG FS/HS | `USB_DEVICE/App/usbd_cdc_if.c` | PLL48CK 或外部晶振 |
| STM32H7 | OTG HS + ULPI | 同 F4 | PLL3Q 48MHz |
| ESP32 | USB Serial/JTAG | `tinyusb_cdcacm_register` | 内建 |
| ESP32-S2/S3 | USB OTG | `tinyusb_cdcacm_register` | 内建 |

- **不覆盖 USB HS (ULPI)** — 外置 PHY 配置取决于具体芯片
- **不覆盖 USB 电源管理**（BC 1.2、UCPD 充电协议）— G4 专属，复杂度高
- **不覆盖 USB 音频类 (UAC)** — 专用领域
- **不覆盖 USB 视频类 (UVC)** — 专用领域
- 与 `peripheral-driver` 配合：通过 USB CDC 连接的外设传感器由 `peripheral-driver` 适配
