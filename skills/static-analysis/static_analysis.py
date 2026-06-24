#!/usr/bin/env python3
"""
static-analysis: 嵌入式 C/C++ 静态分析工具
封装 cppcheck，解析 XML 报告，按严重程度输出问题列表
支持 MISRA C 检查、并行扫描、增量基线对比、多格式导出
"""
import argparse
import subprocess
import sys
import os
import json
import time
import xml.etree.ElementTree as ET
import tempfile
import shutil

SEVERITY_LABEL = {
    "error":       "ERROR       (必须修复)",
    "warning":     "WARNING     (建议修复)",
    "style":       "STYLE       (可选优化)",
    "performance": "PERFORMANCE (性能建议)",
    "portability": "PORTABILITY (可移植性)",
    "information": "INFORMATION (提示信息)",
}

# MISRA 规则级别映射（示例常见规则，其余归为 Required）
MISRA_MANDATORY = {"misra-c2012-1.3", "misra-c2012-2.1", "misra-c2012-18.6"}
MISRA_ADVISORY  = {
    "misra-c2012-4.1", "misra-c2012-4.2", "misra-c2012-7.1",
    "misra-c2012-15.5", "misra-c2012-17.7",
}

# 三类高危 ERROR 的通用修复模板
FIX_TEMPLATES = {
    "nullPointer": """\
  /* --- nullPointer 修复模板 ---
   * 问题：对指针解引用前未检查是否为 NULL
   * 修复：在使用前加空指针守卫
   */
  if (ptr == NULL) {
      // 错误处理：记录日志、返回错误码或断言
      return ERROR_NULL_POINTER;
  }
  ptr->field = value;  // 此时安全使用""",

    "memleak": """\
  /* --- memleak 修复模板 ---
   * 问题：动态分配的内存在所有退出路径上未被释放
   * 修复：确保每条退出路径都调用 free()
   */
  uint8_t *buf = (uint8_t *)malloc(size);
  if (buf == NULL) {
      return ERROR_NO_MEM;
  }
  // ... 使用 buf ...
  if (some_error_condition) {
      free(buf);   // 错误路径也要释放
      return ERROR_CODE;
  }
  free(buf);       // 正常路径释放
  buf = NULL;      // 防止悬空指针""",

    "arrayIndexOutOfBounds": """\
  /* --- arrayIndexOutOfBounds 修复模板 ---
   * 问题：数组下标超出定义范围
   * 修复：访问前进行边界检查
   */
  #define BUF_SIZE  256
  uint8_t buf[BUF_SIZE];
  // 写入前检查索引
  if (index < BUF_SIZE) {
      buf[index] = value;
  } else {
      // 越界处理：截断、报错或断言
      assert(0 && "array index out of bounds");
  }""",
}


def check_cppcheck():
    if not shutil.which("cppcheck"):
        print("错误：未找到 cppcheck")
        print("安装方法：")
        print("  Windows : winget install Cppcheck.Cppcheck")
        print("  Ubuntu  : sudo apt install cppcheck")
        print("  macOS   : brew install cppcheck")
        sys.exit(1)
    result = subprocess.run(["cppcheck", "--version"], capture_output=True, text=True)
    return result.stdout.strip()


