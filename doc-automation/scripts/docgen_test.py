#!/usr/bin/env python3
"""
docgen_test.py — 单元测试骨架自动生成（P2）
============================================
从 C 头文件解析函数声明，生成 minunit 风格测试骨架。

minunit 方案: 零外部依赖，纯标准 C，手写 mock stub。

功能:
  - minunit:   生成 minunit 测试 .c 文件（含空测试桩 + 编译命令注释）
  - check:     检查测试覆盖（对比 .h 声明的函数与测试文件中的测试用例）

用法:
  python docgen_test.py minunit <file.h> [-o test_<file>.c]
  python docgen_test.py check <file.h> <test_file.c>

编译运行:
  gcc -I src -I test test/test_<module>.c src/<module>.c -o test && ./test
"""

import io, os, re, sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 函数声明解析 ──

FUNC_PATTERN = re.compile(
    r'(?:static\s+)?(?:inline\s+)?(?:extern\s+)?'
    r'(\w+(?:\s*\*)?)\s+(\w+)\s*\(([^)]*?)\)\s*;(?!\s*\{)',
    re.MULTILINE,
)


def parse_functions(content: str) -> list[dict]:
    functions = []
    for match in FUNC_PATTERN.finditer(content):
        return_type = match.group(1).strip()
        name = match.group(2).strip()
        # 跳过 HAL 回调/弱函数
        if name.startswith('HAL_') and ('Callback' in name or 'Weak' in name):
            continue
        if name.startswith('__weak') or name.startswith('WEAK'):
            continue

        params_raw = match.group(3).strip()
        params = []
        if params_raw and params_raw != 'void':
            for p in params_raw.split(','):
                p = p.strip()
                if p:
                    tokens = p.split()
                    if tokens:
                        ptype = ' '.join(t for t in tokens if t != tokens[-1])
                        pname = tokens[-1].replace('*', '').strip()
                        params.append({'type': ptype, 'name': pname})

        functions.append({'name': name, 'return_type': return_type, 'params': params})

    return functions


# ── 场景推断（复用） ──


def _infer_test_scenarios(func_name: str, params: list) -> list[str]:
    name_lower = func_name.lower()
    if name_lower.startswith('init_') or name_lower.startswith('deinit_'):
        return ['正常初始化', '重复初始化', '空指针参数']
    if name_lower.startswith(('read_', 'receive_', 'recv_')):
        return ['正常读取', '缓冲区为 NULL', '长度为 0']
    if name_lower.startswith(('write_', 'send_')):
        return ['正常写入', '缓冲区为 NULL', '长度为 0']
    if name_lower.startswith(('enable_', 'start_')):
        return ['使能正常', '重复使能']
    if name_lower.startswith(('disable_', 'stop_')):
        return ['禁用正常', '重复禁用']
    if name_lower.startswith('get_'):
        return ['获取正常值', '参数为 NULL']
    if name_lower.startswith('set_'):
        return ['设置正常值', '参数超范围']
    if name_lower.startswith(('is_', 'has_')):
        return ['条件成立', '条件不成立']
    if name_lower.startswith(('calc_', 'compute_')):
        return ['正常计算', '边界值']
    if name_lower.startswith('hal_'):
        return ['正常调用', '参数错误']
    return ['正常调用', '边界条件']


# ── minunit 测试骨架生成 ──


def _default_value(ctype: str) -> str:
    c = ctype.strip().lower()
    if c in ('uint8_t', 'uint16_t', 'uint32_t', 'uint64_t'): return '0'
    if c in ('int8_t', 'int16_t', 'int32_t', 'int64_t', 'int'): return '-1'
    if c in ('bool', '_bool'): return 'false'
    if c == 'float': return '0.0f'
    if c == 'double': return '0.0'
    if c in ('char',): return "'\\0'"
    if c in ('char*', 'const char*'): return 'NULL'
    if '*' in c: return 'NULL'
    # 指针以外的未知类型（struct/enum/typedef）→ {0}
    return '{0}'


