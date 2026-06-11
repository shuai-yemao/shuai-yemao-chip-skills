#!/usr/bin/env python
"""Sprint 敏捷管理辅助工具。

为 workflow 提供 Sprint Planning / Review / Retrospective 文档生成、
Backlog 管理、Risk Register 维护等功能。

用法:
  python sprint_helper.py --plan --project <path> --sprint <N>
  python sprint_helper.py --review --project <path> --sprint <N>
  python sprint_helper.py --retro --project <path> --sprint <N>
  python sprint_helper.py --backlog --project <path> --list
  python sprint_helper.py --backlog --project <path> --add "title" --priority P1
  python sprint_helper.py --risk --project <path> --list
  python sprint_helper.py --risk --project <path> --add "risk desc" --impact H --probability M
  python sprint_helper.py --change --project <path> --assess "change desc" --scope "引脚/外设/协议"
  python sprint_helper.py --init-project --project <path> [--template <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── 目录结构 ──

SPRINT_DIR_NAME = "docs/敏捷管理"
BACKLOG_FILE = "backlog.json"
RISK_FILE = "risk-register.json"
CHANGE_LOG_FILE = "change-log.jsonl"


# ── 路径解析 ──

def _ensure_project_dir(project: str) -> Path:
    p = Path(project)
    if p.suffix in (".uvprojx", ".uvproj"):
        p = p.parent.parent  # MDK-ARM → 项目根
    elif p.name == "MDK-ARM":
        p = p.parent
    elif not p.is_dir():
        # 尝试当作项目名，在项目模板中查找
        base = Path("D:/zhuomian/KEIL+Arduino+Vscode/Keil+STM32cubeMx/STM32F411CEU6/EmbeddedProject-Folder-Template-main/04_Software/01_Source_Code")
        candidate = base / p.name
        if candidate.exists():
            p = candidate
    return p


def _sprint_dir(project: str, sprint: int | None = None) -> Path:
    base = _ensure_project_dir(project) / SPRINT_DIR_NAME
    if sprint is not None:
        base = base / f"Sprint-{sprint:02d}"
    return base


def _backlog_path(project: str) -> Path:
    return _ensure_project_dir(project) / SPRINT_DIR_NAME / BACKLOG_FILE


def _risk_path(project: str) -> Path:
    return _ensure_project_dir(project) / SPRINT_DIR_NAME / RISK_FILE


def _change_log_path(project: str) -> Path:
    return _ensure_project_dir(project) / SPRINT_DIR_NAME / CHANGE_LOG_FILE


# ── Backlog 管理 ──

def _load_backlog(project: str) -> list[dict]:
    path = _backlog_path(project)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_backlog(project: str, items: list[dict]) -> None:
    path = _backlog_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _next_backlog_id(items: list[dict]) -> int:
    ids = [it.get("id", 0) for it in items]
    return max(ids, default=0) + 1


def cmd_backlog_list(project: str) -> int:
    items = _load_backlog(project)
    if not items:
        print(f"  [ ] Backlog 为空")
        return 0
    print(f"\n📋 Backlog ({len(items)} 项):")
    print(f"  {'─'*60}")
    by_status = {"todo": [], "in-progress": [], "done": []}
    for it in items:
        by_status.setdefault(it.get("status", "todo"), []).append(it)
    for status, label in [("todo", "待办"), ("in-progress", "进行中"), ("done", "已完成")]:
        group = by_status.get(status, [])
        if not group:
            continue
        print(f"\n  [{label}]")
        for it in sorted(group, key=lambda x: x.get("priority", "P3")):
            pid = it.get("id", "?")
            pri = it.get("priority", "P3")
            title = it.get("title", "无标题")
            est = it.get("estimate", "?")
            print(f"    #{pid:02d} [{pri}] {title} (估算: {est}h)")
    return 0


def cmd_backlog_add(project: str, title: str, priority: str, estimate: int,
                    sprint: int | None, category: str) -> int:
    items = _load_backlog(project)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    item = {
        "id": _next_backlog_id(items),
        "title": title,
        "priority": priority.upper() if priority else "P3",
        "estimate": estimate or 0,
        "category": category or "general",
        "status": "todo",
        "sprint": sprint,
        "created": now,
    }
    items.append(item)
    _save_backlog(project, items)
    print(f"  [OK] 添加 Backlog 项 #{item['id']:02d}: {title}")
    return 0


def cmd_backlog_status(project: str, item_id: int, status: str) -> int:
    items = _load_backlog(project)
    for it in items:
        if it.get("id") == item_id:
            it["status"] = status
            it["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_backlog(project, items)
            print(f"  [OK] #{item_id:02d} → {status}")
            return 0
    print(f"  [X] 未找到 #{item_id:02d}")
    return 1


# ── Risk Register 管理 ──

def _load_risks(project: str) -> list[dict]:
    path = _risk_path(project)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save_risks(project: str, items: list[dict]) -> None:
    path = _risk_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _risk_score(impact: str, probability: str) -> str:
    matrix = {
        ("H", "H"): "🔴 CRITICAL",
        ("H", "M"): "🟠 HIGH",
        ("H", "L"): "🟡 MEDIUM",
        ("M", "H"): "🟠 HIGH",
        ("M", "M"): "🟡 MEDIUM",
        ("M", "L"): "🟢 LOW",
        ("L", "H"): "🟡 MEDIUM",
        ("L", "M"): "🟢 LOW",
        ("L", "L"): "🟢 LOW",
    }
    return matrix.get((impact.upper(), probability.upper()), "🟡 MEDIUM")


def cmd_risk_list(project: str) -> int:
    items = _load_risks(project)
    if not items:
        print(f"  [ ] Risk Register 为空")
        return 0
    print(f"\n⚠️  Risk Register ({len(items)} 项):")
    print(f"  {'─'*60}")
    for it in sorted(items, key=lambda x: x.get("id", 0)):
        rid = it.get("id", "?")
        desc = it.get("description", "无描述")
        impact = it.get("impact", "M")
        prob = it.get("probability", "M")
        score = _risk_score(impact, prob)
        status = it.get("status", "open")
        mitigation = it.get("mitigation", "")
        print(f"  #{rid:02d} {score} [{status}]")
        print(f"      {desc}")
        if mitigation:
            print(f"      缓解: {mitigation}")
    return 0


def cmd_risk_add(project: str, description: str, impact: str, probability: str,
                 category: str) -> int:
    items = _load_risks(project)
    now = datetime.now().strftime("%Y-%m-%d")
    item = {
        "id": max([it.get("id", 0) for it in items], default=0) + 1,
        "description": description,
        "impact": impact.upper() if impact else "M",
        "probability": probability.upper() if probability else "M",
        "category": category or "技术",
        "status": "open",
        "created": now,
    }
    score = _risk_score(item["impact"], item["probability"])
    items.append(item)
    _save_risks(project, items)
    print(f"  [OK] 添加风险 #{item['id']:02d} {score}: {description}")
    return 0


def cmd_risk_mitigate(project: str, risk_id: int, mitigation: str) -> int:
    items = _load_risks(project)
    for it in items:
        if it.get("id") == risk_id:
            it["mitigation"] = mitigation
            it["status"] = "mitigated"
            it["updated"] = datetime.now().strftime("%Y-%m-%d")
            _save_risks(project, items)
            print(f"  [OK] #{risk_id:02d} 缓解措施已记录")
            return 0
    print(f"  [X] 未找到 #{risk_id:02d}")
    return 1


# ── Sprint Planning 文档生成 ──

def cmd_sprint_plan(project: str, sprint: int, backlog_items: list[int]) -> int:
    sdir = _sprint_dir(project, sprint)
    sdir.mkdir(parents=True, exist_ok=True)

    items = _load_backlog(project)
    selected = [it for it in items if it.get("id") in backlog_items] if backlog_items else items

    total_est = sum(it.get("estimate", 0) for it in selected if it.get("status") == "todo")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# Sprint {sprint:02d} Planning

- **创建时间**: {now}
- **Sprint 周期**: 待定 → 待定
- **总估算工时**: {total_est}h
- **参与人员**:

## Sprint Goal

```

```

## Backlog 项 ({len(selected)})

| ID | 优先级 | 标题 | 估算(h) | 分类 | 状态 |
|----|--------|------|---------|------|------|
"""
    for it in selected:
        content += f"| #{it.get('id','?'):02d} | {it.get('priority','P3')} | {it.get('title','?')} | {it.get('estimate','?')} | {it.get('category','?')} | {it.get('status','todo')} |\n"

    content += """
## Definition of Done

- [ ] 代码编译 0 Error 0 Warning
- [ ] 静态分析通过 (cppcheck)
- [ ] 烧录到目标板验证通过
- [ ] 串口/RTT 日志确认功能正常
- [ ] 代码审查通过
- [ ] 文档已同步 (注释/开发日志/接口说明)
- [ ] 问题记录已归档 (若有)

## 风险项

| ID | 风险描述 | 影响 | 概率 | 评分 | 缓解措施 |
|----|---------|------|------|------|---------|
"""
    risks = _load_risks(project)
    for it in risks:
        if it.get("status") == "open":
            score = _risk_score(it.get("impact", "M"), it.get("probability", "M"))
            content += f"| #{it.get('id','?'):02d} | {it.get('description','?')} | {it.get('impact','M')} | {it.get('probability','M')} | {score} | {it.get('mitigation','')} |\n"

    filepath = sdir / f"Sprint-{sprint:02d}-Plan.md"
    filepath.write_text(content, encoding="utf-8")
    print(f"  [OK] Sprint {sprint:02d} Plan → {filepath}")
    return 0


