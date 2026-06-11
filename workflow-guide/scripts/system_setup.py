#!/usr/bin/env python3
"""
Chip 一键部署依赖预检与自动修复工具
==========================================
在新机器上或升级后，检查所有依赖项是否就绪，
并自动修复常见问题。

用法:
  python system_setup.py check          # 预检所有依赖（不修复）
  python system_setup.py fix            # 预检 + 自动修复常见问题
  python system_setup.py fix --dry-run  # 试运行，显示将要修复的内容
  python system_setup.py verify         # 验证安装完整（运行 health check）
  python system_setup.py paths          # 检查所有路径配置
  python system_setup.py python-path    # 自动配置 Python 路径
"""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows GBK 控制台兼容
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 路径常量 ──────────────────────────────────────────────────

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA", str(HOME / "AppData" / "Roaming")))

AGENT_DIRS = [
    APPDATA / "CherryStudio" / "Data" / "Agents",
]
SKILLS_DIR = APPDATA / "CherryStudio" / "Data" / "Skills"
WORKFLOW_SCRIPTS = SKILLS_DIR / "workflow" / "scripts"
HEALTH_SCRIPT = SKILLS_DIR / "workflow-guide" / "scripts" / "system_health.py"
STATE_FILE = HOME / ".workflow_state.json"

# 已知工具安装路径
KNOWN_TOOLS: dict[str, list[Path]] = {
    "Python": [],
    "Git": [],
    "J-Link": [
        Path("C:/Program Files/SEGGER/JLink/JLink.exe"),
        Path("C:/Program Files (x86)/SEGGER/JLink/JLink.exe"),
    ],
    "Keil UV4": [
        Path("G:/keil5/core/UV4/UV4.exe"),
        Path("C:/Keil_v5/UV4/UV4.exe"),
        Path("D:/Keil_v5/UV4/UV4.exe"),
    ],
    "CherryStudio": [
        APPDATA / "CherryStudio" / "CherryStudio.exe",
    ],
}


def _find_python() -> Path | None:
    """查找 Python 安装路径"""
    candidates = [
        Path(sys.executable),  # 当前正在使用的
        Path(os.environ.get("PYTHON_PATH", "")),
        HOME / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "{PYTHON_EXE}",
        HOME / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "{PYTHON_EXE}",
        Path("C:/Python312/{PYTHON_EXE}"),
        Path("C:/Python311/{PYTHON_EXE}"),
    ]
    for p in candidates:
        if p and p.exists():
            return p.resolve()
    return None


def _find_git() -> Path | None:
    candidates = [
        Path("C:/Program Files/Git/bin/git.exe"),
        Path("C:/Program Files (x86)/Git/bin/git.exe"),
        HOME / "AppData" / "Local" / "Programs" / "Git" / "bin" / "git.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _check_in_path(name: str) -> bool:
    """检查工具是否在 PATH 中"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["where", name], capture_output=True, text=True, timeout=3
            )
            return True
        else:
            subprocess.run(
                ["which", name], capture_output=True, text=True, timeout=3
            )
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _add_to_user_path(path: str) -> bool:
    """添加路径到 User PATH（Windows）"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        # 使用 PowerShell 修改 User PATH
        cmd = (
            f'[Environment]::SetEnvironmentVariable("PATH", '
            f'"$path;{path}", "User")'
        )
        # 简单方式：直接读取并设置
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f'$old=[Environment]::GetEnvironmentVariable("PATH","User");'
                f'if(($old-split";")-notcontains"{path}"){{'
                f'[Environment]::SetEnvironmentVariable("PATH","{path};$old","User");'
                f'Write-Host "ADDED:{path}"}}'
                f'else{{Write-Host "EXISTS"}}'
            ],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip()
        if "ADDED" in output:
            return True
        elif "EXISTS" in output:
            return True  # 已存在，也算成功
        return False
    except Exception:
        return False


# ── 检查项 ────────────────────────────────────────────────────


