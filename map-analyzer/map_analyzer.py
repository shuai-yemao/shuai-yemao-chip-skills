#!/usr/bin/env python3
"""
map-analyzer: 解析 GCC/Keil/IAR .map 文件，分析 Flash/RAM 使用情况
支持多格式解析、版本对比、JSON/CSV 导出、彩色进度条、优化建议
"""
import argparse
import re
import os
import sys
import json
import csv
from pathlib import Path
from collections import defaultdict

# ─── ANSI 颜色支持检测 ────────────────────────────────────────────────────────

def _ansi_supported():
    """检测当前终端是否支持 ANSI 颜色码（Windows 需要 VT 模式或 colorama）"""
    if sys.platform == "win32":
        # Windows 10 1511+ 的 conhost 支持 VT100，检查环境变量
        if os.environ.get("ANSICON") or os.environ.get("WT_SESSION"):
            return True
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # 启用 ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                new_mode = mode.value | 0x0004
                return bool(kernel32.SetConsoleMode(handle, new_mode))
        except Exception:
            pass
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

ANSI_OK = _ansi_supported()

def colorize(text, pct):
    """按使用率百分比为文本上色（需终端支持 ANSI）"""
    if not ANSI_OK:
        return text
    if pct > 90:
        return f"\033[91m{text}\033[0m"   # 红色
    elif pct > 70:
        return f"\033[93m{text}\033[0m"   # 黄色
    else:
        return f"\033[92m{text}\033[0m"   # 绿色

# ─── 文件搜索 ─────────────────────────────────────────────────────────────────

def find_map_file(start_dir="."):
    """在工程目录中递归搜索 .map 文件"""
    for root, _, files in os.walk(start_dir):
        for f in files:
            if f.endswith(".map"):
                return os.path.join(root, f)
    return None

# ─── GCC 解析 ─────────────────────────────────────────────────────────────────

def parse_gcc_map(content):
    """解析 GCC 链接器 .map 文件，返回 (sections dict, symbols list)"""
    sections = {}
    symbols = []

    # 解析顶层 section 大小（地址 + 大小均为十六进制）
    section_pattern = re.compile(
        r'^(\.\w+(?:\.\w+)*)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)', re.MULTILINE
    )
    for m in section_pattern.finditer(content):
        name, addr, size = m.group(1), m.group(2), m.group(3)
        sz = int(size, 16)
        if sz > 0 and name not in sections:
            sections[name] = sz

    # 解析符号及其来源 .o 文件
    sym_pattern = re.compile(
        r'^ (\.\w+(?:\.\w+)*)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.+\.o)',
        re.MULTILINE
    )
    for m in sym_pattern.finditer(content):
        section, addr, size, obj = m.groups()
        sz = int(size, 16)
        if sz > 0:
            symbols.append({
                "section": section,
                "size": sz,
                "file": os.path.basename(obj.strip())
            })

    return sections, symbols

# ─── Keil 解析 ────────────────────────────────────────────────────────────────

def parse_keil_map(content):
    """
    解析 Keil MDK .map 文件。
    重点解析 'Image component sizes' 段，提取每个 .o 文件的
    Code / RO Data / RW Data / ZI Data 列。
    """
    sections = {}
    symbols = []

    # 定位 Image component sizes 段
    header_pat = re.compile(
        r'Image component sizes.*?'
        r'Code\s+\(inc\.\s+data\)\s+RO\s+Data\s+RW\s+Data\s+ZI\s+Data.*?\n'
        r'(.*?)'
        r'(?:Grand Totals|={10,})',
        re.DOTALL | re.IGNORECASE
    )
    m = header_pat.search(content)
    if not m:
        return sections, symbols

    body = m.group(1)

    total_code = total_ro = total_rw = total_zi = 0

    # 每行: Code  (inc.data)  RO Data  RW Data  ZI Data  Debug  ObjectName
    row_pat = re.compile(
        r'^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+(\S+\.o)',
        re.MULTILINE
    )
    for row in row_pat.finditer(body):
        code, inc_data, ro, rw, zi, obj = row.groups()
        code, ro, rw, zi = int(code), int(ro), int(rw), int(zi)
        total_code += code
        total_ro   += ro
        total_rw   += rw
        total_zi   += zi
        obj_size = code + ro + rw  # Flash 贡献
        symbols.append({
            "section": ".text",
            "size": obj_size,
            "file": os.path.basename(obj),
            "code": code,
            "ro_data": ro,
            "rw_data": rw,
            "zi_data": zi,
        })

    sections[".text"]   = total_code
    sections[".rodata"] = total_ro
    sections[".data"]   = total_rw
    sections[".bss"]    = total_zi

    return sections, symbols


