# Shuai Yemao Chip Skills

Claude Code 技能包集合 — 用于自动化各种开发任务。

## 📊 技能总览

```mermaid
mindmap
  root((Skills))
    学术研究
      academic-paper
      academic-paper-reviewer
      academic-pipeline
      deep-research
    工程开发
      engineering
      engineering-best-practices
      tdd
      grill-with-docs
      codebase-design
    前端开发
      frontend-excellence
      frontend-toolkit
    嵌入式开发
      系统架构
        embedded
        embedded-architect
        embedded-system-design
      代码审查
        embedded-reviewer
      调试工具
        embedded-debugger-framework
        rtos-debug
        cmbacktrace-debug
        segger-rtt-module
      STM32
        stm32-hal-development
        stm32-spl-development
      RTOS
        freertos-module
        rtos-debug
      外设驱动
        i2c-bus
        spi-bus
        uart-module
        adc-module
        dma-module
        timer-module
        watchdog-module
      通信协议
        can-debug
      存储
        flash-module
        sfud-module
        flash-jlink
        flash-openocd
        flash-keil
        flash-platformio
        flash-idf
        gang-flash
      日志
        elog-module
      学习资源
        embedded-learning-notes
        embedded-learning-path-framework
        embedded-note-templates
        embedded-skills-map
    论文写作
      paper-writing
    生产力工具
      grill-me
      teach
      handoff
      caveman
    知识管理
      knowledge-base-search
      obsidian-vault
    个人工具
      edit-article
      obsidian-vault
    杂项工具
      git-guardrails
      migrate-to-shoehorn
    Agent 技能
      agent-skills
    Git 工作流
      git-workflow-skill
```

## 📁 目录结构

```mermaid
graph TB
    subgraph "shuai-yemao-chip-skills"
        A[skills/]
        
        subgraph "学术研究"
            A1[academic-research-skills/]
            A1 --> A1a[academic-paper]
            A1 --> A1b[academic-paper-reviewer]
            A1 --> A1c[academic-pipeline]
            A1 --> A1d[deep-research]
        end
        
        subgraph "工程开发"
            A2[engineering/]
            A2 --> A2a[tdd]
            A2 --> A2b[grill-with-docs]
            A2 --> A2c[codebase-design]
            A2 --> A2d[diagnose]
            
            A3[engineering-best-practices/]
        end
        
        subgraph "前端开发"
            A4[frontend-excellence/]
            A5[frontend-toolkit/]
        end
        
        subgraph "嵌入式开发（38 个）"
            A6[系统架构]
            A6 --> A6a[embedded]
            A6 --> A6b[embedded-architect]
            A6 --> A6c[embedded-system-design]
            
            A7[代码审查]
            A7 --> A7a[embedded-reviewer]
            
            A8[调试工具]
            A8 --> A8a[embedded-debugger-framework]
            A8 --> A8b[rtos-debug]
            A8 --> A8c[cmbacktrace-debug]
            A8 --> A8d[segger-rtt-module]
            
            A9[STM32]
            A9 --> A9a[stm32-hal-development]
            A9 --> A9b[stm32-spl-development]
            
            A10[RTOS]
            A10 --> A10a[freertos-module]
            
            A11[外设驱动]
            A11 --> A11a[i2c-bus]
            A11 --> A11b[spi-bus]
            A11 --> A11c[uart-module]
            A11 --> A11d[adc-module]
            A11 --> A11e[dma-module]
            A11 --> A11f[timer-module]
            A11 --> A11g[watchdog-module]
            
            A12[通信协议]
            A12 --> A12a[can-debug]
            
            A13[存储]
            A13 --> A13a[flash-module]
            A13 --> A13b[sfud-module]
            A13 --> A13c[flash-jlink]
            A13 --> A13d[flash-openocd]
            A13 --> A13e[flash-keil]
            A13 --> A13f[flash-platformio]
            A13 --> A13g[flash-idf]
            A13 --> A13h[gang-flash]
            
            A14[日志]
            A14 --> A14a[elog-module]
            
            A15[学习资源]
            A15 --> A15a[embedded-learning-notes]
            A15 --> A15b[embedded-learning-path-framework]
            A15 --> A15c[embedded-note-templates]
            A15 --> A15d[embedded-skills-map]
        end
        
        subgraph "论文写作"
            A16[paper-writing/]
        end
        
        subgraph "生产力工具"
            A17[productivity/]
            A17 --> A17a[grill-me]
            A17 --> A17b[teach]
            A17 --> A17c[handoff]
            A17 --> A17d[caveman]
        end
        
        subgraph "知识管理"
            A18[knowledge-base-search/]
        end
        
        subgraph "个人工具"
            A19[personal/]
            A19 --> A19a[edit-article]
            A19 --> A19b[obsidian-vault]
        end
        
        subgraph "杂项工具"
            A20[misc/]
            A20 --> A20a[git-guardrails]
            A20 --> A20b[migrate-to-shoehorn]
        end
        
        subgraph "其他"
            A21[agent-skills/]
            A22[git-workflow-skill/]
            A23[learned/]
        end
    end

    style A fill:#e1f5fe
    style A1 fill:#e3f2fd
    style A2 fill:#e8f5e9
    style A4 fill:#fff3e0
    style A6 fill:#fce4ec
    style A17 fill:#f3e5f5
```

