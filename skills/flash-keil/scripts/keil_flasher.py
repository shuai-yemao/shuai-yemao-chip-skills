#!/usr/bin/env python3
"""
keil_flasher.py — Keil MDK 工程产物烧录工具

通过 J-Link Commander 烧录 Keil 编译产出的 .hex/.axf 文件。
支持自动解析 .uvprojx 工程文件，定位输出目录。

用法:
    python keil_flasher.py --project app.uvprojx
    python keil_flasher.py --project app.uvprojx --target "Release"
    python keil_flasher.py --hex Build/app.hex --device STM32F411CE
"""

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


# ── 路径探测 ─────────────────────────────────────────────────────

JLINK_SEARCH_PATHS = [
    r"C:\Program Files\SEGGER\JLink\JLink.exe",
    r"C:\Program Files (x86)\SEGGER\JLink\JLink.exe",
]


def find_jlink():
    """查找 JLink.exe"""
    from shutil import which
    cmd = which("JLink.exe") or which("JLink")
    if cmd:
        return cmd
    for p in JLINK_SEARCH_PATHS:
        if os.path.isfile(p):
            return p
    return None


# ── .uvprojx 解析 ───────────────────────────────────────────────

def parse_uvprojx(proj_path, target_name=None):
    """
    解析 .uvprojx，返回 {output_dir, output_name, device, hex_path, axf_path}
    如果 target_name 为 None，使用第一个 Target
    """
    tree = ET.parse(proj_path)
    root = tree.getroot()

    # 命名空间
    ns = ""
    for _, v in root.tag.split("}", 1) if "}" in root.tag else ("", root.tag):
        pass

    def strip_ns(tag):
        return tag.split("}", 1)[1] if "}" in tag else tag

    # 查找 Target
    targets = {}
    for tge in root.iter():
        tag = strip_ns(tge.tag)
        if tag == "Target":
            name_el = tge.find(".//{*}TargetName")
            if name_el is not None:
                targets[name_el.text] = tge

    if not targets:
        print("[X] 未找到任何 Target")
        return None

    if target_name:
        if target_name not in targets:
            print(f"[X] Target '{target_name}' 不存在，可用: {list(targets.keys())}")
            return None
        target_el = targets[target_name]
    else:
        target_name = list(targets.keys())[0]
        target_el = targets[target_name]
        print(f"    使用第一个 Target: {target_name}")

    # 获取 TargetOption
    to_el = target_el.find(".//{*}TargetOption")
    if to_el is None:
        print("[X] 找不到 TargetOption")
        return None

    # 输出目录 (TargetOption > TargetCommonOption > OutputDirectory)
    out_dir_el = to_el.find(".//{*}OutputDirectory")
    out_name_el = to_el.find(".//{*}OutputName")
    out_dir = out_dir_el.text if out_dir_el is not None else "Objects"
    out_name = out_name_el.text if out_name_el is not None else "output"

    # 输出类型 (TargetOption > TargetCommonOption > CreateHexFile)
    create_hex_el = to_el.find(".//{*}CreateHexFile")
    create_hex = create_hex_el.text == "1" if create_hex_el is not None else False

    # 设备型号 (TargetOption > TargetDriverConfiguration > CPU > DeviceId)
    device_el = to_el.find(".//{*}Cpu")
    device = ""
    if device_el is not None:
        device = device_el.text or ""

    # 输出目录路径（相对工程文件）
    proj_dir = os.path.dirname(os.path.abspath(proj_path))
    out_dir_abs = os.path.join(proj_dir, out_dir)

    # 如果 CreateHexFile=1，输出 .hex，否则用 .axf
    hex_path = None
    axf_path = os.path.join(out_dir_abs, f"{out_name}.axf")
    if create_hex:
        hex_path = os.path.join(out_dir_abs, f"{out_name}.hex")

    return {
        "output_dir": out_dir_abs,
        "output_name": out_name,
        "device": device,
        "hex_path": hex_path,
        "axf_path": axf_path,
    }


# ── 烧录 ────────────────────────────────────────────────────────

def detect_device_from_hex(hex_path):
    """从 .hex 文件尝试推断设备（读取前几行）"""
    try:
        with open(hex_path, "r") as f:
            for _ in range(10):
                line = f.readline()
                if line.startswith(":"):
                    # Intel HEX 格式，不包含设备信息
                    pass
    except Exception:
        pass
    return None


def build_jlink_script(device, hex_path):
    """生成 J-Link Commander 烧录脚本"""
    lines = [
        "silent",
        "r",
        "h",
        "erase",
        f"loadfile {hex_path}",
        "r",
        "g",
        "exit",
    ]
    if device:
        lines.insert(0, f"device {device}")
    return "\n".join(lines)


