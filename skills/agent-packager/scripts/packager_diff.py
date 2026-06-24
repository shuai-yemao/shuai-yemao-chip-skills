#!/usr/bin/env python3
"""
Diff module: 版本差分 / 应用补丁

功能:
  - run_diff: 对比两个 .agentpkg 版本，生成 .agentpatch 差分包
  - run_apply: 将 .agentpatch 应用到目标 Agent 目录
"""

import filecmp
import hashlib
import json
import os
import shutil
import tarfile
import tempfile


SUPPORTED_PATCH_OPS = ["added", "modified", "deleted"]


def run_diff(args):
    """生成差分包"""
    from_path = os.path.abspath(args.from_pkg)
    to_path = os.path.abspath(args.to_pkg)

    if not os.path.isfile(from_path):
        print(f"[X] 源包不存在: {from_path}")
        return 1
    if not os.path.isfile(to_path):
        print(f"[X] 目标包不存在: {to_path}")
        return 1

    print(f"[*] 生成差分包")
    print(f"    From: {os.path.basename(from_path)}")
    print(f"    To:   {os.path.basename(to_path)}")

    output = args.output or to_path.replace(".agentpkg", ".agentpatch")

    with tempfile.TemporaryDirectory() as tmp_from, \
         tempfile.TemporaryDirectory() as tmp_to, \
         tempfile.TemporaryDirectory() as tmp_patch:

        # 解包两个版本
        _extract_package(from_path, tmp_from)
        _extract_package(to_path, tmp_to)

        # 读取 manifests
        manifest_from = _load_manifest(tmp_from)
        manifest_to = _load_manifest(tmp_to)
        ver_from = manifest_from.get("version", "?")
        ver_to = manifest_to.get("version", "?")
        print(f"    v{ver_from} → v{ver_to}")

        # 收集文件列表
        files_from = _collect_file_set(tmp_from)
        files_to = _collect_file_set(tmp_to)

        # 计算差分
        added = files_to - files_from
        deleted = files_from - files_to
        common = files_from & files_to

        modified = set()
        for f in common:
            if f == ".checksums":
                continue
            path_from = os.path.join(tmp_from, f)
            path_to = os.path.join(tmp_to, f)
            if os.path.isfile(path_from) and os.path.isfile(path_to):
                if not filecmp.cmp(path_from, path_to, shallow=False):
                    modified.add(f)

        # 构建 patch 目录
        patch_root = os.path.join(tmp_patch, "agentpatch")
        os.makedirs(patch_root, exist_ok=True)

        # 复制新增文件
        for f in sorted(added):
            src = os.path.join(tmp_to, f)
            dst = os.path.join(patch_root, "added", f)
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        # 复制修改文件
        for f in sorted(modified):
            src = os.path.join(tmp_to, f)
            dst = os.path.join(patch_root, "modified", f)
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        # 删除文件：仅记录路径列表
        deleted_list = sorted(deleted)
        if deleted_list:
            del_path = os.path.join(patch_root, "deleted")
            os.makedirs(del_path, exist_ok=True)
            with open(os.path.join(del_path, "files.txt"), "w") as f:
                for path in deleted_list:
                    f.write(path + "\n")

        # manifest patch
        manifest_patch = _build_manifest_patch(
            manifest_from, manifest_to,
            added, modified, deleted_list
        )
        with open(os.path.join(patch_root, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest_patch, f, indent=2, ensure_ascii=False)

        # 打包差分包
        with tarfile.open(output, "w:gz") as tar:
            tar.add(patch_root, arcname="agentpatch")

    # 统计
    print(f"    Added:    {len(added)}")
    print(f"    Modified: {len(modified)}")
    print(f"    Deleted:  {len(deleted_list)}")
    print(f"    [+PATCH]  {output}")

    return 0


def run_apply(args):
    """应用差分包"""
    patch_path = os.path.abspath(args.patch)
    target_dir = os.path.abspath(args.target_dir)

    if not os.path.isfile(patch_path):
        print(f"[X] 差分包不存在: {patch_path}")
        return 1
    if not os.path.isdir(target_dir):
        print(f"[X] 目标目录不存在: {target_dir}")
        return 1

    print(f"[*] 应用差分包: {os.path.basename(patch_path)}")
    print(f"    目标: {target_dir}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 解包
        with tarfile.open(patch_path, "r:gz") as tar:
            tar.extractall(path=tmpdir)

        patch_root = os.path.join(tmpdir, "agentpatch")
        if not os.path.isdir(patch_root):
            print("[X] 差分包格式错误（缺少 agentpatch/ 目录）")
            return 1

        # 读取 manifest
        manifest_path = os.path.join(patch_root, "manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as f:
                patch_manifest = json.load(f)
            ver_from = patch_manifest.get("versionFrom", "?")
            ver_to = patch_manifest.get("versionTo", "?")
            print(f"    v{ver_from} → v{ver_to}")

        # 创建备份
        backup_path = target_dir.rstrip("/\\") + ".backup"
        if os.path.isdir(backup_path):
            shutil.rmtree(backup_path)
        shutil.copytree(target_dir, backup_path)
        print(f"    备份: {backup_path}")

        # 应用新增
        added_dir = os.path.join(patch_root, "added")
        if os.path.isdir(added_dir):
            for root, _dirs, files in os.walk(added_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), added_dir)
                    dst = os.path.join(target_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), dst)
            print(f"    [OK] 新增文件已添加")

        # 应用修改
        modified_dir = os.path.join(patch_root, "modified")
        if os.path.isdir(modified_dir):
            for root, _dirs, files in os.walk(modified_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), modified_dir)
                    dst = os.path.join(target_dir, rel)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), dst)
            print(f"    [OK] 修改文件已覆盖")

        # 应用删除
        deleted_file = os.path.join(patch_root, "deleted", "files.txt")
        if os.path.isfile(deleted_file):
            with open(deleted_file, "r") as f:
                for line in f:
                    path = line.strip()
                    if not path:
                        continue
                    full = os.path.join(target_dir, path)
                    if os.path.isfile(full):
                        os.remove(full)
                    elif os.path.isdir(full):
                        shutil.rmtree(full)
            print(f"    [OK] 已删除废弃文件")

        print(f"    [OK] 升级完成")

    return 0


def _build_manifest_patch(m_from, m_to, added, modified, deleted):
    """构建差分 manifest"""
    return {
        "patchVersion": "1.0",
        "versionFrom": m_from.get("version", "?"),
        "versionTo": m_to.get("version", "?"),
        "fileChanges": {
            "added": sorted(added),
            "modified": sorted(modified),
            "deleted": deleted,
        },
        "summary": {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
        },
        "description": f"从 v{m_from.get('version', '?')} 升级到 v{m_to.get('version', '?')}"
    }


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
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _collect_file_set(tmpdir):
    """收集目录下所有文件（去掉目录、.checksums）"""
    files = set()
    for root, _dirs, fnames in os.walk(tmpdir):
        for f in fnames:
            rel = os.path.relpath(os.path.join(root, f), tmpdir)
            if rel.startswith("."):
                continue
            files.add(rel)
    # 去掉 .checksums 自身
    files.discard(".checksums")
    files.discard("manifest.json")
    return files