class CheckResult:
    def __init__(self, name: str, status: bool, detail: str = "", fixable: bool = False):
        self.name = name
        self.status = status
        self.detail = detail
        self.fixable = fixable

    def __str__(self):
        icon = "[OK]" if self.status else "[!]" if self.fixable else "[X]"
        return f"  {icon} {self.name}: {self.detail}"


def check_python() -> CheckResult:
    py = _find_python()
    if py:
        try:
            ver = subprocess.run(
                [str(py), "--version"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            return CheckResult("Python", True, f"{ver} @ {py}")
        except Exception:
            return CheckResult("Python", True, f"Found: {py}")
    return CheckResult("Python", False, "未找到", fixable=True)


def check_git() -> CheckResult:
    git = _find_git()
    if git:
        try:
            ver = subprocess.run(
                [str(git), "--version"], capture_output=True, text=True, timeout=5
            ).stdout.strip()
            return CheckResult("Git", True, f"{ver}")
        except Exception:
            return CheckResult("Git", True, f"Found: {git}")
    return CheckResult("Git", False, "未找到", fixable=True)


def check_jlink() -> CheckResult:
    # 优先 PATH
    if _check_in_path("JLink.exe"):
        try:
            ver = subprocess.run(
                ["JLink.exe", "--version"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()[:50]
            return CheckResult("J-Link", True, f"{ver} (PATH)")
        except Exception:
            pass

    # fallback 已知路径
    for p in KNOWN_TOOLS.get("J-Link", []):
        if p.exists():
            return CheckResult("J-Link", True, f"Found: {p}", fixable=False)

    return CheckResult("J-Link", False, "未找到，如需烧录请安装", fixable=True)


def check_keil() -> CheckResult:
    if _check_in_path("UV4.exe"):
        return CheckResult("Keil UV4", True, f"Found in PATH")

    for p in KNOWN_TOOLS.get("Keil UV4", []):
        if p.exists():
            size_kb = p.stat().st_size / 1024
            return CheckResult("Keil UV4", True, f"{p} ({size_kb:.0f} KB)")

    return CheckResult("Keil UV4", False, "未找到，可选依赖", fixable=False)


def check_cherrystudio() -> CheckResult:
    for p in KNOWN_TOOLS.get("CherryStudio", []):
        if p.exists():
            return CheckResult("CherryStudio", True, f"Found: {p}")
    # 检查 Data 目录
    if (APPDATA / "CherryStudio" / "Data").is_dir():
        return CheckResult("CherryStudio", True, "Data 目录存在")
    return CheckResult("CherryStudio", False, "未检测到安装", fixable=True)


def check_agent_dir() -> CheckResult:
    for d in AGENT_DIRS:
        if d.is_dir():
            agents = [x for x in d.iterdir() if (x / "SOUL.md").exists()]
            if agents:
                return CheckResult("Agent 目录", True, f"{len(agents)} 个 Agent: {', '.join(a.name for a in agents)}")
    return CheckResult("Agent 目录", False, "未找到", fixable=False)


def check_skills_count() -> CheckResult:
    if SKILLS_DIR.is_dir():
        count = sum(
            1 for d in SKILLS_DIR.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and not d.name.startswith("__")
            and (d / "SKILL.md").exists()
        )
        status = count >= 50
        detail = f"{count} 个 skill" if status else f"{count} 个（期望 >= 50）"
        return CheckResult("Skills 数量", status, detail)
    return CheckResult("Skills 数量", False, "Skills 目录不存在", fixable=False)


def check_workflow_scripts() -> CheckResult:
    required = [
        "shared.py", "workflow_coordinator.py",
        "build_agent.py", "dev_agent.py", "pm_agent.py",
        "verify_agent.py", "release_agent.py", "fix_agent.py",
    ]
    if not WORKFLOW_SCRIPTS.is_dir():
        return CheckResult("Workflow 脚本", False, "目录不存在", fixable=False)

    missing = [s for s in required if not (WORKFLOW_SCRIPTS / s).exists()]
    if missing:
        return CheckResult("Workflow 脚本", False, f"缺失: {missing}", fixable=False)
    return CheckResult("Workflow 脚本", True, f"9/9 脚本完整")


def check_health_script() -> CheckResult:
    if HEALTH_SCRIPT.exists():
        return CheckResult("Health 检查脚本", True, f"Found: {HEALTH_SCRIPT}")
    return CheckResult("Health 检查脚本", False, "未找到", fixable=False)


def check_disk_space() -> CheckResult:
    """检查磁盘剩余空间"""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-PSDrive -Name C | Select-Object -ExpandProperty Free"],
                capture_output=True, text=True, timeout=5,
            )
            free_gb = float(result.stdout.strip()) / 1024 / 1024 / 1024
            status = free_gb > 1.0
            detail = f"C: 盘剩余 {free_gb:.1f} GB"
            if not status:
                detail += "（不足 1 GB，编译可能失败）"
            return CheckResult("磁盘空间", status, detail)
        else:
            st = os.statvfs("/")
            free_gb = st.f_bavail * st.f_frsize / 1024 / 1024 / 1024
            status = free_gb > 1.0
            return CheckResult("磁盘空间", status, f"剩余 {free_gb:.1f} GB")
    except Exception as e:
        return CheckResult("磁盘空间", True, f"无法检测 ({e})")


# ── 自动修复 ──────────────────────────────────────────────────


def fix_path_issue(name: str, paths: list[Path], dry_run: bool) -> bool:
    """将工具路径添加到 User PATH"""
    for p in paths:
        if p.exists():
            parent = str(p.parent)
            if dry_run:
                print(f"    [DRY-RUN] 添加 PATH: {parent}")
                return True
            if _add_to_user_path(parent):
                print(f"    [OK] 已添加到 User PATH: {parent}")
                return True
            else:
                print(f"    [X] 添加失败: {parent}")
                return False
    print(f"    [!] {name} 可执行文件不存在，无法添加 PATH")
    return False


def run_fix(dry_run: bool = False) -> int:
    """执行预检 + 自动修复"""
    print(f"{'=' * 55}")
    print(f"  Chip 依赖预检与自动修复")
    print(f"  {'试运行模式' if dry_run else '实际执行模式'}")
    print(f"{'=' * 55}")

    checks = [
        check_python(),
        check_git(),
        check_jlink(),
        check_keil(),
        check_cherrystudio(),
        check_agent_dir(),
        check_skills_count(),
        check_workflow_scripts(),
        check_health_script(),
        check_disk_space(),
    ]

    all_ok = True
    fixable_issues = []
    for c in checks:
        print(c)
        if not c.status:
            all_ok = False
            if c.fixable:
                fixable_issues.append(c)

    print(f"\n---")
    print(f"  总计: {len(checks)} 项检查")
    print(f"  通过: {sum(1 for c in checks if c.status)}")
    print(f"  失败: {sum(1 for c in checks if not c.status)}")

    if not fixable_issues:
        if all_ok:
            print(f"\n[OK] 全部检查通过!")
        else:
            print(f"\n[!] 存在不可自动修复的问题，请手动处理")
        return 0 if all_ok else 1

    print(f"\n{'=' * 55}")
    print(f"  [{len(fixable_issues)}] 个可自动修复的问题:")
    print(f"{'=' * 55}")

    for c in fixable_issues:
        print(f"\n  [!] {c.name}: {c.detail}")
        if c.name == "Python":
            py = _find_python()
            if py:
                print(f"    Found: {py}")
            else:
                print(f"    请手动安装 Python 3.10+")
        elif c.name == "Git":
            git = _find_git()
            if git:
                print(f"    Found: {git}")
            else:
                print(f"    请手动安装 Git")
        elif c.name == "J-Link":
            fix_path_issue("J-Link", KNOWN_TOOLS.get("J-Link", []), dry_run)
        elif c.name == "Keil UV4":
            fix_path_issue("Keil UV4", KNOWN_TOOLS.get("Keil UV4", []), dry_run)
        elif c.name == "CherryStudio":
            print(f"    请从 CherryStudio 官网下载安装")
        elif c.name == "Skills 数量":
            print(f"    请运行 Chip-Setup.exe 重新安装技能")

    print(f"\n[*] 修复完成后建议运行: python system_setup.py verify")
    return 0


# ── 命令入口 ──────────────────────────────────────────────────


def cmd_check() -> int:
    """仅检查"""
    print(f"{'=' * 55}")
    print(f"  Chip 系统依赖预检")
    print(f"{'=' * 55}")

    checks = [
        check_python(),
        check_git(),
        check_jlink(),
        check_keil(),
        check_cherrystudio(),
        check_agent_dir(),
        check_skills_count(),
        check_workflow_scripts(),
        check_health_script(),
        check_disk_space(),
    ]

    ok = sum(1 for c in checks if c.status)
    for c in checks:
        print(c)

    print(f"\n---")
    print(f"  通过: {ok}/{len(checks)}")
    if ok == len(checks):
        print(f"\n[OK] 全部依赖就绪!")
    else:
        print(f"\n[!] 存在 {len(checks) - ok} 个问题，运行 'fix' 尝试自动修复")
    return 0 if ok == len(checks) else 1


def cmd_verify() -> int:
    """运行 health check 验证"""
    if HEALTH_SCRIPT.exists():
        print(f"[*] 运行系统健康检查...\n")
        result = subprocess.run(
            [sys.executable, str(HEALTH_SCRIPT)],
            timeout=30,
        )
        return result.returncode
    else:
        print(f"[X] system_health.py 未找到，无法验证")
        print(f"    期望路径: {HEALTH_SCRIPT}")
        return 1


def cmd_paths() -> int:
    """列出所有关键路径配置"""
    print(f"{'=' * 55}")
    print(f"  Chip 路径配置")
    print(f"{'=' * 55}")

    items = [
        ("当前 Python", sys.executable),
        ("Python 版本", sys.version.split()[0]),
        ("Agent 目录", APPDATA / "CherryStudio" / "Data" / "Agents"),
        ("Skills 目录", SKILLS_DIR),
        ("Workflow 脚本", WORKFLOW_SCRIPTS),
        ("Health 脚本", HEALTH_SCRIPT),
        ("快照目录", Path.home() / ".workflow_snapshots"),
        ("状态文件", STATE_FILE),
    ]

    for name, path in items:
        p = Path(str(path))
        exists = p.exists() if not name.startswith("Python 版本") else True
        icon = "[OK]" if exists else "[!]"
        print(f"  {icon} {name:<20} {p}")

    print(f"\n  PATH 中的相关条目:")
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    for entry in path_entries:
        if any(kw in entry.lower() for kw in ["segger", "jlink", "keil", "uv4"]):
            print(f"    {entry}")

    return 0


def cmd_python_path() -> int:
    """自动配置 Python 路径"""
    py = _find_python()
    if not py:
        print("[X] 未找到 Python")
        return 1

    # 输出 Python 配置信息，供用户手动更新 USER.md
    print(f"[OK] Python 路径: {py}")
    print(f"     版本:       ", end="")
    subprocess.run([str(py), "--version"])
    print(f"\n[*] 请在 USER.md 中更新 Python 路径:")
    print(f"    Python: `{py}`")

    # 尝试添加到 PATH
    parent = str(py.parent)
    if _check_in_path(py.name):
        print(f"[OK] 已在 PATH 中: {parent}")
    else:
        print(f"[!] 不在 PATH 中 ({parent})")
        if _add_to_user_path(parent):
            print(f"[OK] 已添加到 User PATH")
        else:
            print(f"[!] 添加失败，请手动添加到系统环境变量")

    return 0


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    command = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if command == "check":
        return cmd_check()
    elif command == "fix":
        return run_fix(dry_run)
    elif command == "verify":
        return cmd_verify()
    elif command == "paths":
        return cmd_paths()
    elif command == "python-path":
        return cmd_python_path()
    else:
        print(f"[X] 未知命令: {command}")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())