def classify_keil(sections):
    """Keil: Flash = Code + RO + RW, RAM = RW + ZI"""
    flash = (sections.get(".text", 0)
             + sections.get(".rodata", 0)
             + sections.get(".data", 0))
    ram   = sections.get(".data", 0) + sections.get(".bss", 0)
    return flash, ram

# ─── IAR 解析 ─────────────────────────────────────────────────────────────────

def parse_iar_map(content):
    """
    解析 IAR EWARM .map 文件。
    解析 MODULE SUMMARY（模块级汇总）和 ENTRY LIST（符号级明细）。
    """
    sections = {}
    symbols = []

    # ── MODULE SUMMARY ──
    mod_header = re.compile(
        r'\*+\s*MODULE SUMMARY\s*\*+.*?\n'
        r'.*?ro code.*?ro data.*?rw data.*?\n'   # 列头
        r'.*?-+.*?\n'                             # 分隔线
        r'(.*?)'
        r'(?:-{10,}|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    m = mod_header.search(content)
    if m:
        body = m.group(1)
        row_pat = re.compile(
            r'^\s*(\S+\.o\b.*?)\s+(\d+)\s+(\d+)\s+(\d+)',
            re.MULTILINE
        )
        total_roc = total_rod = total_rw = 0
        for row in row_pat.finditer(body):
            obj, roc, rod, rw = row.group(1), int(row.group(2)), int(row.group(3)), int(row.group(4))
            total_roc += roc
            total_rod += rod
            total_rw  += rw
            symbols.append({
                "section": ".text",
                "size": roc + rod + rw,
                "file": os.path.basename(obj.strip()),
                "ro_code": roc,
                "ro_data": rod,
                "rw_data": rw,
            })
        sections[".text"]   = total_roc
        sections[".rodata"] = total_rod
        sections[".data"]   = total_rw

    # ── ENTRY LIST（符号级，用于更精确的 Top N）──
    entry_header = re.compile(
        r'\*+\s*ENTRY LIST\s*\*+.*?\n'
        r'.*?Entry.*?Address.*?Size.*?Type.*?Object.*?\n'
        r'.*?-+.*?\n'
        r'(.*?)'
        r'(?:\*{10,}|\Z)',
        re.DOTALL | re.IGNORECASE
    )
    m2 = entry_header.search(content)
    if m2:
        body2 = m2.group(1)
        ent_pat = re.compile(
            r'^\s*(\S+)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(\w+)\s+(\S+)',
            re.MULTILINE
        )
        # 如果已有符号列表，用 ENTRY LIST 替换（更精确）
        entry_syms = []
        for row in ent_pat.finditer(body2):
            name, addr, size, typ, obj = row.groups()
            sz = int(size, 16)
            if sz > 0:
                entry_syms.append({
                    "section": ".text" if "Code" in typ else ".data",
                    "size": sz,
                    "file": os.path.basename(obj.split("[")[0].strip()),
                })
        if entry_syms:
            symbols = entry_syms

    return sections, symbols


def classify_iar(sections):
    """IAR: Flash = ro code + ro data + rw data, RAM = rw data（ZI 若有单独列另加）"""
    flash = (sections.get(".text", 0)
             + sections.get(".rodata", 0)
             + sections.get(".data", 0))
    ram   = sections.get(".data", 0) + sections.get(".bss", 0)
    return flash, ram

# ─── GCC 段分类 ───────────────────────────────────────────────────────────────

def classify_sections(sections):
    """GCC: Flash = .text+.rodata+.ARM+.init_array+.data; RAM = .data+.bss+.heap+.stack"""
    flash_total = sum(v for k, v in sections.items()
                      if any(k.startswith(fk) for fk in [".text", ".rodata", ".ARM",
                                                          ".init_array", ".fini_array"]))
    data_size   = sections.get(".data", 0)
    flash_total += data_size

    ram_total = sum(v for k, v in sections.items()
                    if any(k.startswith(rk) for rk in [".data", ".bss", "._stack", "._heap",
                                                        ".stack", ".heap"]))
    return flash_total, ram_total

# ─── 进度条 ───────────────────────────────────────────────────────────────────

def progress_bar(used, total, width=20):
    """生成带颜色的 ASCII 进度条"""
    if total == 0:
        return "N/A"
    ratio = min(used / total, 1.0)
    pct   = ratio * 100
    filled = int(ratio * width)
    bar   = "▓" * filled + "░" * (width - filled)
    bar   = colorize(bar, pct)
    return bar

# ─── 优化建议 ─────────────────────────────────────────────────────────────────

def print_optimization_hints(flash_pct, ram_pct):
    """当 Flash 或 RAM 使用率 > 80% 时输出优化建议"""
    if flash_pct is not None and flash_pct > 80:
        print("\n[优化建议] Flash 使用率 {:.1f}% 超过 80%，建议：".format(flash_pct))
        print("  Flash 优化：")
        print("    1. 启用链接时优化：在编译和链接时均加 -flto")
        print("    2. 去除未使用符号：-ffunction-sections -fdata-sections -Wl,--gc-sections")
        print("    3. 优化体积优先：使用 -Os 代替 -O2")
        print("    4. 去除调试符号：链接后 strip 或加 -Wl,-s")
        print("    5. 避免 printf/scanf：改用轻量日志（减少格式字符串和 libc 拖入）")
        print("    6. 压缩只读数据：检查是否有大型常量表可精简")
    if ram_pct is not None and ram_pct > 80:
        print("\n[优化建议] RAM 使用率 {:.1f}% 超过 80%，建议：".format(ram_pct))
        print("  RAM 优化：")
        print("    1. 检查 BSS 中的大数组：使用 --top 找出大型全局/静态数组并评估缩减")
        print("    2. 减小堆栈大小：在链接脚本中调低 _Min_Stack_Size（需确认最大调用深度）")
        print("    3. 使用静态分配替代 malloc：避免堆碎片和 malloc 失败风险")
        print("    4. 复用缓冲区：不同功能的临时缓冲区可用 union 或时序复用")
        print("    5. 将只读数据加 const：确保编译器将其放入 Flash 而非 RAM")

# ─── 版本对比 ─────────────────────────────────────────────────────────────────

def compare_maps(cur_symbols, old_symbols, fmt="gcc"):
    """
    对比两组符号列表，输出新增/删除/增大/减小的符号。
    cur_symbols: 当前版本符号列表
    old_symbols: 旧版本符号列表
    返回 diff dict
    """
    def _aggregate(syms):
        d = defaultdict(int)
        for s in syms:
            d[s["file"]] += s["size"]
        return d

    cur_map = _aggregate(cur_symbols)
    old_map = _aggregate(old_symbols)

    added   = {k: v for k, v in cur_map.items() if k not in old_map}
    removed = {k: v for k, v in old_map.items() if k not in cur_map}
    changed = {k: (old_map[k], cur_map[k])
               for k in cur_map if k in old_map and cur_map[k] != old_map[k]}

    return {"added": added, "removed": removed, "changed": changed}


def print_compare(diff, cur_file, old_file):
    """打印版本对比结果"""
    print("\n════════════════ 版本对比 diff ════════════════")
    print(f"基准文件: {old_file}")
    print(f"对比文件: {cur_file}\n")

    total_delta = 0

    if diff["added"]:
        print("[新增符号] (+)")
        for name, sz in sorted(diff["added"].items(), key=lambda x: -x[1]):
            print(f"  {name:<40} +{sz:,} 字节")
            total_delta += sz

    if diff["removed"]:
        print("\n[删除符号] (-)")
        for name, sz in sorted(diff["removed"].items(), key=lambda x: -x[1]):
            print(f"  {name:<40} -{sz:,} 字节")
            total_delta -= sz

    grown    = {k: v for k, v in diff["changed"].items() if v[1] > v[0]}
    shrunk   = {k: v for k, v in diff["changed"].items() if v[1] < v[0]}

    if grown:
        print("\n[增大符号] (↑)")
        for name, (old, new) in sorted(grown.items(), key=lambda x: -(x[1][1]-x[1][0])):
            delta = new - old
            print(f"  {name:<40} +{delta:,} 字节  ({old:,} → {new:,})")
            total_delta += delta

    if shrunk:
        print("\n[减小符号] (↓)")
        for name, (old, new) in sorted(shrunk.items(), key=lambda x: x[1][1]-x[1][0]):
            delta = new - old
            print(f"  {name:<40} {delta:,} 字节  ({old:,} → {new:,})")
            total_delta += delta

    sign = "+" if total_delta >= 0 else ""
    print(f"\n合计变化: {sign}{total_delta:,} 字节")
    print("═══════════════════════════════════════════════\n")

# ─── 导出 ─────────────────────────────────────────────────────────────────────

def export_results(export_fmt, map_file, sections, symbols,
                   flash_used, flash_size, ram_used, ram_size, diff=None):
    """将分析结果导出为 JSON 或 CSV"""
    base = os.path.splitext(map_file)[0]

    data = {
        "map_file": map_file,
        "flash": {
            "used": flash_used,
            "total": flash_size,
            "pct": round(flash_used / flash_size * 100, 2) if flash_size else None
        },
        "ram": {
            "used": ram_used,
            "total": ram_size,
            "pct": round(ram_used / ram_size * 100, 2) if ram_size else None
        },
        "sections": sections,
        "symbols": symbols,
    }
    if diff:
        data["diff"] = {
            "added":   {k: v for k, v in diff["added"].items()},
            "removed": {k: v for k, v in diff["removed"].items()},
            "changed": {k: list(v) for k, v in diff["changed"].items()},
        }

    if export_fmt == "json":
        out_path = base + "_analysis.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[导出] JSON 文件已保存: {out_path}")

    elif export_fmt == "csv":
        out_path = base + "_analysis.csv"
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["文件", "大小(字节)", "段"])
            for sym in sorted(symbols, key=lambda x: -x["size"]):
                writer.writerow([sym["file"], sym["size"], sym.get("section", "")])
        print(f"[导出] CSV 文件已保存: {out_path}")

