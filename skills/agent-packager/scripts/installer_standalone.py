#!/usr/bin/env python3
"""
Chip Agent 一键独立安装器
=========================
双击运行，自动检测 Claude Code / Cursor 并安装。
可配合 PyInstaller 打包为单文件 .exe 分发。

工作模式:
  1. 已打包 (PyInstaller --onefile): 从 sys._MEIPASS 读取内嵌 .agentpkg
  2. 脚本模式: 从同目录读取 .agentpkg

用法:
  python installer_standalone.py                          # 自动检测并安装
  python installer_standalone.py --only claude-code       # 仅安装到指定平台
  python installer_standalone.py --yes                    # 跳过确认提示

注意事项:
  - Claude Code: skills → ~/.claude/skills/, CLAUDE.md, 合并 settings.json (保留 env)
  - Cursor:      skills → ~/.cursor/skills-cursor/, rules/chip.md, 配置 settings.json
"""

import json
import os
import shutil
import sys
import tarfile
import tempfile

# ── 常量 ────────────────────────────────────────────────────────
AGENTPKG_NAME = "chip-embedded-3.0.0.agentpkg"
PLATFORM_NAMES = {
    "claude-code": "Claude Code CLI / VSCode 插件",
    "cursor":      "Cursor IDE",
    "ccswitch":    "CCSwitch (Claude Code 多 Profile 管理)",
}


# ── 资源路径 ────────────────────────────────────────────────────

def get_resource_path():
    """获取资源目录 (PyInstaller 打包时为 sys._MEIPASS, 否则为脚本目录)"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def find_agentpkg(custom_path=None):
    """查找 .agentpkg 文件（支持 PyInstaller 打包路径）"""
    if custom_path and os.path.isfile(custom_path):
        return os.path.abspath(custom_path)

    search_roots = [
        get_resource_path(),
        os.path.join(get_resource_path(), "pkg"),
    ]
    if not getattr(sys, "frozen", False):
        search_roots.append(os.path.dirname(get_resource_path()))
        search_roots.append(os.getcwd())

    seen = set()
    for root in search_roots:
        if not root or root in seen:
            continue
        seen.add(root)
        if not os.path.isdir(root):
            continue
        exact = os.path.join(root, AGENTPKG_NAME)
        if os.path.isfile(exact):
            return exact
        for fname in os.listdir(root):
            if fname.endswith(".agentpkg") and os.path.isfile(os.path.join(root, fname)):
                return os.path.join(root, fname)
    return None


# ── 解包 ────────────────────────────────────────────────────────

def extract_package(pkg_path, target_dir):
    """解包 .agentpkg"""
    with tarfile.open(pkg_path, "r:gz") as tar:
        tar.extractall(path=target_dir)
    inner = os.path.join(target_dir, "agent-package")
    if os.path.isdir(inner):
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), os.path.join(target_dir, item))
        os.rmdir(inner)


def load_manifest(tmpdir):
    """读取 manifest.json"""
    path = os.path.join(tmpdir, "manifest.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 平台检测 ────────────────────────────────────────────────────

def detect_platforms(exclude_vscode=True):
    """检测当前系统上可安装的目标平台"""
    platforms = {}
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA", "")

    # Claude Code
    cc_dir = os.path.join(home, ".claude")
    if os.path.isdir(cc_dir):
        platforms["claude-code"] = cc_dir

    # Cursor
    cursor_dirs = [
        os.path.join(appdata, "Cursor"),
        os.path.join(home, ".cursor"),
    ]
    for d in cursor_dirs:
        if d and os.path.isdir(d):
            platforms["cursor"] = d
            break

    # CCSwitch (~/.agents/skills/)
    ccswitch_skills = os.path.join(home, ".agents", "skills")
    if os.path.isdir(ccswitch_skills):
        platforms["ccswitch"] = ccswitch_skills

    return platforms


# ── 公共函数 ────────────────────────────────────────────────────

def localize_agent_config(tmpdir, base_dir):
    """
    将 agent 配置文件安装到目标目录，路径本地化替换。
    写入: SOUL.md, USER.md, memory/FACT.md
    """
    src_agent = os.path.join(tmpdir, "agent")
    if not os.path.isdir(src_agent):
        return

    user_home = os.path.expanduser("~")
    user_name = os.path.basename(user_home)

    # SOUL.md
    soul_src = os.path.join(src_agent, "SOUL.md")
    if os.path.isfile(soul_src):
        shutil.copy2(soul_src, os.path.join(base_dir, "SOUL.md"))

    # USER.md → 替换路径占位符
    user_src = os.path.join(src_agent, "USER.md")
    if os.path.isfile(user_src):
        with open(user_src, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("{USER_HOME}\\", user_home + "\\")
        content = content.replace("{USER_HOME}/", user_home.replace("\\", "/") + "/")
        content = content.replace("{SERIAL_PORT}", "{SERIAL_PORT}")
        content = content.replace("{PYTHON_EXE}", "python")
        with open(os.path.join(base_dir, "USER.md"), "w", encoding="utf-8") as f:
            f.write(content)
    else:
        _generate_default_user_file(base_dir, user_name, user_home)

    # FACT.md → memory/
    fact_src = os.path.join(src_agent, "FACT.md")
    memory_dir = os.path.join(base_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    if os.path.isfile(fact_src):
        with open(fact_src, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("{USER_HOME}\\", user_home + "\\")
        content = content.replace("{USER_HOME}/", user_home.replace("\\", "/") + "/")
        with open(os.path.join(memory_dir, "FACT.md"), "w", encoding="utf-8") as f:
            f.write(content)


def _generate_default_user_file(base_dir, user_name, user_home):
    """新电脑无模板时生成默认 USER.md"""
    content = f"""# User Profile

