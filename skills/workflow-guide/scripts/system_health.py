#!/usr/bin/env python3
"""
Chip 系统健康诊断脚本
==============================
一键检查整个工作流体系的完整性：
  1. Skill 完整性 — 所有 SKILL.md 是否存在
  2. 核心文件存在性 — SOUL.md / USER.md / FACT.md / CLAUDE.md
  3. Workflow 脚本完整性 — shared.py + 6 Agent + 协调器
  4. 灵魂层同步 — SOUL.md <-> CLAUDE.md 一致性
  5. 锁状态 — ResourceLock 目录是否可写
  6. 依赖存在性 — 外部工具路径是否正确
  7. 配置一致性 — AGENT_MAP <-> WORKFLOWS 流水线匹配
  8. WorkflowState 状态

用法:
  python scripts/system_health.py          # 完整检查
  python scripts/system_health.py --quick   # 快速检查（跳过耗时项）
  python scripts/system_health.py --report  # 输出 JSON 报告

版本历史:
  v1.0.0 (2026-05-29) — 初始版本，8 维检查 + 评分
  v1.1.0 (2026-05-29) — 新增 KNOWN_TOOL_PATHS fallback，GUI 工具文件存在性检查，
                         修复 Git Bash PATH 不继承 Windows User PATH 的问题
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Windows GBK 控制台兼容
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 路径探测 ──────────────────────────────────────────────────────

def _find_agent_dir() -> Path | None:
    """自动探测 Agent 目录"""
    candidates = [
        Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data" / "Agents",
        Path(os.environ.get("CHERRY_AGENT_DIR", "")),
    ]
    for root in candidates:
        if not root.is_dir():
            continue
        # 优先选有 CLAUDE.md + memory/FACT.md 的（完整 Chip 配置）
        for d in sorted(root.iterdir()):
            if (d / "CLAUDE.md").exists() and (d / "memory" / "FACT.md").exists():
                return d
        # 退而求其次选有 memory/FACT.md 的
        for d in sorted(root.iterdir()):
            if (d / "memory" / "FACT.md").exists():
                return d
        # 再退选有 SOUL.md 的
        for d in sorted(root.iterdir()):
            if (d / "SOUL.md").exists():
                return d
    return None


def _find_skills_dir() -> Path | None:
    """自动探测 Skills 目录"""
    candidates = [
        Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data" / "Skills",
        Path(os.environ.get("CHERRY_SKILLS_DIR", "")),
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return None


def _find_workflow_scripts() -> Path | None:
    """自动探测 workflow 脚本目录"""
    skills = _find_skills_dir()
    if skills:
        return skills / "workflow" / "scripts"
    return None


# ── 检查项 ────────────────────────────────────────────────────────

@dataclass
class HealthItem:
    name: str
    status: bool          # True=通过, False=失败
    detail: str = ""
    severity: str = "error"  # error / warning / info

    def icon(self) -> str:
        return {"error": "[X]", "warning": "[!]", "info": "[i]"}.get(self.severity, "[?]")

    def __str__(self) -> str:
        return f"  {self.icon()} {self.name}: {self.detail}"


@dataclass
class HealthReport:
    timestamp: str = ""
    total: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    items: list[HealthItem] = field(default_factory=list)
    agent_dir: str = ""
    skills_dir: str = ""
    skills_count: int = 0

    def add(self, item: HealthItem):
        self.items.append(item)
        self.total += 1
        if item.status:
            self.passed += 1
        elif item.severity == "warning":
            self.warnings += 1
        else:
            self.failed += 1

    def score(self) -> int:
        """计算健康评分 (0-100)"""
        if self.total == 0:
            return 0
        # 基础分: passed/total * 100, 再扣减失败项的权重
        base = int((self.passed / self.total) * 100)
        # 失败项扣分: 每个 error 扣 15%, 每个 warning 扣 5%
        deductions = (self.failed * 15) + (self.warnings * 5)
        return max(0, min(100, base - deductions))

    def grade(self) -> str:
        s = self.score()
        if s == 100: return "健康"
        if s >= 80:  return "良好"
        if s >= 60:  return "警告"
        return "异常"

    def print_summary(self):
        print(f"\n{'='*55}")
        print(f"  Chip 系统健康诊断报告")
        print(f"  时间: {self.timestamp}")
        print(f"  Agent: {self.agent_dir}")
        print(f"  Skills: {self.skills_dir} ({self.skills_count})")
        print(f"{'='*55}")
        for item in self.items:
            print(item)
        print(f"{'='*55}")
        print(f"  评分: {self.score()}% [{self.grade()}]")
        print(f"  通过: {self.passed}/{self.total}  "
              f"失败: {self.failed}  警告: {self.warnings}")
        print(f"{'='*55}\n")

    def to_json(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_dir": self.agent_dir,
            "skills_dir": self.skills_dir,
            "skills_count": self.skills_count,
            "score": self.score(),
            "grade": self.grade(),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "items": [
                {"name": i.name, "status": i.status, "detail": i.detail, "severity": i.severity}
                for i in self.items
            ],
        }


def check_skills_integrity(report: HealthReport, skills_dir: Path):
    """检查所有 skill 的 SKILL.md 存在性"""
    ok = 0
    missing = 0
    total = 0
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        # 跳过隐藏目录、内置目录和共享库目录（非 skill）
        if d.name.startswith(".") or d.name.startswith("__") or d.name == "shared":
            continue
        total += 1
        sk = d / "SKILL.md"
        if sk.exists():
            ok += 1
        else:
            missing += 1

    if missing == 0:
        report.add(HealthItem("Skill 完整性", True, f"{ok}/{total} 个 skill 正常", "info"))
    else:
        report.add(HealthItem("Skill 完整性", False,
                              f"{missing}/{total} 个 skill 缺少 SKILL.md（可能是非 skill 目录）", "warning"))

    # 检查是否有 pipeline.json 语法错误
    bad_json = 0
    for d in sorted(skills_dir.iterdir()):
        pj = d / "pipeline.json"
        if pj.exists():
            try:
                json.loads(pj.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                bad_json += 1
                report.add(HealthItem(f"JSON 语法 [{d.name}/pipeline.json]", False,
                                      "JSON 解析失败", "warning"))

    if bad_json == 0:
        report.add(HealthItem("pipeline.json 语法", True, "全部正常", "info"))


def check_core_files(report: HealthReport, agent_dir: Path):
    """检查核心文件存在性"""
    required = ["SOUL.md", "USER.md", "CLAUDE.md", "memory/FACT.md"]
    for f in required:
        fp = agent_dir / f
        ok = fp.exists() and fp.stat().st_size > 0
        if ok:
            kb = fp.stat().st_size / 1024
            report.add(HealthItem(f"核心文件 [{f}]", True, f"存在 ({kb:.1f} KB)", "info"))
        else:
            report.add(HealthItem(f"核心文件 [{f}]", False, "缺失或为空"))


def check_workflow_scripts(report: HealthReport, wf_scripts: Path | None):
    """检查 workflow 脚本完整性"""
    if not wf_scripts or not wf_scripts.is_dir():
        report.add(HealthItem("Workflow 脚本目录", False, "未找到 workflow/scripts/"))
        return

    required = [
        "shared.py", "workflow_coordinator.py",
        "build_agent.py", "dev_agent.py", "pm_agent.py",
        "verify_agent.py", "release_agent.py", "fix_agent.py",
        "sprint_helper.py",
    ]
    missing = []
    for s in required:
        if not (wf_scripts / s).exists():
            missing.append(s)

    if missing:
        report.add(HealthItem("Workflow 脚本完整性", False,
                              f"缺失: {', '.join(missing)}"))
    else:
        report.add(HealthItem("Workflow 脚本完整性", True,
                              f"{len(required)}/9 个脚本正常", "info"))


def check_soul_sync(report: HealthReport, agent_dir: Path):
    """检查 SOUL.md <-> CLAUDE.md 同步"""
    soul = agent_dir / "SOUL.md"
    claude = agent_dir / "CLAUDE.md"
    if not soul.exists() or not claude.exists():
        report.add(HealthItem("灵魂层同步", False, "SOUL.md 或 CLAUDE.md 不存在"))
        return

    soul_content = soul.read_text(encoding="utf-8")
    claude_content = claude.read_text(encoding="utf-8")

    if soul_content == claude_content:
        report.add(HealthItem("灵魂层同步", True, "SOUL.md == CLAUDE.md", "info"))
    else:
        report.add(HealthItem("灵魂层同步", False, "SOUL.md != CLAUDE.md，需要同步", "warning"))


def check_lock_status(report: HealthReport):
    """检查资源锁状态"""
    lock_dir = Path.home() / ".workflow_locks"
    if not lock_dir.is_dir():
        report.add(HealthItem("资源锁目录", True, "不存在（首次使用时会自动创建）", "info"))
        return

    # 尝试创建测试锁
    import random
    test_lock = lock_dir / f".health_check_{os.getpid()}"
    try:
        os.mkdir(str(test_lock))
        os.rmdir(str(test_lock))
        report.add(HealthItem("资源锁目录", True, "可写可用", "info"))
    except OSError as e:
        report.add(HealthItem("资源锁目录", False, f"不可写: {e}"))

    # 列出活跃锁
    active = [d.name for d in lock_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if active:
        report.add(HealthItem("活跃资源锁", True,
                              f"{len(active)} 个: {', '.join(active[:5])}", "info"))


def check_agent_map_consistency(report: HealthReport, wf_scripts: Path | None):
    """检查 AGENT_MAP 与 WORKFLOWS 一致性"""
    if not wf_scripts:
        return

    shared_file = wf_scripts / "shared.py"
    coord_file = wf_scripts / "workflow_coordinator.py"
    if not shared_file.exists() or not coord_file.exists():
        return

    # 提取 WORKFLOWS 和 AGENT_MAP 的键
    try:
        shared_content = shared_file.read_text(encoding="utf-8")
        coord_content = coord_file.read_text(encoding="utf-8")
    except Exception:
        return

    import re
    # 提取 WORKFLOWS 的键：只在 WORKFLOWS = { ... } 范围内匹配
    # 找 WORKFLOWS 定义区域，只匹配其中有 "steps" 子键的条目
    wf_match = re.search(r'WORKFLOWS\s*=\s*\{(.*?)\n\}', shared_content, re.DOTALL)
    if wf_match:
        wf_section = wf_match.group(1)
        wf_matches = re.findall(r'^\s+"([a-z][\w-]+)"\s*:\s*\{', wf_section, re.MULTILINE)
    else:
        wf_matches = []

    # 提取 AGENT_MAP 的键
    am_match = re.search(r'AGENT_MAP\s*=\s*\{(.*?)\n\}', coord_content, re.DOTALL)
    if am_match:
        am_section = am_match.group(1)
        am_matches = re.findall(r'^\s+"([a-z][\w-]+)"\s*:', am_section, re.MULTILINE)
    else:
        am_matches = []

    workflows_set = set(wf_matches) - {"DISCOVERED_PIPELINES", "PIPELINE_SOURCES"}
    agent_map_set = set(am_matches)

    in_wf_not_in_am = workflows_set - agent_map_set
    in_am_not_in_wf = agent_map_set - workflows_set

    if not in_wf_not_in_am and not in_am_not_in_wf:
        report.add(HealthItem("AGENT_MAP <-> WORKFLOWS 一致性", True,
                              f"{len(workflows_set)} 条流水线映射一致", "info"))
    else:
        detail_parts = []
        if in_wf_not_in_am:
            detail_parts.append(f"WORKFLOWS 有但 AGENT_MAP 无: {in_wf_not_in_am}")
        if in_am_not_in_wf:
            detail_parts.append(f"AGENT_MAP 有但 WORKFLOWS 无: {in_am_not_in_wf}")
        report.add(HealthItem("AGENT_MAP <-> WORKFLOWS 一致性", False,
                              "; ".join(detail_parts), "warning"))


# 已知工具安装路径（用作 PATH 查找的 fallback）
KNOWN_TOOL_PATHS: dict[str, list[str]] = {
    "J-Link (JLink.exe)": [
        r"C:\Program Files\SEGGER\JLink\JLink.exe",
        r"C:\Program Files (x86)\SEGGER\JLink\JLink.exe",
    ],
    "Keil UV4 (UV4.exe)": [
        r"G:\keil5\core\UV4\UV4.exe",
        r"C:\Keil_v5\UV4\UV4.exe",
        r"D:\Keil_v5\UV4\UV4.exe",
    ],
}


def _try_run(cmd: list[str], timeout: int = 5) -> str | None:
    """尝试执行命令，返回 stdout 或 stderr 的前 60 字符；失败返回 None"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        text = result.stdout.strip()[:60] or result.stderr.strip()[:60]
        return text if text else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _check_tool_version(name: str, cmd: list[str], extra_paths: list[str] = None,
                        timeout: int = 5) -> str | None:
    """通过 subprocess 获取工具版本信息，支持 fallback 路径"""
    version = _try_run(cmd, timeout=timeout)
    if version is None and extra_paths:
        for fp in extra_paths:
            if os.path.isfile(fp):
                version = _try_run([fp] + cmd[1:], timeout=timeout)
                if version:
                    break
    return version