def flash_via_jlink(jlink_path, device, hex_path, jlink_sn=None):
    """通过 J-Link Commander 烧录"""
    if not os.path.isfile(hex_path):
        print(f"[X] HEX 文件不存在: {hex_path}")
        return 1

    script = build_jlink_script(device, hex_path)
    print(f"    J-Link: {jlink_path}")
    print(f"    Device: {device or 'auto'}")
    print(f"    HEX:    {hex_path}")
    print(f"    Script:")
    for line in script.split("\n"):
        print(f"      {line}")

    # 写到临时脚本文件
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jlink", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        script_path = f.name

    try:
        cmd = [jlink_path]
        if jlink_sn:
            cmd += ["-SelectEmuBySN", jlink_sn]
        cmd += ["-CommanderScript", script_path]

        print(f"")
        print("    [*] 开始烧录...")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )

        # 输出关键信息
        for line in result.stdout.split("\n"):
            stripped = line.strip()
            if stripped and any(k in stripped.lower() for k in
                               ["error", "fail", "ok", "connected", "flash",
                                "downloaded", "verified", "erase", "script"]):
                print(f"      {stripped}")

        if result.returncode != 0:
            print(f"[X] 烧录失败 (exit={result.returncode})")
            # 显示最后几行错误
            error_lines = [l for l in result.stdout.split("\n")
                          if "error" in l.lower()]
            for el in error_lines[-3:]:
                print(f"      {el.strip()}")
            return 1

        print(f"    [OK] 烧录完成")
        return 0

    except subprocess.TimeoutExpired:
        print(f"[X] 烧录超时 (60s)")
        return 1
    except FileNotFoundError:
        print(f"[X] JLink.exe 未找到: {jlink_path}")
        return 1
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass


# ── 烧录 .axf ───────────────────────────────────────────────────

def axf_to_hex(axf_path, output_dir=None):
    """尝试用 J-Link 将 .axf 转换为 .hex"""
    # .axf 本质是 ELF，J-Link Commander 可以直接加载
    # 但兼容性不如 .hex，尝试用 fromelf / arm-none-eabi-objcopy 转换
    fromelf = r"G:\keil5\core\ARM\ARMCC\bin\fromelf.exe"
    if os.path.isfile(fromelf):
        hex_out = os.path.join(
            output_dir or os.path.dirname(axf_path),
            os.path.splitext(os.path.basename(axf_path))[0] + "_conv.hex"
        )
        cmd = [fromelf, "--i32", "--output", hex_out, axf_path]
        print(f"    尝试用 fromelf 将 .axf 转换为 .hex...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and os.path.isfile(hex_out):
            print(f"    [OK] 转换成功: {hex_out}")
            return hex_out
        else:
            print(f"    [!] fromelf 转换失败，尝试直接烧录 .axf")
    return axf_path


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Keil MDK 编译产物烧录工具 (J-Link)"
    )
    parser.add_argument("--project", "-p", help=".uvprojx 工程文件路径")
    parser.add_argument("--target", "-t", default=None,
                        help="Target 名称（默认用第一个）")
    parser.add_argument("--hex", help="直接指定 .hex 文件（跳过工程解析）")
    parser.add_argument("--axf", help="直接指定 .axf 文件")
    parser.add_argument("--device", "-d", default=None,
                        help="设备型号（自动从工程解析）")
    parser.add_argument("--jlink-sn", default=None, help="J-Link 序列号")
    parser.add_argument("--jlink-path", default=None, help="JLink.exe 路径")

    args = parser.parse_args()

    # 1. 查找 JLink
    jlink_path = args.jlink_path or find_jlink()
    if not jlink_path:
        print("[X] 未找到 JLink.exe，请安装 J-Link 驱动或使用 --jlink-path 指定")
        return 1

    # 2. 确定 hex 文件
    hex_path = args.hex
    device = args.device

    if args.project:
        print(f"[*] 解析工程: {args.project}")
        info = parse_uvprojx(args.project, args.target)
        if not info:
            return 1

        print(f"    输出目录: {info['output_dir']}")
        print(f"    输出名称: {info['output_name']}")
        if info["device"] and not device:
            device = info["device"]
            print(f"    设备型号: {device}")

        if info["hex_path"] and os.path.isfile(info["hex_path"]):
            hex_path = info["hex_path"]
            print(f"    [OK] 找到 .hex: {hex_path}")
        elif os.path.isfile(info["axf_path"]):
            hex_path = axf_to_hex(info["axf_path"], info["output_dir"])
            print(f"    使用 .axf: {hex_path}")
        else:
            print(f"[X] 未找到编译产物，请先运行 build-keil 编译工程")
            return 1

    elif args.axf:
        hex_path = axf_to_hex(args.axf)

    if not hex_path or not os.path.isfile(hex_path):
        print("[X] 未指定有效的 .hex 文件")
        return 1

    # 3. 烧录
    ret = flash_via_jlink(jlink_path, device or "", hex_path, args.jlink_sn)

    return ret


if __name__ == "__main__":
    sys.exit(main())
