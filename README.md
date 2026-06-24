# Shuai Yemao Chip Skills

Claude Code 技能包集合 — 用于自动化各种开发任务。

## 目录结构

```
skills/
├── academic-research-skills/   # 学术研究技能
├── agent-skills/               # Agent 技能
├── engineering/                # 工程技能
├── engineering-best-practices/ # 工程最佳实践
├── frontend-excellence/        # 前端开发技能
├── frontend-toolkit/           # 前端工具包
├── git-workflow-skill/         # Git 工作流技能
├── knowledge-base-search/      # 知识库搜索
├── learned/                    # 学习技能
├── misc/                       # 杂项技能
├── paper-writing/              # 论文写作技能
├── personal/                   # 个人技能
└── productivity/               # 生产力技能
```

## 核心技能

| 技能 | 描述 |
|------|------|
| `academic-research-skills` | 学术研究相关技能 |
| `agent-skills` | Agent 自动化技能 |
| `engineering` | 工程开发技能 |
| `frontend-excellence` | 前端开发最佳实践 |
| `git-workflow-skill` | Git 工作流自动化 |
| `paper-writing` | 论文写作辅助 |
| `productivity` | 生产力提升技能 |

## 使用方法

```bash
# 从技能运行
Skill({ name: 'skill-name', args: { ... } })

# 或在 Claude Code 中直接使用
/<skill-name>
```

## 开发

```bash
# 添加新技能
mkdir skills/new-skill
# 创建 SKILL.md 文件

# 运行测试
npm test
```

## 许可证

MIT License
