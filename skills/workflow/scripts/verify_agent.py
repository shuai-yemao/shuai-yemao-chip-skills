#!/usr/bin/env python
"""verify-agent: 硬件验证 Agent，负责外设测试和压力测试。

负责流水线:
  - hw-integration: 编译→烧录→外设通信测试→稳定性测试
  - stress-test:    烧录→长时间日志采集→结果分析

与 build-agent 共享编译/烧录逻辑，但侧重长时间运行验证。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (AgentInterrupt, 
    SKILLS_ROOT, WORKFLOWS, STEP_LABELS, discover_step_label,
    resolve_script, run_step, extract_errors, print_error_report,
    extract_artifact, make_build_cmd, make_flash_cmd, make_monitor_cmd,
    make_stress_test_cmd, add_common_args, ResourceLock,
    check_cross_skill_conflicts, print_conflict_report,
)

AGENT_NAME = "verify-agent"
MANAGED_PIPELINES = ["hw-integration", "stress-test", "schematic-review"]


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
        elif step in ("peripheral-test", "verify"):
            with ResourceLock("serial", args.port or "default", timeout=5) as lock:
                if not lock.acquired:
                    print(f"  [!] 串口 {args.port} 被占用，尝试继续")
                cmd = make_monitor_cmd(script, args)
        elif step == "schematic-review":
            cmd = [sys.executable, str(script), "analyze", "--all", "--json"]
            print(f"\n  [i] 原理图审查: 读取已保存的原理图数据 (如有)")
            print(f"  [i] 如需远程取新数据，先运行: python pcb_analyzer.py full")
        elif step == "stress-test":
            with ResourceLock("serial", args.port or "default", timeout=30) as lock:
                if not lock.acquired:
                    print(f"  [X] 串口 {args.port} 被占用，压力测试需要独占串口")
                    return 1
                print(f"\n  [i] 压力测试模式: {args.duration or 60} 秒连续日志采集")
                cmd = make_stress_test_cmd(script, args)
        else:
            print(f"  [-] verify-agent 不处理步骤: {label}，跳过")
            continue

        is_interactive = step in ("monitor",)
        ok, stdout, stderr = run_step(step, cmd, inherit_io=is_interactive,
                                       dry_run=args.dry_run)

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
    print(f"{'='*60}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME}: 硬件验证 Agent")
    add_common_args(parser)
    args = parser.parse_args()

    if args.list:
        print(f"\n[{AGENT_NAME}] 管理以下流水线:")
        for name in MANAGED_PIPELINES:
            wf = WORKFLOWS.get(name, {})
            steps_str = " → ".join(STEP_LABELS.get(s, s) for s in wf.get("steps", []))
            print(f"  {name}: {wf.get('description', '')}")
            print(f"    步骤: {steps_str}")
        return 0

    if args.detect:
        print(f"\n[{AGENT_NAME}] 环境探测:")
        for bs in ["keil", "cmake", "platformio"]:
            print(f"  [{bs}]")
            for step in ["build", "flash", "monitor"]:
                path = resolve_script(bs, step)
                exists = path and path.exists()
                icon = "[OK]" if exists else "[X]"
                print(f"    {icon} {step}: {path}")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in MANAGED_PIPELINES:
        print(f"[X] verify-agent 不管理流水线: {args.run}")
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
