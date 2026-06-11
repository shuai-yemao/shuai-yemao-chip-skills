#!/usr/bin/env python3
"""
gang-flash: 多路并行量产烧录工具
支持 OpenOCD 多 ST-Link、J-Link Multi-Emulator、esptool 多串口
内建失败重试、读回校验、CSV/JSON 双格式报告、烧录次数统计
"""
import argparse
import subprocess
import sys
import os
import json
import csv
import time
import hashlib
import threading
import shutil
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 工具函数 ──────────────────────────────────────────
def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def get_firmware_size(path: str) -> int:
    return os.path.getsize(path)


# ── 设备枚举 ──────────────────────────────────────────
def detect_stlinks() -> list:
    """枚举已连接的 ST-Link"""
    try:
        result = subprocess.run(
            ["openocd", "-c", "interface hla",
             "-c", "hla_layout stlink",
             "-c", "transport select hla_swd",
             "-c", "hla enumerate",
             "-c", "shutdown"],
            capture_output=True, text=True, timeout=10
        )
        serials = re.findall(r'[0-9A-F]{24}', result.stderr + result.stdout)
        return sorted(set(serials))
    except Exception as e:
        print(f"警告：ST-Link 枚举失败: {e}")
        return []


def detect_jlinks() -> list:
    """枚举已连接的 J-Link"""
    jlink_bin = shutil.which("JLinkExe") or shutil.which("JLink")
    if not jlink_bin:
        print("警告：JLinkExe 未在 PATH 中找到")
        return []
    try:
        result = subprocess.run(
            [jlink_bin, "-nogui", "1", "-CommandFile", "?", "-ExitOnError", "1"],
            capture_output=True, text=True, timeout=15,
            input="ShowEmuList\nexit\n"
        )
        # 从输出中提取序列号
        serials = re.findall(r'(\d{8,})', result.stdout + result.stderr)
        return sorted(set(serials))
    except Exception as e:
        print(f"警告：J-Link 枚举失败: {e}")
        return []


def detect_serial_ports() -> list:
    """枚举串口"""
    try:
        import serial.tools.list_ports
        ports = sorted([p.device for p in serial.tools.list_ports.comports()])
        return ports
    except ImportError:
        # 回退：使用基础方法
        if sys.platform.startswith("win"):
            import winreg
            ports = []
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "HARDWARE\\DEVICEMAP\\SERIALCOMM")
                for i in range(winreg.QueryInfoKey(key)[1]):
                    ports.append(winreg.EnumValue(key, i)[1])
                return sorted(ports)
            except Exception:
                return []
        return []


# ── 烧录函数（单路） ──────────────────────────────────

