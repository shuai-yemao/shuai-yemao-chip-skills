#!/usr/bin/env python
"""Workflow 多 Agent 协调器。

轻量路由层，接收用户请求 → 路由到对应 Agent 脚本。
兼容原 workflow_runner.py 的 CLI 接口。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (
    SKILLS_ROOT, WORKFLOWS, STEP_LABELS, discover_step_label,
    scan_all_skills_for_pipelines, get_merged_workflows,
    get_pipeline_source, SCRIPT_MAP, ResourceLock,
    add_common_args, check_and_run_chain, WorkflowState,
    WORKFLOW_CHAINS, AgentQueue, AGENT_QUEUES,
    AGENT_QUEUE_ROUTES, trigger_pipeline_via_queue,
    AgentInterrupt,
)

LOG_DIR = Path.home() / ".workflow_logs"

AGENT_MAP = {
    # build-agent
    "build-flash-monitor": "build_agent.py",
    "build-flash-debug":   "build_agent.py",
    "full-cycle":          "build_agent.py",
    # dev-agent
    "bsp-bringup":         "dev_agent.py",
    "add-peripheral":      "dev_agent.py",
    "sprint-dev":          "dev_agent.py",
    "code-review-pipeline":"dev_agent.py",
    "unit-test-pipeline":  "dev_agent.py",
    "arch-review":         "dev_agent.py",
    "dashboard":           "dev_agent.py",
    "project-dev":         "dev_agent.py",
    "skill-optimize":      "dev_agent.py",
    "skill-maintenance":   "dev_agent.py",
    # pm-agent
    "init-project":        "pm_agent.py",
    "sprint-plan":         "pm_agent.py",
    "sprint-wrap":         "pm_agent.py",
    "risk-log":            "pm_agent.py",
    "change-assess":       "pm_agent.py",
    # verify-agent
    "hw-integration":      "verify_agent.py",
    "stress-test":         "verify_agent.py",
    "schematic-review":    "verify_agent.py",
    # release-agent
    "release-prep":        "release_agent.py",
    "release":             "release_agent.py",
    "ota-release":         "release_agent.py",
    # dev-agent
    "cloud-access":        "dev_agent.py",
    # fix-agent
    "fix-verify-commit":   "fix_agent.py",
}

AGENT_DISPLAY = {
    "build_agent.py":   "build-agent (编译/烧录/监控)",
    "dev_agent.py":     "dev-agent (需求调研/开发循环/代码审查)",
    "pm_agent.py":      "pm-agent (项目管理/Sprint)",
    "verify_agent.py":  "verify-agent (硬件验证/压力测试)",
    "release_agent.py": "release-agent (发布管理/签名)",
    "fix_agent.py":     "fix-agent (Bug修复闭环)",
}

SCRIPTS_DIR = Path(__file__).resolve().parent


def list_all(args) -> int:
    merged = get_merged_workflows()
    shown = set()

    print(f"\n{'='*60}")
    print(f"  Workflow 流水线一览（多 Agent 架构）")
    print(f"{'='*60}")

    # 按 Agent 分组
    by_agent: dict[str, list[str]] = {}
    for pipe_name, agent_script in AGENT_MAP.items():
        by_agent.setdefault(agent_script, []).append(pipe_name)

    for agent_script, pipe_names in sorted(by_agent.items()):
        display = AGENT_DISPLAY.get(agent_script, agent_script)
        print(f"\n  [{display}]:")
        for name in pipe_names:
            if name in merged:
                wf = merged[name]
                steps_str = " → ".join(discover_step_label(s) for s in wf["steps"])
                print(f"    {name}")
                print(f"      描述: {wf['description']}")
                print(f"      步骤: {steps_str}")
                # 显示链式触发信息
                chain = WORKFLOW_CHAINS.get(name)
                if chain:
                    nxt = chain.get("next", "")
                    desc = chain.get("description", "")
                    print(f"      ⤷ 完成后自动: {nxt} ({desc})")
                shown.add(name)

    # 动态注册的流水线
    discovered = scan_all_skills_for_pipelines()
    if discovered:
        dynamic_only = {n for n in discovered if n not in AGENT_MAP}
        if dynamic_only:
            print(f"\n  [动态注册流水线]:")
            for name in sorted(dynamic_only):
                wf = discovered[name]
                steps_str = " → ".join(discover_step_label(s) for s in wf["steps"])
                src = get_pipeline_source(name)
                print(f"    {name} (来自 {src})")
                print(f"      描述: {wf.get('description', '')}")
                print(f"      步骤: {steps_str}")

    print(f"\n  构建系统: {', '.join(SCRIPT_MAP.keys())}")
    print(f"  总计: {len(merged)} 条流水线")
    return 0


def detect_all(args) -> int:
    print(f"\n{'='*60}")
    print(f"  Workflow 多 Agent 环境探测")
    print(f"{'='*60}")

    # 检查各 Agent 脚本
    for agent_script, display in AGENT_DISPLAY.items():
        path = SCRIPTS_DIR / agent_script
        exists = path.exists()
        icon = "[OK]" if exists else "[X]"
        print(f"  {icon} {display}: {path}")

    # 检查 sprint_helper
    sh_path = SCRIPTS_DIR / "sprint_helper.py"
    print(f"  {'[OK]' if sh_path.exists() else '[X]'} sprint_helper.py: {sh_path}")

    # 检查共享模块
    shared_path = SCRIPTS_DIR / "shared.py"
    print(f"  {'[OK]' if shared_path.exists() else '[X]'} shared.pyd: {shared_path}")

    # 检查资源锁目录
    ResourceLock.cleanup_stale()
    locks = ResourceLock.list_locks()
    if locks:
        print(f"\n  [i] 活跃资源锁 ({len(locks)}):")
        for l in locks:
            print(f"    {l['file']} (pid={l['pid']})")
    else:
        print(f"\n  [i] 无活跃资源锁")

    # 检查链式触发
    if WORKFLOW_CHAINS:
        print(f"\n  链式触发配置 ({len(WORKFLOW_CHAINS)}):")
        for pipe_name, cfg in WORKFLOW_CHAINS.items():
            print(f"    {pipe_name} → {cfg.get('next', '?')}: {cfg.get('description', '')}")

    # 检查共享状态
    state = WorkflowState.snapshot()
    if state:
        print(f"\n  [i] 共享状态 ({len(state)} keys):")
        for k, v in state.items():
            print(f"    {k} = {v}")

    # 检查构建系统
    print(f"\n  支持构建系统: {', '.join(SCRIPT_MAP.keys())}")
    print(f"  流水线总数: {len(get_merged_workflows())}")
    return 0


def dispatch(args) -> int:
    """路由到目标 Agent 脚本"""
    agent_script = AGENT_MAP.get(args.run)
    if not agent_script:
        # 检查是否是动态注册的
        discovered = scan_all_skills_for_pipelines()
        if args.run in discovered:
            wf = discovered[args.run]
            steps = wf.get("steps", [])
            print(f"\n[i] '{args.run}' 是动态注册流水线 (来自 {get_pipeline_source(args.run)})")
            print(f"    步骤: {', '.join(steps)}")
            print(f"    没有专用 Agent，将由当前 Agent 直接处理")
            return handle_dynamic(args.run, wf, args)
        print(f"[X] 未知流水线: {args.run}")
        print(f"    使用 --list 查看所有可用流水线")
        return 1

    agent_path = SCRIPTS_DIR / agent_script
    if not agent_path.exists():
        print(f"[X] Agent 脚本不存在: {agent_path}")
        return 1

    # 构建转发命令：把同名参数传给子 Agent
    import subprocess
    cmd = [sys.executable, str(agent_path)]

    # 转发 CLI 参数
    arg_map = vars(args)
    positional = ["run", "build_system", "project", "target", "port", "baud",
                  "artifact", "flash_interface", "flash_target", "duration",
                  "save", "issue", "result", "commit_msg",
                  "devlog_project_name", "devlog_session_num", "devlog_start_time",
                  "devlog_work_done", "devlog_problems", "devlog_features",
                  "devlog_progress", "devlog_achieved", "devlog_pending",
                  "devlog_next_steps", "devlog_notes", "devlog_output",
                  "sprint", "backlog_ids", "source_chip", "target_chip",
                  "layers", "porting_type", "archive_obsidian", "import_kb",
                  "tags", "output"]

    bool_flags = ["dry_run", "skip_conflict_check", "verbose",
                  "archive_obsidian", "import_kb"]

    for key in positional:
        val = arg_map.get(key)
        if val is not None and val != parser.get_default(key):
            cli_key = key.replace("_", "-")
            if isinstance(val, bool) and val:
                cmd.append(f"--{cli_key}")
            elif isinstance(val, list):
                cmd.append(f"--{cli_key}")
                cmd.extend(str(v) for v in val)
            else:
                cmd.append(f"--{cli_key}")
                cmd.append(str(val))

    for key in bool_flags:
        if arg_map.get(key):
            cmd.append(f"--{key.replace('_', '-')}")

    print(f"\n{'='*60}")
    print(f"  [协调器] 路由 '{args.run}' → {AGENT_DISPLAY.get(agent_script, agent_script)}")
    print(f"{'='*60}\n")

    proc = subprocess.run(cmd, cwd=os.getcwd() if hasattr(os, 'getcwd') else None)
    if proc.returncode != 0:
        return proc.returncode

    # 流水线完成后检查链式触发
    chain_rc = check_and_run_chain(args.run, args)
    return chain_rc if chain_rc != 0 else 0


def handle_dynamic(name: str, wf: dict, args) -> int:
    """处理动态注册的流水线（无专用 Agent 时直接执行）"""
    from shared import run_step, resolve_script, extract_errors, print_error_report
    steps = wf.get("steps", [])
    total = len(steps)

    for i, step in enumerate(steps):
        label = discover_step_label(step)
        script = resolve_script(args.build_system or "keil", step)
        if not script or not script.exists():
            print(f"\n[X] [{i+1}/{total}] {label} — 无可用脚本")
            continue

        print(f"\n[i] [{i+1}/{total}] {label} (来自动态流水线 '{name}')")
        ok, stdout, stderr = run_step(step, [sys.executable, str(script)])
        if not ok:
            report = extract_errors(stdout, stderr, step)
            print_error_report(report, label)
            print(f"\n[X] [{label}] 失败")
            return 1

    print(f"\n[OK] 动态流水线 {name} 完成")
    return 0


import os


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Workflow 多 Agent 协调器")
    add_common_args(p)
    p.add_argument("--state", action="store_true", help="查看共享状态")
    p.add_argument("--clear-state", action="store_true", help="清空共享状态")
    p.add_argument("--queue", nargs="?", const="all", default=None,
                   help="启动队列监听模式（指定队列名或 all）")
    p.add_argument("--queue-send", nargs=2, metavar=("QUEUE", "PIPELINE"),
                   help="发送消息到队列触发流水线: --queue-send build build-flash-monitor")
    p.add_argument("--queue-list", action="store_true", help="列出所有队列消息")
    p.add_argument("--queue-purge", nargs="+", metavar="QUEUE",
                   help="清空指定队列消息: --queue-purge build dev")
    p.add_argument("--interrupt", nargs=2, metavar=("AGENT", "REASON"),
                   help="发送中断信号: --interrupt build-agent '紧急烧录'")
    p.add_argument("--interrupt-list", action="store_true",
                   help="列出待处理的中断信号")
    p.add_argument("--interrupt-clear", nargs="?", const="all",
                   help="清除中断信号: --interrupt-clear build-agent")
    p.add_argument("--watchdog", action="store_true",
                   help="运行看门狗守护进程（检测锁超时自动回收）")
    p.add_argument("--watchdog-scan", action="store_true",
                   help="手动扫描并回收所有超时锁")
    return p


parser = build_parser()


def main() -> int:
    args = parser.parse_args()

    if args.list:
        return list_all(args)
    if args.detect:
        return detect_all(args)
    if args.state:
        s = WorkflowState.snapshot()
        if not s:
            print("[i] 共享状态为空")
        else:
            print(f"\nWorkflow 共享状态 ({len(s)} keys):")
            for k, v in s.items():
                print(f"  {k} = {v}")
        return 0
    if args.clear_state:
        WorkflowState.clear()
        print("[OK] 共享状态已清空")
        return 0

    # ── 中断操作 ──
    if args.interrupt:
        target, reason = args.interrupt
        AgentInterrupt.send(target, reason=reason, sender="user", priority=5)
        print(f"  [OK] 中断已发送: {target} ({reason})")
        return 0

    if args.interrupt_list:
        sigs = AgentInterrupt.list_pending()
        if not sigs:
            print("[i] 无待处理的中断")
        else:
            for s in sigs:
                print(f"  {s['target']} ← {s['sender']}: {s['reason']} "
                      f"(P{s.get('priority', 0)})")
        return 0

    if args.interrupt_clear:
        if args.interrupt_clear == "all":
            AgentInterrupt.clear_all()
            print("[OK] 所有中断已清除")
        else:
            AgentInterrupt.ack(args.interrupt_clear)
            print(f"[OK] {args.interrupt_clear} 中断已清除")
        return 0

    # ── 看门狗操作 ──
    if args.watchdog_scan:
        recovered = ResourceLock.watchdog_scan_all(max_age=60.0)
        if not recovered:
            print("[i] 看门狗扫描: 无超时锁")
        else:
            print(f"[i] 看门狗扫描: 回收 {len(recovered)} 个超时锁")
        return 0

    if args.watchdog:
        print("[i] 看门狗守护进程启动 (每 15s 扫描)")
        print("    Ctrl+C 停止")
        try:
            while True:
                ResourceLock.watchdog_scan_all(max_age=60.0)
                time.sleep(15)
        except KeyboardInterrupt:
            print("\n[i] 看门狗守护进程停止")
        return 0

    # ── 消息队列操作 ──
    if args.queue_list:
        for qname in sorted(AGENT_QUEUES.keys()):
            count = AgentQueue.count(qname)
            msgs = AgentQueue.list_messages(qname, limit=5)
            consumer = AGENT_QUEUES.get(qname, "?")
            print(f"{qname:<10} -> {consumer:<15} 待处理: {count}")
            if msgs:
                for m in msgs:
                    print(f"    [{m['id']}] {m['sender']} -> {m['type']} ({m['age']:.0f}s)")
        return 0

    if args.queue_purge:
        for qname in args.queue_purge:
            n = AgentQueue.purge(qname)
            print(f"  [OK] {qname}: 清除 {n} 条消息")
        return 0

    if args.queue_send:
        qname, pipeline = args.queue_send
        ok = trigger_pipeline_via_queue(qname, pipeline=pipeline)
        return 0 if ok else 1

    if args.queue:
        # 队列监听模式：持续消费消息
        from shared import consume_queue, AGENT_QUEUE_ROUTES
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if args.queue == "all":
            # 轮询所有队列
            print("[i] 队列监听模式 (all) — 每 2s 轮询所有队列")
            loop_count = 0
            while True:
                had_work = False
                for qname, (agent_script, _) in sorted(AGENT_QUEUE_ROUTES.items()):
                    rc = consume_queue(qname, agent_script, timeout=1.0)
                    if rc != 0:
                        had_work = True
                if not had_work:
                    loop_count += 1
                    if loop_count % 30 == 0:  # 每分钟打印一次心跳
                        print(f"[i] 队列监听中... (Ctrl+C 退出)")
                    time.sleep(2)
        else:
            # 监听单个队列
            if args.queue not in AGENT_QUEUE_ROUTES:
                print(f"[X] 未知队列: {args.queue}")
                return 1
            agent_script = AGENT_QUEUE_ROUTES[args.queue][0]
            print(f"[i] 队列监听模式: {args.queue} -> {agent_script}")
            while True:
                rc = consume_queue(args.queue, agent_script, timeout=5.0)
                if rc == 0:
                    print(f"[i] 等待消息... (Ctrl+C 退出)")
                    time.sleep(2)

    if not args.run:
        parser.print_help()
        return 1
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
