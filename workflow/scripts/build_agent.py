#!/usr/bin/env python
"""build-agent: 编译/烧录/串口监控/GDB 调试专用 Agent。

负责流水线:
  - build-flash-monitor: 编译 → 烧录 → 串口监控
  - build-flash-debug:   编译 → 烧录 → GDB 调试
  - full-cycle:          编译 → 烧录 → 串口监控 → 开发日志
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
    make_monitor_cmd, make_debug_cmd, make_capture_cmd,
    make_devlog_cmd, add_common_args, ResourceLock,
    check_cross_skill_conflicts, print_conflict_report,
    ErrorReport,
)

AGENT_NAME = "build-agent"
MANAGED_PIPELINES = ["build-flash-monitor", "build-flash-debug", "full-cycle"]


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

    # 资源锁: 烧录与串口互斥
    if "flash" in steps and "monitor" in steps:
        print("  [!] 检测到烧录+监控同流水线，注意串口资源竞争")
        print("     build-agent 将串行执行各步骤\n")

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
            # 烧录时持 J-Link 锁
            with ResourceLock("jlink", "default", timeout=60, agent_priority=_AGENT_PRIORITY) as lock:
                if not lock.acquired:
                    print(f"  [X] J-Link 被占用（{ResourceLock.is_locked('jlink','default')}），跳过烧录")
                    return 1
                cmd = make_flash_cmd(script, args, artifact)
        elif step == "monitor":
            # 串口监控时持串口锁 (非阻塞)
            with ResourceLock("serial", args.port or "default", timeout=5) as lock:
                if not lock.acquired:
                    print(f"  [!] 串口 {args.port} 被占用，尝试无锁监控")
                cmd = make_monitor_cmd(script, args)
        elif step == "debug":
            cmd = make_debug_cmd(script, args, artifact)
        elif step == "devlog":
            cmd = make_devlog_cmd(script, args)
        elif step == "capture":
            cmd = make_capture_cmd(script, args)
        else:
            print(f"  [-] build-agent 不处理步骤: {label}，跳过")
            continue

        is_interactive = step in ("monitor", "debug")
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
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME}: 编译/烧录/监控/调试 Agent")
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
            for step in ["build", "flash", "debug", "monitor"]:
                path = resolve_script(bs, step)
                exists = path and path.exists()
                icon = "[OK]" if exists else "[X]"
                print(f"    {icon} {step}: {path}")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in MANAGED_PIPELINES:
        print(f"[X] build-agent 不管理流水线: {args.run}")
        print(f"    管理范围: {', '.join(MANAGED_PIPELINES)}")
        return 1

    if not args.build_system:
        print("[X] 需要 --build-system 参数 (keil/cmake/platformio)")
        return 1

    # 冲突检测
    if not args.skip_conflict_check:
        conflict = check_cross_skill_conflicts(args.build_system, args.run)
        if not conflict.passed:
            print_conflict_report(conflict)
            return 1
        if conflict.warnings:
            for w in conflict.warnings:
                print(f"  [!] {w}")

    return run_pipeline(args.run, args)


if __name__ == "__main__":
    sys.exit(main())
