#!/usr/bin/env python3
"""
中断向量表差异对比工具。

对比两个 startup_xxx.s（或 .s）文件的向量表，
输出新增/删除/顺序变化的向量。

用法:
    python cmp_vectors.py --old startup_stm32f1xx.s --new startup_stm32f4xx.s
    python cmp_vectors.py --old startup_stm32f103xb.s --new startup_stm32f411xe.s --output diff.md
"""

import re
import sys
import argparse


def parse_vector_table(filepath: str) -> list:
    """
    从汇编 startup 文件解析向量表。

    支持的语法格式：
    - ARMCC/DCD:  DCD     WWDG_IRQHandler
    - GCC/.word:  .word   WWDG_IRQHandler
    - IAR/DC32:   DC32    WWDG_IRQHandler
    - 含数字:     DCD     WWDG_IRQHandler  ; Window Watchdog

    返回 [(index, name), ...] 列表
    """
    vectors = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"错误: 文件 {filepath} 不存在")
        sys.exit(1)

    vector_patterns = [
        # DCD name  (ARMCC)
        r'^\s+DCD\s+(\w+(?:Handler|_IRQHandler)?)\b',
        # .word name (GCC)
        r'^\s+\.word\s+(\w+(?:Handler|_IRQHandler)?)\b',
        # DC32 name (IAR)
        r'^\s+DC32\s+(\w+(?:Handler|_IRQHandler)?)\b',
    ]

    # 展开所有模式
    patterns = []
    for p in vector_patterns:
        patterns.append(re.compile(p, re.IGNORECASE))

    # 还需要匹配可能带前缀的: 如 __Vectors_End, __Vectors_Size
    skip_names = {
        '__Vectors_End', '__Vectors_Size',
        '__initial_sp', '_estack',
        'Stack_Size', 'Heap_Size',
    }

    idx = 0
    in_vector_section = False

    for line in lines:
        stripped = line.strip()

        # 检测向量表开始
        if 'Vectors' in stripped and ('DCD' in stripped or '.word' in stripped or 'DC32' in stripped):
            in_vector_section = True

        # 检测向量表结束
        if in_vector_section and ('__Vectors_End' in stripped or '__initial_sp' in stripped):
            if '__Vectors_End' in stripped:
                break
            continue

        if not in_vector_section:
            continue

        # 跳过注释行
        if stripped.startswith(';') or stripped.startswith('//') or stripped.startswith('#'):
            continue

        name = None
        for pat in patterns:
            m = pat.search(stripped)
            if m:
                candidate = m.group(1)
                if candidate not in skip_names and len(candidate) > 2:
                    name = candidate
                break

        if name:
            vectors.append((idx, name))
            idx += 1

    return vectors


def main():
    parser = argparse.ArgumentParser(description='对比两个启动文件的向量表')
    parser.add_argument('--old', required=True, help='源芯片启动文件')
    parser.add_argument('--new', required=True, help='目标芯片启动文件')
    parser.add_argument('--output', help='输出 Markdown 文件')
    args = parser.parse_args()

    old_name = args.old.replace('.s', '').replace('startup_', '')
    new_name = args.new.replace('.s', '').replace('startup_', '')

    old_vectors = parse_vector_table(args.old)
    new_vectors = parse_vector_table(args.new)

    print(f"源芯片 ({old_name}): {len(old_vectors)} 个向量")
    print(f"目标芯片 ({new_name}): {len(new_vectors)} 个向量")
    print()

    # 建立名字索引
    old_map = {name: idx for idx, name in old_vectors}
    new_map = {name: idx for idx, name in new_vectors}

    old_names = set(old_map.keys())
    new_names = set(new_map.keys())

    # 新增的向量
    added = new_names - old_names
    # 删除的向量
    removed = old_names - new_names
    # 共同的向量
    common = old_names & new_names

    # 序号变化的向量
    reordered = []
    for name in sorted(common):
        if old_map[name] != new_map[name]:
            reordered.append((name, old_map[name], new_map[name]))

    # 输出
    lines = [
        f"# 中断向量表差异: {old_name} → {new_name}",
        "",
        f"| 统计 | 数量 |",
        f"|------|------|",
        f"| 源芯片向量数 | {len(old_vectors)} |",
        f"| 目标芯片向量数 | {len(new_vectors)} |",
        f"| 新增 | {len(added)} |",
        f"| 删除 | {len(removed)} |",
        f"| 序号变化 | {len(reordered)} |",
        "",
    ]

    if added:
        lines.append("## 新增的中断向量")
        lines.append("")
        lines.append("| 中断号 | 名称 |")
        lines.append("|--------|------|")
        for idx, name in new_vectors:
            if name in added:
                lines.append(f"| {idx} | {name} |")
        lines.append("")

    if removed:
        lines.append("## 已删除的中断向量")
        lines.append("")
        lines.append("| 中断号 | 名称 |")
        lines.append("|--------|------|")
        for idx, name in old_vectors:
            if name in removed:
                lines.append(f"| {idx} | {name} |")
        lines.append("")

    if reordered:
        lines.append("## 序号变化的中断向量")
        lines.append("")
        lines.append("| 名称 | 旧序号 | 新序号 | 偏移 |")
        lines.append("|------|--------|--------|------|")
        for name, old_idx, new_idx in sorted(reordered, key=lambda x: x[1]):
            delta = new_idx - old_idx
            lines.append(f"| {name} | {old_idx} | {new_idx} | {'+' if delta >= 0 else ''}{delta} |")
        lines.append("")

    lines.append(f"*共 {len(added)} 新增, {len(removed)} 删除, {len(reordered)} 序号变更*")
    lines.append("")

    output = '\n'.join(lines) + '\n'
    print(output)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"输出已保存到: {args.output}")


if __name__ == '__main__':
    main()