> 此文件自动生成。请在首次使用前更新为您自己的信息。

## Name

{user_name}

## Preferences

- **语言**：中文（Simplified Chinese），代码/寄存器/路径/命令保持英文
- **风格**：简洁务实，用数据支撑结论

## Timezone

UTC+8 (Asia/Shanghai)

## Context

### 工作环境
- **操作系统**：Windows
- **Python**：请在此填写您的 Python 路径
- **工程目录**：{user_home}

> 请补充您的具体开发环境信息（MCU 型号、调试器、串口等）。
"""
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, "USER.md"), "w", encoding="utf-8") as f:
        f.write(content)


def install_skills_dir(tmpdir, skills_dir):
    """安装 skills 目录，返回数量"""
    src_skills = os.path.join(tmpdir, "skills")
    if not os.path.isdir(src_skills):
        return 0
    os.makedirs(skills_dir, exist_ok=True)
    count = 0
    for skill_name in sorted(os.listdir(src_skills)):
        src = os.path.join(src_skills, skill_name)
        dst = os.path.join(skills_dir, skill_name)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            count += 1
    return count


# ── 平台安装函数 ────────────────────────────────────────────────

def install_to_claude_code(tmpdir, manifest, base_dir):
    """Claude Code (~/.claude/)"""
    skills_dir = os.path.join(base_dir, "skills")
    count = install_skills_dir(tmpdir, skills_dir)
    localize_agent_config(tmpdir, base_dir)

    # CLAUDE.md
    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        shutil.copy2(soul_src, os.path.join(base_dir, "CLAUDE.md"))

    # settings.json — 合并，保留 env
    settings_path = os.path.join(base_dir, "settings.json")
    settings = {}
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}
    dirs = settings.setdefault("skills", {}).setdefault("directories", [])
    skills_dir_abs = os.path.abspath(skills_dir)
    if skills_dir_abs not in dirs:
        dirs.append(skills_dir_abs)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

    return count


def install_to_cursor(tmpdir, manifest, base_dir):
    """Cursor (~/.cursor/ 或 %APPDATA%/Cursor)"""
    skills_dir = os.path.join(base_dir, "skills-cursor")
    count = install_skills_dir(tmpdir, skills_dir)
    localize_agent_config(tmpdir, base_dir)

    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        rules_dir = os.path.join(base_dir, "rules")
        os.makedirs(rules_dir, exist_ok=True)
        shutil.copy2(soul_src, os.path.join(rules_dir, "chip.md"))

    return count


def install_to_ccswitch(tmpdir, manifest, base_dir):
    """CCSwitch (~/.agents/skills/)"""
    count = install_skills_dir(tmpdir, base_dir)
    skills_dir = os.path.join(tmpdir, "skills")
    if os.path.isdir(skills_dir):
        for skill_name in sorted(os.listdir(skills_dir)):
            src = os.path.join(skills_dir, skill_name)
            dst = os.path.join(base_dir, skill_name)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                count += 1

    # agent/SOUL.md → ~/.agents/SOUL.md（共享参考）
    agents_dir = os.path.dirname(base_dir)
    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        shutil.copy2(soul_src, os.path.join(agents_dir, "CLAUDE.md.chip"))

    return count


INSTALLERS = {
    "claude-code": install_to_claude_code,
    "cursor":      install_to_cursor,
    "ccswitch":    install_to_ccswitch,
}


# ── UI ──────────────────────────────────────────────────────────

def print_banner():
    print(r"""
