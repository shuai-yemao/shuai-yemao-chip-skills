#!/usr/bin/env python3
"""
Version management module: 版本历史管理 / 回滚 / 更新检查

功能:
  - run_list_versions: 查看本地版本历史
  - run_rollback: 回滚到指定版本
  - run_check_update: 检查远程更新

版本历史结构:
  <agent-dir>/.agent-versions/
  ├── current -> 1.2.0              # 当前版本符号链接
  ├── history.json                  # 版本历史记录
  ├── 1.0.0/                       # 版本文档
  │   ├── manifest.json
  │   └── .checksums
  ├── 1.1.0/
  │   ├── manifest.json
  │   └── .checksums
  └── 1.2.0/
      ├── manifest.json
      └── .checksums
"""

import json
import os
import shutil
import sys


def run_list_versions(args):
    """列出本地版本历史"""
    target_dir = os.path.abspath(args.target_dir)
    versions_dir = os.path.join(target_dir, ".agent-versions")

    if not os.path.isdir(versions_dir):
        print(f"[!] 目录中没有版本历史: {versions_dir}")
        return 1

    # 读取版本历史
    history_path = os.path.join(versions_dir, "history.json")
    if os.path.isfile(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        print("[!] history.json 缺失")
        return 1

    # 确定当前版本
    current_link = os.path.join(versions_dir, "current")
    current_ver = "?"
    if os.path.islink(current_link):
        current_ver = os.readlink(current_link)
    elif os.path.isfile(current_link):
        with open(current_link, "r") as f:
            current_ver = f.read().strip()

    print("")
    print(f"  版本历史 ({target_dir}):")
    print(f"  当前: v{current_ver}")
    print("")

    for entry in history.get("versions", []):
        ver = entry.get("version", "?")
        marker = "  ← current" if ver == current_ver else ""
        date = entry.get("date", "?")
        print(f"  v{ver}  ({date}){marker}")
        for change in entry.get("changes", [])[:3]:
            print(f"    - {change}")

    print("")
    return 0


def run_rollback(args):
    """回滚到指定版本"""
    target_dir = os.path.abspath(args.target_dir)
    to_version = args.to
    versions_dir = os.path.join(target_dir, ".agent-versions")

    if not os.path.isdir(versions_dir):
        print(f"[X] 无版本历史，无法回滚")
        return 1

    # 读取历史
    history_path = os.path.join(versions_dir, "history.json")
    if not os.path.isfile(history_path):
        print("[X] history.json 缺失，无法回滚")
        return 1

    with open(history_path, "r", encoding="utf-8") as f:
        history = json.load(f)

    # 确认目标版本存在
    version_entries = {e["version"]: e for e in history.get("versions", [])}
    if to_version not in version_entries:
        print(f"[X] 版本 v{to_version} 不存在")
        print(f"    可用版本: {', '.join(version_entries.keys())}")
        return 1

    # 检查当前版本
    current_link = os.path.join(versions_dir, "current")
    if os.path.islink(current_link):
        current_ver = os.readlink(current_link)
    else:
        current_ver = "?"

    if to_version == current_ver:
        print(f"[!] 当前已经是 v{to_version}")
        return 0

    print(f"[*] 回滚: v{current_ver} → v{to_version}")

    # 创建回滚点
    rollback_point = version_entries.get(current_ver, {})
    rollback_log = {
        "rolledBackFrom": current_ver,
        "rolledBackTo": to_version,
        "timestamp": _now_iso(),
        "manifest": rollback_point
    }

    # 检查目标版本是否有文件快照
    version_dir = os.path.join(versions_dir, to_version)
    if os.path.isdir(version_dir):
        print(f"    从版本快照恢复: .agent-versions/{to_version}/")
        _restore_from_snapshot(version_dir, target_dir)
    else:
        print(f"    [!] 版本 v{to_version} 无文件快照，仅回退版本号标记")

    # 更新 current 指向
    _safe_symlink_or_write(versions_dir, "current", to_version)

    # 记录回滚
    rollback_path = os.path.join(versions_dir, "rollback.json")
    with open(rollback_path, "w", encoding="utf-8") as f:
        json.dump(rollback_log, f, indent=2)

    print(f"    [OK] 已回滚到 v{to_version}")
    return 0


def run_check_update(args):
    """检查远程更新（Registry 模式）"""
    current_path = os.path.abspath(args.current)
    registry_url = args.registry.rstrip("/")

    if not os.path.isfile(current_path):
        print(f"[X] 当前包不存在: {current_path}")
        return 1

    # 读取当前版本
    import tarfile, tempfile
    current_ver = "?"
    with tempfile.TemporaryDirectory() as tmpdir:
        with tarfile.open(current_path, "r:gz") as tar:
            tar.extractall(path=tmpdir)
        inner = os.path.join(tmpdir, "agent-package")
        pkg_dir = inner if os.path.isdir(inner) else tmpdir
        mf_path = os.path.join(pkg_dir, "manifest.json")
        if os.path.isfile(mf_path):
            with open(mf_path, "r", encoding="utf-8") as f:
                mf = json.load(f)
            current_ver = mf.get("version", "?")

    print(f"[*] 检查更新: v{current_ver}")
    print(f"    Registry: {registry_url}")

    # 尝试查询 registry
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{registry_url}/api/v1/packages/chip-embedded-agent/latest",
            headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest_ver = data.get("version", "?")
            print(f"    最新版本: v{latest_ver}")

            if _compare_versions(latest_ver, current_ver) > 0:
                print(f"    [UPDATE] 新版本可用: v{current_ver} → v{latest_ver}")
                print(f"    URL: {data.get('downloadUrl', 'N/A')}")
            else:
                print(f"    [OK] 已是最新版本")

            # 显示 changelog
            changes = data.get("changes", [])
            if changes:
                print(f"    Changelog:")
                for c in changes[:5]:
                    print(f"      - {c}")
    except Exception as e:
        print(f"    [!] 无法连接到 Registry: {e}")
        print(f"    请确认 Registry URL 是否正确")
        return 1

    return 0


def record_version(agent_dir, manifest):
    """记录安装后的版本（供 install 模块调用）"""
    versions_dir = os.path.join(agent_dir, ".agent-versions")
    os.makedirs(versions_dir, exist_ok=True)

    version = manifest.get("version", "0.0.0")

    # 读取或创建历史
    history_path = os.path.join(versions_dir, "history.json")
    history = {"versions": []}
    if os.path.isfile(history_path):
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

    # 去重：如果版本已存在则更新，否则追加
    existing = [e for e in history["versions"] if e.get("version") == version]
    if not existing:
        history["versions"].append({
            "version": version,
            "date": _today_iso(),
            "changes": manifest.get("changelog", [{}])[-1].get("changes", [])
            if manifest.get("changelog") else []
        })

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    # 写入版本快照
    ver_dir = os.path.join(versions_dir, version)
    os.makedirs(ver_dir, exist_ok=True)
    # 只保存 manifest 和 checksums
    mf_path = os.path.join(ver_dir, "manifest.json")
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # 更新 current 指向
    _safe_symlink_or_write(versions_dir, "current", version)


def _restore_from_snapshot(version_dir, target_dir):
    """从版本快照恢复文件"""
    # 快照中只保存 manifest.json 和 .checksums
    # 文件本身在安装时已写入目标目录，回滚时只恢复版本标记
    # 如果快照包含完整文件备份，则恢复
    for item in os.listdir(version_dir):
        item_path = os.path.join(version_dir, item)
        if os.path.isdir(item_path) and item in ("agent", "skills"):
            dst = os.path.join(target_dir, item)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(item_path, dst)


def _safe_symlink_or_write(base_dir, name, target):
    """安全创建符号链接或回退到文件写入"""
    link_path = os.path.join(base_dir, name)
    try:
        if os.path.islink(link_path) or os.path.isfile(link_path):
            os.remove(link_path)
        os.symlink(target, link_path)
    except (OSError, AttributeError):
        # 不支持符号链接（如 Windows 无管理员权限）→ 写入文件
        with open(link_path, "w") as f:
            f.write(target)


def _compare_versions(v1, v2):
    """比较两个 semver 版本号"""
    def parse(v):
        return [int(x) for x in v.split(".")]
    p1, p2 = parse(v1), parse(v2)
    for a, b in zip(p1, p2):
        if a != b:
            return a - b
    return 0


def _now_iso():
    """当前时间 ISO 格式"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso():
    """今天日期"""
    from datetime import date
    return date.today().isoformat()
