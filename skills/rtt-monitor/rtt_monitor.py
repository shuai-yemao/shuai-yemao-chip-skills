#!/usr/bin/env python3
"""
rtt-monitor: 通过 J-Link 或 OpenOCD 实时抓取 SEGGER RTT 日志
支持多通道、关键字过滤、ANSI 颜色、时间戳、自动重连、环缓冲溢出统计
"""
import argparse
import subprocess
import sys
import os
import signal
import tempfile
import threading
import time
import telnetlib
from datetime import datetime

ANSI_RESET  = "\033[0m"
ANSI_RED    = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_GREEN  = "\033[32m"
ANSI_CYAN   = "\033[36m"
ANSI_BLUE   = "\033[34m"

JLINK_CMD = None
RTT_LOGGER_CMD = None

_COMMON_DIRS = [
    r"C:\Program Files\SEGGER\JLink",
    r"C:\Program Files (x86)\SEGGER\JLink",
    r"C:\Program Files\SEGGER\JLink_V930",
    r"C:\Program Files\SEGGER\JLink_V928",
    r"G:\keil5\core\ARM\Segger",
]

def _find_cmd(names):
    """在 PATH 和常见目录中查找可执行文件，返回完整路径"""
    for name in names:
        path = __import__("shutil").which(name)
        if path:
            return path
    for d in _COMMON_DIRS:
        for name in names:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None

def check_jlink():
    global JLINK_CMD
    cmd = _find_cmd(["JLinkExe", "JLink"])
    if cmd is None:
        return False
    try:
        subprocess.run([cmd, "-version"], capture_output=True, timeout=5)
        JLINK_CMD = cmd
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        r = subprocess.run([cmd, "-nogui", "1"],
                           input="exit\n", capture_output=True, text=True, timeout=8)
        JLINK_CMD = cmd
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def check_rtt_logger():
    global RTT_LOGGER_CMD
    cmd = _find_cmd(["JLinkRTTLogger"])
    if cmd is None:
        return False
    try:
        subprocess.run([cmd, "-version"], capture_output=True, timeout=5)
        RTT_LOGGER_CMD = cmd
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # JLinkRTTLogger 可能启动 GUI，只检查文件存在
    if os.path.isfile(cmd):
        RTT_LOGGER_CMD = cmd
        return True
    return False

def colorize(line, use_color):
    if not use_color:
        return line
    upper = line.upper()
    if "ERROR" in upper:
        return ANSI_RED + line + ANSI_RESET
    elif "WARN" in upper:
        return ANSI_YELLOW + line + ANSI_RESET
    elif "INFO" in upper:
        return ANSI_GREEN + line + ANSI_RESET
    elif "DEBUG" in upper:
        return ANSI_CYAN + line + ANSI_RESET
    elif "TRACE" in upper:
        return ANSI_BLUE + line + ANSI_RESET
    return line

def make_timestamp():
    now = datetime.now()
    return now.strftime("[%H:%M:%S.") + f"{now.microsecond // 1000:03d}] "

def process_line(channel, line, use_filter, filter_kw, use_timestamp, use_color):
    """过滤、加时间戳/通道号、着色"""
    line = line.rstrip("\n\r")
    if use_filter and filter_kw and filter_kw not in line:
        return None
    prefix = ""
    if use_timestamp:
        prefix += make_timestamp()
    if channel is not None:
        prefix += f"[Ch{channel}] "
    return prefix + colorize(line, use_color)


# ── JLink 模式 ───────────────────────────────────

def monitor_jlink(device, interface, speed, channels, rtt_addr, log_file,
                  use_filter, filter_kw, use_timestamp, use_color, stats,
                  verbose=False):
    if not check_jlink():
        print("错误：未找到 JLink Commander"); sys.exit(1)

    # JLinkRTTLogger 支持多通道: -RTTChannel 0xFFFFFFFF 抓全部通道
    rtt_ch = "0xFFFFFFFF" if len(channels) > 1 else str(channels[0])
    logger_cmd = RTT_LOGGER_CMD or "JLinkRTTLogger"
    cmd = [
        logger_cmd,
        "-device", device, "-if", interface, "-speed", str(speed),
        "-RTTChannel", rtt_ch,
    ]
    if rtt_addr:
        cmd += ["-RTTAddress", rtt_addr]
    out_path = log_file or os.path.join(tempfile.gettempdir(), "rtt_output.log")
    cmd.append(out_path)

    print(f"[rtt-monitor] JLink 模式 | {device} @ {interface}/{speed}kHz")
    if len(channels) > 1:
        print(f"[rtt-monitor] 多通道模式: {channels} (全波段)")
    else:
        print(f"[rtt-monitor] Channel: {channels[0]}")
    print(f"[rtt-monitor] 日志文件: {out_path}")
    print(f"[rtt-monitor] 启动... (Ctrl+C 停止)\n")

    max_retry = 3
    attempt = 0
    while attempt <= max_retry:
        if attempt > 0:
            print(f"[rtt-monitor] 断连，重试 {attempt}/{max_retry}...")
            time.sleep(2)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def tail_log(path):
            time.sleep(1)
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                while proc.poll() is None:
                    line = f.readline()
                    if line:
                        # RTTLogger 输出格式: "CH<num>: ..." 或纯文本
                        ch = None
                        for c in channels:
                            if line.startswith(f"CH{c}:"):
                                ch = c
                                line = line[len(f"CH{ch}:"):]
                                break
                        result = process_line(ch, line.lstrip(), use_filter, filter_kw,
                                              use_timestamp, use_color)
                        if result is not None:
                            print(result)
                            stats["lines"] += 1
                            stats["bytes"] += len(line.encode("utf-8", errors="replace"))
                            # 检查环缓冲溢出标记（SEGGER_RTT_printf 在溢出时会丢失数据）
                            if "OVERFLOW" in line.upper():
                                stats["overflows"] += 1
                    else:
                        time.sleep(0.05)

        t = threading.Thread(target=tail_log, args=(out_path,), daemon=True)
        t.start()
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            print(f"\n[rtt-monitor] 已停止，日志: {out_path}")
            return
        ret = proc.returncode
        if ret == 0:
            return
        attempt += 1
    print(f"[rtt-monitor] 重试 {max_retry} 次后停止。")


