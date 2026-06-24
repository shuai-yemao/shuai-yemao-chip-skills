---
name: devlog
description: 在每个项目开发会话结束时，生成结构化的 Markdown 开发日志，记录时间、工作内容、问题与解决方案、功能实现、整体进度。当用户提到开发日志、会话记录、工作记录、项目日志、开发回顾、记录问题、写日志时使用。
version: "1.0.0"
---

# Devlog — 开发日志生成

## 概述

在每个项目开发会话结束时，自动收集 git 信息和用户输入，生成结构化的开发日志，存入 `docs/开发日志/` 目录。

## 用法

### 参数模式（推荐 workflow 集成）

```bash
python scripts/devlog.py --project /path/to/project \
    --work-done "实现了 USART1 printf 重定向" \
    --problems-solutions "串口无输出 | USART1 时钟未使能 | 添加 __HAL_RCC_USART1_CLK_ENABLE()" \
    --features "printf 重定向 | 串口初始化" \
    --progress 60 \
    --achieved "printf 重定向、串口通信" \
    --pending "DMA 模式、中断接收" \
    --next-steps "- 实现 USART1 DMA 收发\n- 添加环形缓冲区"
```

### 交互模式

```bash
python scripts/devlog.py -i --project /path/to/project
```

### 仅打印不写文件

```bash
python scripts/devlog.py --project /path/to/project --print
```

### 指定输出路径

```bash
python scripts/devlog.py --project /path/to/project --output ./custom-devlog.md
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `--project` | 项目目录路径，用于自动收集 git 信息和确定输出位置 |
| `--project-name` | 项目名称（默认从目录名推断） |
| `--session-num` | 会话序号（默认自动检测已有日志 +1） |
| `--start-time` | 会话开始时间 |
| `--work-done` | 本次完成的工作内容 |
| `--problems-solutions` | 遇到的问题及解决方案 |
| `--features` | 功能/模块变更 |
| `--progress` | 整体进度百分比 (0-100) |
| `--achieved` | 已实现的内容 |
| `--pending` | 待完成的内容 |
| `--next-steps` | 下一步计划 |
| `--notes` | 备注 |
| `--output` | 输出路径（默认自动生成） |
| `--print` | 仅打印到控制台，不写文件 |
| `-i` / `--interactive` | 交互模式，逐项问答 |
| `-v` / `--verbose` | 详细输出 |

## 自动收集的信息

- **Git 分支**: 当前分支名
- **最近提交**: 最近 5 个 commit
- **文件变更**: git status --short 列出的未提交变更
- **会话序号**: 自动扫描已有日志文件

## 输出结构

默认输出到 `<项目根>/docs/开发日志/<日期>-会话<序号>.md`

日志模板包含以下章节：
1. **会话信息** — 日期、时间、项目、分支
2. **本次完成工作** — 功能实现、代码修改、测试验证
3. **遇到的问题及解决方案** — 问题/原因/方案表格
4. **功能/模块变更** — 新增/修改的功能
5. **文件变更** — git status 自动检测
6. **当前进度** — 百分比、已实现、待完成
7. **下一步计划** — 待办任务列表
8. **备注** — 额外信息

## 环境要求

- Python 3.8+
- Git（自动信息收集）
