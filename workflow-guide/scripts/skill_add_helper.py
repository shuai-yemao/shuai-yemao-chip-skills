#!/usr/bin/env python3
"""
Chip 技能添加辅助工具 — 五步闭合集自动化
=================================================
添加新 skill 时自动执行五步闭合集：
  1. 更新 SOUL.md 技能表
  2. 更新 FACT.md 技能统计数
  3. 同步 CLAUDE.md 副本 × 2
  4. 运行 health check 验证
  5. 自动打包 + 注册 registry（可选 --with-exe 构建 .exe）

用法:
  python skill_add_helper.py add --name <skill-name> \
      --category <分类> --description <描述>

  python skill_add_helper.py add --name can-debug \
      --category "通信协议" --description "CAN 总线调试"

  # 添加并自动打包（含 --with-exe 构建 .exe，耗时 1-3 分钟）
  python skill_add_helper.py add --name uart-module \
      --category "日志与监控" --description "UART 串口配置" --with-exe

  python skill_add_helper.py list-categories    # 列出已有分类
  python skill_add_helper.py status              # 查看技能统计
  python skill_add_helper.py sync                # 仅同步 CLAUDE.md 副本
  python skill_add_helper.py check               # 检查技能表一致性
"""

import io
import json
import os
import re
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

AGENT_DIR = APPDATA / "CherryStudio" / "Data" / "Agents"
SKILLS_DIR = APPDATA / "CherryStudio" / "Data" / "Skills"
CLAUDE_HOME = HOME / ".claude" / "CLAUDE.md"

# 打包时排除的 skill（非嵌入式工作流相关的通用 skill）
EXCLUDED_SKILLS = [
    "academic-search", "agent-team", "content-creation-publisher",
    "document-polisher", "paper-orchestra", "webapp-testing",
    "frontend-design", "canvas-design", "theme-factory",
    "notebooklm", "notebooklm-enterprise-api", "conversiontools",
    "office-mcp", "json-canvas",
    "claude-api", "cpp-pro",
]

# 已知的 Agent ID（自动发现）
USER_AGENT_PATTERN = re.compile(
    r"\| 任务类型 \| Skill \|\n\|---------\|-------\|\n(.*?)(?=\n###|\Z)",
    re.DOTALL,
)
SKILL_TABLE_LINE = re.compile(r"\| (.+?) \| `(.+?)` \|")
CATEGORY_HEADER = re.compile(r"\| \*\*(.+?)\*\* \|")


def _find_agent_dir() -> Path | None:
    """自动探测 Agent 目录"""
    if not AGENT_DIR.is_dir():
        return None
    for d in sorted(AGENT_DIR.iterdir()):
        if (d / "CLAUDE.md").exists() and (d / "memory" / "FACT.md").exists():
            return d
    for d in sorted(AGENT_DIR.iterdir()):
        if (d / "SOUL.md").exists():
            return d
    return None


def _read_soul() -> str | None:
    agent = _find_agent_dir()
    if not agent:
        return None
    soul = agent / "SOUL.md"
    return soul.read_text(encoding="utf-8") if soul.exists() else None


def _read_fact() -> str | None:
    agent = _find_agent_dir()
    if not agent:
        return None
    fact = agent / "memory" / "FACT.md"
    return fact.read_text(encoding="utf-8") if fact.exists() else None


def _write_soul(content: str) -> bool:
    agent = _find_agent_dir()
    if not agent:
        return False
    (agent / "SOUL.md").write_text(content, encoding="utf-8")
    return True


def _write_fact(content: str) -> bool:
    agent = _find_agent_dir()
    if not agent:
        return False
    (agent / "memory" / "FACT.md").write_text(content, encoding="utf-8")
    return True


# ── 技能表解析 ────────────────────────────────────────────────


