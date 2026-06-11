---
name: gang-flash
description: 多路并行量产烧录工具。支持 OpenOCD 多 ST-Link、J-Link Multi-Emulator、esptool 多串口并行烧录，内建自动重试、读回校验、CSV/JSON 双格式报告、烧录计数统计。当用户提到量产烧录、批量烧录、gang flash、多板烧录、并行烧录、产线烧录、多路 ST-Link/J-Link 时使用。
version: "1.0.0"
---

# gang-flash

多路并行量产烧录工具。同时对多块目标板进行固件烧录，自动枚举已连接的调试探针和串口，
支持 OpenOCD 多 ST-Link、J-Link Multi-Emulator、esptool 多串口三种并行方案；
内建失败自动重试、烧录后读回校验、CSV/JSON 双格式报告、烧录次数统计。

## 触发条件
- "量产烧录"、"批量烧录"、"gang flash"、"多板烧录"、"并行烧录"
- "产线烧录"、"工厂烧录"、"同时烧录多块"
- "多路 ST-Link"、"J-Link 多路"、"多串口 ESP32"
- 用户连接了多个调试探针需要管理

## 参数收集
- firmware: 固件文件路径（所有目标板烧录同一固件）
- method: openocd / jlink / esptool
- targets: 目标设备列表（可选，不填则自动枚举）
- device: MCU 型号
- target_cfg: OpenOCD target 配置（如 target/stm32f4x.cfg）
- jlink_device: J-Link 器件名（如 STM32F407VG）
- chip: ESP 芯片型号（esptool 模式）
- baud: 烧录波特率（默认 921600）
- parallel: 并行度（默认自动 = 已连接设备数）
- retry: 失败重试次数（默认 2）
- retry_delay: 重试间隔秒（默认 2.0）
- verify: 是否烧录后读回比对（默认 true）
- report: JSON 报告路径（默认 flash_report.json）
- csv_report: CSV 报告路径（默认 flash_report.csv）

## 执行流程

### Phase 1: 设备枚举 → Phase 2: 确认固件 → Phase 3: 并行烧录 → Phase 4: 读回校验 → Phase 5: 汇总报告

## 支持的烧录方案

### OpenOCD 多 ST-Link（STM32/GD32/NXP）
每个 ST-Link 使用独立序列号启动独立 OpenOCD 进程，互不干扰。

### J-Link Multi-Emulator
使用 JLinkExe 的 -SelectEmuBySN 参数，每个 J-Link 独立执行 command script：
```
JLinkExe -Device STM32F407VG -SelectEmuBySN 12345678 -Speed 4000 -if SWD -autoconnect 1 -CommanderScript flash.jlink
```

J-Link command script 自动生成：
```
loadbin firmware.bin,0x08000000
verifybin firmware.bin,0x08000000
r
go
exit
```

### esptool 多串口（ESP32/ESP8266）
每个串口独立启动 esptool.py 进程。

## 错误处理与重试

| 错误类型 | 处理策略 |
|---------|---------|
| 烧录校验失败 | 自动重试（最多 N 次），间隔递增 |
| 目标板无响应 | 重试一次，仍失败标记"需人工检查" |
| 探针被占用 | 不重试，标记"设备忙" |
| 供电不足 | 建议降低并行度或使用外部供电 |
| J-Link license 不足 | J-Link Multi-Emulator 需要 J-Link PLUS 以上 |

## 烧录报告

### JSON 格式（机器可读）
```json
{
  "timestamp": "2026-04-27T10:30:00",
  "firmware": "firmware_v1.2.3.bin",
  "firmware_sha256": "a3f4c2d1...",
  "method": "jlink",
  "total": 4,
  "passed": 3,
  "failed": 1,
  "retried": 2,
  "total_duration_s": 18.5,
  "results": [
    {"index": 0, "serial": "12345678", "status": "pass", "duration": 3.2, "retries": 0, "fw_verified": true},
    {"index": 1, "serial": "87654321", "status": "fail", "duration": 8.5, "retries": 2, "error": "目标板无响应"},
    {"index": 2, "serial": "11111111", "status": "pass", "duration": 3.1, "retries": 0, "fw_verified": true},
    {"index": 3, "serial": "22222222", "status": "pass", "duration": 3.7, "retries": 1, "fw_verified": true}
  ]
}
```

### CSV 格式（Excel 可读）
与 JSON 同步输出，便于产线质检人员直接查看。

## 产线集成建议
- 使用 `--parallel` 限制并行数，避免 USB 带宽瓶颈（建议 ≤8）
- OpenOCD 模式建议每个 ST-Link 独立 USB 根集线器
- esptool 模式建议波特率不超 921600，多路时适当降低
- J-Link 模式使用 Ethernet J-Link 可获得更稳定连接
- 烧录后建议运行产线自检程序验证外设功能

## 边界定义

### 不该激活
- 用户只需要烧录**单块**目标板 → 优先用 `flash-jlink` / `flash-openocd` / `flash-idf` 等单板烧录 skill
- 用户还没有经过单板烧录验证阶段 → 量产并行烧录应在单板验证通过后才进行
- 用户讨论的是 "DFU"、"OTA"、"Bootloader 更新" 等非调试探针烧录方式
- 用户的工程尚未产出有效的固件产物（未编译或编译失败）

### 不该做
- **禁止**在未确认固件产物的 SHA256 校验和之前启动并行烧录
- **禁止**在无 `--yes` 参数且非交互终端时自动执行产线烧录（需人工确认）
- **禁止**将不良品烧录结果标记为"通过"，必须如实记录每一路状态
- **禁止**超过 `--parallel` 限制强开更多并行通道（USB 带宽过载可能导致批量失败）
- **禁止**在探针枚举不完整（部分探针未识别）时静默跳过，必须明确列出缺失设备

### 不该碰
- **不触碰**生产数据库：烧录报告写入本地文件，不连接 MES/ERP 等生产系统
- **不触碰**已标记为"不良"的目标板的 Option Bytes 或 Boot 配置
- **不触碰**非目标板的其他 USB 设备（键盘、鼠标、U 盘等）的串口/探针
- **不触碰**固件文件本身：只读取，绝不修改

## 输出约定

烧录完成后输出：
- JSON 报告（flash_report.json）：每路烧录的状态/耗时/重试次数/校验结果
- CSV 报告（flash_report.csv）：产线可读的烧录统计表
- 汇总：总板数、通过数、失败数、总耗时、烧录成功率
- 失败板卡标记具体原因（无响应/校验失败/设备忙）

## 交接关系

- 上游：`build-keil` / `build-cmake`（先编译出固件）
- 上游：`option-bytes`（量产前配置 RDP/WRP 保护）
- 单板验证：先用 `flash-jlink` / `flash-keil` 验证单板烧录通过
- 产线集成：建议结合产线自检程序（测试外设功能）
