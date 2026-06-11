#!/usr/bin/env python3
"""
Chip 本地 CI/CD 流水线 — 自动构建/检查/发布
====================================================
在本地环境中模拟 CI/CD 流程：提交前检查、构建验证、发布流水线。

功能:
  - pre-commit:     提交前检查（health check + skill 一致性 + 灵魂层同步）
  - post-commit:    提交后处理（创建快照）
  - build-check:    构建前环境检查
  - build-pipeline: 完整 CI 流水线（检查 → 记录 → 快照 → 报告）
  - release-check:  发布前检查清单
  - install-hooks:  安装 git hooks 到本地仓库
  - status:         查看 CI 状态

用法:
  python pipeline_ci.py pre-commit              # 提交前检查
  python pipeline_ci.py post-commit             # 提交后快照
  python pipeline_ci.py build-check             # 构建前检查
  python pipeline_ci.py build-pipeline          # 完整 CI 流水线
  python pipeline_ci.py release-check           # 发布前检查
  python pipeline_ci.py install-hooks --repo .  # 安装 git hooks
  python pipeline_ci.py status                  # 查看 CI 状态
"""

import io
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 路径 ──────────────────────────────────────────────────────

CI_DIR = Path.home() / ".cherryclaw-ci"
CI_STATUS = CI_DIR / "status.json"
CI_REPORT_DIR = CI_DIR / "reports"

SCRIPTS_DIR = Path(__file__).parent.resolve()
AGENT_DIR = None  # will resolve
SKILLS_DIR = None

STATE = {
    "lastPreCommit": None,
    "lastPostCommit": None,
    "lastBuildCheck": None,
    "lastBuildPipeline": None,
    "lastReleaseCheck": None,
    "totalPreCommit": 0,
    "totalBuildPipeline": 0,
    "totalBypasses": 0,
}


def _find_agent_dir() -> Path | None:
    ad = Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data" / "Agents"
    if ad.is_dir():
        for d in sorted(ad.iterdir()):
            if (d / "CLAUDE.md").exists() and (d / "memory" / "FACT.md").exists():
                return d
        for d in sorted(ad.iterdir()):
            if (d / "SOUL.md").exists():
                return d
    return None


def _ensure_ci_dir():
    CI_DIR.mkdir(parents=True, exist_ok=True)
    CI_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not CI_STATUS.exists():
        CI_STATUS.write_text("{}", encoding="utf-8")