def _check_tool_exists(paths: list[str]) -> str | None:
    """仅检查工具文件是否存在（用于 GUI 应用）"""
    for fp in paths:
        if os.path.isfile(fp):
            size_kb = os.path.getsize(fp) / 1024
            return f"存在 ({size_kb:.0f} KB)"
    return None


def check_dependencies(report: HealthReport):
    """检查外部工具的存在性"""
    # (name, cmd_or_paths, is_required, is_gui)
    checks: list[tuple[str, list[str] | list[list[str]], bool, bool]] = [
        ("Python", ["python", "--version"], True, False),
        ("Git", ["git", "--version"], False, False),
        ("J-Link (JLink.exe)", ["JLink.exe"], False, True),
        ("Keil UV4 (UV4.exe)", ["UV4.exe"], False, True),
    ]

    for name, spec, required, is_gui in checks:
        if is_gui:
            # GUI 应用：检查文件存在 + 已知路径
            gui_paths = KNOWN_TOOL_PATHS.get(name, [])
            result = _check_tool_exists(gui_paths)
            if result:
                report.add(HealthItem(f"外部工具 [{name}]", True, result, "info"))
            else:
                sev = "error" if required else "warning"
                report.add(HealthItem(f"外部工具 [{name}]", False, "未找到", sev))
        else:
            # CLI 应用：尝试 PATH + fallback
            extra_paths = KNOWN_TOOL_PATHS.get(name, None)
            version = _check_tool_version(name, spec, extra_paths)
            if version:
                report.add(HealthItem(f"外部工具 [{name}]", True, version, "info"))
            else:
                sev = "error" if required else "warning"
                report.add(HealthItem(f"外部工具 [{name}]", False, "未找到", sev))


