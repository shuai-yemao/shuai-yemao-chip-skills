#!/usr/bin/env python3
"""
minunit_runner.py — minunit 测试编译与运行器
===========================================
扫描 project/test/ 下的 test_*.c 文件，与 project/src/*.c 一起编译并运行。

用法:
  python minunit_runner.py <project_dir>

输出:
  直接透传 test runner 的 stdout/stderr，退出码透传。

依赖:
  - gcc (MinGW / MSYS2)
  - minunit.h (test/ 目录下)
  - 外部依赖需手写 mock stub 在 test_*.c 中
"""

import glob
import io
import os
import subprocess
import sys

# Windows 控制台 UTF-8 输出
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def find_project_root(start: str) -> str | None:
    """从 start 向上找包含 src/ 和 test/ 的目录"""
    cur = os.path.abspath(start)
    for _ in range(5):  # 最多向上 5 层
        if os.path.isdir(os.path.join(cur, "src")) and \
           os.path.isdir(os.path.join(cur, "test")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


def main() -> int:
    raw_dir = sys.argv[1] if len(sys.argv) > 1 else "."

    project_dir = find_project_root(raw_dir)
    if not project_dir:
        print(f"[X] 未找到包含 src/ 和 test/ 的项目目录 (从 {raw_dir} 向上搜索)")
        return 1

    src_dir = os.path.join(project_dir, "src")
    test_dir = os.path.join(project_dir, "test")

    # 查找源文件和测试文件
    src_files = sorted(glob.glob(os.path.join(src_dir, "*.c")))
    test_files = sorted(glob.glob(os.path.join(test_dir, "test_*.c")))

    if not test_files:
        print(f"[X] 未找到测试文件: {test_dir}/test_*.c")
        return 1

    if not src_files:
        print(f"[!] 未找到源文件: {src_dir}/*.c (仅编译测试文件)")

    # 构建编译命令
    output = os.path.join(project_dir, "test_runner.exe" if sys.platform == "win32" else "test_runner")
    src_str = " ".join(f'"{f}"' for f in src_files)
    test_str = " ".join(f'"{f}"' for f in test_files)
    inc_flags = f'-I "{src_dir}" -I "{test_dir}"'

    # 删除旧二进制文件，确保 clean build
    if os.path.exists(output):
        os.remove(output)

    compile_cmd = f'gcc {inc_flags} {test_str} {src_str} -o "{output}"'

    print(f"\n  [minunit] 项目: {project_dir}")
    print(f"  [minunit] 测试文件: {len(test_files)}")
    if src_files:
        print(f"  [minunit] 源文件: {len(src_files)}")
    print(f"  $ {compile_cmd}", flush=True)

    # 编译（捕获输出保证顺序）
    ret = subprocess.run(compile_cmd, shell=True, cwd=project_dir,
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ret.stdout:
        for line in ret.stdout.strip().splitlines():
            print(f"    {line}")
    if ret.stderr:
        for line in ret.stderr.strip().splitlines()[-5:]:
            print(f"    ! {line}")
    if ret.returncode != 0:
        print(f"\n[X] 编译失败 (exit={ret.returncode})")
        return ret.returncode

    # 运行
    print(f"\n  [minunit] 运行测试...", flush=True)
    run_ret = subprocess.run(f'"{output}"', shell=True, cwd=project_dir,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run_ret.stdout:
        print(run_ret.stdout)
    if run_ret.stderr:
        for line in run_ret.stderr.strip().splitlines()[-5:]:
            print(f"    ! {line}")
    return run_ret.returncode


if __name__ == "__main__":
    sys.exit(main())