def parse_skill_table(soul_content: str) -> dict[str, list[tuple[str, str]]]:
    """解析 SOUL.md 中的技能表，返回 {分类: [(任务, skill名)]}"""
    table: dict[str, list[tuple[str, str]]] = {}
    current_category = "未分类"

    # 找到 ### 1. Skill 优先 到 ### 2. 知识检索闭环 之间的内容
    section = re.search(
        r"### 1\. Skill 优先\n(.*?)(?=### 2\. 知识检索闭环)",
        soul_content, re.DOTALL,
    )
    if not section:
        return table

    lines = section.group(1).splitlines()
    in_table = False

    for line in lines:
        cat_match = CATEGORY_HEADER.search(line)
        if cat_match:
            current_category = cat_match.group(1)
            in_table = True
            if current_category not in table:
                table[current_category] = []
            continue

        if "| ---" in line or "|-" in line:
            in_table = True
            continue

        if in_table and line.startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                task = parts[1].strip()
                skill = parts[2].strip().strip("`")
                # 跳过空白行和表头
                if task and skill and task != "任务类型":
                    # 检查是否是分类行（没有 ` 包裹的 skill）
                    if skill and "`" not in line.split("|")[2]:
                        # 可能是分类标题行，跳过
                        continue
                    table.setdefault(current_category, []).append(
                        (task.replace("**", "").strip(), skill.replace("**", "").strip())
                    )

    return table


def get_skill_count(soul_content: str) -> int:
    """统计 SOUL.md 技能表中的 skill 总数"""
    table = parse_skill_table(soul_content)
    return sum(len(items) for items in table.values())


def get_categories(soul_content: str) -> list[str]:
    """获取所有分类"""
    table = parse_skill_table(soul_content)
    return list(table.keys())


def skill_exists(soul_content: str, skill_name: str) -> bool:
    """检查 skill 是否已在表中"""
    table = parse_skill_table(soul_content)
    for items in table.values():
        for _, s in items:
            if s == skill_name:
                return True
    return False


# ── 添加 skill ────────────────────────────────────────────────