# ─── 主分析函数 ───────────────────────────────────────────────────────────────

def analyze(map_file, flash_size=None, ram_size=None, top_n=20,
            fmt="gcc", compare_file=None, export_fmt=None, threshold=0):
    """主分析入口"""
    with open(map_file, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # 格式选择
    fmt = fmt.lower()
    if fmt == "keil":
        sections, symbols = parse_keil_map(content)
        flash_used, ram_used = classify_keil(sections)
    elif fmt == "iar":
        sections, symbols = parse_iar_map(content)
        flash_used, ram_used = classify_iar(sections)
    else:  # gcc（默认）
        sections, symbols = parse_gcc_map(content)
        flash_used, ram_used = classify_sections(sections)

    if not sections:
        print(f"警告：未能解析任何 section，请确认 --format 参数（当前: {fmt}）与文件匹配")
        sys.exit(1)

    # ── 输出报告 ──
    print("\n════════════════ 内存使用分析 ════════════════")
    print(f"文件  : {map_file}")
    print(f"格式  : {fmt.upper()}\n")

    flash_pct = None
    if flash_size:
        flash_pct = flash_used / flash_size * 100
        bar = progress_bar(flash_used, flash_size)
        pct_str = colorize(f"{flash_pct:.1f}%", flash_pct)
        print(f"Flash 使用: {flash_used:>8,} / {flash_size:,} 字节 ({pct_str}) {bar}")
        if flash_pct > 100:
            print("  [错误] Flash 溢出！链接必然失败。")
        elif flash_pct > 90:
            print("  [警告] Flash 使用率超过 90%，建议立即优化！")
        elif flash_pct > 80:
            print("  [提示] Flash 使用率超过 80%，请关注优化建议。")
    else:
        print(f"Flash 使用: {flash_used:,} 字节（未指定总大小）")

    ram_pct = None
    if ram_size:
        ram_pct = ram_used / ram_size * 100
        bar = progress_bar(ram_used, ram_size)
        pct_str = colorize(f"{ram_pct:.1f}%", ram_pct)
        print(f"RAM   使用: {ram_used:>8,} / {ram_size:,} 字节 ({pct_str}) {bar}")
        if ram_pct > 100:
            print("  [错误] RAM 溢出！链接必然失败。")
        elif ram_pct > 90:
            print("  [警告] RAM 使用率超过 90%，建议立即优化！")
        elif ram_pct > 80:
            print("  [提示] RAM 使用率超过 80%，请关注优化建议。")
    else:
        print(f"RAM   使用: {ram_used:,} 字节（未指定总大小）")

    print("\n各段明细:")
    for name, size in sorted(sections.items(), key=lambda x: -x[1])[:15]:
        print(f"  {name:<20}: {size:>8,} 字节")

    # 按文件汇总，应用 threshold 过滤
    file_sizes = defaultdict(int)
    for sym in symbols:
        file_sizes[sym["file"]] += sym["size"]

    filtered = {k: v for k, v in file_sizes.items() if v > threshold}
    print(f"\n最大目标文件 Top {top_n}"
          + (f"（threshold > {threshold} 字节）:" if threshold > 0 else ":"))
    for fname, size in sorted(filtered.items(), key=lambda x: -x[1])[:top_n]:
        print(f"  {fname:<40} {size:>8,} 字节")

    # 优化建议
    print_optimization_hints(flash_pct, ram_pct)

    # 版本对比
    diff = None
    if compare_file:
        with open(compare_file, "r", encoding="utf-8", errors="replace") as f:
            old_content = f.read()
        if fmt == "keil":
            _, old_symbols = parse_keil_map(old_content)
        elif fmt == "iar":
            _, old_symbols = parse_iar_map(old_content)
        else:
            _, old_symbols = parse_gcc_map(old_content)

        diff = compare_maps(symbols, old_symbols, fmt)
        print_compare(diff, map_file, compare_file)

    print("\n═══════════════════════════════════════════════\n")

    # 导出
    if export_fmt:
        export_results(export_fmt, map_file, sections, symbols,
                       flash_used, flash_size, ram_used, ram_size, diff)

# ─── CLI 入口 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="嵌入式 .map 文件内存分析工具（支持 GCC / Keil / IAR）"
    )
    parser.add_argument("--map",        default=None,
                        help=".map 文件路径（不填则自动搜索当前目录）")
    parser.add_argument("--flash-size", type=lambda x: int(x, 0), default=None,
                        help="Flash 总大小（字节，支持十六进制，如 0x10000）")
    parser.add_argument("--ram-size",   type=lambda x: int(x, 0), default=None,
                        help="RAM 总大小（字节）")
    parser.add_argument("--top",        type=int, default=20,
                        help="显示最大符号前 N 个（默认 20）")
    parser.add_argument("--format",     choices=["gcc", "keil", "iar"], default="gcc",
                        help="工具链格式：gcc（默认）/ keil / iar")
    parser.add_argument("--compare",    default=None,
                        help="旧版本 .map 文件路径，用于版本间内存变化对比")
    parser.add_argument("--export",     choices=["json", "csv"], default=None,
                        help="导出格式：json（结构化）或 csv（可导入 Excel）")
    parser.add_argument("--threshold",  type=int, default=0,
                        help="Top N 过滤阈值：仅显示大于此字节数的符号（默认 0）")
    args = parser.parse_args()

    map_path = args.map or find_map_file(".")
    if not map_path:
        print("错误：未找到 .map 文件，请通过 --map 指定路径")
        sys.exit(1)

    analyze(
        map_file    = map_path,
        flash_size  = args.flash_size,
        ram_size    = args.ram_size,
        top_n       = args.top,
        fmt         = args.format,
        compare_file= args.compare,
        export_fmt  = args.export,
        threshold   = args.threshold,
    )