╔══════════════════════════════════════════════╗
║            Chip Agent Installer              ║
║   嵌入式系统工程师 Agent — 一键安装工具       ║
╚══════════════════════════════════════════════╝
""")


def print_platform_table(detected):
    print(f"  {'平台':<22} {'状态':<10} {'路径'}")
    print(f"  {'─'*60}")
    for key, name in PLATFORM_NAMES.items():
        if key in detected:
            print(f"  {name:<22} [OK]      {detected[key]}")
        else:
            print(f"  {name:<22} [--]      未检测到")
    print()


def print_report(manifest, results):
    print(f"\n  ┌{'─'*55}┐")
    print(f"  │ Chip Agent 安装完成")
    print(f"  │ {manifest.get('name', '?')} v{manifest.get('version', '?')}")
    print(f"  │ Skills: {manifest.get('skills', {}).get('total', '?')}")
    print(f"  ├{'─'*55}┤")
    for platform, (ok, count) in results.items():
        name = PLATFORM_NAMES.get(platform, platform)
        if ok:
            print(f"  │ [OK] {name:<22} {count} skills")
        else:
            print(f"  │ [X] {name:<22} 安装失败")
    print(f"  └{'─'*55}┘")

    # 各平台激活提示
    hints = {
        "claude-code": "重启终端后生效",
        "cursor":      "重启 Cursor 后 Rules 自动加载",
        "ccswitch":    "CCSwitch 中切换 Profile 后 skills 立即可用",
    }
    active_hints = [hints[p] for p in results if results[p][0]]
    if active_hints:
        print(f"\n  [!] 安装后操作:")
        for p_name, hint in hints.items():
            if p_name in results and results[p_name][0]:
                print(f"      {PLATFORM_NAMES.get(p_name, p_name):<22} {hint}")
    print()


# ── 主流程 ──────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Chip Agent 独立安装器")
    parser.add_argument("--package", "-p", default=None,
                        help=".agentpkg 包路径（默认自动查找）")
    parser.add_argument("--only", default=None,
                        choices=list(PLATFORM_NAMES.keys()) + ["all"],
                        help="仅安装到指定平台")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="跳过确认提示")
    args = parser.parse_args()

    print_banner()

    # ── 查找包 ──
    pkg_path = find_agentpkg(args.package)
    if not pkg_path:
        print("  [X] 未找到 .agentpkg 文件")
        print(f"      将 {AGENTPKG_NAME} 放在本程序同目录下，")
        print("      或用 --package 指定路径。")
        input("\n  按 Enter 退出...")
        return 1

    print(f"  Agent 包: {os.path.basename(pkg_path)}")
    print(f"  大小:     {os.path.getsize(pkg_path) / 1024 / 1024:.1f} MB")

    # ── 解包 ──
    with tempfile.TemporaryDirectory(prefix="chip_install_") as tmpdir:
        print("\n  [*] 正在解包...")
        extract_package(pkg_path, tmpdir)
        manifest = load_manifest(tmpdir)
        print(f"      名称: {manifest.get('name', '?')}")
        print(f"      版本: {manifest.get('version', '?')}")
        print(f"      Skills: {manifest.get('skills', {}).get('total', '?')}")

        # ── 检测平台 ──
        detected = detect_platforms()
        print("\n  [*] 检测到的平台:\n")
        print_platform_table(detected)

        if args.only and args.only != "all":
            detected = {k: v for k, v in detected.items() if k == args.only}

        if not detected:
            print("  [!] 未检测到任何支持的平台。请确认已安装:")
            for name in PLATFORM_NAMES.values():
                print(f"        - {name}")
            input("\n  按 Enter 退出...")
            return 1

        # ── 确认 ──
        if not args.yes:
            try:
                ans = input("  [?] 是否继续安装? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "n"
            if ans not in ("", "y", "yes"):
                print("  已取消。")
                return 0

        # ── 安装 ──
        print("\n  [*] 正在安装...")
        results = {}
        for platform, base_dir in sorted(detected.items()):
            installer = INSTALLERS.get(platform)
            if not installer:
                continue
            try:
                count = installer(tmpdir, manifest, base_dir)
                results[platform] = (True, count)
                print(f"      [OK] {PLATFORM_NAMES.get(platform, platform)}: {count} skills")
            except Exception as e:
                results[platform] = (False, 0)
                print(f"      [X] {PLATFORM_NAMES.get(platform, platform)}: {e}")

        # ── 报告 ──
        print_report(manifest, results)
        ok_count = sum(1 for ok, _ in results.values() if ok)
        print(f"  {ok_count}/{len(results)} 个平台安装成功。\n")

    try:
        input("  按 Enter 退出...")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
