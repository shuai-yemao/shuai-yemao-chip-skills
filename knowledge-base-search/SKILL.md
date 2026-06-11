---
name: knowledge-base-search
description: 六源知识检索管线。Phase1本地知识库(BM25+Vector+RRF+MMR) → Phase2芯片厂商官网文档+立创原理图 → Phase3 GitHub+Gitee开源仓库 → Phase4a技术博客(中7+英2) → Phase4b嵌入式论坛(中15+英5) → Phase4c B站+YouTube视频教程。当用户提到「查知识库」「查文档」「手册里有吗」「搜一下」「有没有相关的」或需要从技术文档中查找信息时使用。返回本地匹配片段+官网文档原文+外部验证结果+论坛链接+视频链接。
version: "1.0.0"
---

# 知识库检索（六源检索管线）

## 适用场景

- 用户问技术细节需要文档支撑
- 用户明确说"查知识库"、"手册里有吗"、"搜一下"、"有没有相关的资料"
- 需要寄存器地址、时序参数、接口协议等精确数据
- 需要技术博客文章、论坛踩坑经验、项目实战教程、B站/YouTube视频教程

## 必要输入

| 输入 | 说明 |
|------|------|
| 查询语句 | 自然语言搜索问题，如 "STM32 SPI DMA 配置" |
| -k / --top-k | 返回结果数（默认 5）|
| --json | JSON 格式输出（默认 Markdown）|
| --verify | 是否执行真伪验证（默认不启用）|
| --list-kbs | 列出所有可用知识库（无需查询）|

## 依赖

- Python 3.8+
- 本地知识库 SQLite 数据库（CherryStudio KB + imported_docs）
- Obsidian Vault（自动发现，可选）
- 搜索需联网（Phase 2-4c 需要 web_search + fetch 工具）
- scripts/kb_search.py（主检索脚本）
- scripts/verify_claims.py（真伪验证脚本，可选）

> **核心原则**：本地知识库是起点，不是终点。
> 六层来源按权威性排序：**芯片厂商官网 > 本地 KB > GitHub 实战代码 > 技术博客 > 嵌入式论坛 > B站/YouTube视频教程**。

## 六源管线

```
                         ┌─────────────────────┐
                         │     用户查询          │
                         └─────────┬───────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│  Phase 1         │    │  Phase 2             │    │  Phase 3         │
│  本地知识库       │    │  厂商官网文档          │    │  GitHub 仓库      │
│  (kb_search.py)  │    │  (web_search +        │    │  (search_repos +  │
│                  │    │   fetch_markdown)     │    │   search_code)    │
│  BM25 + RRF      │    │                       │    │                   │
│  + MMR + 上下文   │    │  ST/Espressif/NXP/    │    │  开源实现/驱动/    │
│                  │    │  TI/Nordic 官网原文     │    │  Gitee 国产源码    │
└────────┬────────┘    └──────────┬──────────┘    └────────┬────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Phase 4a        │    │  Phase 4b        │    │  Phase 4c        │
│  技术博客/社区     │    │  嵌入式论坛       │    │  B站+YouTube     │
│  (web_search_exa) │    │  (web_search_exa)│    │  (web_search_exa) │
│                  │    │                  │    │                   │
│  CSDN/知乎/博客园   │   │  电子发烧友/21ic   │    │                   │
│  掘金/开源中国      │    │  正点原子/野火/硬汉 │    │  中英文视频教程   │
│  51CTO/腾讯云/立创  │    │  ST社区/EEWorld    │    │                   │
│  Hackaday/Medium    │   │  极术/100ask/RT-T   │   │                   │
│                    │    │  立创/阿莫/51黑     │    │                   │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         └──────────────────────┼──────────────────────┘
                                │
                               ▼
                    ┌─────────────────────┐
                    │  输出：六源综合回答    │
                    │  含来源标注 + 链接     │
                    │  + 可信度矩阵         │
                    └─────────────────────┘
```

## Phase 1: 本地知识库检索

