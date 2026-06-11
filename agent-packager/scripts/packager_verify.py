#!/usr/bin/env python3
"""
Verify module: 包完整性校验 / 信息查看

功能:
  - run_info: 显示 .agentpkg 包信息
  - run_verify: 校验 checksums + manifest 完整性
  - verify_checksums: 目录级 SHA256 校验
"""

import hashlib
import json
import os
import sys
import tarfile
import tempfile


def run_info(args):
    """显示包信息"""
    pkg_path = os.path.abspath(args.package)
    if not os.path.isfile(pkg_path):
        print(f"[X] 文件不存在: {pkg_path}")
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        _extract_package(pkg_path, tmpdir)
        manifest = _load_manifest(tmpdir)

        print("")
        print(f"  Agent:     {manifest.get('name', 'unknown')}")
        print(f"  版本:      v{manifest.get('version', '?')}")
        print(f"  类型:      {manifest.get('type', 'unknown')}")
        print(f"  描述:      {manifest.get('description', '-')}")
        print(f"  作者:      {manifest.get('author', '-')}")
        print(f"  创建时间:  {manifest.get('createdAt', '-')}")
        print(f"  平台:      {', '.join(manifest.get('compatibility', {}).get('platforms', []))}")
        print(f"  宿主工具:  {', '.join(manifest.get('compatibility', {}).get('hosts', []))}")

        skills = manifest.get("skills", {})
        print(f"  Skills:    {skills.get('total', 0)}")
        for cat, count in skills.get("categories", {}).items():
            print(f"    - {cat}: {count}")

        wf = manifest.get("workflow", {})
        if wf:
            print(f"  工作流:    v{wf.get('version', '?')}, {wf.get('pipelines', 0)} 条流水线")

        # 文件大小
        size = os.path.getsize(pkg_path)
        if size < 1024 * 1024:
            print(f"  包大小:    {size / 1024:.1f} KB")
        else:
            print(f"  包大小:    {size / (1024 * 1024):.1f} MB")

        # changelog
        changelog = manifest.get("changelog", [])
        if changelog:
            latest = changelog[-1]
            print(f"  最近更新:  v{latest['version']} ({latest['date']})")
            for change in latest["changes"][:5]:
                print(f"    - {change}")
        print("")

    return 0


def run_verify(args):
    """校验包完整性入口"""
    if args.installed and args.target_dir:
        return verify_installed(args.target_dir)
    elif args.package:
        return verify_package(args.package)
    else:
        print("[!] 请指定 --package 或 --installed --target-dir")
        return 1


def verify_package(pkg_path):
    """校验 .agentpkg 包"""
    pkg_path = os.path.abspath(pkg_path)
    if not os.path.isfile(pkg_path):
        print(f"[X] 文件不存在: {pkg_path}")
        return 1

    errors = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"[*] 校验包完整性: {os.path.basename(pkg_path)}")

        # 1. 解包
        try:
            _extract_package(pkg_path, tmpdir)
            print("    [OK] 解包成功")
        except Exception as e:
            print(f"    [X] 解包失败: {e}")
            return 1

        # 2. manifest 存在性
        manifest = _load_manifest(tmpdir)
        print(f"    [OK] manifest.json: {manifest.get('name')} v{manifest.get('version')}")

        # 3. checksums 校验
        if not verify_checksums(tmpdir):
            errors += 1

        # 4. 检查分类完整性
        skills_total = manifest.get("skills", {}).get("total", 0)
        actual_skills = sum(1 for _ in os.scandir(os.path.join(tmpdir, "skills"))
                            if _.is_dir()) if os.path.isdir(os.path.join(tmpdir, "skills")) else 0
        if skills_total != actual_skills:
            print(f"    [X] Skill 数量不匹配: manifest={skills_total}, 实际={actual_skills}")
            errors += 1
        else:
            print(f"    [OK] Skills: {actual_skills}")

        # 5. SOUL.md 存在性
        soul_path = os.path.join(tmpdir, "agent", "SOUL.md")
        if os.path.isfile(soul_path):
            print(f"    [OK] agent/SOUL.md 存在")
        else:
            print(f"    [X] agent/SOUL.md 缺失")
            errors += 1

    if errors == 0:
        print("    [OK] 包完整性校验通过")
        return 0
    else:
        print(f"    [X] 校验发现 {errors} 个问题")
        return 1


def verify_installed(target_dir):
    """校验已安装的 Agent"""
    target_dir = os.path.abspath(target_dir)
    if not os.path.isdir(target_dir):
        print(f"[X] 目录不存在: {target_dir}")
        return 1

    print(f"[*] 校验已安装版本: {target_dir}")
    errors = 0

    # 检查核心文件
    for fname in ["SOUL.md", "USER.md", "FACT.md"]:
        path = os.path.join(target_dir, fname)
        if os.path.isfile(path):
            print(f"    [OK] {fname}")
        else:
            print(f"    [!] {fname} 缺失（可选）")

    # 查找版本历史
    versions_dir = os.path.join(target_dir, ".agent-versions")
    if os.path.isdir(versions_dir):
        history = os.path.join(versions_dir, "history.json")
        if os.path.isfile(history):
            with open(history, "r", encoding="utf-8") as f:
                hist = json.load(f)
            current = os.path.join(versions_dir, "current")
            if os.path.islink(current) or os.path.exists(current):
                print(f"    [OK] 版本历史: {len(hist.get('versions', []))} 个版本")
            else:
                print(f"    [!] 版本历史已记录但当前版本未标记")

    if errors == 0:
        print("    [OK] 已安装版本正常")
    return 0 if errors == 0 else 1


def verify_checksums(target_dir):
    """校验目录文件 SHA256"""
    checksums_path = os.path.join(target_dir, ".checksums")
    if not os.path.isfile(checksums_path):
        print("    [!] 无 .checksums 文件（跳过文件校验）")
        return True

    expected = {}
    with open(checksums_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("  ", 1)
            if len(parts) == 2:
                expected[parts[1]] = parts[0]

    errors = 0
    for rel_path, exp_hash in expected.items():
        full_path = os.path.join(target_dir, rel_path)
        if not os.path.isfile(full_path):
            print(f"    [X] 文件缺失: {rel_path}")
            errors += 1
            continue
        sha256 = hashlib.sha256()
        with open(full_path, "rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != exp_hash:
            print(f"    [X] 校验和不匹配: {rel_path}")
            errors += 1

    if errors > 0:
        print(f"    [X] {errors} 个文件校验失败")
        return False
    print(f"    [OK] 文件校验: {len(expected)} 个文件全部通过")
    return True


def _extract_package(pkg_path, target_dir):
    """解包 .agentpkg"""
    with tarfile.open(pkg_path, "r:gz") as tar:
        tar.extractall(path=target_dir)
    inner = os.path.join(target_dir, "agent-package")
    if os.path.isdir(inner):
        for item in os.listdir(inner):
            os.rename(os.path.join(inner, item),
                      os.path.join(target_dir, item))
        os.rmdir(inner)


def _load_manifest(tmpdir):
    """读取 manifest.json"""
    path = os.path.join(tmpdir, "manifest.json")
    if not os.path.isfile(path):
        print("[X] manifest.json 缺失")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
