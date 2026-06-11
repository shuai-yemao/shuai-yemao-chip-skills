#!/usr/bin/env python3
"""
宏定义映射表生成脚本。

基于源/目标芯片的 CMSIS 或 HAL 头文件，
生成两个芯片之间的宏定义映射对照表（Markdown 格式）。

用法：
    python gen_macro_map.py --source STM32F1 --target STM32F4 [--src-dir <dir>] [--output map.md]

示例：
    python gen_macro_map.py --source STM32F103xB --target STM32F411xE
    python gen_macro_map.py --source STM32F1 --target STM32F4 --src-dir ./Drivers/CMSIS --output rcc_map.md
"""

import os
import re
import sys
import argparse
import glob


# 已知的宏定义映射表（手动整理，按外设分组）
KNOWN_MAPS = {
    # RCC 时钟使能：F1 (APB2) vs F4+ (AHB1)
    'RCC_APB2Periph_GPIOA': 'RCC_AHB1Periph_GPIOA',
    'RCC_APB2Periph_GPIOB': 'RCC_AHB1Periph_GPIOB',
    'RCC_APB2Periph_GPIOC': 'RCC_AHB1Periph_GPIOC',
    'RCC_APB2Periph_GPIOD': 'RCC_AHB1Periph_GPIOD',
    'RCC_APB2Periph_GPIOE': 'RCC_AHB1Periph_GPIOE',
    'RCC_APB2Periph_GPIOF': 'RCC_AHB1Periph_GPIOF',
    'RCC_APB2Periph_GPIOG': 'RCC_AHB1Periph_GPIOG',
    'RCC_APB2Periph_AFIO': 'RCC_APB2Periph_SYSCFG',
    'RCC_APB2Periph_USART1': 'RCC_APB2Periph_USART1',
    'RCC_APB2Periph_SPI1': 'RCC_APB2Periph_SPI1',
    'RCC_APB1Periph_USART2': 'RCC_APB1Periph_USART2',
    'RCC_APB1Periph_USART3': 'RCC_APB1Periph_USART3',
    'RCC_APB1Periph_SPI2': 'RCC_APB1Periph_SPI2',
    'RCC_APB1Periph_I2C1': 'RCC_APB1Periph_I2C1',
    'RCC_APB1Periph_I2C2': 'RCC_APB1Periph_I2C2',
    'RCC_APB1Periph_TIM2': 'RCC_APB1Periph_TIM2',
    'RCC_APB1Periph_TIM3': 'RCC_APB1Periph_TIM3',
    'RCC_APB1Periph_TIM4': 'RCC_APB1Periph_TIM4',

    # GPIO Remap (F1) → AF (F4+)
    'GPIO_Remap_USART1': 'GPIO_AF7_USART1',
    'GPIO_Remap_USART2': 'GPIO_AF7_USART2',
    'GPIO_Remap_SPI1': 'GPIO_AF5_SPI1',
    'GPIO_Remap_I2C1': 'GPIO_AF4_I2C1',
    'GPIO_Remap_TIM1': 'GPIO_AF1_TIM1',
    'GPIO_Remap_TIM2': 'GPIO_AF1_TIM2',
    'GPIO_Remap_TIM3': 'GPIO_AF2_TIM3',

    # 系统时钟
    'SystemCoreClock = 72000000': 'SystemCoreClock = 168000000',
    'HSE_VALUE 8000000': 'HSE_VALUE 8000000',
    'HSI_VALUE 8000000': 'HSI_VALUE 16000000',
}