### 知识库来源

kb_search.py 自动发现并融合以下本地知识源：

| 来源 | 适配器 | 格式 | 发现方式 |
|------|--------|------|---------|
| CherryStudio KB | `SQLiteVectorKB` | SQLite vectors 表 | `KnowledgeBase/*.db` 自动扫描 |
| 外部导入 KB | `SQLiteVectorKB` | SQLite (同 schema) | `imported_docs.db` 自动发现 |
| **Obsidian Vault** | `ObsidianMarkdownKB` | Markdown (.md) | 自动检测 `.obsidian` 目录 |

### 检索管线

```
Query → BM25 + Vector → Adaptive RRF Fusion → MMR Dedup → Context Expansion → Top-K
```

```bash
# 基础搜索
python scripts/kb_search.py "STM32 时钟配置 RCC"

# JSON 输出（程序化消费）
python scripts/kb_search.py "SPI DMA 传输" --json -k 5

# 列出所有可用知识库
python scripts/kb_search.py --list-kbs

# 查看知识库概览
python scripts/kb_search.py --source-stats

# 跳过 Obsidian 自动发现
python scripts/kb_search.py "SPI DMA" --no-obsidian

# 加载 vault 中所有 .md（不限于嵌入式）
python scripts/kb_search.py "FreeRTOS 任务" --obsidian-all

# 纯 BM25（禁用 MMR 和扩展用于 debug）
python scripts/kb_search.py "DMA 双缓冲" --no-mmr --no-expand

# 搜索 + 真伪验证一体
python scripts/kb_search.py "USART SR寄存器 TC标志" --verify -k 3
```

### Obsidian Vault 集成

**自动发现策略**：
1. 检查 `OBSIDIAN_VAULT_PATH` 环境变量
2. 扫描 `~/Documents/Obsidian`、`~/Obsidian` 等常见位置

**嵌入式内容过滤**（默认开启）：文件名或路径含 `stm32`/`esp32`/`mcu`/`freertos`/`rtos`/`uart`/`spi`/`i2c`/`dma`/`嵌入式`/`单片机`/`驱动` 等关键词的 .md 才会加载。`--obsidian-all` 加载全部。

**分块策略**：按 `##` 标题优先切分 → 超长段落按 `\n\n` 再分（chunk_size=800, overlap=100）。

## Phase 2: 芯片厂商官网文档（最高权威）

> **原则**：厂商官网发布的 Reference Manual / Datasheet / Application Note / Errata 是嵌入式开发中最权威的一手来源。

### 常用厂商文档入口

| 厂商 | 文档类型 | 搜索策略 |
|------|---------|---------|
| **ST** | RM / DS / AN / ES | `"STM32F4xx reference manual RM0090 site:st.com"` |
| **Espressif** | TRM / DS / API | `"ESP32 technical reference manual site:espressif.com"` |
| **NXP** | RM / DS / AN | `"i.MX RT1060 reference manual site:nxp.com"` |
| **TI** | DS / UG / AN | `"MSP430 datasheet site:ti.com"` |
| **Nordic** | PS / DS / SDS | `"nRF52840 product specification site:nordicsemi.com"` |
| **GD** | DS / UM | `"GD32F303 datasheet site:gd32mcu.com"` |
| **WCH** | DS / RM | `"CH32V307 datasheet site:wch.cn"` |
| **立创开源硬件** | 原理图+PCB+源码 | `"STM32F411ceu6 原理图 site:oshwhub.com"` |

### 传感器数据手册查找

| 传感器类型 | 常见厂商 | 搜索示例 |
|-----------|---------|---------|
| IMU (6/9轴) | TDK/InvenSense, ST, Bosch | `"MPU6050 datasheet pdf site:invensense.com"` |
| 温湿度 | Sensirion, Bosch, TI | `"BME280 datasheet site:bosch-sensortec.com"` |
| 气压 | Bosch, ST, TE | `"LPS22HB datasheet site:st.com"` |
| ToF 测距 | ST, AMS, TI | `"VL53L0X datasheet site:st.com"` |
| 环境光 | ROHM, AMS, TI | `"BH1750 datasheet site:rohm.com"` |

