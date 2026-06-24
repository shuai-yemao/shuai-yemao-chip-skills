#!/usr/bin/env python3
"""
移植报告自动生成 + 知识归档脚本。

用法:
    # 交互式生成
    python gen_porting_report.py --interactive

    # 从参数快速生成
    python gen_porting_report.py \\
        --source-chip STM32F103C8 \\
        --target-chip STM32F411CEU6 \\
        --type mcu-port \\
        --output "docs/移植文档/"

    # 生成 + 自动归档到 Obsidian
    python gen_porting_report.py \\
        --source-chip ... --target-chip ... \\
        --output "docs/移植文档/" \\
        --archive-obsidian --project "UART_PRINTF_V1"

    # 生成 + 自动导入知识库
    python gen_porting_report.py \\
        --source-chip ... --target-chip ... \\
        --output "docs/移植文档/" \\
        --import-kb --tags "移植,F1→F4"

    # 从移植记录生成回顾文档
    python gen_porting_report.py --retro --from-dir "docs/移植文档/"
"""

import os
import sys
import json
import argparse
from datetime import datetime


# 尝试映射到用户环境的工具路径
OBSIDIAN_VAULT = "C:/Users/zhang/Documents/Obsidian Vault"
SCRIPTS_DIR = os.path.join(
    os.environ.get('CHERRYSTUDIO_DATA', ''),
    'Skills', 'knowledge-base-search', 'scripts'
)

if not os.path.isdir(SCRIPTS_DIR):
    # fallback: 从 agent 路径找
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'knowledge-base-search', 'scripts'
    )


# ========== 报告生成 ==========

def generate_report(args: argparse.Namespace) -> str:
    """生成移植报告 Markdown 内容"""

    today = datetime.now().strftime('%Y-%m-%d')
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 移植类型映射
    type_map = {
        'mcu-port': 'MCU 换型',
        'hal-migration': 'HAL 层迁移',
        'toolchain': '工具链迁移',
        'rtos': 'RTOS 移植',
        'library': '库移植',
        'module': '模块提取移植',
    }
    port_type = type_map.get(args.type, args.type or '{{移植类型}}')

    lines = [
        f"# 移植报告：{args.source_chip or '{{源平台}}'} → {args.target_chip or '{{目标平台}}'}",
        "",
        f"| 项目 | 内容 |",
        f"|------|------|",
        f"| 移植日期 | {today} |",
        f"| 源平台 | {args.source_chip or '{{芯片/HAL/IDE/RTOS 版本}}'} |",
        f"| 目标平台 | {args.target_chip or '{{芯片/HAL/IDE/RTOS 版本}}'} |",
        f"| 移植类型 | {port_type} |",
        f"| 移植用时 | {{X 小时/X 天}} |",
        f"| 移植结论 | □ 全部功能正常 □ 部分可用（见已知问题）|",
        "",
        "---",
        "",
        "## 1. 逐层修改记录",
        "",
    ]

    # 根据 layers 参数决定是否包含各层
    layers = args.layers or '1,2,3,4,5,6,7'
    active_layers = [int(x.strip()) for x in layers.split(',')]

    layer_templates = {
        1: (
            "### Layer 1：启动文件与链接脚本\n\n"
            "| 修改项 | 源 | 目标 | 说明 |\n"
            "|--------|-----|------|------|\n"
            "| 启动文件 | | | |\n"
            "| 链接脚本 | | | |\n"
            "| 中断向量数 | | | |\n"
            "| Stack_Size | | | |\n"
            "| 特殊初始化 | | | (FPU/Cache/MPU) |\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
        ),
        2: (
            "### Layer 2：时钟树\n\n"
            "| 参数 | 旧值 | 新值 | 差异原因 |\n"
            "|------|------|------|---------|\n"
            "| HSI | | | |\n"
            "| HSE | | | |\n"
            "| PLL M/N/P/Q | | | |\n"
            "| SYSCLK | | | |\n"
            "| AHB | | | |\n"
            "| APB1 | | | |\n"
            "| APB2 | | | |\n"
            "| Flash 等待 | | | |\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
            "**运行时验证**：HAL_GetTick() □正常 □异常\n"
        ),
        3: (
            "### Layer 3：GPIO\n\n"
            "| GPIO 用途 | 源引脚 | 目标引脚 | AF 号 | 时钟使能 | 备注 |\n"
            "|-----------|--------|---------|-------|---------|------|\n"
            "| | | | | | |\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
            "**运行时验证**：LED □正常 □异常\n"
        ),
        4: (
            "### Layer 4：外设驱动\n\n"
            "**DMA**\n\n"
            "| 参数 | 旧值 | 新值 |\n"
            "|------|------|------|\n"
            "| 控制器 | | |\n"
            "| Stream/Channel | | |\n\n"
            "**其他外设**（USART/SPI/I2C/TIM/ADC）：\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
            "**运行时验证**：回环测试 □全部通过 □部分失败\n"
        ),
        5: (
            "### Layer 5：中断\n\n"
            "| 中断 | 源 IRQn | 目标 IRQn | 优先级 |\n"
            "|------|---------|----------|--------|\n"
            "| SysTick | | | |\n"
            "| USART1 | | | |\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
            "**运行时验证**：每个中断触发 □正常 □异常\n"
        ),
        6: (
            "### Layer 6：RTOS\n\n"
            "| 参数 | 旧值 | 新值 |\n"
            "|------|------|------|\n"
            "| configCPU_CLOCK_HZ | | |\n"
            "| configTOTAL_HEAP_SIZE | | |\n\n"
            "**编译验证**：□ 0 Error, 0 Warning\n"
            "**运行时验证**：task 调度 □正常 □HardFault\n"
        ),
        7: (
            "### Layer 7：业务逻辑\n\n"
            "| 功能模块 | 移植前输出 | 移植后输出 | 一致性 |\n"
            "|---------|-----------|-----------|--------|\n"
            "| | | | □一致 □不一致 |\n\n"
            "**测试结果汇总**：\n"
            "| 测试项 | 通过 | 失败 |\n"
            "|--------|------|------|\n"
            "| 编译检查 | ✅ | — |\n"
            "| 功能测试 | | |\n"
            "| 性能基线 | | |\n"
        ),
    }

    for layer_num in range(1, 8):
        if layer_num in active_layers:
            lines.append(layer_templates.get(layer_num, ''))
            lines.append('')

    # 陷阱记录
    lines.extend([
        "## 2. 移植陷阱记录\n",
        "| # | 症状 | 根因 | 修复方案 | 排查耗时 |",
        "|---|------|------|---------|---------|",
        "| 1 | | | | |",
        "| 2 | | | | |",
        "",
    ])

    # 修改文件清单
    lines.extend([
        "## 3. 修改文件清单\n",
        "| 文件 | 修改类型 | 行数变化 | 说明 |",
        "|------|---------|---------|------|",
        "| | 新增/修改/删除 | +N/-M | |",
        "",
    ])

    # 已知问题
    lines.extend([
        "## 4. 已知问题与待办\n",
        "- [ ] P0：",
        "- [ ] P1：",
        "- [ ] P2：",
        "",
        "## 5. Flash/RAM 用量\n",
        "| 项目 | 移植前 | 移植后 | 变化 |",
        "|------|--------|--------|------|",
        "| Flash 占用 | | | |",
        "| RAM 占用 | | | |",
        "",
        "## 6. 下次优化建议\n",
        "- ",
        "",
        "---",
        f"*报告自动生成于 {now}，脚本: gen_porting_report.py*",
        "",
    ])

    return '\n'.join(lines)