def check_workflow_state(report: HealthReport):
    """检查 WorkflowState 状态"""
    state_file = Path.home() / ".workflow_state.json"
    if not state_file.exists():
        report.add(HealthItem("WorkflowState", True, "空（无状态文件）", "info"))
        return

    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        keys = list(data.keys())
        report.add(HealthItem("WorkflowState", True,
                              f"{len(keys)} 个 key: {', '.join(keys[:8])}", "info"))
    except (json.JSONDecodeError, OSError) as e:
        report.add(HealthItem("WorkflowState", False, f"读取失败: {e}", "warning"))


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Chip 系统健康诊断")
    parser.add_argument("--quick", action="store_true", help="快速检查（跳过耗时项）")
    parser.add_argument("--report", action="store_true", help="输出 JSON 报告到文件")
    args = parser.parse_args()

    report = HealthReport(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    agent_dir = _find_agent_dir()
    skills_dir = _find_skills_dir()
    wf_scripts = _find_workflow_scripts()

    if agent_dir:
        report.agent_dir = str(agent_dir)
    else:
        print("[X] 未检测到 Agent 目录")
        return 1

    if skills_dir:
        report.skills_dir = str(skills_dir)
        report.skills_count = sum(1 for d in skills_dir.iterdir()
                                   if d.is_dir()
                                   and not d.name.startswith(".")
                                   and not d.name.startswith("__")
                                   and (d / "SKILL.md").exists())
    else:
        print("[X] 未检测到 Skills 目录")
        return 1

    # 执行检查项
    check_skills_integrity(report, skills_dir)
    check_core_files(report, agent_dir)
    check_workflow_scripts(report, wf_scripts)
    check_soul_sync(report, agent_dir)
    check_lock_status(report)
    check_agent_map_consistency(report, wf_scripts)

    if not args.quick:
        check_dependencies(report)

    check_workflow_state(report)

    # 输出
    report.print_summary()

    if args.report:
        import datetime as dt
        out_name = f"health_report_{dt.date.today().isoformat()}.json"
        out_path = Path.cwd() / out_name
        out_path.write_text(json.dumps(report.to_json(), indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"  报告已保存: {out_path}")

    # exit 0=健康/良好, 1=警告, 2=异常
    score_val = report.score()
    if score_val >= 60:
        return 0 if score_val >= 80 else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
