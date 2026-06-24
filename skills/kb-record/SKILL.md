---
name: kb-record
description: 开发问题记录到 Obsidian。使用四段式诊断模板（问题描述→原因分析→实验设计→验证实验）将调试过程中遇到的问题归档到 Obsidian vault 的「问题记录」目录，支持 new/append/summary/search 四种操作模式。当用户提到「记录问题」「归档问题」「问题记录」「diagnostic template」「诊断模板」「记录Bug」「issue记录」或调试闭环中需要归档问题时使用。
version: "1.0.0"
---

# 问题记录归档

> 将开发过程中遇到的问题按「嵌入式系统诊断流程模板」的四段式结构归档到 Obsidian vault，
> 下次搜索可命中类似问题。

## 记录脚本

```bash
# 脚本位置（共享 knowledge-base-search 的脚本目录）
python ../knowledge-base-search/scripts/record_issue.py
```

## 操作模式

### 创建新问题记录

```bash
python ../knowledge-base-search/scripts/record_issue.py new \
    --project "项目名称" \
    --title "问题标题" \
    --description "问题现象描述" \
    --cause "原因分析" \
    --experiment "实验设计" \
    --result "验证结果"
```

### 追加内容到已有记录

```bash
python ../knowledge-base-search/scripts/record_issue.py append \
    --project "项目名称" --issue "2026-xx-xx-问题标题" \
    --result "第二轮验证：代码修改后编译通过，串口输出正常"
```

### 生成摘要

```bash
python ../knowledge-base-search/scripts/record_issue.py summary \
    --project "项目名称"
```

### 搜索问题记录

```bash
python ../knowledge-base-search/scripts/record_issue.py search \
    --keyword "DMA 双缓冲"
```

## 输出路径

```
{Obsidian Vault}/领域/嵌入式/嵌入式项目文档/问题记录/{项目名称}/
  2026-xx-xx-问题标题.md
```

## 诊断模板结构（四段式）

1. **问题描述** — 现象、复现条件、环境
2. **原因分析** — 根因、排查过程
3. **实验设计** — 验证方案、预期结果
4. **验证实验** — 实际结果、结论

## 使用时机

### 何时激活
- 调试过程中遇到了需要记录的问题
- 用户说"记录一下这个问题"、"这个Bug记下来"
- 从 build → flash → capture 闭环后需要归档

### 何时不激活
- 纯理论学习（没有实际工程问题）
- 已经记录过的重复问题

### 边界
- **不修改**其他知识库
- **不修改**已有的 Obsidian 文件内容（仅追加或新建）
- **不添加**未经验证的问题记录
