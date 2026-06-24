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
      embedded
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
        
        subgraph "嵌入式开发"
            A6[embedded/]
        end
        
        subgraph "论文写作"
            A7[paper-writing/]
        end
        
        subgraph "生产力工具"
            A8[productivity/]
            A8 --> A8a[grill-me]
            A8 --> A8b[teach]
            A8 --> A8c[handoff]
            A8 --> A8d[caveman]
        end
        
        subgraph "知识管理"
            A9[knowledge-base-search/]
        end
        
        subgraph "个人工具"
            A10[personal/]
            A10 --> A10a[edit-article]
            A10 --> A10b[obsidian-vault]
        end
        
        subgraph "杂项工具"
            A11[misc/]
            A11 --> A11a[git-guardrails]
            A11 --> A11b[migrate-to-shoehorn]
        end
        
        subgraph "其他"
            A12[agent-skills/]
            A13[git-workflow-skill/]
            A14[learned/]
        end
    end

    style A fill:#e1f5fe
    style A1 fill:#e3f2fd
    style A2 fill:#e8f5e9
    style A4 fill:#fff3e0
    style A6 fill:#fce4ec
    style A8 fill:#f3e5f5
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

### 嵌入式开发（1 个）

| 技能 | 描述 | 触发关键词 |
|------|------|-----------|
| **embedded** | 嵌入式系统开发专家 | embedded, MCU, STM32, ESP32, firmware |

**覆盖领域**：
- MCU 架构：STM32、ESP32、RISC-V、ARM Cortex
- 外设驱动：GPIO、ADC、DMA、Timer、I²C、SPI、UART、CAN
- 无线通信：BLE、WiFi、LoRa、GPS、MQTT
- RTOS：FreeRTOS 任务管理、队列、信号量
- 工具链：CMake、PlatformIO、ESP-IDF、OpenOCD

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
    "学术研究" : 4
    "工程开发" : 6
    "前端开发" : 2
    "嵌入式开发" : 1
    "论文写作" : 1
    "生产力工具" : 5
    "知识管理" : 1
    "个人工具" : 2
    "杂项工具" : 2
    "其他" : 3
```

| 分类 | 数量 | 占比 |
|------|------|------|
| 学术研究 | 4 | 13.3% |
| 工程开发 | 6 | 20.0% |
| 前端开发 | 2 | 6.7% |
| 嵌入式开发 | 1 | 3.3% |
| 论文写作 | 1 | 3.3% |
| 生产力工具 | 5 | 16.7% |
| 知识管理 | 1 | 3.3% |
| 个人工具 | 2 | 6.7% |
| 杂项工具 | 2 | 6.7% |
| 其他 | 3 | 10.0% |
| **总计** | **30** | **100%** |

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