### 文档获取流程

```
步骤 1: 生成搜索查询 → tools: 无（自动识别厂商构造查询）
步骤 2: 搜索文档     → tools: mcp__exa__web_search_exa
步骤 3: 获取内容     → tools: mcp__Uo38RGQK0kgxYuhEv48MX__fetch_markdown
步骤 4: 必要时浏览器  → tools: mcp__JR9pzKyxpIZd13MRVA5yk__navigate_page
```

### 官网文档关键词速查

```
STM32 F4 参考手册 → "RM0090 reference manual STM32F40x STM32F41x site:st.com"
STM32 F1 数据手册 → "STM32F103C8 datasheet site:st.com"
ESP32 技术参考   → "ESP32 technical reference manual site:espressif.com"
ESP32-S3 数据手册 → "ESP32-S3 datasheet site:espressif.com"
nRF52840 规格书   → "nRF52840 product specification site:nordicsemi.com"
```

## Phase 3: GitHub 仓库验证

```bash
工具: mcp__3XBHo9dkU6cK8_8uurDP4__search_repositories
      mcp__3XBHo9dkU6cK8_8uurDP4__search_code
      mcp__3XBHo9dkU6cK8_8uurDP4__search_issues

搜索策略:
  - 官方驱动: "{MCU型号} {外设} HAL driver implementation"
  - 开源项目: "{传感器型号} driver library C"
  - Issues:   "{芯片型号} {外设} bug errata workaround"
  - 代码搜索: "{寄存器名} {配置位}" + language:C
  - **Gitee**: "{MCU型号} {外设} 驱动 site:gitee.com" （国产 MCU SDK 优先搜 Gitee）
```

## Phase 4a: 技术博客/社区文章

**必须并行搜索**博客和文章，中英文各一组：

```bash
工具: mcp__exa__web_search_exa

中文搜索: "{主题} {芯片型号} 配置 详解 注意事项 踩坑"
英文搜索: "{topic} {chip} best practice gotcha errata"

### 中文技术博客/社区

| 平台 | 域名 | 搜索模式 | 适用场景 |
|------|------|---------|---------|
| **CSDN** | `blog.csdn.net` | `"{主题} site:blog.csdn.net"` | 中文最全嵌入式技术博客（含踩坑） |
| **知乎** | `zhuanlan.zhihu.com` | `"{主题} 嵌入式 site:zhuanlan.zhihu.com"` | 架构思考/方案选型/深度分析 |
| **博客园** | `cnblogs.com` | `"{主题} site:cnblogs.com"` | 嵌入式开发实战经验 |
| **掘金** | `juejin.cn` | `"{主题} site:juejin.cn"` | 现代嵌入式开发/RTOS/工具链 |
| **开源中国** | `oschina.net` | `"{主题} site:oschina.net"` | 开源项目/国产MCU/社区讨论 |
| **51CTO** | `blog.51cto.com` | `"{主题} site:blog.51cto.com"` | 技术教程/项目实战 |
| **腾讯云开发者社区** | `cloud.tencent.com/developer` | `"{主题} site:cloud.tencent.com/developer"` | 嵌入式+IoT 方案 |
```

### 英文技术博客/社区（按内容质量排序）

| 平台 | 域名 | 搜索模式 | 适用场景 |
|------|------|---------|---------|
| **Hackaday** | `hackaday.com` | `"{topic} site:hackaday.com"` | 硬件黑客/逆向/嵌入式项目 — 技术深度极高 |
| **Medium** | `medium.com` | `"{topic} embedded site:medium.com"` | 嵌入式工程师深度技术文章（Phil's Lab等） |

## Phase 4b: 嵌入式论坛

**必须并行搜索**以下论坛，中英文各一组：

### 中文论坛（按活跃度/质量排序）

