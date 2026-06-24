#!/usr/bin/env python3
"""
链接脚本差异分析工具。

对比两个链接脚本（.ld / .sct / .icf）的 SECTION 布局、
内存区域定义、堆栈大小等关键差异。

用法:
    python diff_ld.py --old STM32F1.ld --new STM32F4.ld
    python diff_ld.py --old STM32F103.sct --new STM32F411.sct
"""

import re
import sys
import argparse


def parse_memory_regions(content: str) -> dict:
    """解析 MEMORY 块（GCC .ld 格式）"""
    regions = {}

    # GCC .ld: MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 1M }
    mem_pattern = re.compile(
        r'(\w+)\s*\([^)]*\)\s*:\s*ORIGIN\s*=\s*(0x[0-9A-Fa-f]+)\s*,\s*LENGTH\s*=\s*(\d+[KMG]?)',
        re.IGNORECASE
    )

    for m in mem_pattern.finditer(content):
        regions[m.group(1)] = {
            'origin': m.group(2),
            'length': m.group(3)
        }

    return regions


def parse_sct_regions(content: str) -> dict:
    """解析 ARMCC .sct 分散加载文件"""
    regions = {}

    # ARMCC: LR_IROM1 0x08000000 0x00100000
    sct_pattern = re.compile(
        r'(LR_\w+|RW_\w+)\s+(0x[0-9A-Fa-f]+)\s+(0x[0-9A-Fa-f]+)',
        re.IGNORECASE
    )

    for m in sct_pattern.finditer(content):
        regions[m.group(1)] = {
            'origin': m.group(2),
            'length': str(int(m.group(3), 16) // 1024) + 'K' if int(m.group(3), 16) % (1024 * 1024) != 0 else str(int(m.group(3), 16) // (1024 * 1024)) + 'M'
        }

    return regions


def parse_icf_regions(content: str) -> dict:
    """解析 IAR .icf 文件"""
    regions = {}

    # IAR: define symbol __ICFEDIT_region_ROM_start__ = 0x08000000;
    icf_pattern = re.compile(
        r'define\s+symbol\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+[KMG]?)',
        re.IGNORECASE
    )

    for m in icf_pattern.finditer(content):
        name = m.group(1)
        value = m.group(2)
        if 'start' in name.lower():
            region_name = name.replace('__ICFEDIT_region_', '').replace('_start__', '').replace('_start', '')
            if region_name not in regions:
                regions[region_name] = {}
            regions[region_name]['origin'] = value
        elif 'end' in name.lower():
            region_name = name.replace('__ICFEDIT_region_', '').replace('_end__', '').replace('_end', '')
            if region_name not in regions:
                regions[region_name] = {}
            regions[region_name]['end'] = value
        elif 'size' in name.lower():
            if 'heap' in name.lower():
                regions['HEAP_SIZE'] = value
            elif 'cstack' in name.lower() or 'stack' in name.lower():
                regions['STACK_SIZE'] = value

    return regions


def parse_sections(content: str) -> list:
    """解析 SECTION 定义顺序"""
    sections = []

    # GCC .ld SECTIONS 块
    in_sections = False
    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.startswith('SECTIONS'):
            in_sections = True
            continue

        if in_sections and stripped == '}':
            break

        if in_sections:
            # .isr_vector : { ... }
            m = re.match(r'\.(\w[\w.-]*)\s*:', stripped)
            if m:
                sections.append(m.group(1))

    return sections


def main():
    parser = argparse.ArgumentParser(description='链接脚本差异对比')
    parser.add_argument('--old', required=True, help='旧链接脚本')
    parser.add_argument('--new', required=True, help='新链接脚本')
    parser.add_argument('--output', help='输出 Markdown 文件')
    args = parser.parse_args()

    # 读取文件
    try:
        with open(args.old, 'r', encoding='utf-8', errors='ignore') as f:
            old_content = f.read()
    except FileNotFoundError:
        print(f"错误: 文件 {args.old} 不存在")
        sys.exit(1)

    try:
        with open(args.new, 'r', encoding='utf-8', errors='ignore') as f:
            new_content = f.read()
    except FileNotFoundError:
        print(f"错误: 文件 {args.new} 不存在")
        sys.exit(1)

    # 检测格式
    ext_old = args.old.split('.')[-1].lower()
    ext_new = args.new.split('.')[-1].lower()

    # 解析内存区域
    old_regions = {}
    new_regions = {}

    for ext, content, regions in [
        (ext_old, old_content, old_regions),
        (ext_new, new_content, new_regions)
    ]:
        if ext == 'ld':
            regions.update(parse_memory_regions(content))
        elif ext == 'sct':
            regions.update(parse_sct_regions(content))
        elif ext == 'icf':
            regions.update(parse_icf_regions(content))

    # 解析 SECTION 顺序
    old_sections = parse_sections(old_content)
    new_sections = parse_sections(new_content)

    # 输出
    lines = [
        f"# 链接脚本差异: {args.old} → {args.new}",
        "",
        f"| 项目 | 旧脚本 | 新脚本 |",
        f"|------|--------|--------|",
    ]

    # 内存区域对比
    if old_regions or new_regions:
        lines.append("")
        lines.append("## 内存区域定义")
        lines.append("")
        lines.append("| 区域 | 旧起始地址 | 旧大小 | 新起始地址 | 新大小 | 差异 |")
        lines.append("|------|-----------|--------|-----------|--------|------|")

        all_region_names = set(old_regions.keys()) | set(new_regions.keys())
        for name in sorted(all_region_names):
            old_r = old_regions.get(name, {})
            new_r = new_regions.get(name, {})
            old_origin = old_r.get('origin', '—')
            old_len = old_r.get('length', '—')
            new_origin = new_r.get('origin', '—')
            new_len = new_r.get('length', '—')
            diff = '✓' if old_origin == new_origin and old_len == new_len else '⚡'
            lines.append(f"| {name} | {old_origin} | {old_len} | {new_origin} | {new_len} | {diff} |")

    # SECTION 顺序对比
    if old_sections or new_sections:
        lines.append("")
        lines.append("## SECTION 顺序")
        lines.append("")
        lines.append("| 序号 | 旧 Section | 新 Section | 状态 |")
        lines.append("|------|-----------|-----------|------|")

        old_set = set(old_sections)
        new_set = set(new_sections)
        all_sections = []
        max_len = max(len(old_sections), len(new_sections))
        for i in range(max_len):
            old_s = old_sections[i] if i < len(old_sections) else ''
            new_s = new_sections[i] if i < len(new_sections) else ''
            if old_s == new_s:
                status = '✓'
            elif old_s and new_s:
                status = '⚡'
            elif old_s and not new_s:
                status = '✗ 删除'
            else:
                status = '+ 新增'
            lines.append(f"| {i} | {old_s} | {new_s} | {status} |")

        added_secs = new_set - old_set
        removed_secs = old_set - new_set
        if added_secs:
            lines.append(f"\n**新增 Section**: {', '.join(sorted(added_secs))}")
        if removed_secs:
            lines.append(f"\n**删除 Section**: {', '.join(sorted(removed_secs))}")

    output = '\n'.join(lines) + '\n'
    print(output)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"输出已保存到: {args.output}")


if __name__ == '__main__':
    main()
