#!/usr/bin/env python3
"""
docgen_porting.py — 移植指南自动生成（P3）
============================================
对比两组 C 头文件接口，生成接口映射表和移植备忘录。

功能:
  - diff:      对比新旧头文件，生成接口变更报告
  - guide:     生成 Markdown 移植指南文档
  - map:       输出 JSON 格式的接口映射表

用法:
  python docgen_porting.py diff <old.h> <new.h> [-o report.md]
  python docgen_porting.py map  <old.h> <new.h> [-o mapping.json]
  python docgen_porting.py guide <old.h> <new.h> [-o porting-guide.md]

场景:
  - MCU 换型（F1 → F4/F7/G4）
  - HAL → LL 迁移
  - 库版本升级
  - 跨平台移植
"""

import io, json, os, re, sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── API 提取 ──

# 函数声明
FUNC_PATTERN = re.compile(
    r'(?:static\s+)?(?:inline\s+)?(?:extern\s+)?'
    r'\w+(?:\s*\*)?\s+(\w+)\s*\(([^)]*?)\)\s*;(?!\s*\{)',
    re.MULTILINE,
)

# 宏定义
MACRO_PATTERN = re.compile(r'^#\s*define\s+(\w+)\s+(.*)', re.MULTILINE)

# 类型定义
TYPEDEF_PATTERN = re.compile(
    r'typedef\s+(?:enum|struct|union)\s+\w*\s*\{[^}]*\}\s*(\w+);',
    re.DOTALL,
)

# 全局包含
INCLUDE_PATTERN = re.compile(r'#\s*include\s+["<]([^">]+)[">]')


def extract_apis(file_path: str) -> dict:
    """提取头文件中的 API 信息"""
    content = Path(file_path).read_text(encoding='utf-8', errors='replace')
    return {
        'file': file_path,
        'functions': [
            {
                'name': m.group(1),
                'params': m.group(2).strip(),
            }
            for m in FUNC_PATTERN.finditer(content)
            if not m.group(1).startswith('HAL_') or 'Callback' not in m.group(1)
        ],
        'macros': [
            {'name': m.group(1), 'value': m.group(2).strip()}
            for m in MACRO_PATTERN.finditer(content)
        ],
        'typedefs': [
            m.group(1) for m in TYPEDEF_PATTERN.finditer(content)
        ],
        'includes': list(set(
            m.group(1) for m in INCLUDE_PATTERN.finditer(content)
        )),
    }


# ── 差异分析 ──


def diff_apis(old_api: dict, new_api: dict) -> dict:
    """对比两组 API，生成变更报告"""
    old_funcs = {f['name']: f for f in old_api.get('functions', [])}
    new_funcs = {f['name']: f for f in new_api.get('functions', [])}

    old_names = set(old_funcs.keys())
    new_names = set(new_funcs.keys())

    # 精确匹配
    unchanged = old_names & new_names
    removed = old_names - new_names
    added = new_names - old_names

    # 参数变更检测（同名函数参数不同）
    param_changed = []
    for name in sorted(unchanged):
        old_params = old_funcs[name]['params']
        new_params = new_funcs[name]['params']
        if old_params != new_params:
            param_changed.append({
                'name': name,
                'old_params': old_params,
                'new_params': new_params,
            })

    # 宏对比
    old_macros = {m['name']: m for m in old_api.get('macros', [])}
    new_macros = {m['name']: m for m in new_api.get('macros', [])}
    old_macro_names = set(old_macros.keys())
    new_macro_names = set(new_macros.keys())

    return {
        'summary': {
            'total_old': len(old_funcs),
            'total_new': len(new_funcs),
            'unchanged': len(unchanged - {c['name'] for c in param_changed}),
            'param_changed': len(param_changed),
            'removed': len(removed),
            'added': len(added),
        },
        'functions': {
            'unchanged': sorted(unchanged - {c['name'] for c in param_changed}),
            'param_changed': param_changed,
            'removed': sorted(removed),
            'added': sorted(added),
        },
        'macros': {
            'removed': sorted(old_macro_names - new_macro_names),
            'added': sorted(new_macro_names - old_macro_names),
        },
        'typedefs': {
            'removed': sorted(set(old_api.get('typedefs', [])) - set(new_api.get('typedefs', []))),
            'added': sorted(set(new_api.get('typedefs', [])) - set(old_api.get('typedefs', []))),
        },
    }


# ── 生成报告 ──