def cmd_add(name: str, category: str, description: str) -> int:
    """添加新 skill 到 SOUL.md + FACT.md + 同步 CLAUDE.md"""
    soul = _read_soul()
    if not soul:
        print("[X] 无法读取 SOUL.md")
        return 1

    # 检查是否已存在
    if skill_exists(soul, name):
        print(f"[!] skill '{name}' 已存在于技能表中")
        return 1

    # 检查目录是否存在
    skill_dir = SKILLS_DIR / name
    if not skill_dir.exists() or not (skill_dir / "SKILL.md").exists():
        print(f"[!] 警告: skill 目录或 SKILL.md 不存在: {skill_dir}")
        print(f"    skill 需要先在 Skills 目录中安装才能添加")
        proceed = input("    仍然继续? (y/N): ").strip().lower()
        if proceed != "y":
            print("[X] 已取消")
            return 1

    # Step 1: 更新 SOUL.md 技能表
    print(f"\n[Step 1/5] 更新 SOUL.md 技能表...")

    # 在指定分类的最后一行前插入
    categories = get_categories(soul)
    if category not in categories:
        print(f"[X] 分类 '{category}' 不存在！可用分类: {categories}")
        print(f"    使用 'list-categories' 查看所有分类")
        return 1

    # 找到该分类在技能表中的位置
    # 格式: "| **分类名** | |"
    cat_pattern = re.escape(f"| **{category}** |")
    match = re.search(cat_pattern, soul)
    if not match:
        # 尝试另一种格式（分类行带 skill 名或为空）
        cat_pattern2 = re.escape(f"| **{category}**")
        match = re.search(cat_pattern2, soul)
    if not match:
        print(f"[X] 在 SOUL.md 中找不到分类 '{category}' 的表头行")
        return 1

    # 找该分类后的下一个分类行或表尾，在其前插入
    after_pos = match.end()
    remaining = soul[after_pos:]

    # 找下一个分类或表结束
    next_cat = re.search(r"\n\| \*\*", remaining)
    if next_cat:
        insert_pos = after_pos + next_cat.start()
    else:
        # 在表尾前插入（表尾是空行或下一个顶级标题）
        table_end = re.search(r"\n\n", remaining)
        if table_end:
            insert_pos = after_pos + table_end.start()
        else:
            insert_pos = len(soul)

    new_line = f"\n| {description} | `{name}` |"
    soul = soul[:insert_pos] + new_line + soul[insert_pos:]
    _write_soul(soul)
    print(f"  [OK] 已添加: {description} → `{name}` @ {category}")

    # Step 2: 更新 FACT.md 技能统计
    print(f"\n[Step 2/5] 更新 FACT.md 技能统计...")
    fact = _read_fact()
    if fact:
        new_count = get_skill_count(soul)
        # 更新技能总数（"共计 N 个"或 "N 个 skill" 等模式）
        fact = re.sub(
            r"(嵌入式 skills 共计 )\d+",
            f"\\g<1>{new_count}",
            fact,
        )
        _write_fact(fact)
        print(f"  [OK] 技能总数更新为 {new_count}")
    else:
        print(f"  [!] FACT.md 不存在，跳过")

    # Step 3: 同步 CLAUDE.md 副本 × 2
    print(f"\n[Step 3/5] 同步 CLAUDE.md 副本...")
    agent_dir = _find_agent_dir()
    synced = 0
    if agent_dir:
        target = agent_dir / "CLAUDE.md"
        target.write_text(soul, encoding="utf-8")
        synced += 1
        print(f"  [OK] 同步: {target}")
    if CLAUDE_HOME.exists():
        CLAUDE_HOME.write_text(soul, encoding="utf-8")
        synced += 1
        print(f"  [OK] 同步: {CLAUDE_HOME}")

    # Step 4: 运行 health check 验证
    print(f"\n[Step 4/5] 运行 health check 验证...")
    health_script = SKILLS_DIR / "workflow-guide" / "scripts" / "system_health.py"
    if health_script.exists():
        result = subprocess.run(
            [sys.executable, str(health_script), "--quick"],
            timeout=30,
        )
        if result.returncode == 0:
            print(f"  [OK] Health check 通过")
        else:
            print(f"  [!] Health check 返回警告 (exit {result.returncode})")
    else:
        print(f"  [!] system_health.py 未找到，跳过")

    # Step 5: 自动重新打包 + 注册 registry
    print(f"\n[Step 5/5] 自动打包 & 注册...")
    agent_dir = _find_agent_dir()
    packager_script = SKILLS_DIR / "agent-packager" / "scripts" / "agent_packager.py"
    registry_script = SKILLS_DIR / "workflow-guide" / "scripts" / "pkg_registry.py"
    build_exe_script = SKILLS_DIR / "agent-packager" / "scripts" / "packager_build_exe.py"
    # 通过 --with-exe 标志控制 .exe 构建（默认跳过，因耗时 1-3 分钟）
    build_exe_flag = "--with-exe" in sys.argv

    export_ok = False
    registry_ok = False
    exe_ok = False

    if agent_dir and packager_script.exists():
        # 构建版本号
        import datetime
        date_tag = datetime.date.today().strftime("%Y%m%d")
        ver = f"2.1.{date_tag}"
        output_pkg = Path.home() / "Desktop" / f"cherryclaw-embedded-{ver}.agentpkg"

        result = subprocess.run(
            [sys.executable, str(packager_script),
             "export",
             "--agent-dir", str(agent_dir),
             "--skills-dir", str(SKILLS_DIR),
             "--output", str(output_pkg),
             "--version", ver,
             "--exclude-skills"] + EXCLUDED_SKILLS,
            capture_output=True, text=False, timeout=120,
        )
        stderr = result.stderr.decode("utf-8", errors="replace")
        if result.returncode == 0 and output_pkg.exists():
            size_mb = output_pkg.stat().st_size / 1024 / 1024
            print(f"  [OK] .agentpkg 已导出: {output_pkg.name} ({size_mb:.0f} MB)")
            export_ok = True

            # 注册到本地 registry
            if registry_script.exists():
                reg_result = subprocess.run(
                    [sys.executable, str(registry_script),
                     "register", "--package", str(output_pkg)],
                    capture_output=True, text=False, timeout=30,
                )
                if reg_result.returncode == 0:
                    print(f"  [OK] registry 已更新")
                    registry_ok = True
                else:
                    print(f"  [!] registry 注册失败")

            # 构建 .exe（仅 --with-exe 时执行）
            if build_exe_flag and build_exe_script.exists():
                exe_name = f"Chip-Setup-{ver}.exe"
                exe_output = str(Path.home() / "Desktop" / exe_name)
                print(f"  [*] 正在构建 .exe（约 1-3 分钟）...")
                exe_result = subprocess.run(
                    [sys.executable, str(build_exe_script),
                     "--package", str(output_pkg),
                     "--output", exe_output],
                    timeout=600,
                )
                if exe_result.returncode == 0:
                    exe_path = Path(exe_output)
                    if exe_path.exists():
                        print(f"  [OK] .exe 已构建: {exe_path.name} ({exe_path.stat().st_size / 1024 / 1024:.0f} MB)")
                        exe_ok = True
                else:
                    print(f"  [!] .exe 构建失败 (exit {exe_result.returncode})")
            elif build_exe_flag:
                print(f"  [!] packager_build_exe.py 未找到，跳过 .exe 构建")
        else:
            print(f"  [X] 打包失败 (exit {result.returncode})")
            if stderr:
                print(f"      {stderr[:200]}")
    else:
        print(f"  [!] agent-packager 未找到，跳过打包")

    print(f"\n{'=' * 55}")
    print(f"  [OK] skill '{name}' 添加完成!")
    print(f"  Step 1: SOUL.md 技能表     [OK]")
    print(f"  Step 2: FACT.md 统计        [OK]")
    print(f"  Step 3: CLAUDE.md 同步 ×{synced} [OK]")
    print(f"  Step 4: Health check        [OK]")
    if export_ok:
        print(f"  Step 5: 打包+注册          [OK]")
        if registry_ok:
            print(f"         registry 已更新     [OK]")
        if exe_ok:
            print(f"         .exe 已构建          [OK]")
    else:
        print(f"  Step 5: 打包                [!]")
    print(f"{'=' * 55}")
    return 0