| 论坛 | 域名 | 搜索模式 |
|------|------|---------|
| **电子发烧友** | `elecfans.com` | `"{主题} site:elecfans.com"` |
| **21ic电子网** | `bbs.21ic.com` | `"{主题} site:bbs.21ic.com"` |
| **正点原子论坛** | `openedv.com` | `"{主题} site:openedv.com"` |
| **野火论坛** | `firebbs.cn` | `"{主题} site:firebbs.cn"` |
| **硬汉嵌入式** | `armbbs.cn` | `"{主题} site:armbbs.cn"` |
| **STM32中文社区** | `shequ.stmicroelectronics.cn` | `"{主题} site:shequ.stmicroelectronics.cn"` |
| **ST中文论坛** | `stmcu.org.cn` | `"{主题} site:stmcu.org.cn"` |
| **EEWorld** | `eeworld.com.cn` | `"{主题} site:eeworld.com.cn"` |
| **极术社区** | `aijishu.com` | `"{主题} site:aijishu.com"` |
| **韦东山100ask** | `forums.100ask.net` | `"{主题} site:forums.100ask.net"` |
| **RT-Thread社区** | `club.rt-thread.org` | `"{主题} site:club.rt-thread.org"` |
| **立创开源硬件** | `oshwhub.com` | `"{主题} site:oshwhub.com"` |
| **阿莫电子论坛** | `amobbs.com` | `"{主题} site:amobbs.com"` |
| **51黑电子** | `51hei.com` | `"{主题} site:51hei.com"` |
| **好好搭搭** | `haohaodada.com` | `"{主题} site:haohaodada.com"` |

### 英文论坛

| 论坛 | 域名 | 搜索模式 |
|------|------|---------|
| STM32 Community | `community.st.com` | `"{topic} site:community.st.com"` |
| ESP32 Forum | `esp32.com` | `"{topic} site:esp32.com"` |
| EEVblog | `eevblog.com/forum` | `"{topic} site:eevblog.com"` |
| Stack Overflow | `stackoverflow.com` | `"{topic} [c] [embedded] site:stackoverflow.com"` |
| Reddit r/embedded | `reddit.com/r/embedded` | `"{topic} site:reddit.com/r/embedded"` |

### 论坛内容可信度评估

| 信号 | 可信度 |
|------|--------|
| 多位用户独立确认同一解决方案 | 高 |
| 官方 FAE / 版主回复 | 高 |
| 附带可运行的代码 + 寄存器截图 | 中高 |
| 单用户自问自答 | 中 |
| 已被后续回复推翻的早期答案 | 不可用 |

## Phase 4c: B站 + YouTube 视频教程

```bash
工具: mcp__exa__web_search_exa（搜索视频标题/简介）

中文搜索: "{主题} {芯片型号} 教程 site:bilibili.com"
英文搜索: "{topic} {chip} tutorial site:youtube.com"

例: "STM32 CAN 总线 教程 实战 site:bilibili.com"
例: "STM32 CAN bus tutorial site:youtube.com"
```

### 搜索关键词模式

| 搜索意图 | 中文 (B站) | 英文 (YouTube) |
|---------|------------|----------------|
| 外设入门 | `"{外设} 入门 教程 {芯片}"` | `"{peripheral} {chip} tutorial"` |
| 项目实战 | `"{芯片} {项目} 实战"` | `"{chip} {project}"` |
| 调试技巧 | `"{工具} 调试 教程"` | `"{tool} debug tutorial"` |
| 协议解析 | `"{协议} 协议 详解"` | `"{protocol} explained"` |
| 踩坑合集 | `"{芯片} 踩坑 填坑"` | `"{chip} common mistakes gotchas"` |
| RTOS | `"FreeRTOS {主题} 源码分析"` | `"FreeRTOS {topic} deep dive"` |

### 视频内容可信度

| 信号 | 可信度 |
|------|--------|
| 知名UP主/频道（正点原子/野火/Phil's Lab/Dave Jones/GreatScott） | 高 |
| 视频附带 GitHub 源码链接 | 中高 |
| 评论区有用户反馈"已验证可行" | 中高 |
| 播放量 > 10000 + 弹幕正面反馈 | 中 |