def save_report(content: str, output_dir: str, source_chip: str, target_chip: str):
    """保存报告到文件"""
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f"{source_chip or 'SRC'}-{target_chip or 'DST'}-移植-{today}.md"

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[OK] 移植报告已保存: {filepath}")
    return filepath


# ========== 知识归档 ==========

def archive_to_obsidian(report_path: str, project: str, source_chip: str, target_chip: str):
    """将移植概要归档到 Obsidian（通过 record_issue.py）"""
    record_script = os.path.join(SCRIPTS_DIR, 'record_issue.py')

    if not os.path.isfile(record_script):
        print(f"[!] record_issue.py 未找到（预期路径: {record_script}）")
        print(f"[!] 请手动归档: 将 {report_path} 内容复制到 Obsidian 问题记录")
        return False

    title = f"{source_chip}→{target_chip} 移植记录"

    cmd = (
        f'python "{record_script}" new '
        f'--project "{project}" '
        f'--title "{title}" '
        f'--symptom "见移植报告：{report_path}" '
        f'--root-cause "逐层修改见报告" '
        f'--solution "逐层验证见报告" '
        f'--verification "全部 7 层验证"'
    )

    print(f"[...] 归档到 Obsidian...")
    ret = os.system(cmd)
    if ret == 0:
        print(f"[OK] 已归档到 Obsidian: {project} / {title}")
        return True
    else:
        print(f"[X] 归档失败 (exit={ret})，请手动执行: {cmd}")
        return False


def import_to_kb(file_path: str, tags: str):
    """将移植文档导入知识库（通过 import_to_kb.py）"""
    import_script = os.path.join(SCRIPTS_DIR, 'import_to_kb.py')

    if not os.path.isfile(import_script):
        print(f"[!] import_to_kb.py 未找到（预期路径: {import_script}）")
        print(f"[!] 请手动导入: {file_path}")
        return False

    tag_list = tags.split(',') if tags else ['移植']

    cmd = (
        f'python "{import_script}" file '
        f'--file "{file_path}" '
        f'--tags "{",".join(tag_list)}"'
    )

    print(f"[...] 导入知识库 ({tags})...")
    ret = os.system(cmd)
    if ret == 0:
        print(f"[OK] 已导入知识库: tags={tags}")
        return True
    else:
        print(f"[X] 导入失败 (exit={ret})")
        return False


