#!/usr/bin/env python3
"""
寄存器兼容性检查脚本。

扫描源目录中的 C/C++ 代码，检测哪些寄存器名、位字段名、
宏定义在目标芯片上不存在（基于目标芯片头文件）。

用法：
    python check_reg_compat.py --src <src_dir> --target <chip_name> [--cmsis-root <dir>]

示例：
    python check_reg_compat.py --src ./Src --target STM32F411xE
    python check_reg_compat.py --src ./Src --target STM32H743xx --cmsis-root ./Drivers/CMSIS
"""

import re
import os
import sys
import argparse
import glob
from pathlib import Path


# CMSIS 寄存器命名模式
REG_PATTERNS = [
    # 外设→寄存器： USART1->CR1, TIM2->SR
    r'([A-Z][A-Z0-9_]+(?:[1-9]|[1-9][0-9]?))\s*->\s*([A-Z][A-Z0-9_]+)',

    # 外设_BASE + offset: USART1_BASE + 0x0C
    r'([A-Z][A-Z0-9_]+_BASE)\s*\+\s*(0x[0-9A-Fa-f]+)',

    # 寄存器宏: USART_CR1, TIM_SR_UIF
    r'(?:USART|TIM|SPI|I2C|ADC|DMA|RCC|GPIO|EXTI|SYSCFG)\_[A-Z0-9_]+',

    # _ENR 宏: RCC_APB2ENR, RCC_AHB1ENR
    r'RCC_[A-Z0-9_]+ENR_[A-Z0-9_]+',

    # GPIO 相关
    r'GPIO_[A-Z]+_[0-9]+',
    r'GPIO_AF[A-Z0-9_]+',
    r'GPIO_PinSource[0-9]+',

    # Remap 宏 (F1 特有)
    r'GPIO_Remap_[A-Z0-9_]+',
    r'GPIO_PartialRemap[A-Z0-9_]+',
    r'GPIO_FullRemap[A-Z0-9_]+',
]


def extract_symbols_from_code(src_dir: str) -> set:
    """从源码中提取所有芯片相关符号"""
    symbols = set()
    ext_patterns = ('*.c', '*.h', '*.cpp', '*.hpp')

    for ext in ext_patterns:
        for filepath in glob.glob(os.path.join(src_dir, '**', ext), recursive=True):
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue

            # 提取所有大写+数字+下划线构成的符号（长于 4 字符）
            matches = re.findall(r'\b[A-Z][A-Z0-9_]{3,60}\b', content)
            symbols.update(matches)

    return symbols