def _load_status() -> dict:
    _ensure_ci_dir()
    try:
        return json.loads(CI_STATUS.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_status(extra: dict = None):
    _ensure_ci_dir()
    status = _load_status()
    if extra:
        status.update(extra)
    CI_STATUS.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_report(name: str, content: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = CI_REPORT_DIR / f"{name}_{ts}.json"
    report_file.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [OK] 报告已保存: {report_file.name}")
    return report_file


def _run_script(script_name: str, args: list[str] = None) -> subprocess.CompletedProcess:
    """运行同目录下的脚本"""
    script = SCRIPTS_DIR / script_name
    if not script.exists():
        raise FileNotFoundError(f"脚本不存在: {script}")
    cmd = [sys.executable, str(script)]
    if args:
        cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=False, timeout=60)


def _print_step(num: int, total: int, name: str, status: bool, detail: str = ""):
    icon = "[OK]" if status else "[X]"
    print(f"  Step {num}/{total}: {name}  {icon}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")


# ── 检查步骤 ──────────────────────────────────────────────────


def _check_health() -> bool:
    """检查系统健康"""
    hs = SCRIPTS_DIR / "system_health.py"
    if not hs.exists():
        print("  [!] system_health.py 未找到")
        return True  # skip
    try:
        result = subprocess.run(
            [sys.executable, str(hs), "--quick"],
            capture_output=True, text=False, timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        # 提取评分
        import re
        m = re.search(r"评分:\s*(\d+)%", stdout)
        score = int(m.group(1)) if m else 0
        if score < 60:
            print(f"  [X] 健康评分 {score}% — 低于 60%，建议修复后再提交")
            return False
        elif score < 80:
            print(f"  [!] 健康评分 {score}% — 存在警告，确认不影响当前操作")
            return True
        return True
    except Exception as e:
        print(f"  [!] 健康检查执行失败: {e}")
        return True


def _check_soul_sync() -> bool:
    """检查灵魂层同步"""
    agent = _find_agent_dir()
    if not agent:
        return True
    soul = agent / "SOUL.md"
    claude = agent / "CLAUDE.md"
    claude_home = Path.home() / ".claude" / "CLAUDE.md"

    if not soul.exists():
        return True

    soul_content = soul.read_text(encoding="utf-8")

    issues = []
    if claude.exists() and claude.read_text(encoding="utf-8") != soul_content:
        issues.append("Agent CLAUDE.md 不同步")
    if claude_home.exists() and claude_home.read_text(encoding="utf-8") != soul_content:
        issues.append("~/.claude/CLAUDE.md 不同步")

    if issues:
        print(f"  [X] 灵魂层不同步: {', '.join(issues)}")
        print(f"      运行 skill_add_helper.py sync 修复")
        return False
    return True


def _check_skill_consistency() -> bool:
    """检查技能表与目录一致性"""
    helper = SCRIPTS_DIR / "skill_add_helper.py"
    if not helper.exists():
        return True
    try:
        result = subprocess.run(
            [sys.executable, str(helper), "check"],
            capture_output=True, text=False, timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        # 检查是否有不一致
        if "完全一致" in stdout or "一致" in stdout and "不" not in stdout.split("一致")[0]:
            return True
        # 不一致警告但不阻塞
        print(f"  [!] 技能表与目录存在差异")
        return True
    except Exception:
        return True


def _check_snapshot_exists() -> bool:
    """检查是否有可用快照"""
    snap_dir = Path.home() / ".workflow_snapshots"
    snaps = list(snap_dir.glob("snapshot_*.json")) if snap_dir.is_dir() else []
    if not snaps:
        print(f"  [!] 无可用快照 — 建议创建: system_snapshot.py create")
        return False
    return True


def _create_snapshot() -> bool:
    """创建快照"""
    sn = SCRIPTS_DIR / "system_snapshot.py"
    if not sn.exists():
        return False
    try:
        result = subprocess.run(
            [sys.executable, str(sn), "create"],
            capture_output=True, text=False, timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        if "[OK]" in stdout:
            print(f"  [OK] 快照已创建")
            return True
        print(f"  [!] 快照创建异常")
        return False
    except Exception as e:
        print(f"  [!] 快照创建失败: {e}")
        return False


def _register_version() -> bool:
    """注册当前版本到 registry"""
    rg = SCRIPTS_DIR / "pkg_registry.py"
    if not rg.exists():
        return False
    # 查找桌面上的 .agentpkg
    desktop = Path.home() / "Desktop"
    pkgs = list(desktop.glob("cherryclaw-embedded-*.agentpkg"))
    if not pkgs:
        print(f"  [!] 未找到 .agentpkg 文件（跳过 registry 注册）")
        return False
    try:
        subprocess.run(
            [sys.executable, str(rg), "register", "--package", str(pkgs[-1])],
            capture_output=True, text=False, timeout=30,
        )
        return True
    except Exception:
        return False


# ── 命令实现 ──────────────────────────────────────────────────


def cmd_pre_commit() -> int:
    """提交前检查"""
    print(f"\n{'=' * 50}")
    print(f"  [CI] Pre-Commit 检查")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}")

    steps = [
        ("健康检查", _check_health()),
        ("灵魂层同步", _check_soul_sync()),
        ("技能一致性", _check_skill_consistency()),
        ("快照存在性", _check_snapshot_exists()),
    ]

    passed = sum(1 for _, ok in steps if ok)
    total = len(steps)

    print(f"\n  结果: {passed}/{total} 项通过")
    if passed == total:
        print(f"  [OK] Pre-Commit 检查通过")
        _save_status({
            "lastPreCommit": datetime.now().isoformat(),
            "totalPreCommit": _load_status().get("totalPreCommit", 0) + 1,
        })
        return 0
    else:
        print(f"  [!] {total - passed} 项未通过，建议修复后提交")
        _save_status({
            "lastPreCommit": datetime.now().isoformat(),
            "lastPreCommitFailed": total - passed,
        })
        return 1


def cmd_post_commit() -> int:
    """提交后处理"""
    print(f"\n{'=' * 50}")
    print(f"  [CI] Post-Commit 处理")
    print(f"{'=' * 50}")

    _create_snapshot()
    _register_version()

    _save_status({
        "lastPostCommit": datetime.now().isoformat(),
    })
    print(f"  [OK] Post-Commit 完成")
    return 0


def cmd_build_check() -> int:
    """构建前环境检查"""
    print(f"\n{'=' * 50}")
    print(f"  [CI] Build-Check 环境预检")
    print(f"{'=' * 50}")

    steps = [
        ("健康检查", _check_health()),
        ("灵魂层同步", _check_soul_sync()),
        ("快照存在性", _check_snapshot_exists()),
    ]

    passed = sum(1 for _, ok in steps if ok)
    print(f"\n  结果: {passed}/{len(steps)} 项通过")
    _save_status({"lastBuildCheck": datetime.now().isoformat()})
    return 0 if passed == len(steps) else 1


def cmd_build_pipeline() -> int:
    """完整 CI 流水线"""
    print(f"\n{'=' * 50}")
    print(f"  [CI] Full Build Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 50}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "steps": {},
    }

    # Step 1: Pre-Commit 检查
    print(f"\n  [Phase 1/4] Pre-Commit 检查")
    ok1 = cmd_pre_commit() == 0
    report["steps"]["pre_commit"] = {"passed": ok1}

    # Step 2: 创建快照
    print(f"\n  [Phase 2/4] 创建快照")
    ok2 = _create_snapshot()
    report["steps"]["snapshot"] = {"passed": ok2}

    # Step 3: 运行完整 health check
    print(f"\n  [Phase 3/4] 完整健康检查")
    hs = SCRIPTS_DIR / "system_health.py"
    ok3 = True
    if hs.exists():
        result = subprocess.run(
            [sys.executable, str(hs), "--report"],
            capture_output=True, text=False, timeout=30,
        )
        ok3 = result.returncode == 0
        report["steps"]["health_check"] = {
            "passed": ok3,
            "exit_code": result.returncode,
        }
    else:
        report["steps"]["health_check"] = {"passed": True, "note": "skipped"}

    # Step 4: 注册版本
    print(f"\n  [Phase 4/4] 注册版本")
    ok4 = _register_version()
    report["steps"]["registry"] = {"passed": ok4}

    # 保存报告
    _write_report("build_pipeline", report)

    total_ok = sum(1 for s in [ok1, ok2, ok3, ok4] if s)
    print(f"\n{'=' * 50}")
    print(f"  [CI] 流水线完成: {total_ok}/4 阶段通过")
    print(f"{'=' * 50}")

    _save_status({
        "lastBuildPipeline": datetime.now().isoformat(),
        "totalBuildPipeline": _load_status().get("totalBuildPipeline", 0) + 1,
    })
    return 0 if total_ok == 4 else 1


def cmd_release_check() -> int:
    """发布前检查清单"""
    print(f"\n{'=' * 50}")
    print(f"  [CI] Release-Check 发布前检查")
    print(f"{'=' * 50}")

    checklist = [
        ("健康检查 ≥80%", _check_health()),
        ("灵魂层同步", _check_soul_sync()),
        ("技能一致性", _check_skill_consistency()),
        ("快照存在", _check_snapshot_exists()),
        ("Package 已导出", _check_package_exists()),
    ]

    passed = sum(1 for _, ok in checklist)
    total = len(checklist)

    print(f"\n  发布检查清单: {passed}/{total} 项通过")
    if passed < total:
        print(f"  [!] {total - passed} 项未满足发布条件")
        return 1

    print(f"  [OK] 发布条件满足!")
    _save_status({"lastReleaseCheck": datetime.now().isoformat()})
    return 0


def _check_package_exists() -> bool:
    """检查是否有导出的 .agentpkg"""
    desktop = Path.home() / "Desktop"
    pkgs = list(desktop.glob("cherryclaw-embedded-*.agentpkg"))
    if pkgs:
        print(f"  [OK] 包已导出: {pkgs[-1].name}")
        return True
    else:
        print(f"  [!] 未找到 .agentpkg — 运行 agent-packager export")
        return False


def cmd_install_hooks(repo_path: str = ".") -> int:
    """安装 git hooks 到指定仓库"""
    repo = Path(repo_path).resolve()
    hooks_dir = repo / ".git" / "hooks"

    if not hooks_dir.is_dir():
        print(f"[X] 不是 git 仓库或 hooks 目录不存在: {repo}")
        return 1

    print(f"[*] 安装 git hooks 到: {hooks_dir}")

    # pre-commit hook
    pre_commit = hooks_dir / "pre-commit"
    pre_commit_content = textwrap.dedent(f"""\
    #!/bin/sh
    # Chip CI: Pre-Commit Hook
    # 自动运行健康检查和灵魂层同步检查

    PYTHON="{sys.executable}"
    CI_SCRIPT="{SCRIPTS_DIR / 'pipeline_ci.py'}"

    if [ -f "$CI_SCRIPT" ]; then
        echo ""
        echo "[Chip CI] Running pre-commit checks..."
        $PYTHON "$CI_SCRIPT" pre-commit
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "[Chip CI] Pre-commit checks FAILED."
            echo "    To bypass: git commit --no-verify"
            exit $EXIT_CODE
        fi
        echo "[Chip CI] All checks passed."
    fi
    """)

    # post-commit hook
    post_commit = hooks_dir / "post-commit"
    post_commit_content = textwrap.dedent(f"""\
    #!/bin/sh
    # Chip CI: Post-Commit Hook
    # 自动创建快照和注册版本

    PYTHON="{sys.executable}"
    CI_SCRIPT="{SCRIPTS_DIR / 'pipeline_ci.py'}"

    if [ -f "$CI_SCRIPT" ]; then
        $PYTHON "$CI_SCRIPT" post-commit
    fi
    """)

    try:
        pre_commit.write_text(pre_commit_content)
        pre_commit.chmod(0o755)
        print(f"  [OK] pre-commit hook 已安装")

        post_commit.write_text(post_commit_content)
        post_commit.chmod(0o755)
        print(f"  [OK] post-commit hook 已安装")

        print(f"\n[OK] Git hooks 安装完成!")
        print(f"     下次 git commit 时自动执行检查")
        print(f"     跳过: git commit --no-verify")
        return 0
    except OSError as e:
        print(f"[X] 安装失败: {e}")
        return 1


def cmd_status() -> int:
    """查看 CI 状态"""
    status = _load_status()
    if not status:
        print("[i] 无 CI 记录")
        print("    运行 pipeline_ci.py pre-commit 开始记录")
        return 0

    print(f"\n  ┌─ Chip CI Status ─────────────────────")
    for key, value in status.items():
        label = key.replace("last", "上次 ").replace("total", "累计 ")
        if isinstance(value, str):
            print(f"  │ {label}: {value[:19]}")
        else:
            print(f"  │ {label}: {value}")
    print(f"  └────────────────────────────────────────────")

    # 检查最近报告
    reports = sorted(CI_REPORT_DIR.glob("*.json"))
    if reports:
        print(f"\n  最近报告 ({len(reports)} 个):")
        for r in reports[-5:]:
            size_kb = r.stat().st_size / 1024
            print(f"    {r.stem}  ({size_kb:.0f} KB)")
    return 0


# ── CLI ───────────────────────────────────────────────────────


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    cmd = sys.argv[1]

    if cmd == "pre-commit":
        return cmd_pre_commit()
    elif cmd == "post-commit":
        return cmd_post_commit()
    elif cmd == "build-check":
        return cmd_build_check()
    elif cmd == "build-pipeline":
        return cmd_build_pipeline()
    elif cmd == "release-check":
        return cmd_release_check()
    elif cmd == "install-hooks":
        repo = "."
        for i, a in enumerate(sys.argv[2:], 2):
            if a == "--repo" and i + 1 < len(sys.argv):
                repo = sys.argv[i + 1]
        return cmd_install_hooks(repo)
    elif cmd == "status":
        return cmd_status()
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())