# ========== 交互模式 ==========

def interactive_mode():
    """交互式问答生成报告"""
    print("=" * 50)
    print("移植报告生成器（交互模式）")
    print("=" * 50)

    source = input("源芯片/平台: ").strip()
    target = input("目标芯片/平台: ").strip()
    port_type = input("移植类型 (mcu-port/hal-migration/toolchain/rtos/library/module): ").strip() or 'mcu-port'
    layers = input("涉及层数 (默认 1-7，如 1,2,3,4): ").strip() or '1,2,3,4,5,6,7'
    output = input("输出目录 (默认 docs/移植文档/): ").strip() or 'docs/移植文档/'
    project = input("项目名 (用于 Obsidian 归档): ").strip() or 'default'

    archive = input("归档到 Obsidian? (y/N): ").strip().lower() == 'y'
    import_kb = input("导入知识库? (y/N): ").strip().lower() == 'y'
    tags = input("知识库标签 (逗号分隔, 如 '移植,F1,F4'): ").strip() or '移植'

    args = argparse.Namespace(
        source_chip=source,
        target_chip=target,
        type=port_type,
        layers=layers,
        output=output,
        project=project,
        archive_obsidian=archive,
        import_kb=import_kb,
        tags=tags,
    )

    print("\n生成报告...")
    report = generate_report(args)
    filepath = save_report(report, output, source, target)

    if archive:
        archive_to_obsidian(filepath, project, source, target)

    if import_kb:
        import_to_kb(filepath, tags)

    print(f"\n[OK] 完成！报告位置: {filepath}")
    return filepath


# ========== 回顾模式 ==========

def generate_retro(from_dir: str):
    """从已有移植文档生成回顾总结"""
    import glob

    if not os.path.isdir(from_dir):
        print(f"[X] 目录不存在: {from_dir}")
        return

    retro = []
    reports = sorted(glob.glob(os.path.join(from_dir, '**', '*移植*.md'), recursive=True))

    if not reports:
        print(f"[!] 在 {from_dir} 中未找到移植文档")
        return

    today = datetime.now().strftime('%Y-%m-%d')
    lines = [
        f"# 移植回顾总结 ({today})",
        "",
        f"基于 {len(reports)} 次移植记录",
        "",
        "| # | 报告 | 源→目标 | 类型 | 陷阱数 |",
        "|---|------|---------|------|--------|",
    ]

    for i, rp in enumerate(reports, 1):
        name = os.path.basename(rp)
        # 尝试从文件名推断源和目标
        parts = name.replace('移植', '').split('-')
        src = parts[0] if len(parts) > 0 else '?'
        dst = parts[1] if len(parts) > 1 else '?'
        lines.append(f"| {i} | {name} | {src}→{dst} | | |")

    lines.extend([
        "",
        "## 高频陷阱统计",
        "",
        "| 陷阱 | 出现次数 | 涉及移植 |",
        "|------|---------|---------|",
        "",
        "## 流程改进建议",
        "",
        "- ",
    ])

    output_path = os.path.join(from_dir, f"移植回顾总结-{today}.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"[OK] 回顾总结已保存: {output_path}")


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(description='移植报告生成与归档工具')

    # 生成模式
    parser.add_argument('--source-chip', help='源芯片型号')
    parser.add_argument('--target-chip', help='目标芯片型号')
    parser.add_argument('--type', choices=['mcu-port', 'hal-migration', 'toolchain', 'rtos', 'library', 'module'],
                        default='mcu-port', help='移植类型')
    parser.add_argument('--layers', default='1,2,3,4,5,6,7', help='涉及层数 (逗号分隔)')
    parser.add_argument('--output', default='docs/移植文档/', help='输出目录')

    # 归档选项
    parser.add_argument('--archive-obsidian', action='store_true', help='归档到 Obsidian')
    parser.add_argument('--project', default='default', help='项目名 (Obsidian 归档用)')
    parser.add_argument('--import-kb', action='store_true', help='导入知识库')
    parser.add_argument('--tags', default='移植', help='知识库标签 (逗号分隔)')

    # 交互/回顾模式
    parser.add_argument('--interactive', action='store_true', help='交互模式')
    parser.add_argument('--retro', action='store_true', help='回顾模式')
    parser.add_argument('--from-dir', help='回顾模式的源目录')

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.retro:
        generate_retro(args.from_dir or args.output or 'docs/移植文档/')
    else:
        if not args.source_chip and not args.target_chip:
            print("[!] 请指定 --source-chip 和 --target-chip，或使用 --interactive 交互模式")
            parser.print_help()
            sys.exit(1)

        report = generate_report(args)
        filepath = save_report(report, args.output, args.source_chip, args.target_chip)

        if args.archive_obsidian:
            archive_to_obsidian(filepath, args.project, args.source_chip, args.target_chip)

        if args.import_kb:
            import_to_kb(filepath, args.tags)


if __name__ == '__main__':
    main()