def extract_symbols_from_header(header_path: str) -> dict:
    """
    从 CMSIS 头文件提取所有定义的符号。
    返回 {symbol: source_line} 字典
    """
    symbols = {}

    if not os.path.isfile(header_path):
        return symbols

    try:
        with open(header_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return symbols

    # 提取 #define 宏
    for i, line in enumerate(lines):
        # #define SYMBOL value
        m = re.match(r'\s*#\s*define\s+([A-Z][A-Z0-9_]+)\b', line)
        if m:
            symbols[m.group(1)] = f"{header_path}:{i+1}"

        # 枚举常量
        m = re.match(r'\s*([A-Z][A-Z0-9_]+)\s*=', line)
        if m:
            symbols[m.group(1)] = f"{header_path}:{i+1}"

    return symbols


def find_target_header(chip_name: str, cmsis_root: str = None) -> str:
    """尝试找到目标芯片的头文件"""
    search_dirs = []

    if cmsis_root:
        search_dirs.append(cmsis_root)

    # 常见搜索路径
    search_dirs.extend([
        '.',
        './Drivers/CMSIS/Device/ST/STM32F1xx/Include',
        './Drivers/CMSIS/Device/ST/STM32F4xx/Include',
        './Drivers/CMSIS/Device/ST/STM32H7xx/Include',
        './Drivers/CMSIS/Device/ST/STM32G0xx/Include',
        './Drivers/CMSIS/Device/ST/STM32G4xx/Include',
        './Drivers/Core/Include',
        './Inc',
        './include',
    ])

    for d in search_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if chip_name.lower() in f.lower() and f.endswith('.h'):
                    return os.path.join(d, f)

    return ''


def categorize_symbol(symbol: str) -> str:
    """将符号分类"""
    if symbol.startswith('RCC_'):
        return 'RCC'
    elif symbol.startswith('GPIO_'):
        return 'GPIO'
    elif symbol.startswith('USART') or symbol.startswith('UART'):
        return 'USART'
    elif symbol.startswith('SPI'):
        return 'SPI'
    elif symbol.startswith('I2C'):
        return 'I2C'
    elif symbol.startswith('TIM') or symbol.startswith('TIMER'):
        return 'TIM'
    elif symbol.startswith('ADC'):
        return 'ADC'
    elif symbol.startswith('DMA'):
        return 'DMA'
    elif symbol.startswith('NVIC') or symbol.endswith('_IRQn') or symbol.endswith('IRQHandler'):
        return 'NVIC'
    elif symbol.startswith('FLASH') or symbol.startswith('OB_'):
        return 'FLASH'
    elif symbol.startswith('PWR_'):
        return 'PWR'
    elif symbol.startswith('USB') or symbol.startswith('OTG'):
        return 'USB'
    elif symbol.startswith('CAN') or symbol.startswith('FDCAN'):
        return 'CAN'
    elif symbol.startswith('SYSCFG') or symbol.startswith('AFIO'):
        return 'SYSCFG'
    elif symbol.startswith('EXTI'):
        return 'EXTI'
    elif symbol.startswith('DBGMCU'):
        return 'DBGMCU'
    else:
        return 'OTHER'


def main():
    parser = argparse.ArgumentParser(description='检查寄存器兼容性')
    parser.add_argument('--src', required=True, help='源码目录')
    parser.add_argument('--target', required=True, help='目标芯片名（如 STM32F411xE）')
    parser.add_argument('--cmsis-root', help='CMSIS 头文件根目录')
    args = parser.parse_args()

    print(f"=== 寄存器兼容性检查 ===")
    print(f"源码目录: {args.src}")
    print(f"目标芯片: {args.target}")
    print()

    # 1. 提取源码符号
    print("[1/3] 从源码提取符号...")
    src_symbols = extract_symbols_from_code(args.src)
    print(f"  找到 {len(src_symbols)} 个候选符号")

    # 2. 找到目标芯片头文件
    print("[2/3] 查找目标芯片头文件...")
    header_path = find_target_header(args.target, args.cmsis_root)

    if header_path:
        print(f"  头文件: {header_path}")
        target_symbols = extract_symbols_from_header(header_path)
        print(f"  找到 {len(target_symbols)} 个已定义符号")
    else:
        print("  [!] 未找到目标头文件，尝试通过 CMSIS 命名规则过滤")
        target_symbols = {}  # 空字典，降级为模式匹配

    # 3. 对比
    print("[3/3] 分析不兼容符号...")
    incompatible = {}
    unknown = {}

    for sym in sorted(src_symbols):
        if header_path:
            if sym not in target_symbols:
                cat = categorize_symbol(sym)
                if cat != 'OTHER':
                    incompatible.setdefault(cat, []).append(sym)
                else:
                    unknown.setdefault(cat, []).append(sym)
        else:
            # 无头文件，按命名规则过滤
            cat = categorize_symbol(sym)
            if cat != 'OTHER':
                unknown.setdefault(cat, []).append(sym)

    # 输出结果
    if incompatible:
        print("\n  [!] 可能不兼容的寄存器/宏定义：")
        for cat, syms in sorted(incompatible.items()):
            print(f"\n  --- {cat} ({len(syms)} 个) ---")
            for s in syms[:20]:  # 最多显示20个
                print(f"    {s}")
            if len(syms) > 20:
                print(f"    ... 还有 {len(syms)-20} 个")
    else:
        print("\n  [OK] 未检测到明显的不兼容符号")

    if unknown:
        print(f"\n  [?] 未能分类的符号: {sum(len(v) for v in unknown.values())} 个")
        for cat, syms in unknown.items():
            for s in syms[:10]:
                print(f"    {s}")

    print()
    print("注意：此脚本基于静态分析，不保证 100% 准确。")
    print("所有标记为不兼容的项目都需要人工核对参考手册。")


if __name__ == '__main__':
    main()
