#!/usr/bin/env python
"""fix-agent: Bug 修复闭环 Agent，复现→捕获→归档→提交。

负责流水线:
  - fix-verify-commit: 编译→烧录→日志采集→问题归档→Git提交

完整闭环:
  1. build:    编译修复后的代码，确保 0 Error
  2. flash:    烧录到目标板
  3. capture:  采集运行日志（验证修复效果）
  4. record:   更新 Obsidian 问题记录
  5. commit:   Git 提交并引用 Issue 编号
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (AgentInterrupt, 
    SKILLS_ROOT, WORKFLOWS, STEP_LABELS, discover_step_label,
    resolve_script, run_step, extract_errors, print_error_report,
    extract_artifact, make_build_cmd, make_flash_cmd,
    make_capture_cmd, make_record_cmd, make_commit_cmd,
    add_common_args, ResourceLock,
    check_cross_skill_conflicts, print_conflict_report,
)

AGENT_NAME = "fix-agent"
MANAGED_PIPELINES = ["fix-verify-commit"]


def run_pipeline(name: str, args) -> int:
    wf = WORKFLOWS.get(name)
    if not wf:
        print(f"[X] 未知流水线: {name}")
        return 1

    steps = wf["steps"]
    total = len(steps)
    artifact: str | None = args.artifact

    print(f"\n{'='*60}")
    print(f"  [{AGENT_NAME}] 执行流水线: {name}")
    print(f"  {'='*54}")
    print(f"  描述: {wf['description']}")
    print(f"  构建: {args.build_system}")
    if args.project:
        print(f"  路径: {args.project}")
    if args.issue:
        print(f"  问题: {args.issue}")
    if args.commit_msg:
        print(f"  提交: {args.commit_msg}")
    print(f"{'='*60}\n")

    for i, step in enumerate(steps):
        # 检查中断信号
        AGENT_NAME_local = Path(__file__).stem.replace("_agent","")
        if AgentInterrupt.check_at_step(AGENT_NAME_local, i, len(steps),
                                         discover_step_label(step)):
            return 2  # 被中断
        label = discover_step_label(step)
        script = resolve_script(args.build_system, step)
        if not script or not script.exists():
            print(f"\n[X] [{i+1}/{total}] {label} — 脚本不存在: {script}")
            return 1

        print(f"\n{'='*50}")
        print(f"[{i+1}/{total}] {label}")
        print(f"{'='*50}")

        if step == "build":
            cmd = make_build_cmd(script, args)
        elif step == "flash":
            with ResourceLock("jlink", "default", timeout=60, agent_priority=_AGENT_PRIORITY) as lock:
                if not lock.acquired:
                    print(f"  [X] J-Link 被占用，跳过烧录")
                    return 1
                cmd = make_flash_cmd(script, args, artifact)
        elif step == "capture":
            # 采集日志需要独占串口
            with ResourceLock("serial", args.port or "default", timeout=30) as lock:
                if not lock.acquired:
                    print(f"  [X] 串口 {args.port} 被占用，日志采集需独占")
                    return 1
                cmd = make_capture_cmd(script, args)
        elif step == "record":
            cmd = make_record_cmd(args)
            if not cmd:
                print(f"  [!] record_issue.py 未找到，跳过问题归档")
                continue
        elif step == "commit":
            # Git 操作需要项目锁
            with ResourceLock("git", args.project or "default", timeout=30) as lock:
                if not lock.acquired:
                    print(f"  [!] Git 操作被锁定，尝试继续")
                cmd = make_commit_cmd(args)
        else:
            print(f"  [-] fix-agent 不处理步骤: {label}，跳过")
            continue

        ok, stdout, stderr = run_step(step, cmd, dry_run=args.dry_run)

        if step == "build" and not args.dry_run and ok:
            found = extract_artifact(stdout)
            if found:
                artifact = found
                print(f"\n  [i] 检测到产物: {artifact}")

        if not ok and not args.dry_run:
            report = extract_errors(stdout, stderr, step)
            print_error_report(report, label)
            print(f"\n[X] [{label}] 失败，流水线终止")
            return 1

    print(f"\n{'='*60}")
    print(f"  [OK] 流水线 {name} 完成 ({total}/{total} 步骤)")
    if args.issue:
        print(f"  [i] 问题记录: {args.issue}")
    if args.commit_msg:
        print(f"  [i] Git 提交: {args.commit_msg}")
    print(f"{'='*60}\n")

    # [Passive Trigger] Bug 修复完成后，检查是否暴露了 skill 缺口
    print(f"\n  [i] 被动触发: 检查 skill 优化机会")
    print(f"      Bug 根因是否暴露了现有 skill 的缺口？")
    print(f"      - 这个坑已在 skill 文档中记录了吗？")
    print(f"      - SKILL.md 是否需要补充新的陷阱/案例？")
    print(f"      → 如需优化, 执行: workflow --run skill-optimize")
    print(f"      → 或说「优化 <技能名> skill」\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME}: Bug 修复闭环 Agent")
    add_common_args(parser)
    args = parser.parse_args()

    if args.list:
        print(f"\n[{AGENT_NAME}] 管理以下流水线:")
        for name in MANAGED_PIPELINES:
            wf = WORKFLOWS.get(name, {})
            steps_str = " → ".join(STEP_LABELS.get(s, s) for s in wf.get("steps", []))
            print(f"  {name}: {wf.get('description', '')}")
            print(f"    步骤: {steps_str}")
            print(f"    参数: --issue <问题路径> --result <结果> --commit-msg <提交信息>")
        return 0

    if args.detect:
        print(f"\n[{AGENT_NAME}] 环境探测:")
        for bs in ["keil", "cmake", "platformio"]:
            print(f"  [{bs}]")
            for step in ["build", "flash", "capture", "record", "commit"]:
                path = resolve_script(bs, step)
                exists = path and path.exists()
                icon = "[OK]" if exists else "[X]"
                print(f"    {icon} {step}: {path}")
        # 检查 git
        import subprocess
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5)
            print(f"  [OK] git: 已安装")
        except Exception:
            print(f"  [X] git: 未安装或不在 PATH 中")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in MANAGED_PIPELINES:
        print(f"[X] fix-agent 不管理流水线: {args.run}")
        print(f"    管理范围: {', '.join(MANAGED_PIPELINES)}")
        return 1

    if not args.build_system:
        print("[X] 需要 --build-system 参数 (keil/cmake/platformio)")
        return 1

    if not args.skip_conflict_check:
        conflict = check_cross_skill_conflicts(args.build_system, args.run)
        if not conflict.passed:
            print_conflict_report(conflict)
            return 1

    return run_pipeline(args.run, args)


if __name__ == "__main__":
    sys.exit(main())