## 🎯 技能分类

### 学术研究（4 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **academic-paper** | 12-agent 学术论文写作流水线 | write paper, academic paper, 寫論文 |
| **academic-paper-reviewer** | 论文评审和反馈 | review paper, 审查意見 |
| **academic-pipeline** | 学术研究全流程 | research pipeline, 學術研究 |
| **deep-research** | 深度研究和文献综述 | deep research, 深度研究 |

### 工程开发（6 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **tdd** | 测试驱动开发（红-绿-重构） | tdd, test-driven, red-green-refactor |
| **grill-with-docs** | 文档驱动的需求对齐 | grill with docs, 需求对齐 |
| **codebase-design** | 代码库设计和架构 | design codebase, 代码设计 |
| **diagnose** | 问题诊断和修复 | diagnose, debug, 诊断 |
| **engineering-best-practices** | 工程最佳实践 | best practices, 最佳实践 |
| **ask-matt** | 咨询 Matt Pocock | ask matt |

### 前端开发（2 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **frontend-excellence** | 前端开发最佳实践 | frontend excellence, 前端最佳实践 |
| **frontend-toolkit** | 前端工具包 | frontend toolkit, 前端工具 |

### 嵌入式开发（38 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **embedded** | 嵌入式系统开发专家 | embedded, MCU, STM32, ESP32, firmware |
| **embedded-architect** | 嵌入式架构师 | embedded architect, 嵌入式架构 |
| **embedded-reviewer** | 嵌入式代码审查 | embedded review, 嵌入式审查 |
| **embedded-debugger-framework** | 嵌入式调试框架 | embedded debug, 嵌入式调试 |
| **embedded-learning-notes** | 嵌入式学习笔记 | embedded learning, 嵌入式学习 |
| **embedded-learning-path-framework** | 嵌入式学习路径 | embedded path, 学习路径 |
| **embedded-note-templates** | 嵌入式笔记模板 | embedded notes, 笔记模板 |
| **embedded-skills-map** | 嵌入式技能地图 | embedded skills map, 技能地图 |
| **stm32-hal-development** | STM32 HAL 开发 | stm32 hal, HAL 开发 |
| **stm32-spl-development** | STM32 SPL 开发 | stm32 spl, SPL 开发 |
| **freertos-module** | FreeRTOS 模块 | freertos, RTOS |
| **rtos-debug** | RTOS 调试 | rtos debug, RTOS 调试 |
| **i2c-bus** | I²C 总线驱动 | i2c, I2C |
| **spi-bus** | SPI 总线驱动 | spi, SPI |
| **uart-module** | UART 模块 | uart, UART |
| **can-debug** | CAN 总线调试 | can, CAN |
| **adc-module** | ADC 模块 | adc, ADC |
| **dma-module** | DMA 模块 | dma, DMA |
| **timer-module** | Timer 模块 | timer, 定时器 |
| **watchdog-module** | Watchdog 模块 | watchdog, 看门狗 |
| **flash-module** | Flash 模块 | flash, Flash |
| **flash-jlink** | JLink 烧录 | jlink, JLink |
| **flash-openocd** | OpenOCD 烧录 | openocd, OpenOCD |
| **flash-keil** | Keil 烧录 | keil, Keil |
| **flash-platformio** | PlatformIO 烧录 | platformio, PlatformIO |
| **flash-idf** | ESP-IDF 烧录 | esp-idf, ESP-IDF |
| **gang-flash** | 批量烧录 | gang flash, 批量烧录 |
| **sfud-module** | SFUD 存储模块 | sfud, SFUD |
| **elog-module** | ELog 日志模块 | elog, 日志 |
| **cmbacktrace-debug** | CmBacktrace 调试 | cmbacktrace, 堆栈跟踪 |
| **segger-rtt-module** | SEGGER RTT 模块 | segger rtt, RTT |

**覆盖领域**：

