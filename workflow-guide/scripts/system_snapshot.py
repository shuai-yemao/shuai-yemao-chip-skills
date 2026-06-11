#!/usr/bin/env python3
"""
Chip 系统快照与回滚工�?================================
创建、列出、恢复和验证系统快照�?
快照内容:
  - Agent 核心文件: SOUL.md / USER.md / CLAUDE.md / memory/FACT.md
  - WorkflowState: ~/.workflow_state.json
  - 技能清�? Skills 目录下所�?SKILL.md 路径列表
  - system_health.py 报告（可选）

用法:
  python system_snapshot.py create          # 创建快照
  python system_snapshot.py create --with-health  # 创建快照 + 健康报告
  python system_snapshot.py list            # 列出所有快�?  python system_snapshot.py info <name>     # 查看快照详情
  python system_snapshot.py restore --latest     # 恢复到最新快�?  python system_snapshot.py restore --name <n>   # 恢复到指定快�?  python system_snapshot.py verify          # 验证所有快照完整�?  python system_snapshot.py prune --keep 5  # 保留最�?5 个，删除旧的
"""

import datetime
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows GBK 控制台兼�?if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 路径常量 ──────────────────────────────────────────────────

SNAPSHOT_DIR = Path.home() / ".workflow_snapshots"
STATE_FILE = Path.home() / ".workflow_state.json"

AGENT_CANDIDATE_DIRS = [
    Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data" / "Agents",
    Path(os.environ.get("CHERRY_AGENT_DIR", "")),
]
SKILLS_CANDIDATE_DIRS = [
    Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data" / "Skills",
    Path(os.environ.get("CHERRY_SKILLS_DIR", "")),
]
HEALTH_SCRIPT_RELPATH = Path("workflow-guide") / "scripts" / "system_health.py"


def _find_agent_dir() -> Path | None:
    """自动探测 Agent 目录"""
    for root in AGENT_CANDIDATE_DIRS:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if (d / "CLAUDE.md").exists() and (d / "memory" / "FACT.md").exists():
                return d
        for d in sorted(root.iterdir()):
            if (d / "memory" / "FACT.md").exists():
                return d
        for d in sorted(root.iterdir()):
            if (d / "SOUL.md").exists():
                return d
    return None


def _find_skills_dir() -> Path | None:
    for d in SKILLS_CANDIDATE_DIRS:
        if d.is_dir():
            return d
    return None


def _find_health_script() -> Path | None:
    skills = _find_skills_dir()
    if skills:
        hs = skills / HEALTH_SCRIPT_RELPATH
        if hs.exists():
            return hs
    return None