# ── OpenOCD 模式 ─────────────────────────────────

def monitor_openocd(host, port, use_filter, filter_kw, use_timestamp, use_color, stats):
    print(f"[rtt-monitor] OpenOCD 模式 | telnet {host}:{port}")
    max_retry = 3
    attempt = 0
    while attempt <= max_retry:
        if attempt > 0:
            print(f"[rtt-monitor] 重试 {attempt}/{max_retry}...")
            time.sleep(2)
        try:
            tn = telnetlib.Telnet(host, port, timeout=10)
            print(f"[rtt-monitor] 已连接，Ctrl+C 停止...\n")
            attempt = 0
            try:
                while True:
                    data = tn.read_until(b"\n", timeout=1)
                    if data:
                        line = data.decode("utf-8", errors="replace")
                        result = process_line(None, line, use_filter, filter_kw,
                                              use_timestamp, use_color)
                        if result is not None:
                            print(result)
                            stats["lines"] += 1
                            stats["bytes"] += len(line.encode("utf-8", errors="replace"))
            except KeyboardInterrupt:
                tn.close()
                print("\n[rtt-monitor] 已停止。")
                return
            except EOFError:
                tn.close()
                print("[rtt-monitor] 连接断开。")
        except (ConnectionRefusedError, OSError) as e:
            print(f"[rtt-monitor] 连接失败: {e}")
        attempt += 1
    print(f"[rtt-monitor] 重试 {max_retry} 次后停止。")


def print_stats(stats):
    elapsed = time.time() - stats["start"]
    lines = stats["lines"]
    byts  = stats["bytes"]
    overflows = stats["overflows"]
    rate_line = lines / elapsed if elapsed > 0 else 0
    rate_byte = byts / elapsed if elapsed > 0 else 0
    print(f"\n[rtt-monitor] ══════════ 统计 ══════════")
    print(f"  运行时长 : {elapsed:.1f}s")
    print(f"  日志行数 : {lines}")
    print(f"  数据量   : {byts:,} 字节")
    print(f"  行速率   : {rate_line:.1f} 行/秒")
    print(f"  字节速率 : {rate_byte/1024:.1f} KB/s")
    if overflows > 0:
        print(f"  ⚠ 环缓冲溢出 : {overflows} 次 (建议增大 BUFFER_SIZE_UP)")
    print(f"═══════════════════════════════════")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEGGER RTT 实时日志监控")
    parser.add_argument("--device", default=None, help="MCU型号 (JLink模式必填)")
    parser.add_argument("--interface", default="SWD", choices=["SWD", "JTAG"])
    parser.add_argument("--speed", type=int, default=4000)
    parser.add_argument("--channel", default="0", help="RTT 通道号，多通道用逗号分隔 (如 0,1)")
    parser.add_argument("--rtt-addr", default=None, help="RTT 控制块地址 (十六进制)")
    parser.add_argument("--log-file", default=None, help="日志保存路径")
    parser.add_argument("--mode", default="jlink", choices=["jlink", "openocd"])
    parser.add_argument("--openocd-host", default="127.0.0.1")
    parser.add_argument("--openocd-port", type=int, default=4444)
    parser.add_argument("--filter", default=None, dest="filter_kw", help="关键字过滤")
    parser.add_argument("--timestamp", default=True,
                        type=lambda x: x.lower() not in ("false", "0", "no"))
    parser.add_argument("--color", default=True,
                        type=lambda x: x.lower() not in ("false", "0", "no"))
    args = parser.parse_args()

    channels = [int(c.strip()) for c in args.channel.split(",")]

    stats = {"lines": 0, "bytes": 0, "overflows": 0, "start": time.time()}
    use_filter = args.filter_kw is not None

    try:
        if args.mode == "jlink":
            if not args.device:
                print("错误：JLink 模式必须指定 --device"); sys.exit(1)
            monitor_jlink(args.device, args.interface, args.speed,
                          channels, args.rtt_addr, args.log_file,
                          use_filter, args.filter_kw,
                          args.timestamp, args.color, stats)
        else:
            monitor_openocd(args.openocd_host, args.openocd_port,
                            use_filter, args.filter_kw,
                            args.timestamp, args.color, stats)
    finally:
        print_stats(stats)
