#!/usr/bin/env python
"""dev-agent: 开发循环 Agent，含静态分析、单元测试、代码审查、架构评审。

负责流水线:
  - bsp-bringup:         编译→烧录→功能验证→开发日志
  - add-peripheral:      编译→烧录→外设测试→OOP检查→开发日志
  - sprint-dev:          编译→静态分析→烧录→监控→验证→开发日志
  - code-review-pipeline:静态分析→代码审查→编译→验证
  - unit-test-pipeline:  静态分析→单元测试→编译
  - arch-review:         架构评审
  - dashboard:           仪表盘
  - project-dev:         需求细化→多源调研→方案设计→执行开发→开发日志
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (AgentInterrupt, 
    SKILLS_ROOT, WORKFLOWS, STEP_LABELS, STEP_ICONS, discover_step_label,
    resolve_script, run_step, extract_errors, print_error_report,
    extract_artifact, make_build_cmd, make_flash_cmd, make_monitor_cmd,
    make_devlog_cmd, make_static_analysis_cmd, make_map_analyze_cmd,
    make_dashboard_cmd, add_common_args, ResourceLock,
    check_cross_skill_conflicts, print_conflict_report,
    WorkflowState, run_next_pipeline, WORKFLOW_CHAINS,
)

AGENT_NAME = "dev-agent"
MANAGED_PIPELINES = [
    "bsp-bringup", "add-peripheral", "sprint-dev",
    "code-review-pipeline", "unit-test-pipeline",
    "arch-review", "dashboard", "project-dev",
    "skill-optimize",
]


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
            # 对 AI 交互步骤允许无脚本（由 Chip 处理）
            if step in ("code-review", "arch-review", "oop-check", "refine", "research", "plan", "execute",
                         "skill-scan", "skill-fix"):
                print(f"\n[i] [{i+1}/{total}] {label} (交互式步骤，打印提示)")
            else:
                print(f"\n[X] [{i+1}/{total}] {label} — 脚本不存在: {script}")
                return 1

        print(f"\n{'='*50}")
        print(f"[{i+1}/{total}] {label}")
        print(f"{'='*50}")

        # --- 交互式步骤（打印提示）---
        if step == "code-review":
            print(f"\n  进入 [代码审查] 步骤")
            print(f"  {'='*54}")
            print(f"  已加载 embedded-reviewer（嵌入式审查官）")
            print(f"  ")
            print(f"  审查范围:")
            print(f"    - 七层引脚一致性")
            print(f"    - ISR 安全三原则")
            print(f"    - DMA 缓冲区生命周期")
            print(f"    - 并发五图分析")
            print(f"    - MISRA 高频违规 (Top 10)")
            print(f"    - 临界区/中断延迟")
            print(f"  ")
            print(f"  触发方式: 说 \"Review 这段代码\" 或 \"审查 XXX 模块\"")
            print(f"  {'='*54}")
            continue

        if step == "arch-review":
            print(f"\n  进入 [架构评审] 步骤")
            print(f"  {'='*54}")
            print(f"  已加载 embedded-architect（嵌入式架构师）")
            print(f"  ")
            print(f"  评审范围:")
            print(f"    - MCU 选型余量模型")
            print(f"    - 系统架构分层解耦")
            print(f"    - 引脚分配/外设互斥")
            print(f"    - RTOS 任务划分")
            print(f"    - 时钟树/资源架构")
            print(f"    - 第一板 bring-up 策略")
            print(f"  ")
            print(f"  触发方式: 说 \"架构评审 XXX\" 或 \"Review 系统设计\"")
            print(f"  {'='*54}")
            continue

        if step == "oop-check":
            print(f"\n  进入 [OOP 合规检查] 步骤")
            print(f"  {'='*54}")
            print(f"  检查清单:")
            print(f"    - 封装: struct 是否隐藏于 .c 中（信息隐藏）")
            print(f"    - 接口: BSP 是否仅暴露 HAL 级 Core API")
            print(f"    - 抽象层次: 是否有 On/Off/Toggle 等语义化命名")
            print(f"    - 依赖注入: 实现是否通过结构体句柄（避免全局变量）")
            print(f"    - 接口隔离: 是否通过前缀分离硬件差异")
            print(f"    - NULL 安全: 所有接口是否有 NULL 检查")
            print(f"  {'='*54}")
            continue

        # --- 前开发阶段 Meta 步骤（需求→调研→方案→执行）---
        if step == "refine":
            print(f"\n  进入 [需求细化] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 将模糊需求转化为具体的开发规格")
            print(f"  ")
            print(f"  检查清单 (需逐项确认):")
            print(f"    [1] 硬件上下文: MCU/探针/串口/工程路径")
            print(f"    [2] 功能需求: 输入/输出/性能指标/通信协议")
            print(f"    [3] 约束条件: Flash/RAM/引脚/成本/时间")
            print(f"    [4] 依赖检查: 已有代码/第三方库/硬件模块")
            print(f"    [5] 风险预判: 已知坑点/兼容性/时序约束")
            print(f"  ")
            print(f"  可用工具: brainstorming skill")
            print(f"  产出: 需求规格文档")
            print(f"  {'='*54}")
            continue

        if step == "research":
            print(f"\n  进入 [多源调研] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 通过多源检索确定技术方案（六源交叉验证）")
            print(f"  ")
            print(f"  检索管线 (逐级执行):")
            print(f"    [1] 本地 KB: kb_search.py (18863 chunks + Obsidian)")
            print(f"    [2] 厂商文档: 数据手册/参考手册/应用笔记")
            print(f"    [3] GitHub: 搜索成熟开源实现")
            print(f"    [4] 论坛: 电子发烧友/21ic/amoBBS/STM32社区")
            print(f"    [5] 博客/B站: 项目实战/踩坑经验")
            print(f"    [6] 真伪验证: verify_claims.py (评分≥0.70)")
            print(f"    [7] 方案对比: 至少 2-3 种方案，标注优缺点")
            print(f"  ")
            print(f"  产出: 技术方案对比报告（已通过真伪验证）")
            print(f"  {'='*54}")
            continue

        if step == "plan":
            print(f"\n  进入 [方案设计] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 将技术方案转化为可执行的开发计划")
            print(f"  ")
            print(f"  检查清单:")
            print(f"    [1] 架构设计: 模块划分/接口定义/数据流")
            print(f"    [2] 引脚分配: 七层一致性审查")
            print(f"    [3] 实施步骤: 按依赖排列执行顺序")
            print(f"    [4] 测试方案: 自检函数/测试用例/验收标准")
            print(f"    [5] 回滚方案: 出问题时如何回退")
            print(f"  ")
            print(f"  可用工具: writing-plans skill")
            print(f"  产出: 开发计划文档（可直接由 workflow 执行）")
            print(f"  {'='*54}")
            continue

        if step == "execute":
            print(f"\n  进入 [执行开发] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 按计划执行开发任务")
            print(f"  ")
            print(f"  根据方案选择对应流水线:")
            print(f"    - 新外设驱动 → add-peripheral")
            print(f"    - BSP 初始化 → bsp-bringup")
            print(f"    - Sprint 开发 → sprint-dev")
            print(f"    - 代码审查   → code-review-pipeline")
            print(f"    - 架构评审   → arch-review")
            print(f"    - 编译烧录   → build-flash-monitor")
            print(f"  ")
            print(f"  触发方式: 说 \"执行 <流水线名>\"")
            print(f"  Chip 将调用 coordinator 运行目标流水线")
            print(f"  状态文件 ~/.workflow_state.json 自动传递上下文")
            print(f"  {'='*54}")
            continue

        # --- 技能优化 AI 步骤 ---
        if step == "skill-scan":
            print(f"\n  进入 [技能扫描] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 评估所有嵌入式技能质量，识别低分技能")
            print(f"  ")
            print(f"  评估方法 (Darwin 8 维度):")
            print(f"    [1] Frontmatter 质量  (8分)")
            print(f"    [2] 工作流清晰度       (15分)")
            print(f"    [3] 边界条件覆盖       (10分)")
            print(f"    [4] 检查点设计         (7分)")
            print(f"    [5] 指令具体性         (15分)")
            print(f"    [6] 资源整合度         (5分)")
            print(f"    [7] 整体架构           (15分)")
            print(f"    [8] 实测表现           (25分)")
            print(f"  ")
            print(f"  输出: 低分技能列表 + 具体待改进项")
            print(f"  {'='*54}")
            continue

        if step == "skill-fix":
            print(f"\n  进入 [技能修复] 步骤")
            print(f"  {'='*54}")
            print(f"  目标: 按 skill-scan 结果和 research 素材修复 SKILL.md")
            print(f"  ")
            print(f"  操作流程:")
            print(f"    [1] 确认待修复技能列表")
            print(f"    [2] 逐一审查 SKILL.md 缺口")
            print(f"    [3] 补充缺失内容（陷阱/案例/章节）")
            print(f"    [4] kb-import 导入高价值素材到知识库")
            print(f"    [5] 更新 embedded-skills-map（如需）")
            print(f"    [6] 重新 register 确保生效")
            print(f"  ")
            print(f"  可用工具: darwin-skill (评分), kb-search (检索), kb-import (入库)")
            print(f"  {'='*54}")
            continue

        # --- 构建命令 ---
        if step == "build":
            cmd = make_build_cmd(script, args)
        elif step == "flash":
            with ResourceLock("jlink", "default", timeout=60, agent_priority=_AGENT_PRIORITY) as lock:
                if not lock.acquired:
                    print(f"  [X] J-Link 被占用，跳过烧录")
                    return 1
                cmd = make_flash_cmd(script, args, artifact)
        elif step == "monitor":
            with ResourceLock("serial", args.port or "default", timeout=5) as lock:
                if not lock.acquired:
                    print(f"  [!] 串口 {args.port} 被占用")
                cmd = make_monitor_cmd(script, args)
        elif step in ("peripheral-test", "verify"):
            with ResourceLock("serial", args.port or "default", timeout=5) as lock:
                cmd = make_monitor_cmd(script, args)
        elif step == "static-analysis":
            cmd = make_static_analysis_cmd(script, args)
        elif step == "unit-test":
            cmd = [sys.executable, str(script)]
            if args.project:
                p = Path(args.project)
                src = p.parent if p.suffix in (".uvprojx", ".uvproj") else p
                cmd += [str(src)]
        elif step == "devlog":
            cmd = make_devlog_cmd(script, args)
        elif step == "dashboard":
            cmd = make_dashboard_cmd(script, args)
        elif step == "map-analyze":
            cmd = make_map_analyze_cmd(script, args)
        else:
            print(f"  [-] dev-agent 不处理步骤: {label}，跳过")
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
    parser = argparse.ArgumentParser(description=f"{AGENT_NAME}: 开发循环 Agent")
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
            for step in ["build", "flash", "monitor", "static-analysis", "unit-test"]:
                path = resolve_script(bs, step)
                exists = path and path.exists()
                icon = "[OK]" if exists else "[X]"
                print(f"    {icon} {step}: {path}")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in MANAGED_PIPELINES:
        print(f"[X] dev-agent 不管理流水线: {args.run}")
        print(f"    管理范围: {', '.join(MANAGED_PIPELINES)}")
        return 1

    # 检查是否需要 build-system（arch-review/dashboard 不需要）
    from shared import WORKFLOWS as _WF
    _steps = _WF.get(args.run, {}).get("steps", [])
    _needs_build = any(s in _steps for s in ["build", "flash", "monitor", "debug", "capture",
                                              "static-analysis", "unit-test", "verify",
                                              "peripheral-test"])
    if _needs_build and not args.build_system:
        print("[X] 该流水线需要 --build-system 参数 (keil/cmake/platformio)")
        return 1

    if not args.skip_conflict_check and args.build_system:
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