def generate_minunit_test(funcs: list[dict], module_name: str) -> str:
    """生成 minunit 风格测试文件"""
    lines = [
        f"/*",
        f" * test_{module_name}.c — minunit 单元测试",
        f" * 编译: gcc -I src -I test $< {module_name}.c -o test && ./test",
        f" *",
        f" * 使用指南:",
        f" *   1. 将模块的外部依赖替换为内联 mock stub",
        f" *   2. 在 test_xxx 函数中填充断言",
        f" *   3. 在 main() 中添加 mu_run(test_xxx)",
        f" */",
        "",
        '#include <stdio.h>',
        f'#include "{module_name}.h"',
        '#include "minunit.h"',
        "",
        "static int tests_run = 0, tests_failed = 0;",
        "",
        "/* ========== Mock Stubs ========== */",
        "// TODO: 将被测模块的外部依赖替换为 mock 变量 + stub 函数",
        "// static struct { int call_count; /* ... */ } mock;",
        "// void HAL_Dependency_Func(void) { mock.call_count++; }",
        "",
        "/* ========== 测试用例 ========== */",
        "",
    ]

    for func in funcs:
        scenarios = _infer_test_scenarios(func['name'], func['params'])
        is_void = func['return_type'].lower() in ('void',)

        for i, scenario in enumerate(scenarios):
            test_name = f"test_{func['name']}_{i}"
            lines.append(f"static void {test_name}(void)")
            lines.append("{")

            # 参数声明 + 默认值
            declared = []
            for p in func['params']:
                vn = p['name'].replace('*', '_ptr')
                lines.append(f"    {p['type']} {vn} = {_default_value(p['type'])};")
                declared.append(vn)

            lines.append("")
            lines.append(f"    // test: {scenario}")
            param_call = ", ".join(declared)
            if is_void:
                lines.append(f"    // {func['name']}({param_call});")
            else:
                lines.append(f"    // mu_assert(result == {func['name']}({param_call}));")
            lines.append("")
            lines.append("    // TODO: 断言")
            lines.append("}")
            lines.append("")

    # main
    lines.append("int main(void)")
    lines.append("{")
    lines.append('    printf("=== %s Test ===\\n", "' + module_name + '");')
    for func in funcs:
        for i, _ in enumerate(_infer_test_scenarios(func['name'], func['params'])):
            lines.append(f'    mu_run(test_{func["name"]}_{i});')
    lines.append("    mu_done();")
    lines.append("}")

    return '\n'.join(lines)


# ── 测试覆盖检查 ──


def cmd_check(header_path: str, test_path: str) -> int:
    h_content = Path(header_path).read_text(encoding='utf-8', errors='replace')
    t_content = Path(test_path).read_text(encoding='utf-8', errors='replace')

    declared = {f['name'] for f in parse_functions(h_content)}
    tested = set()
    for m in re.finditer(r'test_(\w+)_\d+\s*\(', t_content):
        tested.add(m.group(1))

    missing = declared - tested
    extra = tested - declared
    total = len(declared)
    covered = len(tested & declared)

    print(f"头文件: {header_path}")
    print(f"测试文件: {test_path}")
    print(f"声明函数: {total}")
    print(f"有测试用例: {covered}")
    print(f"覆盖率: {covered/total*100:.0f}%" if total > 0 else "覆盖率: N/A")
    print("")

    if missing:
        print(f"[!] 缺少测试 ({len(missing)}):")
        for n in sorted(missing):
            print(f"    - {n}")
    if extra:
        print(f"[i] 多余测试 (已删除的函数):")
        for n in sorted(extra):
            print(f"    - {n}")

    return 0 if not missing else 1


# ── CLI ──


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 3:
        print_usage()
        return 1

    cmd = sys.argv[1]
    target = sys.argv[2]

    if cmd == 'minunit':
        path = Path(target)
        if not path.exists():
            print(f"[X] 文件不存在: {target}")
            return 1
        content = path.read_text(encoding='utf-8', errors='replace')
        funcs = parse_functions(content)
        module_name = path.stem
        test_code = generate_minunit_test(funcs, module_name)

        output = None
        if '-o' in sys.argv:
            idx = sys.argv.index('-o')
            if idx + 1 < len(sys.argv):
                output = sys.argv[idx + 1]
        else:
            output = f"test_{module_name}.c"

        Path(output).write_text(test_code, encoding='utf-8')
        total_cases = sum(len(_infer_test_scenarios(f['name'], f['params'])) for f in funcs)
        print(f"[OK] minunit 测试文件: {output}")
        print(f"     共 {len(funcs)} 个函数，{total_cases} 个测试桩")
        print(f"     - 需要: 手写 mock stub + 填充断言")
        print(f"     - 依赖: minunit.h（src 同级 test/ 目录下）")
        print(f"     - 编译: gcc -I src -I test {output} {module_name}.c -o test")

    elif cmd == 'check':
        if len(sys.argv) < 4:
            print("[X] check 需要两个参数: <header.h> <test_file.c>")
            return 1
        return cmd_check(target, sys.argv[3])

    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
