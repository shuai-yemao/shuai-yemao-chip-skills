#!/usr/bin/env python
"""J-Link 内存/寄存器读取工具。

替代 MCP keil_reg_read，通过 JLink Commander 读取目标芯片的内存和外设寄存器。

用法:
  keil_reg_reader.py --device STM32F411CE --addr 0x40023800 --count 4
  keil_reg_reader.py --device STM32F411CE --addr 0x40023800 --group RCC
  keil_reg_reader.py --device STM32F411CE --list-groups
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# STM32F4 外设基地址映射
PERIPHERAL_GROUPS: dict[str, tuple[str, int, str]] = {
    "RCC":      ("0x40023800", 50, "Reset and Clock Control"),
    "GPIOA":    ("0x40020000", 16, "GPIO Port A"),
    "GPIOB":    ("0x40020400", 16, "GPIO Port B"),
    "GPIOC":    ("0x40020800", 16, "GPIO Port C"),
    "GPIOD":    ("0x40020C00", 16, "GPIO Port D"),
    "GPIOE":    ("0x40021000", 16, "GPIO Port E"),
    "GPIOH":    ("0x40021C00", 16, "GPIO Port H"),
    "USART1":   ("0x40011000", 18, "USART1"),
    "USART2":   ("0x40004400", 18, "USART2"),
    "USART6":   ("0x40011400", 18, "USART6"),
    "SPI1":     ("0x40013000", 16, "SPI1"),
    "SPI2":     ("0x40003800", 16, "SPI2"),
    "TIM2":     ("0x40000000", 22, "TIM2"),
    "TIM3":     ("0x40000400", 22, "TIM3"),
    "TIM4":     ("0x40000800", 22, "TIM4"),
    "TIM5":     ("0x40000C00", 22, "TIM5"),
    "IWDG":     ("0x40003000", 4, "Independent Watchdog"),
    "WWDG":     ("0x40002C00", 4, "Window Watchdog"),
    "ADC1":     ("0x40012000", 32, "ADC1"),
    "DAC":      ("0x40007400", 8, "DAC"),
    "PWR":      ("0x40007000", 4, "Power Control"),
    "EXTI":     ("0x40013C00", 12, "External Interrupt"),
    "SYSCFG":   ("0x40013800", 20, "System Configuration"),
    "DMA1":     ("0x40026000", 24, "DMA1"),
    "DMA2":     ("0x40026400", 24, "DMA2"),
    "FLASH":    ("0x40023C00", 12, "Flash Interface"),
    "SCB":      ("0xE000ED00", 22, "System Control Block"),
    "NVIC":     ("0xE000E100", 50, "NVIC ISER/ICER/ISPR/ICPR"),
    "SYSTICK":  ("0xE000E010", 4, "SysTick Timer"),
    "DBGMCU":   ("0xE0042000", 8, "Debug MCU"),
}

# STM32F4 寄存器偏移名 (常用)
REGISTER_NAMES_RCC: dict[int, str] = {
    0x00: "CR", 0x04: "CFGR", 0x08: "CIR", 0x0C: "AHB1RSTR",
    0x10: "AHB2RSTR", 0x14: "AHB3RSTR", 0x18: "Reserved",
    0x1C: "APB1RSTR", 0x20: "APB2RSTR", 0x24: "Reserved",
    0x28: "AHB1ENR", 0x2C: "AHB2ENR", 0x30: "AHB3ENR",
    0x34: "Reserved", 0x38: "APB1ENR", 0x3C: "APB2ENR",
    0x40: "Reserved", 0x44: "Reserved", 0x48: "AHB1LPENR",
    0x4C: "AHB2LPENR", 0x50: "AHB3LPENR", 0x54: "Reserved",
    0x58: "APB1LPENR", 0x5C: "APB2LPENR", 0x60: "BDCR",
    0x64: "CSR", 0x68: "SSCGR", 0x6C: "PLLI2SCFGR",
    0x70: "Reserved", 0x74: "DCKCFGR",
}

REGISTER_NAMES_GPIO: dict[int, str] = {
    0x00: "MODER", 0x04: "OTYPER", 0x08: "OSPEEDR",
    0x0C: "PUPDR", 0x10: "IDR", 0x14: "ODR",
    0x18: "BSRR", 0x1C: "LCKR", 0x20: "AFRL",
    0x24: "AFRH",
}

REGISTER_NAMES_USART: dict[int, str] = {
    0x00: "SR", 0x04: "DR", 0x08: "BRR",
    0x0C: "CR1", 0x10: "CR2", 0x14: "CR3",
    0x18: "GTPR",
}


def find_jlink() -> str | None:
    """查找 JLink.exe 路径"""
    candidates = [
        r"C:\Program Files\SEGGER\JLink\JLink.exe",
        r"C:\Program Files (x86)\SEGGER\JLink\JLink.exe",
    ]
    import shutil
    path = shutil.which("JLink") or shutil.which("JLink.exe")
    if path:
        return path
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def read_memory_jlink(device: str, addr: int, count: int,
                      jlink_path: str | None = None) -> list[int] | None:
    """通过 JLink Commander 读取内存"""
    jlink = jlink_path or find_jlink()
    if not jlink:
        print("❌ 未找到 JLink.exe")
        return None

    # 构造 JLink 命令脚本
    cmds = (
        f"device {device}\n"
        f"si SWD\n"
        f"speed 4000\n"
        f"connect\n"
        f"mem {hex(addr)} {count * 4}\n"
        f"exit\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jlink",
                                     delete=False, encoding="ascii") as f:
        f.write(cmds)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [jlink, "-device", device, "-if", "SWD", "-speed", "4000",
             "-autoconnect", "1", "-CommanderScript", tmp_path],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print("❌ JLink 超时")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return parse_mem_output(output, addr, count)


def parse_mem_output(output: str, base_addr: int,
                     expected_count: int) -> list[int] | None:
    """解析 JLink mem 输出为 32-bit 值列表"""
    values: list[int] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or "J-Link>" in line or "mem " in line.lower():
            continue
        # 格式: 40023800 = 83 77 00 03 ...
        m = re.match(r'^([0-9A-Fa-f]+)\s*=\s*([0-9A-Fa-f\s]+)', line)
        if m:
            addr_str = m.group(1)
            byte_str = m.group(2).strip()
            bytes_list = byte_str.split()
            if len(bytes_list) >= 4:
                # 小端组装 32-bit
                b = [int(x, 16) for x in bytes_list[:4]]
                val = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)
                values.append(val)
    return values if values else None


def get_register_name(group: str, offset: int) -> str:
    """根据外设组和偏移返回寄存器名"""
    group_upper = group.upper()
    if group_upper == "RCC":
        return REGISTER_NAMES_RCC.get(offset, f"+0x{offset:04X}")
    if group_upper.startswith("GPIO"):
        return REGISTER_NAMES_GPIO.get(offset, f"+0x{offset:04X}")
    if group_upper.startswith("USART"):
        return REGISTER_NAMES_USART.get(offset, f"+0x{offset:04X}")
    return f"+0x{offset:04X}"


def print_registers(device: str, group: str, base_addr: int,
                    values: list[int], count: int) -> None:
    """打印寄存器值表格"""
    print(f"\n📊 {group} ({PERIPHERAL_GROUPS.get(group, ('', 0, ''))[2]})")
    print(f"  设备: {device}  |  基址: 0x{base_addr:08X}  |  读取: {len(values)} 字\n")
    print(f"  {'地址':<12} {'偏移':<8} {'寄存器名':<16} {'值':<12} {'二进制':<36}")
    print(f"  {'-'*11} {'-'*7} {'-'*15} {'-'*11} {'-'*35}")
    for i in range(min(len(values), count)):
        addr = base_addr + i * 4
        offset = i * 4
        reg_name = get_register_name(group, offset)
        val = values[i]
        bits = f"{val:032b}"
        dec_str = f"0x{val:08X}"
        print(f"  0x{addr:08X}  +0x{offset:04X}  {reg_name:<16} {dec_str:<12} {bits}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="J-Link 内存/寄存器读取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--device", default="STM32F411CE", help="目标芯片型号")
    parser.add_argument("--addr", help="起始地址 (hex), 如 0x40023800")
    parser.add_argument("--count", type=int, default=8, help="读取 32-bit 字数")
    parser.add_argument("--group", help="外设组名, 如 RCC/GPIOA/USART1")
    parser.add_argument("--jlink", help="JLink.exe 路径")
    parser.add_argument("--list-groups", action="store_true", help="列出支持的外设组")
    args = parser.parse_args()

    if args.list_groups:
        print("\n📋 支持的外设组:\n")
        print(f"  {'组名':<12} {'基地址':<14} {'描述':<30}")
        print(f"  {'-'*11} {'-'*13} {'-'*29}")
        for name, (base, _count, desc) in sorted(PERIPHERAL_GROUPS.items()):
            print(f"  {name:<12} {base:<14} {desc:<30}")
        print("\n  也可用 --addr 指定任意地址 + --count 指定字数\n")
        return 0

    # 确定地址和字数
    addr = None
    count = args.count
    group_name = args.group

    if group_name:
        info = PERIPHERAL_GROUPS.get(group_name.upper())
        if not info:
            print(f"❌ 未知外设组: {group_name}，用 --list-groups 查看可用组")
            return 1
        base_str, group_count, _desc = info
        addr = int(base_str, 16)
        count = group_count
    elif args.addr:
        addr = int(args.addr, 16) if args.addr.startswith("0x") else int(args.addr, 0)
    else:
        print("❌ 请指定 --addr 或 --group")
        return 1

    # 读取内存
    values = read_memory_jlink(args.device, addr, count, args.jlink)
    if not values:
        print("❌ 读取失败，请检查 J-Link 连接和目标板上电")
        return 1

    # 输出
    display_group = group_name.upper() if group_name else f"0x{addr:08X}"
    print_registers(args.device, display_group, addr, values, count)

    return 0


if __name__ == "__main__":
    sys.exit(main())
