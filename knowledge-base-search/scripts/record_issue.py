#!/usr/bin/env python3
"""
问题记录工具 — 按「嵌入式系统诊断流程模板」归档到 Obsidian Vault。

功能：
  new      — 从模板创建新的问题记录
  append   — 向已有记录追加实验结果
  summary  — 查看某项目下所有问题记录概览
  search   — 按关键词搜索问题记录

用法:
  python record_issue.py new \
      --project "STM32F103-UART" \
      --title "串口发送首字节丢失" \
      --symptom "上电后首次发送'H'丢失" \
      --mcu "STM32F103C8T6"

  python record_issue.py append \
      --file "2026-05-03-串口发送首字节丢失.md" \
      --result "清除TC位后发送正常"

  python record_issue.py summary --project "STM32F103-UART"

  python record_issue.py search "DMA 双缓冲 bug"

环境变量:
  OBSIDIAN_VAULT_PATH: Obsidian vault 根目录
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse
import json
import re
import hashlib

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

TEMPLATE_PATH = "领域/嵌入式/嵌入式项目文档/嵌入式系统诊断流程模板.md"
ISSUE_OUTPUT_DIR = "领域/嵌入式/嵌入式项目文档/问题记录"

# 初步 checklist 项（来自模板）
CHECKLIST_ITEMS = [
    ("0", "排除硬件问题：跑已知正常固件验证硬件"),
    ("1", "程序爆栈：调整启动文件栈大小或 RTOS 任务栈"),
    ("2", "过度优化：降低优化等级至 -O0"),
    ("3", "死循环/HardFault：调试模式暂停查看 PC/LR，栈回溯"),
    ("4", "执行错误：打印每个相关函数的返回值"),
    ("5", "空指针：打断点检查指针是否为 0x00000000"),
    ("6", "API 用错：RTOS 用原生 API 而非 CMSIS wrapper"),
    ("7", "未执行到：关键分支放 printf 标记"),
    ("8", "线程饿死：加 vTaskDelay(100)"),
    ("9", "无 while(1)：检查线程是否有死循环"),
    ("10", "死锁：依次关闭互斥量/信号量排查"),
    ("11", "局部变量未赋初值"),
]


def get_vault_path() -> Optional[Path]:
    """获取 Obsidian vault 路径"""
    env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env_path:
        return Path(env_path)

    # 方法1: 调用 kb_search 的发现逻辑
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from kb_search import _find_obsidian_vaults
        vaults = _find_obsidian_vaults()
        if vaults:
            return Path(vaults[0][1])
    except Exception:
        pass

    # 方法2: 逐个扫描常见目录
    candidates = [
        os.path.expandvars(r"%USERPROFILE%\Documents\Obsidian Vault"),
        os.path.expandvars(r"%USERPROFILE%\Documents\Obsidian"),
        os.path.expandvars(r"%USERPROFILE%\Documents\Vault"),
        os.path.expandvars(r"%USERPROFILE%\Obsidian"),
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Obsidian"),
        os.path.expanduser("~/Documents/Obsidian Vault"),
        os.path.expanduser("~/Documents/Obsidian"),
        os.path.expanduser("~/Obsidian"),
    ]
    for cand in candidates:
        try:
            p = Path(cand)
            if not p.is_dir():
                continue
            if (p / ".obsidian").is_dir():
                return p
        except Exception:
            continue

    # 方法3: Documents 下自动搜索 .obsidian 目录
    for docs_name in ["Documents", "文档"]:
        docs = os.path.expandvars(f"%USERPROFILE%\\{docs_name}")
        try:
            for sub in Path(docs).iterdir():
                if sub.is_dir() and (sub / ".obsidian").is_dir():
                    return sub
        except Exception:
            continue

    return None


def get_output_dir(vault: Path, project: str) -> Path:
    """获取输出的目录，自动创建"""
    out = vault / ISSUE_OUTPUT_DIR / project
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate_filename(title: str, created_at: Optional[datetime] = None) -> str:
    """生成文件名：日期-标题.md"""
    dt = created_at or datetime.now()
    date_str = dt.strftime("%Y-%m-%d")
    # 安全文件名：去掉特殊字符
    safe_title = re.sub(r'[\\/:*?"<>|]', '-', title)
    safe_title = safe_title.strip()[:80]
    return f"{date_str}-{safe_title}.md"


# ═══════════════════════════════════════════════════════════════
# 模板渲染
# ═══════════════════════════════════════════════════════════════

def render_template(
    title: str,
    project: str,
    mcu: str = "",
    symptom: str = "",
    repro_steps: str = "",
    expected: str = "",
    checklist_checked: list[str] = None,
    hypothesis: str = "",
    experiment_plan: str = "",
    created_at: Optional[datetime] = None,
) -> str:
    """从模板渲染 Markdown 内容"""

    dt = created_at or datetime.now()

    # 构建 checklist（标出已检查项和未检查项）
    checklist_lines = []
    checked_set = set(checklist_checked or [])
    for num, desc in CHECKLIST_ITEMS:
        marker = "[✓]" if num in checked_set else "[ ]"
        checklist_lines.append(f"- {marker} {num}. {desc}")

    content = f"""# 项目: {project} | 问题: {title}

