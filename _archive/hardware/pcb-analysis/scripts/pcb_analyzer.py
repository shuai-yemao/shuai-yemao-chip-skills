#!/usr/bin/env python3
"""
PCB 原理图分析器——主入口

一键分析 LCEDA Pro 原理图: BOM + 电源树 + 引脚分配 + 网络拓扑 + DRC。

用法:
  python pcb_analyzer.py status          # 检查桥状态
  python pcb_analyzer.py serve           # 启动桥服务器
  python pcb_analyzer.py wait-plugin     # 等待插件连接
  python pcb_analyzer.py read            # 读取原理图并保存
  python pcb_analyzer.py analyze         # 分析已保存的原理图数据
  python pcb_analyzer.py full            # 一键完成: 启动→等待→读取→分析

分析选项:
  python pcb_analyzer.py analyze --all      # 全部模块 (默认)
  python pcb_analyzer.py analyze --bom      # 仅 BOM
  python pcb_analyzer.py analyze --power    # 仅电源
  python pcb_analyzer.py analyze --pin      # 仅引脚
  python pcb_analyzer.py analyze --net      # 仅网络
  python pcb_analyzer.py analyze --conflict # 仅冲突检查
  python pcb_analyzer.py analyze --json     # JSON 输出
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
AIEDA_PROJECT = Path(r"{USER_HOME}\projects\ai-eda\ai_eda")
AIEDA_PYTHON = AIEDA_PROJECT / "aieda_python"
SCHEMATIC_DATA_PATH = AIEDA_PROJECT / "schematic_data.json"

# 确保可导入 ai_eda 的 client/protocol
sys.path.insert(0, str(AIEDA_PYTHON))
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# 导入本地模块
# ---------------------------------------------------------------------------
from bridge_manager import (
    is_server_running,
    is_plugin_connected,
    get_status,
    start_server,
    wait_for_plugin,
    read_schema,
    stop_server,
)
from schema_reader import parse_schema, load_schematic_json


def cmd_status() -> None:
    """检查桥服务器和插件连接状态"""
    running = is_server_running()
    if not running:
        print("[X] 桥服务器未运行")
        print("    运行 'python pcb_analyzer.py serve' 启动")
        return

    status = get_status()
    print(f"[OK] 桥服务器运行中")
    print(f"     URL: http://127.0.0.1:8787")
    print(f"     插件连接: {'[OK]' if status.get('plugin_connected') else '[X]'}")

    meta = status.get("plugin_meta")
    if meta:
        print(f"     插件信息: {json.dumps(meta, ensure_ascii=False)}")

    pending = status.get("pending_commands", 0)
    if pending:
        print(f"     待处理命令: {pending}")


def cmd_serve() -> None:
    """启动桥服务器"""
    if is_server_running():
        print("[OK] 桥服务器已在运行")
        return
    start_server()


def cmd_wait_plugin() -> None:
    """等待 LCEDA Pro 插件连接"""
    if not is_server_running():
        print("[X] 桥服务器未运行，请先运行 'python pcb_analyzer.py serve'")
        return
    wait_for_plugin()


def cmd_read() -> dict[str, Any] | None:
    """读取原理图数据并保存到文件"""
    if not is_server_running():
        print("[X] 桥服务器未运行")
        return None

    if not is_plugin_connected():
        print("[X] LCEDA Pro 插件未连接")
        print("    请在 LCEDA Pro 中: AI EDA → Start Bridge")
        return None

    data = read_schema()
    if data:
        # 保存到文件
        SCHEMATIC_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEMATIC_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        size = SCHEMATIC_DATA_PATH.stat().st_size
        print(f"[OK] 数据已保存: {SCHEMATIC_DATA_PATH.name} ({size / 1024:.1f} KB)")
    return data


def cmd_analyze(args: argparse.Namespace) -> None:
    """分析原理图数据"""
    # 从文件加载
    if not SCHEMATIC_DATA_PATH.exists():
        print(f"[X] 找不到原理图数据: {SCHEMATIC_DATA_PATH}")
        print("    请先运行 'python pcb_analyzer.py read'")
        return

    data = load_schematic_json(str(SCHEMATIC_DATA_PATH))
    parsed = parse_schema(data)

    # 确定运行哪些模块
    run_all = args.all
    run_bom = args.bom or run_all
    run_power = args.power or run_all
    run_pin = args.pin or run_all
    run_net = args.net or run_all
    run_drc = args.conflict or run_all

    results: dict[str, Any] = {}
    status_flags: list[str] = []

    # BOM 分析
    if run_bom:
        from analyzers.bom_analyzer import analyze_bom
        results["bom"] = analyze_bom(parsed)
        status_flags.append(f"BOM={results['bom']['total_parts']}")

    # 电源分析
    if run_power:
        from analyzers.power_analyzer import analyze_power
        results["power"] = analyze_power(parsed)
        rail_count = len(results["power"].get("rails", {}))
        status_flags.append(f"Power={rail_count}rails")

    # 引脚映射
    if run_pin:
        from analyzers.pin_mapper import analyze_pin_mapping
        results["pinmap"] = analyze_pin_mapping(parsed)
        mcu_name = results["pinmap"].get("mcu", {}).get("name", "?")
        peri_count = len(results["pinmap"].get("peripheral_nets", {}))
        status_flags.append(f"MCU={mcu_name}")
        status_flags.append(f"Peri={peri_count}")

    # 网络分析
    if run_net:
        from analyzers.net_analyzer import analyze_network
        results["net"] = analyze_network(parsed)
        status_flags.append(f"Nets={results['net']['total_nets']}")

    # 冲突检查 (可以引用其他模块的结果)
    if run_drc:
        from analyzers.conflict_checker import check_conflicts
        results["conflict"] = check_conflicts(
            parsed,
            bom_result=results.get("bom"),
            power_result=results.get("power"),
            pin_result=results.get("pinmap"),
            net_result=results.get("net"),
        )
        s = results["conflict"].get("summary", {})
        status_flags.append(f"DRC: E={s.get('errors',0)} W={s.get('warnings',0)}")

    # 输出
    print(f"[OK] 分析完成: {' | '.join(status_flags)}")
    print()

    if args.json:
        # JSON 输出
        from reports.report_generator import generate_json_report
        report = generate_json_report(
            parsed,
            bom=results.get("bom", {}),
            power=results.get("power", {}),
            pinmap=results.get("pinmap", {}),
            net=results.get("net", {}),
            conflict=results.get("conflict", {}),
        )
        print(report)
    else:
        # ASCII 文本报告
        from reports.report_generator import generate_text_report
        report = generate_text_report(
            parsed,
            bom=results.get("bom", {}),
            power=results.get("power", {}),
            pinmap=results.get("pinmap", {}),
            net=results.get("net", {}),
            conflict=results.get("conflict", {}),
        )
        print(report)


def cmd_full(args: argparse.Namespace) -> None:
    """一键完整流程: 启动服务器 → 等待插件 → 读取原理图 → 分析"""
    print("=" * 70)
    print("PCB SCHEMATIC ANALYSIS — FULL PIPELINE")
    print("=" * 70)
    print()

    # Step 1: 启动服务器
    print("[1/4] 桥服务器")
    if not is_server_running():
        if not start_server():
            print("[X] 桥服务器启动失败")
            sys.exit(1)
    else:
        print("[OK] 桥服务器已在运行")
    print()

    # Step 2: 等待插件连接
    print("[2/4] LCEDA Pro 插件")
    if not is_plugin_connected():
        if not wait_for_plugin():
            print("[X] 插件未连接 — 请在 LCEDA Pro 中点击 AI EDA > Start Bridge")
            sys.exit(1)
    else:
        print("[OK] 插件已连接")
    print()

    # Step 3: 读取原理图
    print("[3/4] 读取原理图")
    data = read_schema()
    if not data:
        print("[X] 原理图读取失败")
        sys.exit(1)
    # 保存
    SCHEMATIC_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEMATIC_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    size = SCHEMATIC_DATA_PATH.stat().st_size
    print(f"[OK] 已保存: {SCHEMATIC_DATA_PATH.name} ({size / 1024:.1f} KB)")
    print()

    # Step 4: 综合分析
    print("[4/4] 综合分析")
    print()
    # 临时修改 args
    args.all = True
    args.json = getattr(args, "json", False)
    cmd_analyze(args)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PCB 原理图分析工具 (LCEDA Pro + ai_eda bridge)"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # status
    sub.add_parser("status", help="检查桥服务器和插件连接状态")

    # serve
    sub.add_parser("serve", help="启动桥服务器")

    # wait-plugin
    sub.add_parser("wait-plugin", help="等待 LCEDA Pro 插件连接")

    # read
    sub.add_parser("read", help="读取原理图并保存")

    # analyze
    ap = sub.add_parser("analyze", help="分析已保存的原理图数据")
    ap.add_argument("--all", action="store_true", default=True, help="运行全部模块 (默认)")
    ap.add_argument("--bom", action="store_true", help="仅 BOM 分析")
    ap.add_argument("--power", action="store_true", help="仅电源分析")
    ap.add_argument("--pin", action="store_true", help="仅引脚映射")
    ap.add_argument("--net", action="store_true", help="仅网络分析")
    ap.add_argument("--conflict", action="store_true", help="仅冲突检查")
    ap.add_argument("--json", action="store_true", help="JSON 格式输出 (默认 ASCII)")

    # full
    fp = sub.add_parser("full", help="一键完成: 启动→等待→读取→分析")
    fp.add_argument("--json", action="store_true", help="JSON 格式输出")

    # stop
    sub.add_parser("stop", help="停止桥服务器")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "serve":
        cmd_serve()
    elif args.command == "wait-plugin":
        cmd_wait_plugin()
    elif args.command == "read":
        cmd_read()
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "full":
        cmd_full(args)
    elif args.command == "stop":
        stop_server()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