| 分类 | Skills |
|------|--------|
| **系统架构** | embedded, embedded-architect, embedded-system-design |
| **代码审查** | embedded-reviewer |
| **调试工具** | embedded-debugger-framework, rtos-debug, cmbacktrace-debug, segger-rtt-module |
| **STM32 开发** | stm32-hal-development, stm32-spl-development |
| **RTOS** | freertos-module, rtos-debug |
| **外设驱动** | i2c-bus, spi-bus, uart-module, adc-module, dma-module, timer-module, watchdog-module |
| **通信协议** | can-debug |
| **存储** | flash-module, sfud-module, flash-jlink, flash-openocd, flash-keil, flash-platformio, flash-idf, gang-flash |
| **日志** | elog-module |
| **学习资源** | embedded-learning-notes, embedded-learning-path-framework, embedded-note-templates, embedded-skills-map |

### 论文写作（1 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **paper-writing** | 论文写作辅助 | write paper, 写论文 |

### 生产力工具（5 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **grill-me** | 需求挖掘和对齐 | grill me, 需求挖掘 |
| **teach** | 技能教学和学习 | teach, 学习 |
| **handoff** | 上下文交接 | handoff, 交接 |
| **caveman** | 简化表达 | caveman, 简化 |
| **write-a-skill** | 创建新技能 | write skill, 创建技能 |

### 知识管理（1 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **knowledge-base-search** | 跨知识库检索 | search kb, 搜索知识库 |

### 个人工具（2 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **edit-article** | 文章编辑 | edit article, 编辑文章 |
| **obsidian-vault** | Obsidian 知识库管理 | obsidian, vault |

### 杂项工具（2 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **git-guardrails** | Git 安全防护 | git guardrails, Git 安全 |
| **migrate-to-shoehorn** | 迁移到 Shoehorn | migrate, 迁移 |

### 其他（3 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **agent-skills** | Agent 技能包 | agent skills |
| **git-workflow-skill** | Git 工作流 | git workflow |
| **learned** | 学习技能 | learned |

## 📈 统计信息

```mermaid
pie title Skills 分布
    "嵌入式开发" : 38
    "工程开发" : 6
    "生产力工具" : 5
    "学术研究" : 4
    "前端开发" : 2
    "个人工具" : 2
    "杂项工具" : 2
    "其他" : 3
    "论文写作" : 1
    "知识管理" : 1
```

| 分类 | 数量 | 占比 |
|------|------|------|
| **嵌入式开发** | **38** | **58.5%** |
| 工程开发 | 6 | 9.2% |
| 生产力工具 | 5 | 7.7% |
| 学术研究 | 4 | 6.2% |
| 前端开发 | 2 | 3.1% |
| 个人工具 | 2 | 3.1% |
| 杂项工具 | 2 | 3.1% |
| 其他 | 3 | 4.6% |
| 论文写作 | 1 | 1.5% |
| 知识管理 | 1 | 1.5% |
| **总计** | **65** | **100%** |

## 🚀 快速开始

### 安装技能

```bash
# 克隆技能仓库
git clone https://github.com/shuai-yemao/shuai-yemao-chip-skills.git ~/.claude/skills-tmp

# 复制到 skills 目录
cp -r ~/.claude/skills-tmp/skills/* ~/.claude/skills/

# 清理
rm -rf ~/.claude/skills-tmp
```

### 使用技能

```bash
# 启动 Claude Code
claude

# 直接使用技能
/write paper on AI          # 使用 academic-paper
/help me with TDD           # 使用 tdd
/design this API            # 使用 codebase-design
/embedded MCU problem       # 使用 embedded
```

## 🔧 自定义技能

### 创建新技能

```bash
# 创建技能目录
mkdir -p ~/.claude/skills/my-skill

# 创建 SKILL.md
cat > ~/.claude/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: "我的自定义技能"
---

# My Skill

## When to Use
- 当用户需要...

## How It Works
1. 步骤 1
2. 步骤 2

## Examples
- 示例 1
EOF
```

### 技能格式要求

```yaml
---
name: skill-name
description: "技能描述，包含触发关键词"
metadata:
  version: "1.0.0"
  last_updated: "2026-06-24"
  status: active
  task_type: open-ended
  related_skills:
    - related-skill-1
    - related-skill-2
---

# Skill Name

## When to Use
- 触发条件 1
- 触发条件 2

## How It Works
1. 步骤 1
2. 步骤 2

## Examples
- 示例 1
```

## 📚 相关仓库

| 仓库 | 内容 | 地址 |
|------|------|------|
| **shuai-yemao-chip** | 核心配置 | https://github.com/shuai-yemao/shuai-yemao-chip |
| **shuai-yemao-chip-skills** | 技能包（本仓库） | https://github.com/shuai-yemao/shuai-yemao-chip-skills |
| **shuai-yemao-workflow** | 工作流 | https://github.com/shuai-yemao/shuai-yemao-workflow |

## 📋 更新日志

### 2026-06-24

- ✅ 添加嵌入式开发技能（embedded）
- ✅ 重构 README，使用 Mermaid 图表
- ✅ 完善技能分类和描述
- ✅ 添加使用示例和自定义指南

## 📄 许可证

MIT License