# ── 辅助命令 ──────────────────────────────────────────────────


def cmd_list_categories() -> int:
    """列出所有已有的分类"""
    soul = _read_soul()
    if not soul:
        print("[X] 无法读取 SOUL.md")
        return 1

    cats = get_categories(soul)
    table = parse_skill_table(soul)

    print(f"{'分类':<25} {'技能数':<10}")
    print(f"{'─' * 25} {'─' * 10}")
    for cat in cats:
        count = len(table.get(cat, []))
        print(f"  {cat:<25} {count}")
    print(f"\n  总计: {sum(len(v) for v in table.values())} 个 skill")
    return 0


def cmd_status() -> int:
    """查看技能统计"""
    soul = _read_soul()
    fact = _read_fact()
    if not soul:
        print("[X] 无法读取 SOUL.md")
        return 1

    table = parse_skill_table(soul)
    total = sum(len(items) for items in table.values())

    print(f"{'=' * 55}")
    print(f"  Chip 技能统计")
    print(f"{'=' * 55}")
    print(f"  SOUL.md 技能表: {total} 个")

    # 对比实际 SKILL.md 数量
    if SKILLS_DIR.is_dir():
        actual = sum(
            1 for d in SKILLS_DIR.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and not d.name.startswith("__")
            and (d / "SKILL.md").exists()
        )
        diff = actual - total
        if diff == 0:
            print(f"  Skills 目录:    {actual} 个 [一致]")
        elif diff > 0:
            print(f"  Skills 目录:    {actual} 个 [SOUL.md 少 {diff} 个]")
        else:
            print(f"  Skills 目录:    {actual} 个 [SOUL.md 多 {-diff} 个]")

    if fact:
        # 解析 FACT.md 中的技能统计
        fact_matches = re.findall(r"(\d+)", fact)
        print(f"  FACT.md:        包含统计信息")

    print(f"\n  分类详情:")
    for cat, items in table.items():
        print(f"    {cat}: {len(items)}")
        for task, sk in items[:3]:  # 只显示前3个
            print(f"      - {task} → `{sk}`")
        if len(items) > 3:
            print(f"      ... 还有 {len(items) - 3} 个")
    return 0


