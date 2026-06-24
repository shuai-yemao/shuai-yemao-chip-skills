#!/usr/bin/env python3
"""
Install module: 解包 .agentpkg → 目标平台适配 → 安装

安装流程:
  1. 解包验证 (checksums)
  2. 检查依赖 (Python 版本、可选工具)
  3. 目标平台适配 (路径映射)
  4. 交互式配置向导 (路径/串口/SN)
  5. 注册 skills (根据目标平台)
  6. 写入 agent 配置
  7. 生成安装报告
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile


def run_install(args):
    """CLI 入口"""
    pkg_path = os.path.abspath(args.package)
    target = args.target

    if not os.path.isfile(pkg_path):
        print(f"[X] 包文件不存在: {pkg_path}")
        return 1

    print(f"[*] 安装 Agent 包到 {target}")
    print(f"    包文件: {pkg_path}")

    # ── 试运行模式 ──
    if args.dry_run:
        print("    [DRY-RUN] 模拟安装，不写入任何文件")
        with tempfile.TemporaryDirectory(prefix="agentpkg_dry_") as tmpdir:
            _extract_package(pkg_path, tmpdir)
            manifest = _load_manifest(tmpdir)
            plan = _build_install_plan(manifest, target, args)
            _print_install_plan(plan)
        print("    [DRY-RUN] 完成，未写入任何文件")
        return 0

    # ── 签名验证 ──
    if args.verify_signature:
        from packager_sign import verify_signature
        if not args.public_key:
            print("[!] --verify-signature 需要 --public-key 参数")
            return 1
        if not verify_signature(pkg_path, args.public_key):
            if not args.force:
                print("[X] 签名验证失败，使用 --force 跳过")
                return 1
            print("[!] 签名验证失败，但 --force 已指定，继续安装")

    # ── 正式安装 ──
    result = _do_install(pkg_path, target, args)
    if result == 0:
        print("    [OK] 安装完成")
    return result


def _do_install_all(pkg_path, args):
    """安装到所有支持的目标平台"""
    from packager_platforms import list_supported_platforms
    targets = [t for t in list_supported_platforms() if t != "all"]
    results = {}
    for target in targets:
        print(f"\n{'='*50}")
        print(f"[*] 安装到 {target}")
        print(f"{'='*50}")
        result = _do_install(pkg_path, target, args)
        results[target] = result
    print(f"\n{'='*50}")
    print(f"[*] 全部安装完成")
    ok = sum(1 for r in results.values() if r == 0)
    fail = sum(1 for r in results.values() if r != 0)
    print(f"    [OK] {ok} 个平台成功, [X] {fail} 个平台失败")
    for t, r in results.items():
        status = "[OK]" if r == 0 else "[X]"
        print(f"    {status} {t}")
    return 0 if fail == 0 else 1


def _do_install(pkg_path, target, args):
    """执行实际安装"""
    if target == "all":
        return _do_install_all(pkg_path, args)
    with tempfile.TemporaryDirectory(prefix="agentpkg_install_") as tmpdir:
        # 1. 解包
        _extract_package(pkg_path, tmpdir)
        manifest = _load_manifest(tmpdir)
        print(f"    Agent: {manifest['name']} v{manifest['version']}")

        # 2. 校验 checksums
        from packager_verify import verify_checksums
        if not verify_checksums(tmpdir):
            print("[X] 包完整性校验失败（文件可能被篡改）")
            if not args.force:
                return 1
            print("[!] --force 已指定，跳过校验")

        # 3. 检查依赖
        _check_dependencies(manifest, args)

        # 4. 交互式配置
        config = {}
        if args.interactive:
            config = _interactive_config(manifest)
            _apply_config(tmpdir, config)
        else:
            config = _auto_config(manifest, target, args)

        # 5. 平台适配安装
        platform_installers = {
            "cherrystudio": _install_to_cherrystudio,
            "continue": _install_to_continue,
            "windsurf": _install_to_windsurf,
            "cursor": _install_to_cursor,
            "claude-code": _install_to_claude_code,
            "project": _install_to_project,
        }
        installer = platform_installers.get(target)
        if not installer:
            print(f"[X] 不支持的平台: {target}")
            return 1

        result = installer(tmpdir, manifest, args, config)

        # 6. 记录版本历史
        if result == 0:
            _record_version(tmpdir, manifest, target, args)
            _print_install_report(manifest, target, config)

    return result


def _extract_package(pkg_path, target_dir):
    """解包 .agentpkg 到目标目录"""
    with tarfile.open(pkg_path, "r:gz") as tar:
        # .agentpkg 内部顶级目录为 agent-package/
        tar.extractall(path=target_dir)
    # 如果有包内顶级目录，移到外面
    inner = os.path.join(target_dir, "agent-package")
    if os.path.isdir(inner):
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item),
                        os.path.join(target_dir, item))
        os.rmdir(inner)


def _load_manifest(tmpdir):
    """读取 manifest.json"""
    path = os.path.join(tmpdir, "manifest.json")
    if not os.path.isfile(path):
        print(f"[X] 包中缺少 manifest.json")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_dependencies(manifest, args):
    """检查依赖"""
    deps = manifest.get("dependencies", {})
    tools = deps.get("tools", {})

    py_req = tools.get("python", {})
    if py_req.get("required", True):
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"    Python: {py_ver} (需要 {py_req.get('version', '>=3.10')})")

    # 可选工具提示
    ext_tools = deps.get("externalTools", {})
    for name, info in ext_tools.items():
        platform = info.get("platform", "")
        if platform and platform != sys.platform.replace("win32", "windows").replace("darwin", "macos").replace("linux", "linux"):
            continue
        if info.get("required", False):
            print(f"    [?] 需要 {name}: {info.get('description', '')}")
            found = _which(name)
            if not found:
                print(f"        [MISS] 未找到")


def _interactive_config(manifest):
    """交互式配置向导"""
    print("")
    print("╔══════════════════════════════════════════╗")
    print("║      Agent Package 安装配置向导          ║")
    print("╚══════════════════════════════════════════╝")
    print("")

    config = {}

    # Python 路径
    default_py = sys.executable
    answer = input(f"  Python 路径 [{default_py}]: ").strip()
    config["python_path"] = answer or default_py

    # J-Link SN
    sn = _auto_detect_jlink_sn()
    default_sn = sn or "跳过（可选依赖）"
    answer = input(f"  J-Link SN [{default_sn}]: ").strip()
    config["jlink_sn"] = answer if answer else (sn or "")

    # Keil path
    keil = _auto_detect_keil()
    default_keil = keil or "跳过（可选依赖）"
    answer = input(f"  Keil UV4 路径 [{default_keil}]: ").strip()
    config["keil_path"] = answer if answer else (keil or "")

    # 串口
    ports = _auto_detect_serial_ports()
    if ports:
        print(f"  可用串口: {', '.join(ports[:5])}")
    default_port = ports[0] if ports else "跳过"
    answer = input(f"  串口号 [{default_port}]: ").strip()
    config["serial_port"] = answer if answer else (ports[0] if ports else "")

    print("")
    return config


def _auto_config(manifest, target, args):
    """自动配置（非交互模式）"""
    config = {
        "python_path": sys.executable,
        "jlink_sn": _auto_detect_jlink_sn() or "",
        "keil_path": _auto_detect_keil() or "",
        "serial_port": "",
    }
    ports = _auto_detect_serial_ports()
    if ports:
        config["serial_port"] = ports[0]

    if args.agent_dir:
        config["agent_dir"] = args.agent_dir
    if args.skills_dir:
        config["skills_dir"] = args.skills_dir

    return config


def _apply_config(tmpdir, config):
    """将用户配置写回到包中的文件"""
    for root, _dirs, files in os.walk(tmpdir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            original = content
            content = content.replace("{USER_HOME}\\", os.path.expanduser("~") + "\\")
            content = content.replace("{SERIAL_PORT}", config.get("serial_port", ""))
            content = content.replace("{PYTHON_EXE}", config.get("python_path", ""))

            if content != original:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)


def _install_to_cherrystudio(tmpdir, manifest, args, config):
    """安装到 CherryStudio"""
    # 目标路径检测或参数指定
    base = config.get("skills_dir") or os.path.join(
        os.environ.get("APPDATA", ""),
        "CherryStudio", "Data"
    ) if sys.platform == "win32" else os.path.join(
        os.path.expanduser("~"), ".config", "CherryStudio"
    )

    skills_dir = config.get("skills_dir") or os.path.join(base, "Skills")
    agent_dir = config.get("agent_dir") or os.path.join(base, "Agents")

    print(f"    Skills → {skills_dir}")
    print(f"    Agent  → {agent_dir}")

    # 安装 skills
    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        os.makedirs(skills_dir, exist_ok=True)
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print(f"      [+] skill/{skill_name}")

    # 安装 agent 配置
    src_agent = os.path.join(tmpdir, "agent")
    if os.path.isdir(src_agent):
        os.makedirs(agent_dir, exist_ok=True)
        for fname in os.listdir(src_agent):
            src = os.path.join(src_agent, fname)
            dst = os.path.join(agent_dir, fname)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                print(f"      [+] agent/{fname}")

    # 安装 workflow 脚本
    src_wf = os.path.join(tmpdir, "workflow")
    if os.path.isdir(src_wf):
        wf_target = os.path.join(skills_dir, "workflow")
        if os.path.isdir(wf_target):
            # 只更新 scripts 子目录
            dst_scripts = os.path.join(wf_target, "scripts")
            if os.path.isdir(dst_scripts):
                shutil.rmtree(dst_scripts)
            src_scripts = os.path.join(src_wf, "scripts")
            if os.path.isdir(src_scripts):
                shutil.copytree(src_scripts, dst_scripts)
        print(f"      [+] workflow/scripts")

    return 0


def _install_to_continue(tmpdir, manifest, args, config):
    """安装到 Continue.dev"""
    continue_dir = os.path.join(os.path.expanduser("~"), ".continue")
    os.makedirs(continue_dir, exist_ok=True)

    skills_dir = os.path.join(continue_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)
    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    # 尝试更新 Continue config.json
    config_path = os.path.join(continue_dir, "config.json")
    continue_config = {}
    if os.path.isfile(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            try:
                continue_config = json.load(f)
            except json.JSONDecodeError:
                pass
    continue_config["skills"] = list(os.listdir(skills_dir))
    continue_config["agentPackages"] = continue_config.get("agentPackages", [])
    continue_config["agentPackages"].append({
        "name": manifest["name"],
        "version": manifest["version"],
        "soulmd": "~/.continue/skills/SOUL.md"
    })
    _apply_config(tmpdir, config)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(continue_config, f, indent=2)

    return 0


def _install_to_windsurf(tmpdir, manifest, args, config):
    """安装到 Windsurf"""
    windsurf_dir = os.path.join(os.path.expanduser("~"), ".windsurf")
    os.makedirs(windsurf_dir, exist_ok=True)

    skills_dir = os.path.join(windsurf_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        _apply_config(tmpdir, config)
        shutil.copy2(soul_src, os.path.join(windsurf_dir, "rules.md"))

    return 0


def _install_to_cursor(tmpdir, manifest, args, config):
    """安装到 Cursor"""
    # 探测 Cursor 目录
    cursor_dir = os.path.join(os.path.expanduser("~"), ".cursor")
    if not os.path.isdir(cursor_dir):
        # 尝试从 APPDATA 找
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            cursor_dir = os.path.join(appdata, "Cursor")
    os.makedirs(cursor_dir, exist_ok=True)

    # Skills → ~/.cursor/skills-cursor/
    skills_dir = os.path.join(cursor_dir, "skills-cursor")
    os.makedirs(skills_dir, exist_ok=True)
    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"      [+]   skills-cursor/{skill_name}")

    # .cursorrules (agent personality)
    _apply_config(tmpdir, config)
    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        cursor_rules = os.path.join(cursor_dir, "rules", "chip.md")
        os.makedirs(os.path.dirname(cursor_rules), exist_ok=True)
        shutil.copy2(soul_src, cursor_rules)
        print(f"      [+]   {cursor_rules}")

    return 0


def _install_to_claude_code(tmpdir, manifest, args, config):
    """安装到 Claude Code (CLI)"""
    claude_dir = os.path.join(os.path.expanduser("~"), ".claude")
    os.makedirs(claude_dir, exist_ok=True)

    # Skills → ~/.claude/skills/
    skills_dir = os.path.join(claude_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)
    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"      [+]   skills/{skill_name}")

    # CLAUDE.md (agent personality — 全局 fallback)
    _apply_config(tmpdir, config)
    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        claude_md = os.path.join(claude_dir, "CLAUDE.md")
        shutil.copy2(soul_src, claude_md)
        print(f"      [+]   ~/.claude/CLAUDE.md")

    # settings.json — 注册 skills 目录
    settings_path = os.path.join(claude_dir, "settings.json")
    settings = {}
    if os.path.isfile(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                pass
    settings.setdefault("skills", {}).setdefault("directories", [])
    skills_dir_abs = os.path.abspath(skills_dir)
    if skills_dir_abs not in settings["skills"]["directories"]:
        settings["skills"]["directories"].append(skills_dir_abs)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    print(f"      [+]   ~/.claude/settings.json (skills 目录已注册)")

    return 0


def _install_to_project(tmpdir, manifest, args, config):
    """安装为项目级配置（当前工作目录）"""
    project_dir = os.getcwd()
    print(f"    项目目录: {project_dir}")

    _apply_config(tmpdir, config)

    # CLAUDE.md — Claude Code 项目级
    soul_src = os.path.join(tmpdir, "agent", "SOUL.md")
    if os.path.isfile(soul_src):
        claude_md = os.path.join(project_dir, "CLAUDE.md")
        shutil.copy2(soul_src, claude_md)
        print(f"      [+]   {project_dir}/CLAUDE.md")

    # .cursorrules — Cursor 项目级
    claude_md_local = os.path.join(project_dir, "CLAUDE.md")
    if os.path.isfile(claude_md_local):
        cursor_rules = os.path.join(project_dir, ".cursorrules")
        shutil.copy2(claude_md_local, cursor_rules)
        print(f"      [+]   {project_dir}/.cursorrules")

    # .clinerules — Cline 项目级
    clinerules = os.path.join(project_dir, ".clinerules")
    if os.path.isfile(claude_md_local) and not os.path.isfile(clinerules):
        shutil.copy2(claude_md_local, clinerules)
        print(f"      [+]   {project_dir}/.clinerules")

    # skills → _skills/ 子目录
    skills_dir = os.path.join(project_dir, "_skills")
    os.makedirs(skills_dir, exist_ok=True)
    src_skills = os.path.join(tmpdir, "skills")
    if os.path.isdir(src_skills):
        for skill_name in os.listdir(src_skills):
            src = os.path.join(src_skills, skill_name)
            dst = os.path.join(skills_dir, skill_name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
        print(f"      [+]   _skills/ ({len(os.listdir(src_skills))} skills)")

    return 0


def _record_version(tmpdir, manifest, target, args):
    """记录版本历史到目标"""
    # 安装时不需要记录到包目录，由版本管理模块处理
    pass


def _print_install_report(manifest, target, config):
    """打印安装报告"""
    print("")
    print("┌─────────────────────────────────────────┐")
    print(f"│ Agent Package 安装完成                    │")
    print(f"│ {manifest['name']} v{manifest['version']}                      │")
    print(f"│ 目标平台: {target}                              │")
    print(f"│ Skills: {manifest['skills']['total']}                                 │")
    print("├─────────────────────────────────────────┤")
    if config.get("python_path"):
        print(f"│ [+] Python: {config['python_path']}")
    if config.get("jlink_sn"):
        print(f"│ [+] J-Link SN: {config['jlink_sn']}")
    else:
        print(f"│ [ ] J-Link: 未配置（可选，跳过）")
    if config.get("keil_path"):
        print(f"│ [+] Keil: {config['keil_path']}")
    else:
        print(f"│ [ ] Keil: 未找到（可选，跳过）")
    if config.get("serial_port"):
        print(f"│ [+] 串口: {config['serial_port']}")
    print("└─────────────────────────────────────────┘")


def _build_install_plan(manifest, target, args):
    """构建安装计划（用于 dry-run 展示）"""
    return {
        "name": manifest["name"],
        "version": manifest["version"],
        "target": target,
        "skills_count": manifest["skills"]["total"],
        "categories": manifest["skills"].get("categories", {}),
    }


def _print_install_plan(plan):
    """打印安装计划"""
    print(f"    包名: {plan['name']} v{plan['version']}")
    print(f"    目标: {plan['target']}")
    print(f"    技能: {plan['skills_count']} 个")
    for cat, count in plan.get("categories", {}).items():
        print(f"      - {cat}: {count}")


def _auto_detect_jlink_sn():
    """自动探测 J-Link SN"""
    try:
        jlink = _which("JLink.exe") or _which("JLink")
        if not jlink:
            # 常见安装路径
            common = [
                r"C:\Program Files\SEGGER\JLink\JLink.exe",
                r"C:\Program Files (x86)\SEGGER\JLink\JLink.exe",
            ]
            jlink = next((p for p in common if os.path.isfile(p)), None)
        if not jlink:
            return ""

        result = subprocess.run(
            [jlink, "-ListEmulatorsId"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.split("\n"):
            if "S/N" in line:
                parts = line.split("S/N:")
                if len(parts) > 1:
                    return parts[1].strip().split()[0]
        return ""
    except Exception:
        return ""


def _auto_detect_keil():
    """自动探测 Keil UV4 路径"""
    common = [
        r"G:\keil5\core\UV4\UV4.exe", r"C:\Keil_v5\UV4\UV4.exe",
        r"D:\Keil_v5\UV4\UV4.exe", r"G:\Keil_v5\UV4\UV4.exe",
    ]
    for p in common:
        if os.path.isfile(p):
            return p
    return ""


def _auto_detect_serial_ports():
    """自动枚举可用串口"""
    try:
        if sys.platform == "win32":
            import serial.tools.list_ports
            return [p.device for p in serial.tools.list_ports.comports()[:10]]
    except ImportError:
        pass
    return []


def _which(cmd):
    """检查命令是否存在"""
    return shutil.which(cmd)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", "-p", required=True)
    parser.add_argument("--target", "-t", default="cherrystudio")
    parser.add_argument("--interactive", "-i", action="store_true")
    parser.add_argument("--agent-dir")
    parser.add_argument("--skills-dir")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-signature", action="store_true")
    parser.add_argument("--public-key")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    sys.exit(run_install(args))
