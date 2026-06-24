#!/usr/bin/env python3
"""
Chip 独立安装器构建脚本
=================================
使用 PyInstaller 将 installer_standalone.py + .agentpkg 打包为单文件 .exe。

用法:
  # 指定 agent 包和输出路径
  python packager_build_exe.py --package chip-embedded-2.1.0.agentpkg --output Chip-Setup.exe

  # 默认使用当前目录下的 .agentpkg, 输出到桌面
  python packager_build_exe.py

注意事项:
  - 需要安装 PyInstaller: pip install pyinstaller
  - 生成的 .exe 约 70-75 MB (含 Python 运行时 + agent 包)
  - 仅在 Windows 上构建
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def find_agentpkg(search_dir=None):
    """查找目录下的 .agentpkg 文件"""
    if search_dir is None:
        search_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in os.listdir(search_dir):
        if fname.endswith(".agentpkg"):
            return os.path.join(search_dir, fname)
    return None


def build_exe(pkg_path, output_path, icon_path=None):
    """使用 PyInstaller 构建单文件 .exe"""
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    installer_py = os.path.join(scripts_dir, "installer_standalone.py")

    # 校验
    if not os.path.isfile(installer_py):
        print(f"[X] 找不到 installer_standalone.py: {installer_py}")
        return 1
    if not os.path.isfile(pkg_path):
        print(f"[X] 找不到 agent 包: {pkg_path}")
        return 1

    pkg_name = os.path.basename(pkg_path)
    output_dir = os.path.dirname(output_path) or os.getcwd()
    output_name = os.path.basename(output_path)

    print(f"[*] 构建 Chip 独立安装器")
    print(f"    Agent 包:    {pkg_path} ({os.path.getsize(pkg_path)/1024/1024:.1f} MB)")
    print(f"    安装器脚本:  {installer_py}")
    print(f"    输出路径:    {output_path}")
    print()

    # 构建 PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # 单文件 exe
        "--console",                    # 显示控制台窗口（交互式安装需要）
        "--clean",                      # 清理缓存
        "--name", os.path.splitext(output_name)[0],
        "--distpath", output_dir,
        "--add-data", f"{pkg_path}{os.pathsep}pkg",  # agentpkg → pkg/ 子目录
    ]
    if icon_path and os.path.isfile(icon_path):
        cmd.extend(["--icon", icon_path])

    cmd.append(installer_py)

    print(f"    PyInstaller 命令:")
    print(f"    {' '.join(cmd)}")
    print()

    # 更清晰的提示告知用户正在做什么
    if sys.platform == "win32":
        print(f"    [*] 正在构建，预计需要 1-3 分钟...")
        print(f"    [*] 构建期间可能会弹出 Windows 安全警告，请允许。")
    print()

    # 执行
    result = subprocess.run(cmd, capture_output=False, timeout=600)

    # 清理 PyInstaller 临时文件
    for d in ["build", "__pycache__"]:
        dpath = os.path.join(scripts_dir, d)
        if os.path.isdir(dpath):
            shutil.rmtree(dpath, ignore_errors=True)
    spec_file = os.path.join(scripts_dir, os.path.splitext(output_name)[0] + ".spec")
    if os.path.isfile(spec_file):
        os.remove(spec_file)

    if result.returncode != 0:
        print(f"\n[X] 构建失败 (exit code {result.returncode})")
        return result.returncode

    # 验证输出
    exe_path = os.path.join(output_dir, output_name)
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / 1024 / 1024
        print(f"\n[OK] 构建成功!")
        print(f"     输出: {exe_path}")
        print(f"     大小: {size_mb:.1f} MB")
    else:
        print(f"\n[!] 构建可能已完成，但未找到预期的输出文件:")
        print(f"    {exe_path}")

    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Chip 独立安装器构建工具")
    parser.add_argument("--package", "-p", default=None,
                        help=".agentpkg 包路径（默认自动查找）")
    parser.add_argument("--output", "-o", default="Chip-Setup.exe",
                        help="输出 .exe 路径（默认当前目录 Chip-Setup.exe）")
    parser.add_argument("--icon", default=None,
                        help="自定义图标 .ico 文件")
    args = parser.parse_args()

    # 自动查找 agentpkg
    if not args.package:
        args.package = find_agentpkg()
        if args.package:
            print(f"[*] 自动找到 agent 包: {args.package}")
        else:
            print(f"[X] 未找到 .agentpkg 文件，请用 --package 指定")
            return 1

    return build_exe(args.package, args.output, args.icon)


if __name__ == "__main__":
    sys.exit(main())
