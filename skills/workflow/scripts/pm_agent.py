#!/usr/bin/env python
"""pm-agent: 项目管理 Agent，负责 Sprint 全流程管理。

负责流水线:
  - init-project:   创建 Backlog/Risk Register/docs 目录
  - sprint-plan:    生成 Sprint Plan 文档 + DoD
  - sprint-wrap:    开发日志 → Sprint Review → Sprint Retro
  - risk-log:       风险登记册更新
  - change-assess:  变更影响评估 + 七层引脚审查清单
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (AgentInterrupt, 
    SKILLS_ROOT, WORKFLOWS, STEP_LABELS, discover_step_label,
    resolve_script, run_step, add_common_args, ResourceLock, AGENT_PRIORITY,
)

_AGENT_PRIORITY = AGENT_PRIORITY["pm-agent"]

AGENT_NAME = "pm-agent"
MANAGED_PIPELINES = [
    "init-project", "sprint-plan", "sprint-wrap",
    "risk-log", "change-assess",
]


def handle_sprint_step(step: str, args) -> int:
    """调用 sprint_helper.py 执行 Sprint 管理操作"""
    script = SKILLS_ROOT / "workflow" / "scripts" / "sprint_helper.py"
    if not script.exists():
        print(f"[X] sprint_helper.py 不存在: {script}")
        return 1

    cmd = [sys.executable, str(script), "--project", args.project or "."]
    if args.sprint:
        cmd += ["--sprint", str(args.sprint)]
    if args.backlog_ids:
        cmd += ["--backlog-ids"] + [str(i) for i in args.backlog_ids]

    step_flags = {
        "init-bsp":       ["--init-project"],
        "sprint-plan":    ["--plan"],
        "sprint-review":  ["--review"],
        "sprint-retro":   ["--retro"],
        "risk-log":       ["--risk", "--list"],
        "change-assess":  ["--change", "--assess", getattr(args, 'assess', '默认变更')],
    }
    flags = step_flags.get(step, [])
    cmd += flags

    print(f"\n  $ {' '.join(cmd)}")
    ok, stdout, stderr = run_step(step, cmd)
    if not ok:
        print(f"[X] Sprint 步骤 [{step}] 失败")
        return 1
    return 0


def run_pipeline(name: str, args) -> int:
    wf = WORKFLOWS.get(name)
    if not wf:
        print(f"[X] 未知流水线: {name}")
        return 1

    steps = wf["steps"]
    total = len(steps)

    print(f"\n{'='*60}")
    print(f"  [{AGENT_NAME}] 执行流水线: {name}")
    print(f"  {'='*54}")
    print(f"  描述: {wf['description']}")
    if args.project:
        print(f"  路径: {args.project}")
    if args.sprint:
        print(f"  Sprint: {args.sprint}")
    print(f"{'='*60}\n")

    for i, step in enumerate(steps):
        # 检查中断信号
        AGENT_NAME_local = Path(__file__).stem.replace("_agent","")
        if AgentInterrupt.check_at_step(AGENT_NAME_local, i, len(steps),
                                         discover_step_label(step)):
            return 2  # 被中断
        label = discover_step_label(step)
        print(f"\n{'='*50}")
        print(f"[{i+1}/{total}] {label}")
        print(f"{'='*50}")

        # 使用资源锁保护 git/project 操作
        with ResourceLock("project", args.project or "default", timeout=30, agent_priority=_AGENT_PRIORITY) as lock:
            if not lock.acquired:
                print(f"  [!] 项目资源被占用，尝试继续")

            step_map = {
                "init-bsp": "init-bsp",
                "sprint-plan": "sprint-plan",
                "sprint-review": "sprint-review",
                "sprint-retro": "sprint-retro",
                "risk-log": "risk-log",
                "change-assess": "change-assess",
                "devlog": None,  # devlog 走 devlog 脚本
            }
            mapped_step = step_map.get(step)
            if mapped_step:
                rc = handle_sprint_step(mapped_step, args)
                if rc != 0:
                    return rc
            elif step == "devlog":
                script = resolve_script(args.build_system or "keil", step)
                if script and script.exists():
                    from shared import make_devlog_cmd
                    cmd = make_devlog_cmd(script, args)
                    ok, stdout, stderr = run_step(step, cmd)
                    if not ok:
                        print(f"[X] devlog 失败")
                        return 1
                else:
                    print(f"  [!] devlog 脚本不存在，跳过")
            else:
                print(f"  [-] pm-agent 不处理步骤: {label}，跳过")

    print(f"\n{'='*60}")
    print(f"  [OK] 流水线 {name} 完成 ({total}/{total} 步骤)")
    print(f"{'='*60}\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME}: 项目管理 Agent")
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
        script = SKILLS_ROOT / "workflow" / "scripts" / "sprint_helper.py"
        exists = script.exists()
        print(f"\n[{AGENT_NAME}] 环境探测:")
        print(f"  {'[OK]' if exists else '[X]'} sprint_helper.py: {script}")
        print(f"  {'[OK]' if Path(args.project or '.').exists() else '[i]'} 项目目录: {args.project or '(未指定)'}")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in MANAGED_PIPELINES:
        print(f"[X] pm-agent 不管理流水线: {args.run}")
        print(f"    管理范围: {', '.join(MANAGED_PIPELINES)}")
        return 1

    return run_pipeline(args.run, args)


if __name__ == "__main__":
    sys.exit(main())
