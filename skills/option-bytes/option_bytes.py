#!/usr/bin/env python3
"""
option-bytes: STM32 Option Bytes 安全读取与配置工具
所有写操作需用户明确确认，防止误操作锁死芯片
支持 STM32F1/F4/L4/G0/H7 系列
"""
import argparse
import subprocess
import sys
import shutil
import re
import json
import datetime

BOR_LEVEL_MAP = {0: "1.8V", 1: "2.1V", 2: "2.4V", 3: "2.7V"}

DEVICE_COMMANDS = {
    "stm32f1": {
        "read": "stm32f1x options_read 0", "unlock": "stm32f1x unlock 0",
        "write": "stm32f1x options_write 0 {value}", "target": "target/stm32f1x.cfg",
    },
    "stm32f4": {
        "read": "stm32f4x options_read 0", "unlock": "stm32f4x unlock 0",
        "write": "stm32f4x options_write 0 {value}", "target": "target/stm32f4x.cfg",
    },
    "stm32l4": {
        "read": "stm32l4x option_read 0 0x40022020", "unlock": "stm32l4x unlock 0",
        "write": "stm32l4x option_write 0 0x40022020 {value}", "target": "target/stm32l4x.cfg",
    },
    "stm32g0": {
        "read": "stm32g0x option_read 0", "unlock": "stm32g0x unlock 0",
        "write": "stm32g0x option_write 0 {value}", "target": "target/stm32g0x.cfg",
    },
    "stm32h7": {
        "read": "stm32h7x options_read 0", "unlock": "stm32h7x unlock 0",
        "write": "stm32h7x options_write 0 {value}", "target": "target/stm32h7x.cfg",
    },
    "stm32l5": {
        "read": "stm32l5x option_read 0", "unlock": "stm32l5x unlock 0",
        "write": "stm32l5x option_write 0 {value}", "target": "target/stm32l5x.cfg",
    },
}

INTERFACE_CFG_MAP = {
    "stlink": "interface/stlink.cfg", "jlink": "interface/jlink.cfg",
    "cmsis-dap": "interface/cmsis-dap.cfg",
}

def check_openocd():
    if not shutil.which("openocd"):
        print("错误：未找到 openocd"); sys.exit(1)

def detect_device_family(device: str) -> str:
    device = device.lower()
    for family in sorted(DEVICE_COMMANDS.keys(), key=len, reverse=True):
        if device.startswith(family):
            return family
    return "stm32f4"

def resolve_interface_cfg(args) -> str:
    return args.interface_cfg or INTERFACE_CFG_MAP.get(args.interface.lower(),
                                                        f"interface/{args.interface.lower()}.cfg")

