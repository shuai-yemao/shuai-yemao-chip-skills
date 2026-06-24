---
name: kb-import
description: 搜索成果导入本地知识库。将验证通过的高价值内容（论坛解决方案/B站视频代码/官网关键章节/社区文章）写入 imported_docs.db，实现知识沉淀闭环。支持 URL/text/file/batch 四种导入方式。当用户提到「导入知识库」「保存到知识库」「记住这个」「收藏」「知识沉淀」「add to kb」「import to kb」或验证通过后需要归档高价值内容时使用。
version: "1.0.0"
---

# 搜索成果导入本地知识库

> **闭环核心**: 每次多源搜索得到的高价值内容，自动写入 `imported_docs.db`，
> 使未来搜索命中这些已验证内容，实现知识积累。

## 导入脚本

```bash
# 脚本位置（共享 knowledge-base-search 的脚本目录）
python ../knowledge-base-search/scripts/import_to_kb.py
```

## 导入方式

### 从文本导入（推荐方式）

```bash
python ../knowledge-base-search/scripts/import_to_kb.py --text "{内容}" \
    --title "{文档标题}" --source-type {datasheet|forum|bilibili|blog|github|article} \
    --tags "{逗号分隔标签}"
```

### 从 URL 导入

```bash
# 社区文章
python ../knowledge-base-search/scripts/import_to_kb.py --url "https://blog.example.com/article" \
    --source-type blog --tags "STM32,DMA"

# 论坛帖子
python ../knowledge-base-search/scripts/import_to_kb.py --url "https://bbs.21ic.com/thread-xxxxx.html" \
    --source-type forum --tags "STM32,SPI,踩坑"

# B站视频（含简介和代码链接）
python ../knowledge-base-search/scripts/import_to_kb.py --url "https://www.bilibili.com/video/BVxxxxxx" \
    --source-type bilibili --tags "教程,FreeRTOS,项目实战"

# GitHub 仓库 README
python ../knowledge-base-search/scripts/import_to_kb.py --url "https://github.com/owner/repo" \
    --source-type github --tags "driver,sensor"
```

### 批量导入

```bash
# 从文本文件逐行读取 URL
python ../knowledge-base-search/scripts/import_to_kb.py --batch urls.txt
```

### 管理已导入内容

```bash
# 列出所有已导入
python ../knowledge-base-search/scripts/import_to_kb.py --list

# 查看统计数据
python ../knowledge-base-search/scripts/import_to_kb.py --stats

# 按关键词删除
python ../knowledge-base-search/scripts/import_to_kb.py --remove "关键词"
```

## 导入判定标准

| 条件 | 操作 |
|------|------|
| 论坛帖子含多用户确认的有效解决方案 + 代码 | → 摘录关键代码 + 问题根因说明 → 导入 |
| B站视频含可运行的项目源码（GitHub 链接） | → 导入视频简介 + GitHub 项目 README |
| 社区文章含 HAL 示例代码且经验证正确 | → 摘录关键代码片段 + 陷阱说明 → 导入 |
| 官网数据手册被确认为最新版本 | → 导入关键寄存器/时序章节 |
| GitHub Issue 含有效 workaround | → 导入问题描述 + 解决方案 |
| 传感器校准公式/寄存器映射 | → 直接导入（此类信息持久有效）|
| 论坛中官方 FAE 的权威回复 | → 导入原文 + 标注 [FAE官方回复] |
| 与现有 KB 内容重复 | → 跳过 |
| 未经交叉验证的高风险信息 | → 标注 [待验证] → 可选导入 |
| 论坛帖子仅提出问题未解决 | → 仅记录问题现象，不导入 |

## 导入后效果

```
imported_docs.db  ─┬─ 自动被 kb_search.py 发现
                   ├─ 纳入 BM25 索引（与主 KB 同等权重）
                   ├─ 跨库搜索结果中标记 [导入KB]
                   └─ 随每次搜索自动增长，形成知识沉淀
```

## 使用时机

### 何时激活
- 验证通过（≥0.70）的高价值内容需要持久化
- 官网关键章节摘录需要保存
- 论坛/B站的实战踩坑经验需要归档
- 用户说"把这个记住"、"保存一下"

### 何时不激活
- 内容未经交叉验证
- 与现有 KB 内容完全重复
- 商业机密/版权受限内容

### 边界
- **不修改**其他知识库（CherryStudio 主 KB、Obsidian Vault）
- **不导入**未经交叉验证的内容
- **不导入**商业机密或受版权保护的内容