def flash_stlink(serial_num: str, firmware: str, target_cfg: str) -> dict:
    """ST-Link / OpenOCD 烧录"""
    start = time.time()
    cmd = [
        "openocd",
        "-f", "interface/stlink.cfg",
        "-c", f"hla_serial {serial_num}",
        "-f", target_cfg,
        "-c", f"program {firmware} verify reset exit",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        output = result.stdout + result.stderr
        success = ("Verified OK" in output or "** Verified OK **" in output) and result.returncode == 0
        error = ""
        if not success:
            # 提取最后有意义的一行作为错误
            lines = [l for l in output.splitlines() if l.strip() and not l.startswith("Info")]
            error = lines[-1] if lines else "未知错误"
        return {"status": "pass" if success else "fail", "duration_s": round(elapsed, 2), "error": error}
    except subprocess.TimeoutExpired:
        return {"status": "fail", "duration_s": time.time() - start, "error": "烧录超时 (120s)"}
    except FileNotFoundError:
        return {"status": "fail", "duration_s": time.time() - start, "error": "openocd 未安装或不在 PATH"}


def flash_jlink(serial_num: str, firmware: str, jlink_device: str, speed_khz: int = 4000) -> dict:
    """J-Link 烧录（生成并执行 command script）"""
    jlink_bin = shutil.which("JLinkExe") or shutil.which("JLink")
    if not jlink_bin:
        return {"status": "fail", "duration_s": 0, "error": "JLinkExe 未找到"}

    # 生成 J-Link command script
    script = f"""r
loadbin {firmware}, 0x08000000
verifybin {firmware}, 0x08000000
r
go
exit
"""
    script_path = f"_jlink_{serial_num}.jlink"
    with open(script_path, "w") as f:
        f.write(script)

    start = time.time()
    cmd = [
        jlink_bin,
        "-Device", jlink_device,
        "-SelectEmuBySN", serial_num,
        "-Speed", str(speed_khz),
        "-if", "SWD",
        "-autoconnect", "1",
        "-nogui", "1",
        "-CommanderScript", script_path,
        "-ExitOnError", "1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start
        output = result.stdout + result.stderr
        success = "O.K." in output and result.returncode == 0
        error = ""
        if not success:
            lines = [l for l in output.splitlines() if "ERROR" in l or "FAIL" in l or "error" in l.lower()]
            error = lines[-1] if lines else "未知错误"
        return {"status": "pass" if success else "fail", "duration_s": round(elapsed, 2), "error": error}
    except subprocess.TimeoutExpired:
        return {"status": "fail", "duration_s": time.time() - start, "error": "烧录超时 (120s)"}
    finally:
        if os.path.exists(script_path):
            os.remove(script_path)


def flash_esptool(port: str, firmware: str, chip: str, baud: int, flash_addr: str = "0x0") -> dict:
    """ESP32 串口烧录"""
    start = time.time()
    cmd = [
        "esptool.py",
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
        "write_flash", flash_addr, firmware,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        elapsed = time.time() - start
        output = result.stdout + result.stderr
        success = "Hash of data verified" in output
        return {"status": "pass" if success else "fail", "duration_s": round(elapsed, 2),
                "error": "" if success else "烧录校验失败"}
    except subprocess.TimeoutExpired:
        return {"status": "fail", "duration_s": time.time() - start, "error": "烧录超时 (180s)"}


# ── 烧录后读回校验 ─────────────────────────────────────

def verify_readback(method: str, target: str, firmware: str, **kwargs) -> bool:
    """烧录后读回固件并比对 SHA256（简化版：不做全量读回，信任烧录工具的 verify 步骤）"""
    # OpenOCD/J-Link/esptool 已经在烧录命令中自带了 verify，
    # 此函数作为扩展点，未来可实现独立读回比对
    return True


# ── 并行烧录核心 ──────────────────────────────────────

def flash_one_with_retry(idx: int, target: str, firmware: str, method: str,
                         max_retries: int, retry_delay: float,
                         lock: threading.Lock, results: list, **flash_kwargs) -> dict:
    """单路烧录 + 重试逻辑"""
    total_retries = 0
    last_error = ""

    for attempt in range(1 + max_retries):
        with lock:
            if attempt == 0:
                print(f"  ⏳ 板 #{idx:<3} 烧录中... ({target})")
            else:
                print(f"  🔄 板 #{idx:<3} 重试 {attempt}/{max_retries}... ({target})")

        if method == "esptool":
            res = flash_esptool(target, firmware,
                                flash_kwargs.get("chip", "esp32"),
                                flash_kwargs.get("baud", 921600))
        elif method == "jlink":
            res = flash_jlink(target, firmware,
                              flash_kwargs.get("jlink_device", "Cortex-M4"),
                              flash_kwargs.get("jlink_speed", 4000))
        else:  # openocd
            res = flash_stlink(target, firmware,
                               flash_kwargs.get("target_cfg", "target/stm32f1x.cfg"))

        if res["status"] == "pass":
            res["retries"] = attempt
            res["index"] = idx
            res["serial"] = target
            with lock:
                print_result_line(idx, target, res)
            return res

        total_retries = attempt + 1
        last_error = res.get("error", "未知错误")

        if attempt < max_retries:
            time.sleep(retry_delay)

    # 全部重试失败
    res = {
        "status": "fail",
        "serial": target,
        "index": idx,
        "duration_s": 0,
        "retries": total_retries,
        "error": last_error,
        "fw_verified": False,
    }
    with lock:
        print_result_line(idx, target, res)
    return res


def print_result_line(idx: int, target: str, res: dict):
    icon = "✅" if res["status"] == "pass" else "❌"
    sn = target[:24] + "..." if len(target) > 24 else target
    dur = res.get("duration_s", 0)
    retries = f" (重试{res.get('retries', 0)}次)" if res.get("retries", 0) > 0 else ""
    err = f"\n        失败原因: {res.get('error', '')}" if res["status"] == "fail" else ""
    print(f"  {icon} 板 #{idx:<3} {sn:<28} {dur:.1f}s{retries}{err}")


# ── 运行主流程 ────────────────────────────────────────
def run_gang_flash(firmware: str, method: str, targets: list,
                   max_workers: int, max_retries: int, retry_delay: float,
                   report_path: str, csv_report_path: str,
                   flash_count_file: str = None,
                   **flash_kwargs):
    fw_hash = sha256_file(firmware)
    fw_size = get_firmware_size(firmware)
    total = len(targets)

    print(f"\n{'═'*54}")
    print(f"  量产烧录")
    print(f"{'═'*54}")
    print(f"  固件      : {firmware} ({fw_size:,} 字节)")
    print(f"  SHA256    : {fw_hash[:48]}...")
    print(f"  烧录方式  : {method}")
    print(f"  目标数量  : {total}  |  并行度: {max_workers}  |  重试: {max_retries}")
    print(f"{'═'*54}\n")

    lock = threading.Lock()
    results = [None] * total
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for i, target in enumerate(targets):
            f = executor.submit(flash_one_with_retry, i, target, firmware, method,
                                max_retries, retry_delay, lock, results, **flash_kwargs)
            futures[f] = i

        for f in as_completed(futures):
            idx = futures[f]
            try:
                res = f.result()
                results[idx] = res
            except Exception as e:
                results[idx] = {
                    "serial": targets[idx], "index": idx, "status": "fail",
                    "duration_s": 0, "retries": 0, "error": str(e), "fw_verified": False
                }
                with lock:
                    print(f"  ❌ 板 #{idx:<3} 异常: {e}")

    total_time = time.time() - start_time
    passed = sum(1 for r in results if r and r["status"] == "pass")
    failed = total - passed
    total_retries = sum(r.get("retries", 0) for r in results if r)
    avg_time = total_time / total if total > 0 else 0

    # ── 汇总报告 ──
    print(f"\n{'═'*54}")
    print(f"  量产烧录报告")
    print(f"{'═'*54}")
    print(f"  总计: {total} 块  |  ✅ 成功: {passed}  |  ❌ 失败: {failed}")
    print(f"  总耗时: {total_time:.1f}s  |  平均: {avg_time:.1f}s/块  |  重试: {total_retries} 次")
    if failed > 0:
        print(f"\n  ⚠ 失败板:")
        for r in results:
            if r and r["status"] == "fail":
                print(f"     板 #{r['index']}  {r['serial']}  →  {r.get('error', '未知')}")
        print(f"\n  建议：检查连接、供电，重新插拔后单独重烧")
    print(f"{'═'*54}\n")

    # ── JSON 报告 ──
    report = {
        "timestamp": datetime.now().isoformat(),
        "firmware": firmware,
        "firmware_sha256": fw_hash,
        "firmware_size": fw_size,
        "method": method,
        "total": total,
        "passed": passed,
        "failed": failed,
        "retried": total_retries,
        "total_duration_s": round(total_time, 2),
        "avg_duration_s": round(avg_time, 2),
        "results": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  📊 JSON 报告: {report_path}")

    # ── CSV 报告 ──
    if csv_report_path:
        with open(csv_report_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "index", "serial", "status", "duration_s", "retries", "fw_verified", "error"
            ])
            writer.writeheader()
            for r in results:
                if r:
                    writer.writerow({k: r.get(k, "") for k in writer.fieldnames})
        print(f"  📊 CSV  报告: {csv_report_path}")

    # ── 烧录计数统计 ──
    if flash_count_file:
        try:
            if os.path.exists(flash_count_file):
                with open(flash_count_file, "r") as f:
                    stats = json.load(f)
            else:
                stats = {"total_flashed": 0, "total_passed": 0, "total_failed": 0, "sessions": []}
            stats["total_flashed"] += total
            stats["total_passed"] += passed
            stats["total_failed"] += failed
            stats["last_session"] = datetime.now().isoformat()
            stats["sessions"].append({
                "timestamp": datetime.now().isoformat(),
                "firmware": firmware,
                "total": total,
                "passed": passed,
                "failed": failed,
                "duration_s": round(total_time, 2),
            })
            # 保留最近 100 次会话
            if len(stats["sessions"]) > 100:
                stats["sessions"] = stats["sessions"][-100:]
            with open(flash_count_file, "w", encoding="utf-8") as f:
                json.dump(stats, f, indent=2, ensure_ascii=False)
            print(f"  📈 历史统计: {flash_count_file} (总计烧录 {stats['total_flashed']} 块)")
        except Exception as e:
            print(f"  ⚠ 烧录统计写入失败: {e}")

    return failed == 0


# ── 主入口 ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="多路并行量产烧录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --firmware build/firmware.bin --method openocd --device STM32F407VG
  %(prog)s --firmware build/firmware.bin --method jlink --jlink-device STM32F407VG
  %(prog)s --firmware build/firmware.bin --method esptool --chip esp32
  %(prog)s --firmware build/firmware.bin --method openocd --targets 066DFF50... 066DFF53...
  %(prog)s --firmware build/firmware.bin --method openocd --retry 3 --parallel 4
        """
    )
    parser.add_argument("--firmware", required=True, help="固件文件路径 (.bin)")
    parser.add_argument("--method", default="openocd",
                        choices=["openocd", "jlink", "esptool"],
                        help="烧录方式 (默认 openocd)")
    parser.add_argument("--targets", nargs="*", default=None,
                        help="目标序列号/串口列表（不填则自动枚举）")

    # OpenOCD 参数
    parser.add_argument("--device", default="STM32F103C8", help="MCU 型号")
    parser.add_argument("--target-cfg", default="target/stm32f1x.cfg",
                        help="OpenOCD target 配置文件")

    # J-Link 参数
    parser.add_argument("--jlink-device", default="STM32F407VG",
                        help="J-Link 器件名")
    parser.add_argument("--jlink-speed", type=int, default=4000,
                        help="J-Link SWD 速度 (kHz, 默认 4000)")

    # esptool 参数
    parser.add_argument("--chip", default="esp32", help="ESP 芯片型号")
    parser.add_argument("--baud", type=int, default=921600, help="烧录波特率")
    parser.add_argument("--flash-addr", default="0x0", help="ESP flash 地址")

    # 控制参数
    parser.add_argument("--parallel", type=int, default=8, help="最大并行数")
    parser.add_argument("--retry", type=int, default=2, help="失败重试次数 (默认 2)")
    parser.add_argument("--retry-delay", type=float, default=2.0, help="重试间隔秒 (默认 2.0)")

    # 报告参数
    parser.add_argument("--report", default="flash_report.json", help="JSON 报告路径")
    parser.add_argument("--csv-report", default="flash_report.csv", help="CSV 报告路径")
    parser.add_argument("--count-file", default=None, help="烧录计数统计文件路径")

    # 安全参数
    parser.add_argument("--no-verify", action="store_true", help="跳过烧录后校验（不推荐）")
    parser.add_argument("--yes", action="store_true", help="跳过确认提示")

    args = parser.parse_args()

    # 验证固件存在
    if not os.path.exists(args.firmware):
        print(f"错误：固件文件不存在: {args.firmware}")
        sys.exit(1)

    # 枚举目标
    targets = args.targets
    if not targets:
        print("[gang-flash] 自动枚举目标设备...")
        if args.method == "esptool":
            targets = detect_serial_ports()
        elif args.method == "jlink":
            targets = detect_jlinks()
        else:
            targets = detect_stlinks()

        if not targets:
            print(f"错误：未检测到任何目标设备")
            if args.method == "jlink":
                print("  提示：确认 JLinkExe 在 PATH 中，且 J-Link 已通过 USB 连接")
            elif args.method == "openocd":
                print("  提示：确认运行了 ST-Link 驱动安装程序，且调试器已连接")
            else:
                print("  提示：确认设备已插入并安装了串口驱动")
            sys.exit(1)
        print(f"[gang-flash] 检测到 {len(targets)} 个目标")

    # 确认
    if not args.yes:
        print(f"\n目标列表 ({len(targets)}):")
        for i, t in enumerate(targets):
            print(f"  [{i}] {t}")
        confirm = input(f"\n即将并行烧录 {len(targets)} 块目标板，是否继续? (y/N): ").strip().lower()
        if confirm != "y":
            print("操作已取消")
            sys.exit(0)

    # 构建 kwargs
    flash_kwargs = {}
    if args.method == "openocd":
        flash_kwargs["target_cfg"] = args.target_cfg
    elif args.method == "jlink":
        flash_kwargs["jlink_device"] = args.jlink_device
        flash_kwargs["jlink_speed"] = args.jlink_speed
    else:  # esptool
        flash_kwargs["chip"] = args.chip
        flash_kwargs["baud"] = args.baud

    # 执行
    success = run_gang_flash(
        firmware=args.firmware,
        method=args.method,
        targets=targets,
        max_workers=args.parallel,
        max_retries=args.retry,
        retry_delay=args.retry_delay,
        report_path=args.report,
        csv_report_path=args.csv_report,
        flash_count_file=args.count_file,
        **flash_kwargs,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
