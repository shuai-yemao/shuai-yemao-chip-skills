---
name: lvgl-module
description: |
  LVGL(Light and Versatile Graphics Library) 轻量级嵌入式 GUI 开发指南。
  覆盖 LVGL 架构（对象树/显示驱动/输入设备/动画）、
  移植到 STM32(SPI LCD/FSMC/RGB) 和 ESP32(SPI LCD)、
  控件库（按钮/标签/列表/图表/滑块/键盘）、
  样式系统、动画引擎、中文字体处理、内存优化、
  与 SquareLine Studio 结合的可视化设计。
  当用户提到 LVGL、GUI、嵌入式图形、触摸屏、LCD 显示、
  LittlevGL、ST7789、ILI9341、FT5x06、TouchGFX 对比、
  SquareLine Studio、UI 设计、嵌入式 HMI、人机界面 时使用。
version: "1.0.0"
---

# LVGL 嵌入式 GUI 开发指南

## 适用场景

- 需要为嵌入式设备添加图形用户界面（LCD 显示屏+触摸）
- 需要将 LVGL 移植到 STM32 或 ESP32 平台
- 需要使用 LVGL 控件库构建仪表盘/菜单/设置界面
- 需要优化 LVGL 内存占用和渲染性能
- 需要与 SquareLine Studio 配合进行 UI 可视化设计

## 必要输入

| 参数 | 说明 |
|------|------|
| MCU 平台 | STM32 / ESP32 / 其他 |
| 显示接口 | SPI / 8/16 位并口 / RGB / MIPI DSI |
| 分辨率 | 320x240 / 480x320 / 800x480 |
| 色彩深度 | 16bit(RGB565) / 32bit(ARGB8888) |
| 触摸 | 电阻/电容(FT5x06/GT911) / 无 |
| 帧缓冲 | 单缓冲 / 双缓冲 / DMA2D |
| 字体 | 拉丁文 / 中文(UTF-8) / 其他 |

## LVGL 架构

```
App (应用层)
  │
  ├── Widgets (控件): btn/label/roller/dropdown/chart/...
  ├── Layout (布局): Flex / Grid
  ├── Styles (样式): 颜色/圆角/边框/阴影/透明度
  ├── Animations (动画): 缓动/关键帧/自动
  ├── Events (事件): 点击/滑动/长按/值变更
  └── Objects (对象树): 父-子层级管理
        │
Display Driver (显示驱动)     Input Device (输入设备)
  └─ flush_cb()               └─ read_cb()
```

### 对象树示例

```c
lv_obj_t *scr = lv_scr_act();                       // 活动屏幕
lv_obj_t *btn = lv_btn_create(scr);                  // 按钮(子)
lv_obj_t *lbl = lv_label_create(btn);                // 标签(按钮的子)
lv_label_set_text(lbl, "Click Me");
lv_obj_center(btn);                                  // 居中
```

## 移植指南

### STM32 + SPI LCD (ILI9341 + 1 帧缓冲)

```c
// 1. 定义显示缓冲区
#define LVGL_BUF_SIZE  (320 * 240 / 10)  // 7680 字节
static lv_disp_draw_buf_t disp_buf;
static lv_color_t buf[LVGL_BUF_SIZE];

// 2. 显示刷新回调（SPI DMA 发送像素数据）
void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p)
{
    ili9341_set_window(area->x1, area->y1, area->x2, area->y2);
    ili9341_send_pixels((uint16_t *)color_p,
        (area->x2 - area->x1 + 1) * (area->y2 - area->y1 + 1));

    lv_disp_flush_ready(disp);  // 通知 LVGL 刷新完成
}

// 3. 触摸读取回调
void my_touch_read(lv_indev_drv_t *indev, lv_indev_data_t *data)
{
    ft5x06_get_xy(&data->point.x, &data->point.y);
    data->state = (touch_pressed) ? LV_INDEV_STATE_PR : LV_INDEV_STATE_REL;
}

// 4. 初始化 LVGL
void lvgl_init(void)
{
    lv_init();

    lv_disp_draw_buf_init(&disp_buf, buf, NULL, LVGL_BUF_SIZE);

    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.hor_res = 320;
    disp_drv.ver_res = 240;
    lv_disp_drv_register(&disp_drv);

    static lv_indev_drv_t indev_drv;
    lv_indev_drv_init(&indev_drv);
    indev_drv.type = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touch_read;
    lv_indev_drv_register(&indev_drv);
}

// 5. 主循环（5ms 调用一次）
void main_loop(void)
{
    lv_tick_inc(5);        // LVGL 心跳
    HAL_Delay(5);
    lv_timer_handler();    // LVGL 任务处理
}
```

### ESP32 + SPI LCD (IDF 例程)

```c
// ESP32-S3 + ST7789 240x240 SPI LCD
#include "lvgl.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_st7789.h"

void app_main(void)
{
    // 1. 初始化 SPI LCD
    esp_lcd_panel_io_handle_t io_handle;
    esp_lcd_panel_handle_t panel_handle;
    // ... SPI 配置代码 ...

    // 2. 挂载 LVGL    
    lv_init();
    lv_disp_draw_buf_init(&disp_buf, buf1, buf2, LVGL_BUF_SIZE);

    // 3. 配置显示驱动（使用 ESP LCD 面板库）
    lv_disp_drv_init(&disp_drv);
    disp_drv.flush_cb = lcd_flush_cb;  // 调用 panel_draw_bitmap
    disp_drv.hor_res = 240;
    disp_drv.ver_res = 240;
    lv_disp_drv_register(&disp_drv);

    // 4. LVGL 任务
    while (1) {
        lv_timer_handler();
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
```