### 输出格式

```
[B站视频]
  标题: {视频标题}
  UP主: {UP主名称}
  链接: https://www.bilibili.com/video/{BV号}
  播放量: {播放量}
  简介: {摘要}
```

## 命令参考

```bash
# 基础搜索（Top 5，完整管线）
python scripts/kb_search.py "STM32 时钟配置 RCC"

# JSON 输出
python scripts/kb_search.py "SPI DMA 传输" --json -k 5

# 列出所有可用知识库
python scripts/kb_search.py --list-kbs

# 查看知识库概览
python scripts/kb_search.py --source-stats

# 纯 BM25（禁用 MMR 和扩展用于 debug）
python scripts/kb_search.py "DMA 双缓冲" --no-mmr --no-expand
```

## 执行步骤

### Step 1 确定查询
分析用户问题，提取关键词和技术术语，构造适合本地 KB 搜索的查询语句。

### Step 2 本地知识库搜索（Phase 1）
```bash
python scripts/kb_search.py "查询语句" -k 5 [--json]
```
返回本地匹配片段，含来源标注（来自哪个知识库、文件、行号）。

### Step 3 外部来源搜索（Phase 2-4）
根据本地搜索结果的质量和覆盖范围，决定是否需要补充搜索：
- 芯片厂商官网文档（Phase 2）— 需要精确寄存器/时序参数时必查
- GitHub 开源仓库（Phase 3）— 需要代码实现参考时查
- 技术博客/论坛/B站（Phase 4）— 需要实践经验时查

### Step 4 真伪验证（Phase 5，可选）
```bash
python scripts/verify_claims.py --verify --claims "断言1|断言2"
```
交叉比对多源结果，输出可信度评分。

### Step 5 输出综合回答
合并本地 KB 命中 + 外部来源 + 验证结果，标注来源链接和可信度评分。

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 本地 KB 无命中 | 查询太过冷门或知识库未覆盖 | 转 Phase 2-4 全力搜索外部来源 |
| 网络搜索不可用 | 网络不通或搜索工具受限 | 仅用本地 KB + Obsidian 结果 |
| 真伪验证无任何来源 | 断言太具体，无法找到交叉验证 | 降低可信度标注，提示用户自行验证 |
| Obsidian 检测不到 | .obsidian 目录不存在或 vault 路径不对 | 不加载 Obsidian，仅用 CherryStudio KB |

### 何时激活
- 用户问技术细节需要文档支撑
- 用户明确说"查知识库"、"手册里有吗"、"搜一下"、"有没有相关的资料"
- 需要寄存器地址、时序参数、接口协议等精确数据
- 需要技术博客文章、论坛踩坑经验、项目实战教程、B站/YouTube视频教程

### 何时不激活
- 纯编程/代码逻辑问题（不需要文档）
- 用户已指定信息来源
- 纯对话闲聊

### 边界
- **不要**把本地 KB 结果当作唯一正确答案
- **不要**跳过 Phase 2/3/4 — 必须做六源交叉验证
- **不要**仅依赖社区博客而不查官网数据手册
- **必须**在输出中附带论坛帖子和B站视频的**直达链接**

## 交接关系

- 下游（验证）：本 skill 输出结果后 → `kb-verify`（真伪验证）
- 下游（导入）：高价值内容 → `kb-import`（导入知识库）
- 下游（记录）：遇到的问题 → `kb-record`（归档到 Obsidian）
- 互补（数据手册）：`kb-datasheet`（获取厂商数据手册）
- 互补（外部搜索）：Phase 2-4 依赖 web_search + fetch 工具链
- 真伪验证 → 使用 **kb-verify** skill
- 内容导入知识库 → 使用 **kb-import** skill
- 问题记录到 Obsidian → 使用 **kb-record** skill
- 数据手册获取 → 使用 **kb-datasheet** skill