def extract_defines_from_headers(search_dir: str, chip_filter: str = None) -> dict:
    """从头文件中提取 #define 宏"""
    defines = {}

    if not os.path.isdir(search_dir):
        return defines

    for root, _, files in os.walk(search_dir):
        for f in files:
            if not f.endswith('.h'):
                continue
            if chip_filter and chip_filter.lower() not in f.lower():
                continue

            filepath = os.path.join(root, f)
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except Exception:
                continue

            # 提取所有 #define
            for m in re.finditer(r'#\s*define\s+(\w+)\s+(.*?)(?:\n|$)', content, re.MULTILINE):
                name = m.group(1)
                value = m.group(2).strip()
                # 只保留芯片相关的宏（大写）
                if name.isupper() and len(name) > 4:
                    defines[name] = value

    return defines


def match_by_pattern(source_defines: dict, target_defines: dict) -> list:
    """通过模式匹配找到潜在映射"""
    matches = []

    # 分组匹配策略：同名则映射
    common_names = set(source_defines.keys()) & set(target_defines.keys())
    for name in sorted(common_names):
        s_val = source_defines[name]
        t_val = target_defines[name]
        if s_val != t_val:
            matches.append((name, s_val, name, t_val, '同名异值'))

    # 后缀数字匹配：如 USART1 相关宏
    for s_name, s_val in source_defines.items():
        if s_name in KNOWN_MAPS:
            t_name = KNOWN_MAPS[s_name]
            t_val = target_defines.get(t_name, '?')
            matches.append((s_name, s_val, t_name, t_val, '已知映射'))

    return matches


def main():
    parser = argparse.ArgumentParser(description='生成宏定义映射对照表')
    parser.add_argument('--source', required=True, help='源芯片标识')
    parser.add_argument('--target', required=True, help='目标芯片标识')
    parser.add_argument('--src-dir', default='.', help='CMSIS/HAL 头文件目录')
    parser.add_argument('--output', help='输出 Markdown 文件')
    parser.add_argument('--group', default='all',
                        choices=['all', 'rcc', 'gpio', 'usart', 'spi', 'i2c', 'tim', 'dma'],
                        help='按外设分组输出')
    args = parser.parse_args()

    print(f"源芯片: {args.source}")
    print(f"目标芯片: {args.target}")
    print()

    # 提取头文件宏
    src_defines = extract_defines_from_headers(args.src_dir, args.source)
    tgt_defines = extract_defines_from_headers(args.src_dir, args.target)
    print(f"源芯片头文件: {len(src_defines)} 个宏")
    print(f"目标芯片头文件: {len(tgt_defines)} 个宏")

    # 匹配
    matches = match_by_pattern(src_defines, tgt_defines)

    # 分组
    group_filters = {
        'rcc': lambda n: n.startswith('RCC_'),
        'gpio': lambda n: n.startswith('GPIO_'),
        'usart': lambda n: n.startswith(('USART_', 'UART_')),
        'spi': lambda n: n.startswith('SPI_'),
        'i2c': lambda n: n.startswith('I2C_'),
        'tim': lambda n: n.startswith(('TIM_', 'TIMER_')),
        'dma': lambda n: n.startswith('DMA_'),
    }

    if args.group != 'all':
        filters = group_filters.get(args.group, lambda n: True)
        matches = [(s, sv, t, tv, note) for s, sv, t, tv, note in matches
                   if filters(s) or filters(t)]

    # 输出
    lines = [
        f"# 宏定义映射表: {args.source} → {args.target}",
        "",
        f"> 自动生成于 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "> 请人工核对后使用",
        "",
        "| 源宏 | 源值 | 目标宏 | 目标值 | 备注 |",
        "|------|------|--------|--------|------|",
    ]

    for s_name, s_val, t_name, t_val, note in matches:
        # 截断过长的值
        s_val = (s_val[:60] + '...') if len(s_val) > 60 else s_val
        t_val = (t_val[:60] + '...') if len(t_val) > 60 else t_val
        lines.append(f"| `{s_name}` | `{s_val}` | `{t_name}` | `{t_val}` | {note} |")

    lines.append("")
    lines.append(f"共 {len(matches)} 条映射")

    output = '\n'.join(lines) + '\n'

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"输出已保存到: {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
