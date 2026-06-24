#!/usr/bin/env python
"""开发日志生成工具。

在每个项目开发会话结束时，生成结构化的 Markdown 开发日志，
记录：时间、工作内容、问题与解决方案、功能实现、整体进度。

支持两种模式：
  1. 交互模式（--interactive）：逐项问答，适合 CLI 交互
  2. 参数模式（直接传参）：适合 workflow 流水线集成

默认输出路径：<project>/docs/开发日志/<日期>-<会话>.md
"""

from __future__ import annotations

import argparse
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


# ---------------------------------------------------------------------------
# Git 信息自动收集
# ---------------------------------------------------------------------------

def git_info(project_dir: str | None) -> dict[str, Any]:
    """自动从 git 仓库收集分支、最近提交、文件变更等信息。"""
    info: dict[str, Any] = {
        "branch": "N/A",
        "recent_commits": [],
        "changed_files": [],
        "commit_count_since": 0,
    }
    if not project_dir:
        return info
    cwd = project_dir if os.path.isdir(project_dir) else os.path.dirname(project_dir)

    def _run(*cmd: str) -> str:
        try:
            r = subprocess.run(
                ["git", "-C", cwd, *cmd],
                capture_output=True, text=True, encoding="utf-8",
                timeout=10,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    branch = _run("rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        info["branch"] = branch

    # 最近 5 个提交
    log = _run("log", "--oneline", "-5")
    if log:
        info["recent_commits"] = log.splitlines()

    # 当前未提交的变更
    status = _run("status", "--short")
    if status:
        info["changed_files"] = status.splitlines()

    # HEAD~1 以来的提交数（不含当前工作区）
    since = _run("rev-list", "--count", "HEAD^..HEAD")
    if since:
        try:
            info["commit_count_since"] = int(since)
        except ValueError:
            pass

    return info


def format_git_section(info: dict[str, Any]) -> str:
    """将 git 信息格式化为 markdown 表格行。"""
    lines = []
    lines.append(f"- **分支**: {info.get('branch', 'N/A')}")
    if info["recent_commits"]:
        lines.append("- **最近提交**:")
        for c in info["recent_commits"]:
            lines.append(f"  - `{c}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 文件变更分类
# ---------------------------------------------------------------------------

def classify_change(file_line: str) -> str:
    """根据 git status --short 前缀分类文件变更类型。"""
    prefix = file_line[:2].strip() if len(file_line) >= 2 else ""
    mapping = {
        "M": "修改",
        "A": "新增",
        "D": "删除",
        "R": "重命名",
        "C": "复制",
        "?": "未跟踪",
    }
    for k, v in mapping.items():
        if k in prefix:
            return v
    return "变更"


def format_changed_files(files: list[str]) -> str:
    """格式化文件变更列表为 markdown 表格。"""
    if not files:
        return "  无文件变更"
    lines = []
    lines.append("| 路径 | 变更类型 |")
    lines.append("|------|----------|")
    for f in files:
        if len(f) >= 3:
            prefix = f[:2]
            path = f[3:]
            change_type = classify_change(f)
        else:
            prefix = ""
            path = f
            change_type = "变更"
        lines.append(f"| {path} | {change_type} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Devlog 模板
# ---------------------------------------------------------------------------

DEVLOG_TEMPLATE = """# 开发日志

## 会话信息

- **日期**: {date}
- **时间**: {start_time} — {end_time}
- **项目**: {project_name}
- **会话序号**: #{session_num}
{git_section}

---

## 本次完成工作

{work_done}

---

## 遇到的问题及解决方案

{problems_solutions}

---

## 功能/模块变更

{features}

---

## 文件变更

{changed_files}

---

## 当前进度

- **整体进度**: {progress}%
- **已实现**: {achieved}
- **待完成**: {pending}

---

## 下一步计划

{next_steps}

---

## 备注

{notes}

---

*日志生成时间: {generated_at}*
"""


def _normalize_newlines(text: str) -> str:
    """将字符串中的 \\n 转义序列替换为实际换行符。"""
    return text.replace("\\n", "\n").replace("\\n", "\n")


def _format_table(content: str, headers: list[str]) -> str:
    """将 | 分隔的内容格式化为 markdown 表格。

    输入: "a | b | c"
    输出:
    | a | b | c |
    """
    lines = content.strip().split("\n")
    # 生成表头
    header = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    rows = []
    for line in lines:
        if not line.strip():
            continue
        if "|" in line:
            cells = [c.strip() for c in line.split("|")]
            rows.append("| " + " | ".join(cells) + " |")
        else:
            rows.append(f"| {line.strip()} |")
    if rows:
        return header + "\n" + sep + "\n" + "\n".join(rows)
    return content


def _format_list(text: str, *, inline: bool = False) -> str:
    """将文本格式化为列表。

    Args:
        text: 原始文本
        inline: 如果为 True，用逗号分隔（适合进度字段）
    """
    if not text or text == "（待补充）":
        return text
    text = _normalize_newlines(text)
    # 检测是否包含 | 分隔符，作为表格处理
    if "|" in text:
        return text
    # 检测是否有换行符
    if "\n" in text:
        lines = text.split("\n")
        if inline:
            # 逗号分隔的内联格式
            items = [l.strip().lstrip("- ") for l in lines if l.strip()]
            return "、".join(items)
        items = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                items.append(line)
            else:
                items.append(f"- {line}")
        return "\n".join(items)
    if inline:
        # 单行内联
        return text.lstrip("- ")
    return text


def generate_devlog(args: argparse.Namespace, git: dict[str, Any]) -> str:
    """生成开发日志 markdown 内容。"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    # 自动收集 git 信息
    git_section = format_git_section(git)

    # 文件变更
    changed = format_changed_files(git.get("changed_files", []))

    # 如果通过 CLI 传入了文件变更，优先使用
    if args.changed_files:
        changed = format_changed_files(args.changed_files)

    # 处理各字段
    work_done = _format_list(args.work_done) if args.work_done else "（待补充）"
    problems = _format_table(args.problems_solutions, ["问题", "原因", "方案"]) if args.problems_solutions else "（待补充）"
    features = _format_list(args.features) if args.features else "（待补充）"
    achieved = _format_list(args.achieved, inline=True) if args.achieved else "（待补充）"
    pending = _format_list(args.pending, inline=True) if args.pending else "（待补充）"
    next_steps = _format_list(args.next_steps) if args.next_steps else "（待补充）"
    notes_val = args.notes if args.notes else "无"

    return DEVLOG_TEMPLATE.format(
        date=date_str,
        start_time=args.start_time or time_str,
        end_time=time_str,
        project_name=args.project_name or Path(args.project or ".").name,
        session_num=args.session_num or 1,
        git_section=git_section,
        work_done=work_done,
        problems_solutions=problems,
        features=features,
        changed_files=changed,
        progress=args.progress or 0,
        achieved=achieved,
        pending=pending,
        next_steps=next_steps,
        notes=notes_val,
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
    )


# ---------------------------------------------------------------------------
# 输出路径
# ---------------------------------------------------------------------------

def resolve_output_path(project_dir: str | None, session_num: int) -> Path:
    """确定开发日志输出路径：<project>/docs/开发日志/<日期>-会话<序号>.md"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    if project_dir and os.path.isdir(project_dir):
        base = Path(project_dir)
    elif project_dir:
        base = Path(project_dir).parent
    else:
        base = Path.cwd()

    devlog_dir = base / "docs" / "开发日志"
    devlog_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名：日期-会话序号.md
    filename = f"{date_str}-会话{session_num}.md"
    return devlog_dir / filename


def find_next_session(project_dir: str | None) -> int:
    """自动查找下一个会话序号。"""
    if not project_dir or not os.path.isdir(project_dir):
        return 1
    devlog_dir = Path(project_dir) / "docs" / "开发日志"
    if not devlog_dir.exists():
        return 1
    max_num = 0
    for f in devlog_dir.glob("*.md"):
        # 匹配 "日期-会话N.md" 格式
        try:
            stem = f.stem
            parts = stem.split("-会话")
            if len(parts) == 2:
                num = int(parts[1])
                max_num = max(max_num, num)
        except (ValueError, IndexError):
            pass
    return max_num + 1


# ---------------------------------------------------------------------------
# 交互模式
# ---------------------------------------------------------------------------

def interactive_input(prompt: str, default: str = "") -> str:
    """交互式输入，支持默认值。"""
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    val = input(f"  {prompt}: ").strip()
    return val if val else "（待补充）"


def run_interactive(args: argparse.Namespace) -> argparse.Namespace:
    """交互模式：逐项问答收集信息。"""
    print("\n" + "=" * 50)
    print("  📝 开发日志 — 交互式录入")
    print("=" * 50)
    print("  （直接回车使用默认值 / 输入 ! 跳过当前项）")

    args.project_name = interactive_input("项目名称", args.project_name or "")
    args.start_time = interactive_input("开始时间", args.start_time or "")
    args.session_num = int(interactive_input("会话序号", str(args.session_num or find_next_session(args.project))))

    print("\n--- 本次完成工作 ---")
    print("  （每行一条，空行结束）")
    lines = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if line == "!":
            lines = []
            break
        lines.append(line)
    if lines:
        args.work_done = "\n".join(f"- {l}" for l in lines)

    print("\n--- 遇到的问题及解决方案 ---")
    print("  （格式: 问题 | 原因 | 解决方案，每行一条，空行结束）")
    lines = []
    while True:
        line = input("  > ").strip()
        if not line:
            break
        if line == "!":
            lines = []
            break
        lines.append(line)
    if lines:
        rows = []
        for l in lines:
            parts = [p.strip() for p in l.split("|")]
            if len(parts) == 3:
                rows.append(f"| {parts[0]} | {parts[1]} | {parts[2]} |")
            else:
                rows.append(f"| {l} | | |")
        args.problems_solutions = "\n".join(rows)

    args.features = interactive_input("功能/模块变更")
    args.progress = interactive_input("整体进度 (%)", "0")
    args.achieved = interactive_input("已实现")
    args.pending = interactive_input("待完成")
    args.next_steps = interactive_input("下一步计划")
    args.notes = interactive_input("备注", "无")

    return args


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="开发日志生成工具 — 在每个项目会话结束时生成结构化日志",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 核心参数
    p.add_argument("--project", help="项目目录路径（用于自动收集 git 信息和确定输出位置）")
    p.add_argument("--project-name", help="项目名称（默认从目录名推断）")
    p.add_argument("--session-num", type=int, default=0, help="会话序号（默认自动检测）")
    p.add_argument("--start-time", help="会话开始时间")

    # 工作内容
    p.add_argument("--work-done", help="本次完成的工作内容（支持 | 分隔多条）")
    p.add_argument("--problems-solutions", help="遇到的问题及解决方案")
    p.add_argument("--features", help="功能/模块变更")

    # 进度
    p.add_argument("--progress", type=int, default=0, help="整体进度百分比")
    p.add_argument("--achieved", help="已实现的内容")
    p.add_argument("--pending", help="待完成的内容")
    p.add_argument("--next-steps", help="下一步计划")
    p.add_argument("--notes", help="备注")

    # 文件变更（手动覆盖，自动从 git 收集）
    p.add_argument("--changed-files", nargs="*", help="文件变更列表（覆盖 git 自动检测）")

    # 输出
    p.add_argument("--output", help="输出路径（默认自动生成到 <project>/docs/开发日志/）")
    p.add_argument("--print", action="store_true", help="仅打印到控制台，不写文件")

    # 模式
    p.add_argument("-i", "--interactive", action="store_true", help="交互模式")

    # 显示参数（让 workflow 可以传 verbose）
    p.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # ── 交互模式 ──
    if args.interactive:
        args = run_interactive(args)

    # ── 自动检测会话序号 ──
    if not args.session_num or args.session_num <= 0:
        args.session_num = find_next_session(args.project)

    # ── 收集 git 信息 ──
    git = git_info(args.project)
    if args.verbose:
        print(f"\n  [!] Git 分支: {git['branch']}")
        if git["recent_commits"]:
            print(f"  [!] 最近提交 ({len(git['recent_commits'])}):")
            for c in git["recent_commits"]:
                print(f"       {c}")
        if git["changed_files"]:
            print(f"  [!] 未提交文件变更 ({len(git['changed_files'])}):")
            for f in git["changed_files"]:
                print(f"       {f}")

    # ── 生成日志 ──
    content = generate_devlog(args, git)

    # ── 仅打印 ──
    if args.print:
        print(content)
        return 0

    # ── 确定输出路径 ──
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = resolve_output_path(args.project, args.session_num)

    # ── 写文件 ──
    output_path.write_text(content, encoding="utf-8")
    print(f"\n  [OK] 开发日志已生成: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