# ── Sprint Review 文档生成 ──

def cmd_sprint_review(project: str, sprint: int) -> int:
    sdir = _sprint_dir(project, sprint)
    sdir.mkdir(parents=True, exist_ok=True)

    items = _load_backlog(project)
    sprint_items = [it for it in items if it.get("sprint") == sprint or it.get("status") == "done"]
    done = [it for it in sprint_items if it.get("status") == "done"]
    wip = [it for it in sprint_items if it.get("status") == "in-progress"]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# Sprint {sprint:02d} Review

- **创建时间**: {now}
- **Sprint 周期**: 待定 → 待定

## 完成项 ({len(done)})

"""
    for it in done:
        content += f"- [#{it.get('id','?'):02d}] {it.get('title','?')}\n"

    if wip:
        content += f"""
## 未完成 ({len(wip)})

"""
        for it in wip:
            content += f"- [#{it.get('id','?'):02d}] {it.get('title','?')} (进行中)\n"

    content += """
## Demo 清单

- [ ] 功能演示
- [ ] 性能数据
- [ ] 问题回放 (若有)

## 反馈

### 干系人反馈
```

```

### 技术反馈
```

```

## 下一步

- [ ] 未完成的项移至下个 Sprint
- [ ] 新需求进入 Backlog
"""
    filepath = sdir / f"Sprint-{sprint:02d}-Review.md"
    filepath.write_text(content, encoding="utf-8")
    print(f"  [OK] Sprint {sprint:02d} Review → {filepath}")
    return 0


# ── Sprint Retrospective 文档生成 ──

def cmd_sprint_retro(project: str, sprint: int) -> int:
    sdir = _sprint_dir(project, sprint)
    sdir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# Sprint {sprint:02d} Retrospective

- **创建时间**: {now}

## 做得好的 (Keep)

1.
2.
3.

## 可以改进的 (Problem)

1.
2.
3.

## 行动项 (Try)

| 行动项 | 负责人 | 截止日期 |
|--------|--------|---------|
|  |  |  |
|  |  |  |
|  |  |  |

## 技术和流程反思

### 工具链/构建
```

```

### 测试/验证
```

```

### 沟通/协作
```

```

## 措施跟踪 (上次 Sprint)

| 措施 | 状态 | 备注 |
|------|------|------|
|  | [ ] |  |
|  | [ ] |  |
"""
    filepath = sdir / f"Sprint-{sprint:02d}-Retro.md"
    filepath.write_text(content, encoding="utf-8")
    print(f"  [OK] Sprint {sprint:02d} Retrospective → {filepath}")
    return 0