## 内存优化策略

| MCU | RAM | 缓冲策略 | 最大分辨率 | 帧率 |
|-----|-----|---------|-----------|------|
| STM32F103C8 | 20KB | 单缓冲 1/10 行 | 320x240 | ~20fps |
| STM32F411CE | 128KB | 单缓冲 1/4 行 | 480x320 | ~30fps |
| STM32H743 | 1MB | 双缓冲 + DMA2D | 800x480 | ~60fps |
| ESP32 | 520KB | 双缓冲(SPIRAM) | 800x480 | ~30fps |
| ESP32-S3 | 512KB | 双缓冲(PSRAM) | 800x480 | ~40fps |

**优化技巧**：
- 减小 `LV_MEM_SIZE`（LVGL 堆，默认 32KB → 可降至 8KB）
- 用 `LV_COLOR_DEPTH=16`（RGB565）+ `LV_COLOR_16_SWAP`（SPI 兼容）
- 中文字体仅包含用到的字符，不用全字库
- 图片用 LVGL 图像转换器压缩（BMP→C Array，可选压缩）

## 中文支持

```c
// LVGL 配置文件 lv_conf.h 中启用 UTF-8 中文
#define LV_TXT_ENC LV_TXT_ENC_UTF8

// 字体声明（使用 LVGL 字体转换工具）
LV_FONT_DECLARE(chinese_16);   // 中文字体（仅含常用字）

lv_obj_t *label = lv_label_create(scr);
lv_obj_set_style_text_font(label, &chinese_16, 0);
lv_label_set_text(label, "你好，世界！");
```

**字体大小估算**：
- 全量 GB2312 (6763 字) 16px: ~350KB Flash
- 常用 300 字 16px: ~25KB Flash
- 仅数字和字母 16px: ~3KB Flash

## 常见问题调试

| 现象 | 根因 | 解决 |
|------|------|------|
| 黑屏/无显示 | SPI 初始化错误或引脚不对 | 检查 SPI 接线，LCD 复位时序 |
| 花屏 | 色彩深度不匹配或字节序错 | 确认 `LV_COLOR_DEPTH` 与 LCD 匹配 |
| 触摸无反应 | I2C/SPI 触摸驱动未正确初始化 | 检查触摸中断引脚，I2C 地址 |
| 界面卡顿 | 帧缓冲太小或 CPU 不够 | 增大缓冲，启用 DMA2D(STM32) |
| 内存不足 | lv_mem_alloc 失败 | 增大 `LV_MEM_SIZE`，减少控件数 |
| 中文显示口 | 未加载中文字体 | 启用并链接中文字体文件 |

## 平台差异

| 平台 | 显示接口 | 帧缓冲 | 加速特性 |
|------|---------|--------|---------|
| STM32F1 | SPI / FSMC | 单缓冲 | 无硬件加速 |
| STM32F4 | SPI / FSMC | 单缓冲 | DMA2D(图像拷贝+填充) |
| STM32H7 | SPI / RGB / MIPI | 双缓冲 | DMA2D + LTDC + JPEG |
| ESP32 | SPI | 双缓冲(PSRAM) | SPIRAM 大缓冲 |
| ESP32-S3 | SPI/RGB(LCD_CAM) | 双缓冲 | 内建 JPEG/GPU 加速 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| lv_init 后死机 | `LV_MEM_SIZE` 分配超出 RAM | 检查 RAM 大小，减小 `LV_MEM_SIZE` |
| 控件不显示 | 未 attach 到对象树 | 创建时指定父对象(scr 或 container) |
| 刷新闪烁 | 单缓冲 + 全屏刷新 | 切换到双缓冲 或 用 DMA2D |
| SPI 传输慢(<5fps) | SPI 时钟太低 | 提高 SPI 时钟至 40-80MHz |

## 边界定义

### 不该激活
- 用户需要的是工业 HMI 组态屏（昆仑通态/威纶通）→ 使用厂家组态软件
- 用户需要的是 PC 端 GUI（Qt/C#/Web）→ 非嵌入式范围
- 用户需要 TouchGFX/emWin 等其他嵌入式 GUI 库的用法
- 用户只需要 LED/数码管显示（不需要图形界面）

### 不该做
- **禁止**在 LVGL timer handler 中做阻塞式操作（如 HAL_Delay(100)）
- **禁止**直接在 LVGL 回调中操作硬件外设
- **禁止**在主循环中频繁创建/删除控件（产生内存碎片）

### 不该碰
- **不触碰** LVGL 内部对象管理（lv_mem_alloc 由库自己管理）
- **不触碰** SquareLine Studio 生成的 UI 代码（不改生成文件，通过事件扩展）
- **不触碰** LCD 驱动 IC 的寄存器配置（由 LCM 初始化代码管理）

## 交接关系

- 下游：`timer-module`（LVGL 定时器心跳 lv_tick_inc）
- 下游：`spi-bus`（SPI LCD 驱动底层通信）
- 下游：`dma-module`（SPI DMA 传输像素数据）
- 下游：`peripheral-driver`（触摸芯片驱动 FT5x06/GT911）
- 参考：`chip-architecture`（MCU 选型：是否有 DMA2D/LTDC）
