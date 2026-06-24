#!/usr/bin/env python3
"""
session-close.py — 开发会话收尾工具

用法:
  session-close <项目目录> [参数...]

功能:
  1. 生成开发日志（调用 devlog.py，自动填充 git/build 信息）
  2. 更新仪表盘资源占用（调用 init-project-files.py --update）
  3. 可选：从串口监控捕获最后 N 秒日志
  4. 可选：交互式记录本次遇到的问题

参数:
  --work-done "内容"    本次完成的工作（| 分隔多条）
  --problems "问题|原因|方案"   遇到的问题（| 分隔转为表格）
  --progress N          整体进度百分比
  --next "待办内容"     下次待办
  --capture N           从串口捕获 N 秒日志（需 serial-monitor）
  --port COM            串口号（配合 --capture）
  --baud 115200         波特率（配合 --capture）
  --no-devlog           跳过开发日志（仅更新仪表盘）
  --no-dashboard        跳过仪表盘更新（仅生成日志）
  --interactive         交互模式

依赖: Python 3.8+, devlog/scripts/devlog.py, init-project-files.py
"""

import os, sys, subprocess, argparse
from pathlib import Path
from datetime import datetime

# 查找 skill 脚本的基目录
SKILLS_BASE = Path(__file__).parent.parent.parent  # skills/obsidian-viz/references/ → skills/

def find_script(relative: str) -> Path | None:
    """在 skill 目录中搜索脚本"""
    candidates = [
        SKILLS_BASE / relative,
        SKILLS_BASE / relative.replace("/", "\\"),
        Path(__file__).parent / relative.split("/")[-1],
    ]
    for c in candidates:
        if c.exists():
            return c
    return None

def run_script(script: Path, args: list[str], cwd: str | None = None) -> tuple[int, str]:
    """运行一个 Python 脚本"""
    python = sys.executable
    if not script or not script.exists():
        return -1, f"[X] 脚本不存在: {script}"
    cmd = [python, str(script)] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           cwd=cwd, timeout=120)
        result = ""
        if r.stdout:
            result += r.stdout
        if r.stderr:
            # stderr 可能含 GBK 编码的警告，过滤掉线程级的编码异常
            stderr_filtered = [l for l in r.stderr.splitlines()
                               if '_readerthread' not in l
                               and 'UnicodeDecodeError' not in l]
            if stderr_filtered:
                result += "\n".join(stderr_filtered)
        return r.returncode, result
    except subprocess.TimeoutExpired:
        return -1, "[X] 执行超时"
    except Exception as e:
        return -1, f"[X] 执行失败: {e}"

def get_python_path() -> str:
    """获取可用 Python 路径"""
    return sys.executable

def main():
    # Windows 控制台 UTF-8 编码兼容
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except: pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try: sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except: pass

    p = argparse.ArgumentParser(description="开发会话收尾工具")
    p.add_argument("project", help="项目目录路径")
    p.add_argument("--work-done", help="本次完成的工作（| 分隔多条）")
    p.add_argument("--problems", help="遇到的问题（问题|原因|方案）")
    p.add_argument("--progress", type=int, default=0, help="整体进度百分比")
    p.add_argument("--next", help="下次待办")
    p.add_argument("--capture", type=int, default=0, help="从串口捕获 N 秒日志")
    p.add_argument("--port", default="{SERIAL_PORT}", help="串口号（默认 {SERIAL_PORT}）")
    p.add_argument("--baud", type=int, default=115200, help="波特率（默认 115200）")
    p.add_argument("--no-devlog", action="store_true", help="跳过开发日志")
    p.add_argument("--no-dashboard", action="store_true", help="跳过仪表盘更新")
    p.add_argument("-i", "--interactive", action="store_true", help="交互模式")
    args = p.parse_args()

    proj_dir = Path(args.project).resolve()
    if not proj_dir.exists():
        print(f"[X] 项目目录不存在: {proj_dir}")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"  会话收尾: {proj_dir.name}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # 1. 生成开发日志
    if not args.no_devlog:
        devlog_script = find_script("devlog/scripts/devlog.py")
        if devlog_script and devlog_script.exists():
            print("[*] 步骤 1/3: 生成开发日志...")
            dl_args = ["--project", str(proj_dir)]
            if args.work_done:
                dl_args += ["--work-done", args.work_done]
            if args.problems:
                dl_args += ["--problems-solutions", args.problems]
            if args.progress:
                dl_args += ["--progress", str(args.progress)]
            if args.next:
                dl_args += ["--next-steps", args.next]

            if args.interactive:
                dl_args += ["--interactive"]

            code, out = run_script(devlog_script, dl_args)
            for line in out.splitlines():
                try: print(f"  {line}")
                except: pass
            if code == 0:
                print("  [+] 开发日志生成完成")
            else:
                print(f"  [!] 开发日志生成异常 (exit={code})")
        else:
            print(f"  [~] devlog 脚本未找到，跳过开发日志 (查找路径: {devlog_script})")
    else:
        print("  [~] 跳过开发日志 (--no-devlog)")

    # 2. 更新仪表盘
    if not args.no_dashboard:
        print("[*] 步骤 2/3: 更新仪表盘资源占用...")
        init_script = find_script("obsidian-viz/references/init-project-files.py")
        if init_script and init_script.exists():
            code, out = run_script(init_script, [str(proj_dir), "--update"])
            for line in out.splitlines():
                try: print(f"  {line}")
                except: print(f"  [{line[:40]}...]")
            if code == 0:
                print("  [+] 仪表盘已更新: docs/dashboard.html")
            else:
                print(f"  [!] 仪表盘更新异常 (exit={code})")
        else:
            print(f"  [~] init-project-files.py 未找到，跳过仪表盘更新")
    else:
        print("  [~] 跳过仪表盘更新 (--no-dashboard)")

    # 3. 捕获串口日志（可选）
    if args.capture > 0:
        print(f"[*] 步骤 3/3: 捕获串口日志 ({args.capture}s, {args.port} @ {args.baud})...")
        mon_script = find_script("serial-monitor/scripts/serial_monitor.py")
        if mon_script and mon_script.exists():
            log_path = proj_dir / "docs" / f"serial-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            code, out = run_script(mon_script, [
                "--port", args.port, "--baud", str(args.baud),
                "--duration", str(args.capture), "--save", str(log_path)
            ])
            if log_path.exists():
                print(f"  [+] 日志已保存: {log_path} ({log_path.stat().st_size} bytes)")
            else:
                print("  [~] 串口捕获未返回数据")
        else:
            print(f"  [~] serial-monitor 脚本未找到，跳过日志捕获")

    # 完成
    print(f"\n{'='*50}")
    print(f"  [OK] 会话收尾完成!")
    print(f"       开发日志: docs/开发日志/")
    print(f"       仪表盘:   docs/dashboard.html")
    if args.capture > 0:
        print(f"       串口日志: docs/serial-log-*.log")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