# ── Change Request 影响评估 ──

def cmd_change_assess(project: str, description: str, scope: str) -> int:
    """生成变更影响评估报告。"""
    path = _change_log_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 七层引脚审查模板 (嵌入式特有)
    pin_checklist = ""
    if "引脚" in scope or "GPIO" in scope.upper() or "外设" in scope:
        pin_checklist = """
## 引脚变更 7 层审查

- [ ] L1: 宏定义 — GPIO 端口/引脚/ADC 通道号与数据手册一致
- [ ] L2: GPIO_AppInit — 模式、成员、时钟使能、端口号匹配宏
- [ ] L3: EXTI 配置 — PortSource/PinSource 匹配新引脚
- [ ] L4: NVIC 通道 — EXTI_Line 与 ISR 正确映射
- [ ] L5: ISR 实现 — 各 ISR 只处理对应 EXTI_Line 范围
- [ ] L6: 功能代码 — ADC_ReadChannel/GPIO 读写通过宏间接引用
- [ ] L7: 注释同步 — 所有注解与实际一致
"""

    content = f"""# 变更请求 — {description}

- **创建时间**: {now}
- **变更范围**: {scope}
- **请求人**:
- **状态**: 待评估

## 变更描述

```

```

## 影响评估

| 维度 | 影响 | 工作量估算 |
|------|------|-----------|
| 代码修改 |  |  |
| 引脚/硬件 |  |  |
| 测试 |  |  |
| 文档 |  |  |
| 回归风险 |  |  |
{pin_checklist}
## 决策

- [ ] 批准
- [ ] 拒绝 (原因: )
- [ ] 推迟 (到 Sprint ____)

## 实施计划

| 步骤 | 描述 | 负责人 | 预计工时 |
|------|------|--------|---------|
|  |  |  |  |
|  |  |  |  |
"""

    # 保存到变更日志
    entry = {
        "time": now,
        "description": description,
        "scope": scope,
        "status": "assessing",
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 输出评估文档
    doc_dir = _ensure_project_dir(project) / "docs/变更管理"
    doc_dir.mkdir(parents=True, exist_ok=True)
    safe_name = description.replace(" ", "_").replace("/", "_")[:30]
    filepath = doc_dir / f"{datetime.now().strftime('%Y%m%d')}-{safe_name}.md"
    filepath.write_text(content, encoding="utf-8")
    print(f"  [OK] 变更评估文档 → {filepath}")
    print(f"  [!] 请补充变更描述后提交审批")
    return 0


# ── 项目初始化 ──

def cmd_init_project(project: str, template: str | None) -> int:
    """初始化敏捷管理目录结构。"""
    pdir = _ensure_project_dir(project)

    # 创建敏捷管理目录
    sprint_root = pdir / SPRINT_DIR_NAME
    sprint_root.mkdir(parents=True, exist_ok=True)

    # 创建空 backlog 和 risk register
    for fname, default in [
        (BACKLOG_FILE, []),
        (RISK_FILE, []),
    ]:
        fpath = sprint_root / fname
        if not fpath.exists():
            fpath.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")

    # 创建 docs 子目录
    for subdir in ["开发日志", "变更管理", "测试报告", "设计文档"]:
        (pdir / f"docs/{subdir}").mkdir(parents=True, exist_ok=True)

    # 检查是否有 .gitignore
    gitignore = pdir / ".gitignore"
    if not gitignore.exists():
        content = """# Build artifacts
MDK-ARM/**/*.o
MDK-ARM/**/*.d
MDK-ARM/**/*.crf
MDK-ARM/**/*.dep
MDK-ARM/**/*.hex
MDK-ARM/**/*.bin
MDK-ARM/**/*.axf
MDK-ARM/**/*.map
MDK-ARM/**/*.log
build/
*.elf

# IDE
MDK-ARM/*.uvoptx
MDK-ARM/*.uvguix.*

# OS
Thumbs.db
.DS_Store
"""
        gitignore.write_text(content, encoding="utf-8")
        print(f"  [OK] 创建 .gitignore")

    print(f"\n[OK] 项目初始化完成: {pdir}")
    print(f"  敏捷管理: {sprint_root}")
    print(f"  Backlog: {sprint_root / BACKLOG_FILE}")
    print(f"  Risk Register: {sprint_root / RISK_FILE}")
    print(f"  文档目录: docs/开发日志, docs/变更管理, docs/测试报告, docs/设计文档")
    return 0


# ── CLI ──

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sprint 敏捷管理辅助工具")
    p.add_argument("--project", required=True, help="工程路径")
    p.add_argument("--sprint", type=int, default=1, help="Sprint 编号")

    # Backlog
    p.add_argument("--backlog", action="store_true", help="Backlog 管理模式")
    p.add_argument("--list", action="store_true", help="列出项")
    p.add_argument("--add", help="添加项 (标题)")
    p.add_argument("--priority", default="P3", help="优先级 P0/P1/P2/P3")
    p.add_argument("--estimate", type=int, default=0, help="估算工时 (h)")
    p.add_argument("--category", default="general", help="分类")
    p.add_argument("--status", help="更新状态 (todo/in-progress/done)")
    p.add_argument("--item-id", type=int, help="项 ID")

    # Risk
    p.add_argument("--risk", action="store_true", help="Risk Register 管理")
    p.add_argument("--risk-add", help="添加风险描述")
    p.add_argument("--impact", default="M", help="影响 H/M/L")
    p.add_argument("--probability", default="M", help="概率 H/M/L")
    p.add_argument("--mitigate", help="缓解措施")
    p.add_argument("--risk-id", type=int, help="风险 ID")

    # Sprint Docs
    p.add_argument("--plan", action="store_true", help="生成 Sprint Planning 文档")
    p.add_argument("--review", action="store_true", help="生成 Sprint Review 文档")
    p.add_argument("--retro", action="store_true", help="生成 Sprint Retrospective 文档")
    p.add_argument("--backlog-ids", nargs="*", type=int, help="本 Sprint 选的 Backlog ID 列表")

    # Change
    p.add_argument("--change", action="store_true", help="变更请求模式")
    p.add_argument("--assess", help="变更描述")
    p.add_argument("--scope", default="代码", help="变更范围")

    # Project Init
    p.add_argument("--init-project", action="store_true", help="初始化项目管理结构")
    p.add_argument("--template", help="项目模板路径")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.init_project:
        return cmd_init_project(args.project, args.template)

    if args.backlog:
        if args.list:
            return cmd_backlog_list(args.project)
        if args.add:
            return cmd_backlog_add(args.project, args.add, args.priority,
                                    args.estimate, args.sprint, args.category)
        if args.item_id and args.status:
            return cmd_backlog_status(args.project, args.item_id, args.status)
        parser.print_help()
        return 1

    if args.risk:
        if args.list:
            return cmd_risk_list(args.project)
        if args.risk_add:
            return cmd_risk_add(args.project, args.risk_add, args.impact,
                                 args.probability, args.category)
        if args.risk_id and args.mitigate:
            return cmd_risk_mitigate(args.project, args.risk_id, args.mitigate)
        parser.print_help()
        return 1

    if args.change:
        if args.assess:
            return cmd_change_assess(args.project, args.assess, args.scope)
        parser.print_help()
        return 1

    if args.plan:
        return cmd_sprint_plan(args.project, args.sprint, args.backlog_ids or [])
    if args.review:
        return cmd_sprint_review(args.project, args.sprint)
    if args.retro:
        return cmd_sprint_retro(args.project, args.sprint)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