def extract_includes_from_cmake(cmake_path):
    """从 CMakeLists.txt 粗略提取 include_directories"""
    includes = []
    if not os.path.exists(cmake_path):
        return includes
    with open(cmake_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    import re
    pattern = re.compile(r'include_directories\s*\(([^)]+)\)', re.MULTILINE)
    for m in pattern.finditer(content):
        for path in m.group(1).split():
            path = path.strip().strip('"')
            if path and not path.startswith('$'):
                includes.append(path)
    return includes


def detect_compile_db(src_dir):
    """自动检测 build/compile_commands.json，返回路径或 None"""
    candidates = [
        os.path.join(src_dir, "build", "compile_commands.json"),
        os.path.join(os.path.dirname(src_dir), "build", "compile_commands.json"),
        os.path.join(os.getcwd(), "build", "compile_commands.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def run_analysis(src_dir, include_dirs, defines, std, suppress_list,
                 jobs=None, misra=False, compile_db=None):
    """执行 cppcheck 分析，返回 (XML 报告路径, subprocess 结果, 耗时秒数)"""
    with tempfile.NamedTemporaryFile(
        suffix=".xml", delete=False, mode="w", encoding="utf-8"
    ) as f:
        xml_path = f.name

    cmd = [
        "cppcheck",
        "--enable=all",
        f"--std={std}",
        "--platform=arm32-wchar_t2",
        "--suppress=missingIncludeSystem",
        "--xml",
        "--xml-version=2",
        f"--output-file={xml_path}",
    ]

    # 并行线程数
    n_jobs = jobs if jobs else (os.cpu_count() or 1)
    cmd.append(f"-j{n_jobs}")

    # compile_commands.json 优先
    if compile_db:
        cmd.append(f"--project={compile_db}")
        print(f"[static-analysis] 使用 compile_commands.json: {compile_db}")
    else:
        for inc in include_dirs:
            cmd.append(f"-I{inc}")
        for define in defines:
            cmd.append(f"-D{define}")

    for sup in suppress_list:
        cmd.append(f"--suppress={sup}")

    if misra:
        cmd.append("--addon=misra")

    if not compile_db:
        cmd.append(src_dir)

    print(f"[static-analysis] 执行: {' '.join(cmd[:6])} ... {src_dir}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - t0
    return xml_path, result, elapsed


def count_source_files(src_dir):
    """统计目录下 .c/.cpp 文件数"""
    count = 0
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith((".c", ".cpp", ".cxx", ".cc")):
                count += 1
    return count


def classify_misra_level(err_id):
    """将 MISRA 规则 ID 分级"""
    if err_id in MISRA_MANDATORY:
        return "Mandatory"
    if err_id in MISRA_ADVISORY:
        return "Advisory"
    return "Required"


def parse_issues(xml_path):
    """解析 XML，返回 issues dict: severity -> list[dict]"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    issues = {}
    for error in root.iter("error"):
        sev = error.get("severity", "information")
        loc = error.find("location")
        file_path = loc.get("file", "unknown") if loc is not None else "unknown"
        line = loc.get("line", "?") if loc is not None else "?"
        msg = error.get("msg", "")
        err_id = error.get("id", "")

        issues.setdefault(sev, []).append({
            "file": os.path.basename(file_path),
            "file_full": file_path,
            "line": line,
            "id":   err_id,
            "msg":  msg,
            "severity": sev,
        })
    return issues


def load_baseline(baseline_path):
    """加载基线文件，返回问题集合（file:line:id 的 set）"""
    if not os.path.isfile(baseline_path):
        return None
    with open(baseline_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    baseline_set = set()
    for item in data:
        key = f"{item['file']}:{item['line']}:{item['id']}"
        baseline_set.add(key)
    return baseline_set


def save_baseline(baseline_path, issues):
    """将全量问题保存为基线 JSON"""
    all_items = []
    for items in issues.values():
        all_items.extend(items)
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"[static-analysis] 基线已保存: {baseline_path}  ({len(all_items)} 项)")


def filter_new_issues(issues, baseline_set):
    """过滤掉基线中已有的问题，只保留新增问题"""
    new_issues = {}
    for sev, items in issues.items():
        new_items = []
        for item in items:
            key = f"{item['file']}:{item['line']}:{item['id']}"
            if key not in baseline_set:
                new_items.append(item)
        if new_items:
            new_issues[sev] = new_items
    return new_issues


def print_report(issues, src_dir, file_count, elapsed, baseline_mode=False):
    """输出格式化报告，返回 error_count"""
    total = sum(len(v) for v in issues.values())

    print("\n═══════════════ 静态分析报告 (cppcheck) ═══════════════")
    mode_tag = " [增量模式 - 仅显示新增问题]" if baseline_mode else ""
    print(f"扫描目录: {src_dir}  |  扫描文件: {file_count}  |  耗时: {elapsed:.1f}s{mode_tag}")

    if total == 0:
        print("未发现问题！")
        print("═══════════════════════════════════════════════════════\n")
        return 0

    misra_items = []

    for sev_key in ["error", "warning", "performance", "style", "portability", "information"]:
        items = issues.get(sev_key, [])
        if not items:
            continue
        label = SEVERITY_LABEL.get(sev_key, sev_key.upper())
        print(f"\n{label} — {len(items)} 项")
        for item in items:
            print(f"  {item['file']}:{item['line']:<6} [{item['id']:<35}] {item['msg']}")
            if item["id"].startswith("misra"):
                misra_items.append(item)

    # MISRA 问题分级汇总
    if misra_items:
        print("\n--- MISRA C 问题分级汇总 ---")
        by_level = {"Mandatory": [], "Required": [], "Advisory": []}
        for item in misra_items:
            level = classify_misra_level(item["id"])
            by_level[level].append(item)
        for level in ["Mandatory", "Required", "Advisory"]:
            lvl_items = by_level[level]
            if lvl_items:
                print(f"  [{level}] {len(lvl_items)} 项")
                for item in lvl_items:
                    print(f"    {item['file']}:{item['line']}  {item['id']}  {item['msg']}")

    error_count   = len(issues.get("error", []))
    warning_count = len(issues.get("warning", []))
    print(f"\n总计: {total} 项问题  |  ERROR: {error_count}  WARNING: {warning_count}")
    print("═══════════════════════════════════════════════════════\n")

    # 高危问题修复模板
    error_items = issues.get("error", [])
    shown_templates = set()
    for item in error_items:
        eid = item["id"]
        if eid in FIX_TEMPLATES and eid not in shown_templates:
            shown_templates.add(eid)
            print(f"--- 修复模板: {eid} ({item['file']}:{item['line']}) ---")
            print(FIX_TEMPLATES[eid])
            print()

    return error_count


def export_html(xml_path, output_dir):
    """调用 cppcheck-htmlreport 将 XML 转为 HTML 报告"""
    if not shutil.which("cppcheck-htmlreport"):
        print("警告：未找到 cppcheck-htmlreport，跳过 HTML 导出")
        print("      可通过 pip install cppcheck-htmlreport 安装")
        return
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "cppcheck-htmlreport",
        f"--file={xml_path}",
        f"--report-dir={output_dir}",
        "--title=Static Analysis Report",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        index_path = os.path.join(output_dir, "index.html")
        print(f"[static-analysis] HTML 报告已生成: {index_path}")
    else:
        print(f"[static-analysis] HTML 报告生成失败: {result.stderr.strip()}")


def export_json(issues, output_path):
    """将问题列表导出为 JSON 文件"""
    all_items = []
    for items in issues.values():
        all_items.extend(items)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
    print(f"[static-analysis] JSON 报告已生成: {output_path}  ({len(all_items)} 项)")


def export_xml_copy(xml_path, output_path):
    """将 XML 报告复制到指定路径"""
    shutil.copy2(xml_path, output_path)
    print(f"[static-analysis] XML 报告已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="嵌入式静态代码分析（cppcheck）")
    parser.add_argument("--src", default=".", help="源码目录")
    parser.add_argument("--include", nargs="*", default=[], help="头文件目录")
    parser.add_argument("--define", nargs="*", default=[], help="宏定义，如 STM32F407xx")
    parser.add_argument("--std", default="c11",
                        choices=["c99", "c11", "c17", "c++11", "c++14", "c++17"])
    parser.add_argument("--suppress", nargs="*", default=[], help="要抑制的警告 ID")
    parser.add_argument("--cmake", default="CMakeLists.txt",
                        help="CMakeLists.txt 路径（自动提取 include）")
    # 新增参数
    parser.add_argument("--misra", action="store_true",
                        help="启用 MISRA C 规则检查（需 cppcheck misra addon）")
    parser.add_argument("--jobs", type=int, default=None,
                        help="并行扫描线程数（默认 CPU 核心数）")
    parser.add_argument("--compile-db", default=None,
                        help="compile_commands.json 路径（精确 include/define 推断）")
    parser.add_argument("--export", choices=["html", "xml", "json"], default=None,
                        help="导出格式：html / xml / json")
    parser.add_argument("--export-dir", default="cppcheck_report",
                        help="HTML 报告输出目录（默认 cppcheck_report）")
    parser.add_argument("--export-file", default=None,
                        help="json/xml 导出文件路径（默认自动命名）")
    parser.add_argument("--baseline", default=None,
                        help="基线文件路径；不存在时保存基线，存在时做增量对比")
    args = parser.parse_args()

    version = check_cppcheck()
    print(f"[static-analysis] 工具版本: {version}")

    # Step 0: 自动推断 compile_commands.json
    compile_db = args.compile_db
    if compile_db is None:
        detected = detect_compile_db(args.src)
        if detected:
            print(f"[static-analysis] 自动检测到 compile_commands.json: {detected}")
            compile_db = detected

    # 自动从 CMakeLists.txt 补充 include（仅在无 compile_db 时有效）
    auto_includes = extract_includes_from_cmake(args.cmake)
    all_includes = list(set(args.include + auto_includes))

    # 统计源文件数
    file_count = count_source_files(args.src)

    xml_path, proc, elapsed = run_analysis(
        args.src, all_includes, args.define, args.std, args.suppress,
        jobs=args.jobs, misra=args.misra, compile_db=compile_db
    )

    try:
        issues = parse_issues(xml_path)

        # 基线处理
        baseline_mode = False
        if args.baseline:
            baseline_set = load_baseline(args.baseline)
            if baseline_set is None:
                # 基线不存在，保存当前结果为基线
                save_baseline(args.baseline, issues)
                print("[static-analysis] 首次扫描，结果已保存为基线，全量显示：")
            else:
                # 基线存在，过滤出新增问题
                original_total = sum(len(v) for v in issues.values())
                issues = filter_new_issues(issues, baseline_set)
                new_total = sum(len(v) for v in issues.values())
                baseline_mode = True
                print(f"[static-analysis] 增量模式：全量 {original_total} 项，新增 {new_total} 项")

        error_count = print_report(issues, args.src, file_count, elapsed,
                                   baseline_mode=baseline_mode)

        # 导出处理
        if args.export == "html":
            export_html(xml_path, args.export_dir)
        elif args.export == "json":
            out_file = args.export_file or "cppcheck_report.json"
            export_json(issues, out_file)
        elif args.export == "xml":
            out_file = args.export_file or "cppcheck_report.xml"
            export_xml_copy(xml_path, out_file)

    finally:
        if os.path.exists(xml_path):
            os.unlink(xml_path)

    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
