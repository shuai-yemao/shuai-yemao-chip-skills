---
name: pcb-analysis
description: LCEDA Pro 原理图综合分析——通过 ai_eda WebSocket 桥接器读取 LCEDA Pro 原理图，自动生成包含 BOM、电源树、引脚分配、网络拓扑和设计规则检查（引脚冲突/电源短路/悬空网络/多驱动源）的完整分析报告。当用户提到原理图分析、PCB 分析、BOM 分析、电源树、引脚分配、网络拓扑、设计规则检查、DRC、LCEDA、立创 EDA 原理图、分析原理图时使用。
version: "1.0.0"
---

# LCEDA Pro 原理图分析

通过 ai_eda WebSocket 桥接器读取 LCEDA Pro 原理图，自动生成包含 BOM、电源树、引脚分配、网络拓扑和设计规则检查的完整分析报告。

## 适用场景

- 需要分析当前打开的 LCEDA Pro 原理图，生成 BOM 清单
- 需要追踪电压轨链路，验证电源去耦完整性
- 需要检查 MCU 引脚分配是否存在冲突或外设复用问题
- 需要分析网络拓扑，检测悬空、单点连接或遗漏连接
- 需要在设计审查前做一次全面的设计规则检查

## 必要输入

| 参数 | 说明 |
|------|------|
| 分析模式 | --bom / --power / --pinmap / --net / --conflict / --all |
| 输出格式 | 控制台 ASCII（默认）或 --json |
| 桥服务器 | 运行在 127.0.0.1:8787（自动管理） |

## 依赖

- LCEDA Pro 已安装并打开目标原理图
- ai_eda 桥接插件已安装（`aieda-js_v0.1.1.eext`）
- Python 3.9+（依赖 `aiohttp`）
- 桥服务器（`bridge_server.py`）需要 `ai_eda` 项目环境

## 执行步骤

### 一键分析（all-in-one）
```bash
python scripts/pcb_analyzer.py full
```
自动：启动桥服务器 → 等待插件连接 → 读取原理图 → 分析 → 输出报告

### 逐模块分析
```bash
python scripts/pcb_analyzer.py status          # 检查桥连接状态
python scripts/pcb_analyzer.py analyze --bom    # 仅 BOM 分析
python scripts/pcb_analyzer.py analyze --power  # 仅电源分析
python scripts/pcb_analyzer.py analyze --pinmap # 仅引脚分配
python scripts/pcb_analyzer.py analyze --net    # 仅网络分析
python scripts/pcb_analyzer.py analyze --conflict # 仅冲突检查
python scripts/pcb_analyzer.py analyze --all    # 全部模块
python scripts/pcb_analyzer.py analyze --all --json # JSON 输出
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 桥服务器无法启动 | aiohttp 未安装或端口被占用 | pip install aiohttp，检查 8787 端口 |
| 插件未连接 | LCEDA Pro 未安装插件 | 确认 aieda-js 插件已安装并启用 |
| 读取原理图失败 | 原理图未打开或格式问题 | 确认目标原理图已在 LCEDA Pro 中打开 |
| 分析结果为空 | 原理图数据异常 | 检查原理图是否包含有效元件和网络 |

## 输出约定

### 控制台输出
- BOM：器件列表（型号/制造商/LCSC 编号/数量/类型分类）
- 电源树：电压轨链路图 + 稳压器/去耦器件标注
- 引脚映射：MCU 引脚 → 外设功能 → 连接网络 映射表
- 网络拓扑：网络名 → 连接器件列表 → 扇出数
- 冲突检查：引脚冲突/短路/悬空网络/多驱动源 列表

### JSON 输出（--json）
结构化数据，适合导入其他工具或自动化流水线消费。

## 边界定义

### 不该激活
- 用户没有打开 LCEDA Pro 或原理图文件
- 用户需要的是 PCB 布线审查而非原理图分析
- 用户使用非立创 EDA 工具（Altium Designer / KiCad / PADS 等）
- 用户只需要查看 PDF 版的原理图（无需分析）

### 不该做
- **禁止**在没有桥连接的情况下猜测原理图内容
- **禁止**修改 LCEDA Pro 中的原理图数据（只读分析）
- **禁止**在没有插件确认连接时重复发起连接请求
- **禁止**覆盖用户已有的分析缓存文件

### 不该碰
- **不触碰** LCEDA Pro 软件配置和数据文件
- **不触碰**原理图中的元件参数（只读取不修改）
- **不触碰**桥服务器的全局配置

## 交接关系

- 上游：LCEDA Pro 原理图设计完成
- 下游：分析报告供 `embedded-reviewer` 做设计审查
- 发现引脚冲突时 → 参考 `stm32-hal-development`（外设分配）
- 发现电源问题时 → 参考 `lowpower-design`（电源架构设计）
- 自动化流水线：`workflow`（schematic-review 流水线）