> 创建时间: {dt.strftime('%Y-%m-%d %H:%M')}
> MCU: {mcu or '待补充'}

# 一、问题的描述

## 1. 问题的表现是怎样的？

{symptom or '(待补充：截图/录屏/复现文档)'}

## 2. 问题的复现路径

{repro_steps or '1. (待补充：工程文件 + 复现细节)'}

## 3. 正常的预期是什么？

{expected or '(待补充)'}

# 二、问题产生的可能原因分析

## 1. 初步 checklist 确认

{chr(10).join(checklist_lines)}

## 2. 提出可能的假设

{hypothesis or '(待补充：假设列表)'}

# 三、设计实验，验证可能的原因和猜想

{experiment_plan or '## 实验 1\n\n(待设计)' if experiment_plan else ''}

# 四、验证实验

> 实验记录将在后续通过 `record_issue.py append` 追加到此区域。
"""
    return content


# ═══════════════════════════════════════════════════════════════
# 命令: new — 创建新问题记录
# ═══════════════════════════════════════════════════════════════

def _unescape_newlines(text: str) -> str:
    """将字面量 \\n 转为实际换行"""
    return text.replace("\\n", "\n")


def cmd_new(args):
    vault = get_vault_path()
    if not vault:
        print("错误: 未找到 Obsidian vault。请设置 OBSIDIAN_VAULT_PATH 环境变量。",
              file=sys.stderr)
        sys.exit(1)

    output_dir = get_output_dir(vault, args.project)
    filename = generate_filename(args.title)
    filepath = output_dir / filename

    if filepath.exists() and not args.force:
        print(f"文件已存在: {filepath}")
        print("使用 --force 覆盖，或使用 append 命令追加内容。")
        sys.exit(1)

    content = render_template(
        title=args.title,
        project=args.project,
        mcu=args.mcu,
        symptom=_unescape_newlines(args.symptom),
        repro_steps=_unescape_newlines(args.repro),
        expected=_unescape_newlines(args.expected),
        checklist_checked=args.checklist.split(",") if args.checklist else [],
        hypothesis=_unescape_newlines(args.hypothesis),
        experiment_plan=_unescape_newlines(args.experiment),
    )

    filepath.write_text(content, encoding="utf-8")

    # 相对路径便于在 Obsidian 中定位
    rel_path = filepath.relative_to(vault)
    print(f"✓ 问题记录已创建: {rel_path}")
    print(f"  绝对路径: {filepath}")
    print(f"\n后续操作:")
    print(f"  追加实验结果:  python record_issue.py append --file \"{rel_path}\" --result \"...\"")
    return rel_path


# ═══════════════════════════════════════════════════════════════
# 命令: append — 追加实验结果到已有记录
# ═══════════════════════════════════════════════════════════════

def _find_next_experiment_num(content: str) -> int:
    """找到文件中已有实验编号的最大值+1"""
    matches = re.findall(r'## 第(\d+)次实验', content)
    if not matches:
        return 1
    return max(int(m) for m in matches) + 1


def cmd_append(args):
    vault = get_vault_path()
    if not vault:
        print("错误: 未找到 Obsidian vault。", file=sys.stderr)
        sys.exit(1)

    # 支持相对路径和绝对路径
    filepath = Path(args.file)
    if not filepath.is_absolute():
        filepath = vault / filepath

    if not filepath.exists():
        # 尝试在问题记录目录下搜索
        issue_dir = vault / ISSUE_OUTPUT_DIR
        matches = list(issue_dir.rglob(f"*{args.file}*"))
        if len(matches) == 1:
            filepath = matches[0]
        elif len(matches) > 1:
            print("找到多个匹配文件:")
            for m in matches:
                print(f"  {m.relative_to(vault)}")
            print("请用完整相对路径指定 --file")
            sys.exit(1)
        else:
            print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
            sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    exp_num = _find_next_experiment_num(content)
    dt = datetime.now()

    append_block = f"""