def run_openocd(interface_cfg: str, target_cfg: str, commands: list, timeout=60) -> tuple:
    cmd = ["openocd", "-f", interface_cfg, "-f", target_cfg]
    for c in commands:
        cmd += ["-c", c]
    cmd += ["-c", "shutdown"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout + result.stderr, result.returncode


# ─── 解析器 ───────────────────────────────────────

def parse_raw_option_bytes(output: str, family: str) -> dict:
    """从 OpenOCD 输出解析原始 Option Bytes，按系列位域拆解"""
    fields = {}
    hex_match = re.search(r"(?i)option[s\s_byte]*[:\s]+(?:0x)?([0-9A-Fa-f]{4,8})", output)
    raw_val = None
    if hex_match:
        try:
            raw_val = int(hex_match.group(1), 16)
        except ValueError:
            pass

    if raw_val is None:
        fields["RAW"] = "未能解析 Option Bytes 原始值"
        return fields

    fields["RAW"] = f"0x{raw_val:08X}"

    rdp_byte = raw_val & 0xFF
    rdp_map = {0xAA: "Level 0 (无保护)", 0xCC: "Level 2 (永久锁定)"}
    fields["RDP"] = f"0x{rdp_byte:02X} → {rdp_map.get(rdp_byte, 'Level 1 (读保护)')}"

    if family in ("stm32f1", "stm32f4"):
        nrst_stop  = (raw_val >> 8) & 1
        nrst_stdby = (raw_val >> 9) & 1
        bor_lev    = (raw_val >> 10) & 3
        wdg_sw     = (raw_val >> 12) & 1
        nwrp       = (raw_val >> 16) & 0xFFFF
        fields["nRST_STOP"]  = f"{nrst_stop} ({'STOP不复位' if nrst_stop else 'STOP会复位'})"
        fields["nRST_STDBY"] = f"{nrst_stdby} ({'待机不复位' if nrst_stdby else '待机会复位'})"
        fields["BOR_LEV"]    = f"{bor_lev} (~{BOR_LEVEL_MAP.get(bor_lev, '?')})"
        fields["WDG_SW"]     = f"{wdg_sw} ({'软件看门狗' if wdg_sw else '硬件看门狗'})"
        protected = [str(i) for i in range(16) if not ((nwrp >> i) & 1)]
        fields["nWRP"] = f"0x{nwrp:04X} ({'扇区 ' + ','.join(protected) + ' 写保护' if protected else '无写保护'})"

    elif family == "stm32g0":
        nboot1   = (raw_val >> 8) & 1
        nboot_sel = (raw_val >> 14) & 1
        borf_lev  = (raw_val >> 16) & 0xFF
        borr_lev  = (raw_val >> 24) & 3
        fields["nBOOT1"]    = str(nboot1)
        fields["nBOOT_SEL"] = f"{nboot_sel} ({'Option Bytes选Boot' if nboot_sel else 'BOOT0引脚选Boot'})"
        fields["BORF_LEV"]  = f"0x{borf_lev:02X}"
        fields["BORR_LEV"]  = str(borr_lev)

    elif family.startswith("stm32h7"):
        security = (raw_val >> 25) & 1
        boot_ube = (raw_val >> 26) & 1
        bcm4     = (raw_val >> 28) & 1
        bcm7     = (raw_val >> 29) & 1
        fields["SECURITY"]  = f"{security} ({'TrustZone使能' if security else '关闭'})"
        fields["BOOT_UBE"]  = str(boot_ube)
        fields["BCM4"]      = f"{bcm4} ({'M4 Boot使能' if bcm4 else '关闭'})"
        fields["BCM7"]      = f"{bcm7} ({'M7 Boot使能' if bcm7 else '关闭'})"

    return fields


def print_option_bytes(output: str, fields: dict = None):
    print("\n═══════════ STM32 Option Bytes ═══════════")
    if fields:
        for name, val in fields.items():
            print(f"  {name:<14}: {val}")
    else:
        for line in output.splitlines():
            if any(kw in line.lower() for kw in
                   ["option", "rdp", "wrp", "bor", "iwdg", "nrst", "pcrop", "security", "boot"]):
                print(f"  {line.strip()}")
    print("══════════════════════════════════════════\n")


def confirm_write(operation: str, device: str, warning: str, confirm_code: str) -> bool:
    print(f"\n{'='*50}")
    print(f"⚠  即将执行：{operation}")
    print(f"   目标芯片：{device}")
    print(f"   警告：{warning}")
    print(f"{'='*50}")
    user_input = input(f"\n请输入确认码 [{confirm_code}] 以继续，或直接回车取消：").strip()
    return user_input == confirm_code


def cmd_read(args, family: str, cmds: dict):
    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, rc = run_openocd(interface_cfg, target_cfg,
                             ["init", "reset halt", cmds["read"]])
    fields = parse_raw_option_bytes(output, family)
    print_option_bytes(output, fields)


def cmd_dump(args, family: str, cmds: dict):
    if not args.output:
        print("错误：dump 操作需要指定 --output <文件路径.json>"); sys.exit(1)
    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, rc = run_openocd(interface_cfg, target_cfg,
                             ["init", "reset halt", cmds["read"]])
    fields = parse_raw_option_bytes(output, family)
    print_option_bytes(output, fields)
    dump_data = {
        "timestamp": datetime.datetime.now().isoformat(), "device": args.device,
        "family": family.upper(), "interface": args.interface,
        "openocd_rc": rc, "fields": fields, "raw_output": output,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(dump_data, f, ensure_ascii=False, indent=2)
    print(f"[option-bytes] 已导出: {args.output}")


def cmd_unlock(args, family: str, cmds: dict):
    if not confirm_write("解除 RDP 读保护", args.device,
                         "此操作将全片擦除 Flash！固件数据永久丢失！请确认已备份固件！",
                         "CONFIRM-UNLOCK"):
        print("操作已取消。"); return
    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, rc = run_openocd(interface_cfg, target_cfg,
                             ["init", "halt", cmds["unlock"], "reset"], timeout=120)
    print(output)
    print("[OK] 解锁完成 (Flash 已擦除)" if rc == 0 else "[FAIL] 解锁失败")


def cmd_set_rdp(args, family: str, cmds: dict):
    """设置 RDP 级别：--rdp-level 0/1/2"""
    if args.rdp_level is None:
        print("错误：set-rdp 操作需要指定 --rdp-level (0/1/2)"); sys.exit(1)
    level = args.rdp_level
    if level == 0:
        value = "0xAA"
        warn  = "设置为 Level 0（无保护），可正常调试和读取 Flash"
        code  = "CONFIRM-RDP0"
    elif level == 1:
        value = "0xBB"
        warn  = "Level 1（读保护），调试接口无法读取 Flash，解除需全片擦除"
        code  = "CONFIRM-RDP1"
    elif level == 2:
        value = "0xCC"
        warn  = "⚠ Level 2（永久锁定）！芯片将永久无法调试、读取、再编程！绝不可逆！"
        code  = "CONFIRM-RDP2-PERMANENT"
    else:
        print(f"错误：无效的 RDP 级别: {level}"); sys.exit(1)

    if not confirm_write(f"设置 RDP Level {level}", args.device, warn, code):
        print("操作已取消。"); return

    # 先读取当前值，仅修改 RDP 字节
    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, _ = run_openocd(interface_cfg, target_cfg,
                            ["init", "reset halt", cmds["read"]])
    fields = parse_raw_option_bytes(output, family)
    raw_hex = fields.get("RAW", "")
    if raw_hex.startswith("0x"):
        current = int(raw_hex, 16)
        new_val = (current & 0xFFFFFF00) | int(value, 16)
    else:
        print("警告：无法读取当前 Option Bytes，将使用默认值"); new_val = 0xAA

    write_cmd = cmds["write"].format(value=f"0x{new_val:08X}")
    output2, rc = run_openocd(interface_cfg, target_cfg,
                              ["init", "reset halt", write_cmd, "reset"], timeout=60)
    print(output2)
    if rc == 0:
        print(f"[OK] RDP Level {level} 设置完成，正在回读验证...")
        cmd_read(args, family, cmds)
    else:
        print("[FAIL] RDP 设置失败")


def cmd_set_wrp(args, family: str, cmds: dict):
    """设置写保护扇区 --wrp-sectors 0,1,2"""
    if args.wrp_sectors is None:
        print("错误：set-wrp 操作需要指定 --wrp-sectors (如 --wrp-sectors 0,1,2)"); sys.exit(1)
    sectors = [int(s.strip()) for s in args.wrp_sectors.split(",")]
    if any(s < 0 or s > 15 for s in sectors):
        print("错误：扇区号必须在 0~15 之间"); sys.exit(1)

    wrp_bits = 0xFFFF
    for s in sectors:
        wrp_bits &= ~(1 << s)

    if not confirm_write(f"设置 WRP 写保护", args.device,
                         f"保护扇区: {sectors}，这些扇区将无法写入/擦除。解除需全片擦除后重设。",
                         f"CONFIRM-WRP-{'-'.join(str(s) for s in sectors)}"):
        print("操作已取消。"); return

    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, _ = run_openocd(interface_cfg, target_cfg,
                            ["init", "reset halt", cmds["read"]])
    fields = parse_raw_option_bytes(output, family)
    raw_hex = fields.get("RAW", "")
    if raw_hex.startswith("0x"):
        current = int(raw_hex, 16)
        new_val = (current & 0x0000FFFF) | (wrp_bits << 16)
    else:
        new_val = (wrp_bits << 16) | 0xAA

    write_cmd = cmds["write"].format(value=f"0x{new_val:08X}")
    output2, rc = run_openocd(interface_cfg, target_cfg,
                              ["init", "reset halt", write_cmd, "reset"], timeout=60)
    print(output2)
    if rc == 0:
        print(f"[OK] WRP 设置完成 (保护扇区 {sectors})，正在回读验证...")
        cmd_read(args, family, cmds)
    else:
        print("[FAIL] WRP 设置失败")


def cmd_set_bor(args, family: str, cmds: dict):
    if args.bor_level is None:
        print("错误：set-bor 需要 --bor-level (0~3)"); sys.exit(1)
    level = args.bor_level
    if level not in BOR_LEVEL_MAP:
        print(f"错误：BOR level 必须 0~3, 收到 {level}"); sys.exit(1)
    voltage = BOR_LEVEL_MAP[level]
    if not confirm_write(f"设置 BOR Level {level} (~{voltage})", args.device,
                         f"修改低压保护阈值，不当设置可能导致意外复位",
                         f"CONFIRM-BOR{level}"):
        print("操作已取消。"); return

    interface_cfg = resolve_interface_cfg(args)
    target_cfg = args.target_cfg or cmds["target"]
    output, _ = run_openocd(interface_cfg, target_cfg,
                            ["init", "reset halt", cmds["read"]])
    fields = parse_raw_option_bytes(output, family)
    raw_hex = fields.get("RAW", "")
    if raw_hex.startswith("0x"):
        current = int(raw_hex, 16)
        new_val = (current & ~(0x3 << 10)) | (level << 10)
    else:
        new_val = 0xAA

    write_cmd = cmds["write"].format(value=f"0x{new_val:08X}")
    output2, rc = run_openocd(interface_cfg, target_cfg,
                              ["init", "reset halt", write_cmd, "reset"], timeout=60)
    print(output2)
    if rc == 0:
        print(f"[OK] BOR {level} (~{voltage}) 设置完成，回读验证...")
        cmd_read(args, family, cmds)
    else:
        print("[FAIL] BOR 设置失败")


def main():
    parser = argparse.ArgumentParser(description="STM32 Option Bytes 安全读取与配置工具",
                                     epilog="写操作不可逆，请谨慎操作！")
    parser.add_argument("--device", required=True, help="STM32 型号，如 STM32F407VG")
    parser.add_argument("--interface", default="stlink",
                        choices=["stlink", "jlink", "cmsis-dap"])
    parser.add_argument("--interface-cfg", default=None, help="覆盖 interface cfg 路径")
    parser.add_argument("--target-cfg", default=None, help="覆盖 target cfg 路径")
    parser.add_argument("--rdp-level", type=int, choices=[0, 1, 2],
                        help="RDP 级别 (set-rdp 操作)")
    parser.add_argument("--bor-level", type=int, choices=[0, 1, 2, 3],
                        help="BOR 阈值 (set-bor 操作)")
    parser.add_argument("--wrp-sectors", default=None,
                        help="写保护扇区号，逗号分隔 (set-wrp 操作，如 0,1,2)")
    parser.add_argument("--output", default=None, help="dump 输出 JSON 路径")
    parser.add_argument("operation",
                        choices=["read", "unlock", "set-rdp", "set-wrp",
                                 "set-bor", "set-iwdg", "set-boot", "dump", "custom"],
                        help="read=读取 unlock=解除RDP set-rdp=设读保护 set-wrp=设写保护 set-bor=设BOR dump=导出JSON")
    args = parser.parse_args()

    check_openocd()
    family = detect_device_family(args.device)
    cmds = DEVICE_COMMANDS.get(family, DEVICE_COMMANDS["stm32f4"])

    print(f"[option-bytes] 目标: {args.device} (系列: {family.upper()})")
    print(f"[option-bytes] 探针: {args.interface}")
    print(f"[option-bytes] Interface: {resolve_interface_cfg(args)}")
    print(f"[option-bytes] Target:    {args.target_cfg or cmds['target']}")

    dispatch = {
        "read":    lambda: cmd_read(args, family, cmds),
        "unlock":  lambda: cmd_unlock(args, family, cmds),
        "set-rdp": lambda: cmd_set_rdp(args, family, cmds),
        "set-wrp": lambda: cmd_set_wrp(args, family, cmds),
        "set-bor": lambda: cmd_set_bor(args, family, cmds),
        "dump":    lambda: cmd_dump(args, family, cmds),
    }

    handler = dispatch.get(args.operation)
    if handler:
        handler()
    else:
        print(f"[option-bytes] 操作 '{args.operation}' 需根据具体芯片手册构造命令。")
        print(f"[option-bytes] 建议先执行 read/dump 查看当前 Option Bytes。")
        sys.exit(1)


if __name__ == "__main__":
    main()
