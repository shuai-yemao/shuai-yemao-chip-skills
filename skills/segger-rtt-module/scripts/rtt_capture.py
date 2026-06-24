#!/usr/bin/env python3
"""
rtt_capture.py — JLink RTT 自动读取工具

通过 JLinkRTTClient 自动捕获 RTT 输出。

工作原理：
1. 启动后台 JLink 进程维持 RTT Server
2. 启动 JLinkRTTClient 连接到 Server 监听
3. 复位目标板触发固件启动和 RTT 输出
4. 捕获输出并返回

限制：单次故障输出（HardFault）的 RTT 数据生成极快（毫秒级），
RTT Client 捕获窗口可能错过。建议用 JLinkRTTViewer GUI 获得完整输出。
本脚本适用于持续输出日志的固件。

用法:
  python rtt_capture.py --device STM32F411CE --timeout 8
  python rtt_capture.py --device STM32F411CE --flash firmware.axf --timeout 8
"""

import subprocess, sys, os, time, argparse


def find_exe(name):
    candidates = [
        f"C:/Program Files/SEGGER/JLink/{name}.exe",
        f"C:/Program Files (x86)/SEGGER/JLink/{name}.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return name


def flash_device(device, axf_path):
    jlink = find_exe("JLink")
    inp = f'loadfile "{axf_path}"\nr\ng\nexit\n'
    try:
        r = subprocess.run([jlink, "-device", device, "-if", "SWD", "-speed", "4000", "-autoconnect", "1"],
            input=inp, capture_output=True, text=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return "O.K." in (r.stdout + r.stderr)
    except:
        return False


def kill_all():
    for exe in ["JLinkRTTViewer.exe", "JLinkRTTClient.exe", "JLinkRTTLogger.exe", "JLink.exe"]:
        os.system(f'taskkill /F /IM {exe} 2>nul')
    time.sleep(2)


def capture_rtt(device, timeout_s=10):
    """
    顺序: 启动 RTT Server → RTT Client → 复位板子 → 捕获
    """
    # 1. 启动后台 JLink 保持 RTT Server 连接
    server = subprocess.Popen(
        [find_exe("JLink"), "-device", device, "-if", "SWD", "-speed", "4000", "-autoconnect", "1"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    server.stdin.write(b"connect\n")
    server.stdin.flush()
    time.sleep(3)

    # 2. 启动 RTT Client 监听
    rtt_log = os.environ.get("TMP", "C:/Windows/Temp") + f"/rtt_capture_{int(time.time())}.log"
    os.makedirs(os.path.dirname(rtt_log), exist_ok=True)

    client_proc = subprocess.Popen(
        [find_exe("JLinkRTTClient")],
        stdout=open(rtt_log, "w", encoding="utf-8"), stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    time.sleep(4)

    # 3. 复位板子触发输出（通过后台 JLink 连接）
    server.stdin.write(b"r\ng\n")
    server.stdin.flush()

    # 4. 等待输出
    time.sleep(timeout_s)

    # 5. 清理
    client_proc.terminate()
    try: client_proc.wait(3)
    except: client_proc.kill()

    try:
        server.stdin.write(b"exit\n")
        server.stdin.flush()
        server.terminate()
        server.wait(3)
    except:
        server.kill()

    # 6. 读取输出
    text = ""
    if os.path.exists(rtt_log):
        with open(rtt_log, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        try: os.remove(rtt_log)
        except: pass

    # 过滤头信息
    lines = [l for l in text.split("\n")
             if l.strip() and not any(l.strip().startswith(p)
                for p in ("###", "SEGGER", "Process:", "Connecting", "J-Link", "localhost"))]

    return "\n".join(lines) if lines else text


def main():
    parser = argparse.ArgumentParser(description="JLink RTT 自动捕获工具")
    parser.add_argument("--device", default="STM32F411CE")
    parser.add_argument("--timeout", type=int, default=6, help="复位后等待(秒)")
    parser.add_argument("--flash", help="闪存.axf后捕获")

    args = parser.parse_args()
    kill_all()

    if args.flash:
        sys.stderr.write(f"[RTT] Flashing...\n")
        if not flash_device(args.device, args.flash):
            sys.stderr.write("[RTT] Flash FAILED\n"); sys.exit(1)
        sys.stderr.write("[RTT] Flash OK\n")
        time.sleep(2)

    sys.stderr.write("[RTT] Capturing (listen→reset→read)...\n")
    output = capture_rtt(args.device, args.timeout)

    if output.strip():
        print(output.strip())
    else:
        sys.stderr.write("[RTT] No data\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