## 第{exp_num}次实验

### 1. 实验时间

{_unescape_newlines(args.time) or dt.strftime('%Y-%m-%d %H:%M')}

### 2. 实验环境

#### 1. 本次测试环境

{_unescape_newlines(args.env) or '- MCU: (待补充)\n- 固件版本: (待补充)\n- 电源: (待补充)'}

#### 2. 相关文档

{_unescape_newlines(args.refs) or '(待补充)'}

#### 3. 实验步骤

{_unescape_newlines(args.steps) or '(待补充)'}

#### 4. 实验结果

##### 4.1 输出结果

{_unescape_newlines(args.result) or '(待补充)'}

##### 4.2 实验分析

{_unescape_newlines(args.analysis) or f'1. 与前次实验步骤对比: (待补充)\n2. 与前次实验结果对比: (待补充)'}
{f'\n\n**状态: ✓ 问题已解决**' if args.resolved else f'\n\n**状态: ✗ 问题未解决**' if args.resolved is False else ''}
"""

    filepath.write_text(content + append_block, encoding="utf-8")
    rel = filepath.relative_to(vault)
    print(f"✓ 第 {exp_num} 次实验结果追加到: {rel}")

    if args.resolved:
        print("  🎉 问题已解决！")


# ═══════════════════════════════════════════════════════════════
# 命令: summary — 项目问题记录概览
# ═══════════════════════════════════════════════════════════════

def cmd_summary(args):
    vault = get_vault_path()
    if not vault:
        print("错误: 未找到 Obsidian vault。", file=sys.stderr)
        sys.exit(1)

    issue_dir = vault / ISSUE_OUTPUT_DIR
    if args.project:
        search_dir = issue_dir / args.project
    else:
        search_dir = issue_dir

    if not search_dir.exists():
        print(f"目录不存在: {search_dir.relative_to(vault)}")
        return

    md_files = sorted(search_dir.rglob("*.md"), reverse=True)
    if not md_files:
        print("(无问题记录)")
        return

    print(f"{'文件':50s}  {'大小':>8s}  {'状态':8s}  {'实验次数':>8s}")
    print("-" * 85)

    total_issues = 0
    resolved = 0
    for f in md_files:
        if f.name.endswith("模板.md") or f.name == TEMPLATE_PATH.split("/")[-1]:
            continue
        total_issues += 1
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        size = f.stat().st_size
        size_str = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"

        # 解析状态
        exp_count = len(re.findall(r'## 第(\d+)次实验', content))
        is_resolved = "✓ 已解决" in content or "已解决" in content.split("# 四、验证实验")[-1] if "# 四" in content else False
        if is_resolved:
            resolved += 1
            status = "✓ 已解决"
        elif exp_count > 0:
            status = "⚙ 实验中"
        else:
            status = "○ 新建"

        rel = f.relative_to(issue_dir)
        print(f"  {str(rel):48s}  {size_str:>8s}  {status:8s}  {exp_count:>8d}")

    print("-" * 85)
    print(f"总计: {total_issues} 个问题, {resolved} 已解决, "
          f"{total_issues - resolved} 待解决")


# ═══════════════════════════════════════════════════════════════
# 命令: search — 搜索历史问题记录
# ═══════════════════════════════════════════════════════════════

def cmd_search(args):
    vault = get_vault_path()
    if not vault:
        print("错误: 未找到 Obsidian vault。", file=sys.stderr)
        sys.exit(1)

    issue_dir = vault / ISSUE_OUTPUT_DIR
    if not issue_dir.exists():
        print("(无问题记录目录)")
        return

    query_tokens = args.query.lower().split()
    results = []

    for f in issue_dir.rglob("*.md"):
        if f.name.endswith("模板.md"):
            continue
        try:
            content = f.read_text(encoding="utf-8").lower()
        except Exception:
            continue

        # 简单 BM25-like 评分
        score = 0
        for t in query_tokens:
            score += content.count(t)

        if score > 0:
            # 提取标题
            title_match = re.search(r'# 项目: (.+) \| 问题: (.+)', content)
            project = title_match.group(1) if title_match else ""
            issue_title = title_match.group(2) if title_match else ""

            # 提取状态
            is_resolved = ("状态: ✓ 问题已解决" in content or
                       "状态: ✓ 已解决" in content or
                       "问题已解决" in content.split("# 四、验证实验")[-1] if "# 四" in content else False)
            exp_count = len(re.findall(r'## 第(\d+)次实验', content))

            results.append({
                "file": f,
                "rel": str(f.relative_to(vault)),
                "project": project,
                "title": issue_title,
                "score": score,
                "resolved": is_resolved,
                "experiments": exp_count,
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    top = results[:args.top]
    if not top:
        print(f"(无匹配 \"{args.query}\")")
        return

    print(f"搜索 \"{args.query}\" 找到 {len(top)}/{len(results)} 条:\n")
    for i, r in enumerate(top, 1):
        status = "✓" if r["resolved"] else "⚙"
        print(f"  {i}. [{status}] {r['project']}/{r['title'][:60]}")
        print(f"     {r['rel']}  (匹配度: {r['score']}, 实验: {r['experiments']}次)")
        print()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="问题记录工具 — 按诊断流程模板归档到 Obsidian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 创建新问题记录
  python record_issue.py new --project "STM32F103-UART" \\
      --title "串口发送首字节丢失" --symptom "上电后首字节'H'丢失" \\
      --mcu "STM32F103C8T6" --checklist "0,6,11"

  # 追加实验结果
  python record_issue.py append \\
      --file "2026-05-03-串口发送首字节丢失.md" \\
      --result "清除TC位后发送正常, 5次测试全部通过" --resolved

  # 项目概览
  python record_issue.py summary --project "STM32F103-UART"

  # 搜索问题记录
  python record_issue.py search "DMA 双缓冲 溢出"
        """
    )
    sub = p.add_subparsers(dest="command", help="操作")

    # --- new ---
    p_new = sub.add_parser("new", help="从模板创建新的问题记录")
    p_new.add_argument("--project", required=True, help="项目名称（如 STM32F103-UART）")
    p_new.add_argument("--title", required=True, help="问题标题")
    p_new.add_argument("--mcu", default="", help="MCU 型号")
    p_new.add_argument("--symptom", default="", help="问题表现描述")
    p_new.add_argument("--repro", default="", help="复现步骤")
    p_new.add_argument("--expected", default="", help="正常预期行为")
    p_new.add_argument("--checklist", default="",
                       help="已检查的 checklist 项编号，逗号分隔 (0-11)")
    p_new.add_argument("--hypothesis", default="", help="可能的原因假设")
    p_new.add_argument("--experiment", default="", help="实验设计方案")
    p_new.add_argument("--force", action="store_true", help="覆盖已存在的同名文件")

    # --- append ---
    p_append = sub.add_parser("append", help="追加实验结果到已有记录")
    p_append.add_argument("--file", required=True, help="目标 .md 文件（支持相对路径或文件名片段）")
    p_append.add_argument("--time", default="", help="实验时间")
    p_append.add_argument("--env", default="", help="实验环境描述")
    p_append.add_argument("--refs", default="", help="相关文档引用")
    p_append.add_argument("--steps", default="", help="实验步骤")
    p_append.add_argument("--result", default="", help="实验结果")
    p_append.add_argument("--analysis", default="", help="实验分析与对比")
    p_append.add_argument("--resolved", dest="resolved", action="store_true", default=None,
                          help="标记问题已解决")
    p_append.add_argument("--unresolved", dest="resolved", action="store_false",
                          help="标记问题未解决")

    # --- summary ---
    p_summary = sub.add_parser("summary", help="项目问题记录概览")
    p_summary.add_argument("--project", default="", help="项目名称（留空=所有项目）")

    # --- search ---
    p_search = sub.add_parser("search", help="搜索历史问题记录")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--top", type=int, default=10, help="返回结果数 (默认10)")

    args = p.parse_args()

    if args.command == "new":
        cmd_new(args)
    elif args.command == "append":
        cmd_append(args)
    elif args.command == "summary":
        cmd_summary(args)
    elif args.command == "search":
        cmd_search(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