def _get_version() -> str:
    """�?FACT.md 或包名推测当前版�?""
    agent_dir = _find_agent_dir()
    if agent_dir:
        fact = agent_dir / "memory" / "FACT.md"
        if fact.exists():
            content = fact.read_text(encoding="utf-8")
            import re
            # 优先匹配 "新增: **workflow-guide vX.Y.Z**"
            m = re.search(r"workflow-guide v(\d+\.\d+\.\d+)", content)
            if m:
                return m.group(1)
            # 其次匹配 "2.1.0" 这种版本号行
            m = re.search(r"Chip-embedded-([\d.]+)", content)
            if m:
                return m.group(1)
    return "dev"


# ── 核心功能 ──────────────────────────────────────────────────


def cmd_create(include_health: bool = False) -> int:
    """创建系统快照"""
    agent_dir = _find_agent_dir()
    skills_dir = _find_skills_dir()
    if not agent_dir:
        print("[X] 未检测到 Agent 目录")
        return 1

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    version = _get_version()

    snapshot = {
        "type": "Chip-snapshot",
        "version": version,
        "created_at": datetime.datetime.now().isoformat(),
        "agent_dir": str(agent_dir),
        "skills_dir": str(skills_dir) if skills_dir else "",
        "files": {},
        "skills_list": [],
        "workflow_state": None,
    }

    # 1. 备份 Agent 核心文件
    core_files = ["SOUL.md", "USER.md", "CLAUDE.md", "memory/FACT.md"]
    for rel in core_files:
        fp = agent_dir / rel
        if fp.exists():
            snapshot["files"][rel] = {
                "size": fp.stat().st_size,
                "mtime": datetime.datetime.fromtimestamp(
                    fp.stat().st_mtime
                ).isoformat(),
                "content": fp.read_text(encoding="utf-8"),
            }
            print(f"  [OK] 备份: {rel} ({fp.stat().st_size / 1024:.1f} KB)")
        else:
            print(f"  [!] 跳过: {rel} (不存�?")

    # 2. 备份 WorkflowState
    if STATE_FILE.exists():
        try:
            snapshot["workflow_state"] = json.loads(
                STATE_FILE.read_text(encoding="utf-8")
            )
            print(f"  [OK] 备份: WorkflowState ({len(snapshot['workflow_state'])} keys)")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [!] WorkflowState 读取失败: {e}")

    # 3. 记录技能清�?    if skills_dir:
        skills = sorted(
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and not d.name.startswith("__")
            and (d / "SKILL.md").exists()
        )
        snapshot["skills_list"] = skills
        print(f"  [OK] 技能清�? {len(skills)} �?skill")
    else:
        print(f"  [!] Skills 目录未找�?)

    # 4. 可�? 包含健康报告
    if include_health:
        health_script = _find_health_script()
        if health_script:
            try:
                # 使用 text=False 避免 GBK 解码错误
                result = subprocess.run(
                    [sys.executable, str(health_script), "--report"],
                    capture_output=True,
                    text=False,
                    timeout=30,
                )
                stdout = result.stdout.decode("utf-8", errors="replace")[:2000] if result.stdout else ""
                stderr = result.stderr.decode("utf-8", errors="replace")[:500] if result.stderr else ""
                snapshot["health_report"] = {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.returncode,
                }
                print(f"  [OK] 健康报告已附�?(exit code {result.returncode})")
            except Exception as e:
                print(f"  [!] 健康报告生成失败: {e}")

    # 写入快照文件
    snap_name = f"snapshot_{timestamp}_{version}.json"
    snap_path = SNAPSHOT_DIR / snap_name
    snap_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 写入最新快照索引（方便 --latest�?    latest_link = SNAPSHOT_DIR / "latest"
    latest_link.write_text(snap_name, encoding="utf-8")

    size_kb = snap_path.stat().st_size / 1024
    print(f"\n[OK] 快照创建完成:")
    print(f"     名称: {snap_name}")
    print(f"     版本: {version}")
    print(f"     大小: {size_kb:.1f} KB")
    print(f"     路径: {snap_path}")
    return 0


def cmd_list() -> int:
    """列出所有快�?""
    if not SNAPSHOT_DIR.is_dir():
        print("[i] 无快照目录（首次使用时会自动创建�?)
        return 0

    snaps = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if not snaps:
        print("[i] 无可用快�?)
        return 0

    print(f"  {'名称':<45} {'版本':<12} {'大小':<8} {'时间'}")
    print(f"  {'─' * 45} {'─' * 12} {'─' * 8} {'─' * 20}")
    for snap in snaps:
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            size = snap.stat().st_size / 1024
            created = data.get("created_at", "unknown")[:19]
            version = data.get("version", "?")
            icon = " [L]" if snap.name == _get_latest_name() else ""
            print(f"  {snap.name:<45} {version:<12} {size:>6.0f}KB {created}{icon}")
        except (json.JSONDecodeError, OSError):
            print(f"  {snap.name:<45} {'损坏':<12} {'?':>8}")

    print(f"\n  总计: {len(snaps)} 个快�?)
    return 0


def cmd_info(name: str) -> int:
    """查看快照详情"""
    snap_path = _resolve_snapshot(name)
    if not snap_path:
        print(f"[X] 快照不存�? {name}")
        return 1

    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[X] 快照读取失败: {e}")
        return 1

    print(f"  名称:        {snap_path.name}")
    print(f"  版本:        {data.get('version', '?')}")
    print(f"  创建时间:    {data.get('created_at', '?')}")
    print(f"  Agent 目录:  {data.get('agent_dir', '?')}")
    print(f"  Skills 目录: {data.get('skills_dir', '?')}")
    print(f"  文件备份:")
    for rel, info in data.get("files", {}).items():
        mtime = info.get("mtime", "?")[:19]
        size = info.get("size", 0) / 1024
        print(f"    {rel:<30} {size:>6.1f} KB  ({mtime})")
    skills = data.get("skills_list", [])
    print(f"  技能数�?    {len(skills)}")
    wf_state = data.get("workflow_state")
    print(f"  WorkflowState: {'�? if wf_state else '�?}")
    if wf_state:
        print(f"    keys: {list(wf_state.keys())}")
    health = data.get("health_report")
    if health:
        print(f"  健康报告:    exit code {health.get('exit_code', '?')}")
    print(f"  文件大小:    {snap_path.stat().st_size / 1024:.1f} KB")
    return 0


def cmd_restore(name: str = "latest", dry_run: bool = False) -> int:
    """恢复快照"""
    snap_path = _resolve_snapshot(name)
    if not snap_path:
        print(f"[X] 快照不存�? {name}")
        return 1

    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[X] 快照读取失败: {e}")
        return 1

    agent_dir = Path(data.get("agent_dir", ""))
    if not agent_dir.is_dir():
        print(f"[X] Agent 目录不存�? {agent_dir}")
        return 1

    version = data.get("version", "?")
    created = data.get("created_at", "?")[:19]
    print(f"[i] 准备恢复快照: {snap_path.name}")
    print(f"    版本: {version}, 创建�? {created}")
    print()

    if dry_run:
        print(f"[i] 试运行模�?- 不会实际写入文件")
        for rel in data.get("files", {}):
            print(f"    [DRY-RUN] 恢复: {rel}")
        if data.get("workflow_state"):
            print(f"    [DRY-RUN] 恢复: WorkflowState")
        print(f"\n[OK] 试运行完成，未写入任何文�?)
        return 0

    # 恢复核心文件
    restored = 0
    skipped = 0
    for rel, info in data.get("files", {}).items():
        fp = agent_dir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        try:
            fp.write_text(info["content"], encoding="utf-8")
            print(f"  [OK] 恢复: {rel} ({info.get('size', 0) / 1024:.1f} KB)")
            restored += 1
        except OSError as e:
            print(f"  [X] 恢复失败: {rel} - {e}")

    # 恢复 WorkflowState
    if data.get("workflow_state"):
        try:
            STATE_FILE.write_text(
                json.dumps(data["workflow_state"], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"  [OK] 恢复: WorkflowState ({len(data['workflow_state'])} keys)")
            restored += 1
        except OSError as e:
            print(f"  [X] WorkflowState 恢复失败: {e}")

    # 记录回滚
    rollback_record = {
        "type": "rollback",
        "snapshot": snap_path.name,
        "version_from": _get_version(),
        "version_to": version,
        "created_at": datetime.datetime.now().isoformat(),
        "files_restored": restored,
    }
    rollback_path = SNAPSHOT_DIR / f"rollback_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    rollback_path.write_text(json.dumps(rollback_record, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[OK] 快照恢复完成! 已恢�?{restored} 个文�?)
    print(f"    回滚记录: {rollback_path.name}")
    print(f"    [!] 建议运行 health check 验证恢复状�?")
    print(f"        python system_health.py")
    return 0


def cmd_verify() -> int:
    """验证所有快照完整�?""
    if not SNAPSHOT_DIR.is_dir():
        print("[i] 无快照目�?)
        return 0

    snaps = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if not snaps:
        print("[i] 无可用快�?)
        return 0

    ok = 0
    corrupt = 0
    for snap in snaps:
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            # 校验必要字段
            required = ["type", "version", "created_at", "files"]
            if all(k in data for k in required):
                ok += 1
            else:
                print(f"  [X] 字段缺失: {snap.name}")
                corrupt += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"  [X] JSON 损坏: {snap.name} - {e}")
            corrupt += 1

    total = len(snaps)
    if corrupt == 0:
        print(f"[OK] 全部 {total}/{total} 个快照完整性验证通过")
        return 0
    else:
        print(f"[!] {ok}/{total} 正常, {corrupt}/{total} 损坏")
        return 1


def cmd_prune(keep: int = 5) -> int:
    """删除旧快照，保留最�?N �?""
    if not SNAPSHOT_DIR.is_dir():
        print("[i] 无快照目�?)
        return 0

    snaps = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    if len(snaps) <= keep:
        print(f"[i] 当前 {len(snaps)} 个快照，<= 保留�?{keep}，无需清理")
        return 0

    to_delete = snaps[:-keep]
    for snap in to_delete:
        snap.unlink()
        print(f"  [DEL] {snap.name}")

    print(f"\n[OK] 已删�?{len(to_delete)} 个旧快照，保留最�?{keep} �?)
    return 0


# ── 辅助函数 ──────────────────────────────────────────────────


def _get_latest_name() -> str | None:
    latest_link = SNAPSHOT_DIR / "latest"
    if latest_link.exists():
        return latest_link.read_text(encoding="utf-8").strip()
    return None


def _resolve_snapshot(name: str) -> Path | None:
    """将快照名称解析为路径"""
    if name == "latest":
        latest_name = _get_latest_name()
        if not latest_name:
            # 最新文�?            snaps = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
            if snaps:
                return snaps[-1]
            return None
        return SNAPSHOT_DIR / latest_name

    # 按名称精确匹�?    fp = SNAPSHOT_DIR / name
    if fp.exists():
        return fp
    # 按前缀匹配
    matches = sorted(SNAPSHOT_DIR.glob(f"snapshot_{name}*.json"))
    if matches:
        return matches[-1]
    return None


# ── CLI ───────────────────────────────────────────────────────


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    command = sys.argv[1]

    if command == "create":
        include_health = "--with-health" in sys.argv
        return cmd_create(include_health)
    elif command == "list":
        return cmd_list()
    elif command == "info":
        name = sys.argv[2] if len(sys.argv) > 2 else "latest"
        return cmd_info(name)
    elif command == "restore":
        name = "latest"
        dry_run = False
        for arg in sys.argv[2:]:
            if arg == "--dry-run":
                dry_run = True
            elif arg.startswith("--name="):
                name = arg.split("=", 1)[1]
            elif arg.startswith("--name "):
                pass  # handled below
            elif not arg.startswith("-"):
                name = arg
        return cmd_restore(name, dry_run)
    elif command == "verify":
        return cmd_verify()
    elif command == "prune":
        keep = 5
        for arg in sys.argv[2:]:
            if arg.startswith("--keep="):
                keep = int(arg.split("=", 1)[1])
        return cmd_prune(keep)
    else:
        print(f"[X] 未知命令: {command}")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())
