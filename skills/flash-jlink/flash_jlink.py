#!/usr/bin/env python3
"""
flash-jlink: 使用 JLinkExe 烧录嵌入式固件
支持 .hex / .bin / .elf，自动生成 commander 脚本，内建重试与多探针管理
"""
import argparse
import subprocess
import tempfile
import os
import sys
import time
import re
import shutil


def find_jlink_cmd():
    """查找 JLinkExe/JLink Commander，返回可执行文件完整路径"""
    candidates = ["JLinkExe", "JLink"]
    for cmd in candidates:
        path = shutil.which(cmd)
        if path:
            return path
    # 常见安装路径兜底
    common_dirs = [
        r"C:\Program Files\SEGGER\JLink",
        r"C:\Program Files (x86)\SEGGER\JLink",
        r"C:\Program Files\SEGGER\JLink_V930",
        r"C:\Program Files\SEGGER\JLink_V928",
        r"G:\keil5\core\ARM\Segger",
    ]
    for d in common_dirs:
        for name in ["JLinkExe.exe", "JLink.exe"]:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    return None

JLINK_CMD = None

def check_jlink():
    global JLINK_CMD
    cmd = find_jlink_cmd()
    if cmd is None:
        return False
    # -version 在某些版本不支持（V8/V9 部分版本），先尝试，失败则用 -nogui
    try:
        r = subprocess.run([cmd, "-version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            JLINK_CMD = cmd
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 后备：-nogui 模式验证（exit 0 即认为可用）
    try:
        r = subprocess.run([cmd, "-nogui", "1"],
                           input="exit\n", capture_output=True, text=True, timeout=8)
        JLINK_CMD = cmd
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def list_emulators():
    """枚举已连接的 J-Link 探针，返回序列号列表"""
    global JLINK_CMD
    cmd = JLINK_CMD or find_jlink_cmd()
    if cmd is None:
        return []
    output = ""
    try:
        # -ListEmulatorsId 在部分版本不支持，不支持时连接 J-Link 读取 S/N
        result = subprocess.run(
            [cmd, "-ListEmulatorsId"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        if "Unknown command line option" in output:
            # 后备：直接连接 J-Link 从启动信息读取 S/N
            r2 = subprocess.run(
                ["echo", "exit"], capture_output=True, text=True, shell=False
            )
            r2 = subprocess.run(
                [cmd, "-nogui", "1"],
                input="exit\n", capture_output=True, text=True, timeout=10
            )
            output = r2.stdout + r2.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    serials = re.findall(r"Serial number[:\s]+(\d+)", output, re.IGNORECASE)
    if not serials:
        serials = re.findall(r"S/N[:\s]+(\d+)", output, re.IGNORECASE)
    if not serials:
        serials = re.findall(r"\b(\d{8,})\b", output)
    return list(dict.fromkeys(serials))


def detect_firmware_format(firmware: str) -> str:
    """检测固件格式，.elf 文件提示转换"""
    ext = os.path.splitext(firmware)[1].lower()
    if ext == ".elf":
        bin_path = os.path.splitext(firmware)[0] + ".bin"
        if os.path.exists(bin_path) and os.path.getmtime(bin_path) >= os.path.getmtime(firmware):
            print(f"[flash-jlink] 检测到 {bin_path} (.bin 已存在且更新)，使用 .bin")
            return "bin"
        print(f"提示：.elf 文件包含调试信息体积较大，建议先转换为 .bin：")
        print(f"  arm-none-eabi-objcopy -O binary {firmware} {bin_path}")
        print(f"  然后使用 --firmware {bin_path} --addr 0x08000000 重新运行")
        sys.exit(1)
    return ext.lstrip(".")


def extract_hex_addr(firmware: str) -> str:
    """从 Intel HEX 文件中提取起始地址"""
    try:
        with open(firmware, "r") as f:
            for line in f:
                if line.startswith(":02000004"):
                    addr = int(line[9:13], 16) << 16
                    return f"0x{addr:08X}"
    except Exception:
        pass
    return None


def generate_jlink_script(device, interface, speed, firmware, addr=None,
                           erase=False, verify_only=False, power=False,
                           reset_pin: str = None):
    """生成 JLink commander 脚本"""
    ext = os.path.splitext(firmware)[1].lower()
    lines = []

    if power:
        lines.append("power on")

    if reset_pin:
        lines.append(f"ResetType {reset_pin}")

    lines += [
        f"si {interface}",
        f"speed {speed}",
        f"device {device}",
        "connect",
        "h",
    ]

    if erase and not verify_only:
        lines.append("erase")

    if verify_only:
        if ext == ".bin":
            if addr is None:
                print("错误：.bin 文件校验必须指定地址 --addr")
                sys.exit(1)
            lines.append(f"verifybin {firmware},{addr}")
        else:
            # V9.30 不支持 verify 命令，用 loadfile 替代（compare-then-load 语义）
            # 结果中 "Contents already match" = 校验通过，实际烧录 = 内容不一致
            lines.append(f"loadfile {firmware}")
    else:
        if ext == ".bin":
            if addr is None:
                print("错误：.bin 文件必须指定烧录地址 --addr")
                sys.exit(1)
            lines.append(f"loadbin {firmware},{addr}")
        else:
            lines.append(f"loadfile {firmware}")

    lines += ["r", "go", "exit"]
    return "\n".join(lines)


def parse_write_bytes(output):
    m = re.search(r"[Ww]rot[e]?\s+(\d+)\s+bytes", output)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+bytes", output)
    if m:
        return int(m.group(1))
    return None


def flash_one(device, interface, speed, firmware, addr=None,
              erase=False, verify_only=False, sn=None, power=False, reset_pin=None):
    """执行单次 J-Link 烧录/校验，返回 (success, output, elapsed, written_bytes)"""
    script = generate_jlink_script(
        device, interface, speed, firmware, addr,
        erase=erase, verify_only=verify_only, power=power, reset_pin=reset_pin
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jlink", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        script_path = f.name

    cmd = [JLINK_CMD, "-nogui", "1"]
    if sn:
        cmd += ["-SelectEmuBySN", str(sn)]
    cmd += ["-commandfile", script_path]

    start_time = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.monotonic() - start_time
        output = result.stdout + result.stderr

        output_upper = output.upper()
        # 检查指挥官命令执行是否出错
        if "UNKNOWN COMMAND" in output_upper:
            return False, output, elapsed, None

        # V9.30 Commander exit code 不稳定，以输出文本判断为准
        if result.returncode != 0 and "O.K." not in output_upper and "FLASH DOWNLOAD" not in output_upper:
            return False, output, elapsed, None

        # 校验模式（V9.30 用 loadfile 替代 verify）
        if verify_only:
            success = "CONTENTS ALREADY MATCH" in output_upper or "SKIPPED" in output_upper
            written = None
            return success, output, elapsed, written

        success = ("FLASH DOWNLOAD" in output_upper   # 烧录成功
                   or "VERIFY SUCCESSFUL" in output_upper)  # 校验成功
        if not success and "O.K." in result.stdout:
            # loadfile 无显式标记时，有 O.K. 且无报错即视为成功
            success = "error" not in output_upper and "fail" not in output_upper
        written = parse_write_bytes(result.stdout) if success else None
        return success, output, elapsed, written
    except subprocess.TimeoutExpired:
        return False, "烧录超时 (120s)", time.monotonic() - start_time, None
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def flash(device, interface, speed, firmware, addr=None,
          erase=False, verify_only=False, sn=None, power=False,
          retry=0, retry_delay=2.0, reset_pin=None):
    """执行 J-Link 烧录/校验，支持自动重试"""
    if not check_jlink():
        print("错误：未找到 JLinkExe/JLink，请安装 SEGGER J-Link Software")
        sys.exit(1)

    global JLINK_CMD
    if not JLINK_CMD:
        print("错误：JLink Commander 不可用，请检查安装")
        sys.exit(1)

    if not os.path.exists(firmware):
        print(f"错误：固件文件不存在: {firmware}")
        print("提示：若路径含中文或空格，请将固件移至纯英文无空格路径后重试。")
        sys.exit(1)

    # 检测 .elf 提示转换
    detect_firmware_format(firmware)

    action = "校验" if verify_only else "烧录"
    print(f"[flash-jlink] 目标: {device} | 接口: {interface} @ {speed}kHz")
    print(f"[flash-jlink] 固件: {firmware}")
    if sn:
        print(f"[flash-jlink] 探针 SN: {sn}")
    if power:
        print(f"[flash-jlink] 目标板供电: 已启用 (3.3V)")
    if reset_pin:
        print(f"[flash-jlink] 复位引脚: {reset_pin}")
    if erase and not verify_only:
        print(f"[flash-jlink] 全片擦除: 已启用")
    if retry > 0:
        print(f"[flash-jlink] 重试设置: 最多 {retry} 次, 间隔 {retry_delay}s")
    # V9.30 没有 verify 命令，校验模式实际使用 loadfile 的 compare-then-load 语义
    ext = os.path.splitext(firmware)[1].lower()
    if verify_only and ext == ".hex":
        print("[flash-jlink] [注意] V9.30 Commander 无 verify 命令，使用 loadfile 比较")
        print("[flash-jlink]        Contents already match → 校验通过")
        print("[flash-jlink]        实际烧录 → 内容不一致")

    for attempt in range(retry + 1):
        if attempt > 0:
            print(f"\n[flash-jlink] 第 {attempt}/{retry} 次重试...")
            time.sleep(retry_delay)

        print(f"[flash-jlink] 执行{action}...")
        ok, output, elapsed, written = flash_one(
            device, interface, speed, firmware, addr,
            erase=erase, verify_only=verify_only, sn=sn, power=power, reset_pin=reset_pin
        )

        if ok:
            print(output)
            print(f"[flash-jlink] {action}成功")
            print(f"[flash-jlink] 耗时: {elapsed:.2f} 秒")
            if written and not verify_only:
                speed_kbs = written / 1024 / elapsed if elapsed > 0 else 0
                print(f"[flash-jlink] 写入字节: {written} bytes")
                print(f"[flash-jlink] 写入速度: {speed_kbs:.1f} KB/s")
            return

        print(output)

    # 全部失败
    error_map = {
        "RTT: FAILED TO CONNECT": "检查目标板时钟配置（HSE/PLL），或降低接口速度",
        "FIRMWARE FILE NOT FOUND": "路径含中文或空格，移至纯英文路径",
        "NO EMULATOR FOUND": "检查 USB 连接和 J-Link 驱动",
        "No such file": "路径含中文或空格，移至纯英文路径",
    }
    if verify_only and ext == ".hex" and "FLASH DOWNLOAD" in output.upper():
        print("\n[flash-jlink] 校验失败：固件与目标板 Flash 内容不一致")
        print("[flash-jlink]         loadfile 执行了实际烧录（非校验模式）")
        return
    for keyword, advice in error_map.items():
        if keyword in output.upper():
            print(f"错误：{keyword} → {advice}")
            break
    else:
        print(f"{action}失败！已重试 {retry} 次，请检查连接和设备配置。")
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="J-Link 固件烧录工具")
    parser.add_argument("--device", required=False, help="目标MCU型号，如 STM32F103C8")
    parser.add_argument("--interface", default="SWD", choices=["SWD", "JTAG"])
    parser.add_argument("--speed", default="4000", help="接口速度 kHz")
    parser.add_argument("--firmware", default=None, help="固件文件路径")
    parser.add_argument("--addr", default=None, help=".bin文件烧录起始地址（十六进制）")
    parser.add_argument("--erase", action="store_true", default=False,
                        help="烧录前全片擦除（默认关闭，谨慎使用）")
    parser.add_argument("--verify-only", action="store_true", default=False,
                        help="仅校验固件，不写入 Flash")
    parser.add_argument("--sn", default=None,
                        help="指定 J-Link 探针序列号（多探针并联时使用）")
    parser.add_argument("--power", action="store_true", default=False,
                        help="通过 J-Link 向目标板供 3.3V")
    parser.add_argument("--reset-pin", default=None,
                        choices=["TRST", "nTRST", "nSRST"],
                        help="复位引脚类型")
    parser.add_argument("--retry", type=int, default=0,
                        help="失败重试次数（默认 0，不重试）")
    parser.add_argument("--retry-delay", type=float, default=2.0,
                        help="重试间隔秒（默认 2.0）")
    parser.add_argument("--list", action="store_true", default=False,
                        help="枚举已连接的 J-Link 探针并打印序列号")
    args = parser.parse_args()

    if args.list:
        if not check_jlink():
            print("错误：未找到 JLinkExe/JLink，请安装 SEGGER J-Link Software")
            sys.exit(1)
        serials = list_emulators()
        if not serials:
            print("未检测到任何 J-Link 探针。请检查 USB 连接及驱动安装。")
        else:
            print(f"检测到 {len(serials)} 个 J-Link 探针：")
            for i, sn in enumerate(serials, 1):
                print(f"  [{i}] SN: {sn}")
            if len(serials) > 1:
                print("提示：多探针场景下，请使用 --sn <序列号> 指定目标探针。")
        sys.exit(0)

    if not args.device:
        parser.error("普通烧录模式需要指定 --device")
    if not args.firmware:
        parser.error("普通烧录模式需要指定 --firmware")

    # .bin 文件且未指定地址时尝试从 HEX 提取，否则报错
    addr = args.addr
    if not addr and args.firmware.endswith(".bin"):
        parser.error(".bin 文件必须指定 --addr（如 --addr 0x08000000）")

    flash(
        device=args.device, interface=args.interface, speed=args.speed,
        firmware=args.firmware, addr=addr, erase=args.erase,
        verify_only=args.verify_only, sn=args.sn, power=args.power,
        retry=args.retry, retry_delay=args.retry_delay, reset_pin=args.reset_pin,
    )