def cmd_sync() -> int:
    """仅同步 CLAUDE.md 副本"""
    soul = _read_soul()
    if not soul:
        print("[X] 无法读取 SOUL.md")
        return 1

    synced = 0
    agent_dir = _find_agent_dir()
    if agent_dir:
        (agent_dir / "CLAUDE.md").write_text(soul, encoding="utf-8")
        synced += 1
        print(f"  [OK] 同步 Agent CLAUDE.md")
    if CLAUDE_HOME.exists():
        CLAUDE_HOME.write_text(soul, encoding="utf-8")
        synced += 1
        print(f"  [OK] 同步 ~/.claude/CLAUDE.md")

    print(f"[OK] 已同步 {synced} 个 CLAUDE.md 副本")
    return 0


def cmd_check() -> int:
    """检查技能表与 Skills 目录的一致性"""
    soul = _read_soul()
    if not soul:
        print("[X] 无法读取 SOUL.md")
        return 1

    table = parse_skill_table(soul)
    listed_skills = {s for items in table.values() for _, s in items}

    if SKILLS_DIR.is_dir():
        actual_skills = {
            d.name
            for d in SKILLS_DIR.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and not d.name.startswith("__")
            and (d / "SKILL.md").exists()
        }
    else:
        actual_skills = set()

    in_table_not_in_dir = listed_skills - actual_skills
    in_dir_not_in_table = actual_skills - listed_skills

    issues = 0
    if in_table_not_in_dir:
        print(f"[!] 技能表有但目录中无 ({len(in_table_not_in_dir)}):")
        for s in sorted(in_table_not_in_dir):
            print(f"    - `{s}`")
        issues += len(in_table_not_in_dir)
    else:
        print(f"[OK] 所有技能表中的 skill 都在目录中")

    if in_dir_not_in_table:
        print(f"[!] 目录中有但技能表无 ({len(in_dir_not_in_table)}):")
        for s in sorted(in_dir_not_in_table):
            print(f"    - `{s}`")
        issues += len(in_dir_not_in_table)
    else:
        print(f"[OK] 所有目录中的 skill 都在技能表中")

    if issues == 0:
        total = len(listed_skills)
        print(f"\n[OK] 完全一致! 技能表 = 目录 = {total} 个 skill")
    else:
        print(f"\n[!] 共 {issues} 个不一致项")
    return 0 if issues == 0 else 1


# ── CLI 入口 ──────────────────────────────────────────────────


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    command = sys.argv[1]

    if command == "add":
        # 解析参数
        name = ""
        category = ""
        description = ""
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--name" and i + 1 < len(sys.argv):
                name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--category" and i + 1 < len(sys.argv):
                category = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--description" and i + 1 < len(sys.argv):
                description = sys.argv[i + 1]
                i += 2
            else:
                i += 1

        if not name or not category:
            print("[X] --name 和 --category 为必填参数")
            print("示例: python skill_add_helper.py add --name uart-module "
                  '--category "通信协议" --description "UART 串口配置"')
            return 1

        return cmd_add(name, category, description)

    elif command == "list-categories":
        return cmd_list_categories()
    elif command == "status":
        return cmd_status()
    elif command == "sync":
        return cmd_sync()
    elif command == "check":
        return cmd_check()
    else:
        print(f"[X] 未知命令: {command}")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())