def generate_diff_report(diff: dict, old_file: str, new_file: str) -> str:
    """生成 Markdown 差异报告"""
    s = diff['summary']
    lines = [
        f"# 接口变更分析报告",
        "",
        f"- **源文件**: `{old_file}`",
        f"- **目标文件**: `{new_file}`",
        "",
        "## 统计摘要",
        "",
        f"| 指标 | 数量 |",
        f"|------|------|",
        f"| 源接口数 | {s['total_old']} |",
        f"| 目标接口数 | {s['total_new']} |",
        f"| 未变更 | {s['unchanged']} |",
        f"| 参数变更 | {s['param_changed']} |",
        f"| 已移除 | {s['removed']} |",
        f"| 新增 | {s['added']} |",
        "",
    ]

    if diff['functions']['param_changed']:
        lines += ["## 参数变更函数", "", "| 函数名 | 旧参数 | 新参数 |", "|--------|--------|--------|"]
        for f in diff['functions']['param_changed']:
            lines.append(f"| `{f['name']}` | `{f['old_params']}` | `{f['new_params']}` |")
        lines.append("")

    if diff['functions']['removed']:
        lines += ["## 已移除函数", "", "以下函数在目标接口中不存在，需要替换实现：", ""]
        for name in diff['functions']['removed']:
            lines.append(f"- `{name}`")
        lines.append("")

    if diff['functions']['added']:
        lines += ["## 新增函数", "", "以下函数在目标接口中新增：", ""]
        for name in diff['functions']['added']:
            lines.append(f"- `{name}`")
        lines.append("")

    return '\n'.join(lines)


def generate_porting_guide(diff: dict, old_file: str, new_file: str) -> str:
    """生成完整移植指南"""
    lines = [
        f"# 移植指南",
        "",
        f"## 概述",
        f"",
        f"- **源平台**: `{Path(old_file).stem}`",
        f"- **目标平台**: `{Path(new_file).stem}`",
        f"- **接口变更率**: {diff['summary']['unchanged']}/{diff['summary']['total_old']} 未变更 "
        f"({diff['summary']['unchanged']/max(diff['summary']['total_old'],1)*100:.0f}%)",
        "",
        "## 前置条件",
        "",
        "1. 确认目标 MCU 的外设资源（Flash/RAM/外设数量）满足需求",
        "2. 检查目标 MCU 的 CMSIS 版本和 HAL 库版本",
        "3. 准备目标平台的工程模板（Keil / CubeIDE / CMake）",
        "4. 确认调试探针和目标平台的连接",
        "",
    ]

    # 接口映射表
    lines += [
        "## 接口映射表",
        "",
        "| 序号 | 源接口 | 目标接口 | 变更类型 | 移植动作 |",
        "|------|--------|----------|----------|----------|",
    ]

    idx = 1
    for name in diff['functions']['unchanged']:
        lines.append(f"| {idx} | `{name}` | `{name}` | 未变更 | 直接迁移 |")
        idx += 1

    for f in diff['functions']['param_changed']:
        lines.append(f"| {idx} | `{f['name']}` | `{f['name']}` | 参数变更 | 调整调用参数 |")
        idx += 1

    for name in diff['functions']['removed']:
        lines.append(f"| {idx} | `{name}` | — | 已移除 | 需替代实现 |")
        idx += 1

    for name in diff['functions']['added']:
        lines.append(f"| {idx} | — | `{name}` | 新增 | 按需适配 |")
        idx += 1

    lines.append("")

    # 移植注意事项
    lines += [
        "## 关键注意事项",
        "",
        "### 1. 启动文件",
        "- 替换为对应 MCU 的 startup_*.s 文件",
        "- 更新中断向量表（不同系列中断号可能不同）",
        "",
        "### 2. 时钟配置",
        "- 检查 HSI/HSE 频率是否一致",
        "- 更新 PLL 配置参数（输入频率/倍频系数）",
        "- 确认 AHB/APB1/APB2 时钟分频",
        "",
        "### 3. 外设驱动",
        "- HAL 库版本差异可能导致 API 签名变化",
        "- 检查 DMA 流/通道号映射",
        "- 检查 TIM 定时器编号和中断号",
        "- 检查 ADC 通道号和采样时间配置",
        "",
        "### 4. GPIO 引脚",
        "- 不同系列 GPIO 寄存器布局可能不同",
        "- 检查 AFIO 时钟使能（F1 系列特有）",
        "- 引脚重映射配置可能不同",
        "",
        "### 5. 链接脚本",
        "- 更新 Flash/RAM 起始地址和大小",
        "- 检查 Section 区域划分",
        "",
        "---",
        "",
        "*本指南由 docgen_porting.py 自动生成，请根据实际情况验证和补充。*",
    ]

    return '\n'.join(lines)


# ── CLI ──


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 4:
        print_usage()
        return 1

    cmd = sys.argv[1]
    old_file = sys.argv[2]
    new_file = sys.argv[3]

    output = None
    if '-o' in sys.argv:
        idx = sys.argv.index('-o')
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    old_api = extract_apis(old_file)
    new_api = extract_apis(new_file)
    diff = diff_apis(old_api, new_api)

    if cmd == 'diff':
        report = generate_diff_report(diff, old_file, new_file)
    elif cmd == 'guide':
        report = generate_porting_guide(diff, old_file, new_file)
    elif cmd == 'map':
        report = json.dumps({
            'old_file': old_file,
            'new_file': new_file,
            'diff': diff,
        }, ensure_ascii=False, indent=2)
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1

    s = diff['summary']
    if output:
        Path(output).write_text(report, encoding='utf-8')
        print(f"[OK] 移植指南已生成: {output}")
        print(f"     未变更 {s['unchanged']}, 参数变更 {s['param_changed']}, "
              f"移除 {s['removed']}, 新增 {s['added']}")
    else:
        print(report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
