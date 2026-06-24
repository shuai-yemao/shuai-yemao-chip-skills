#!/usr/bin/env python3
"""
docgen_api.py — API 文档自动生成（P1）
========================================
从 C 头文件中提取 API 声明，生成结构化 Markdown API 文档。

功能:
  - extract:   从 .h 文件提取 API 信息，输出 JSON
  - generate:  从 JSON 生成 Markdown API 文档
  - build:     提取+生成一步完成（默认）

用法:
  python docgen_api.py build <file.h> [-o output.md]
  python docgen_api.py build <dir>   [-o output.md]
  python docgen_api.py extract <file.h>
  python docgen_api.py generate <input.json> -o <output.md>
"""

import io, json, os, re, sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 函数解析（复用 docgen_annotate 的解析逻辑的简化版） ──

FUNC_PATTERN = re.compile(
    r'(?:static\s+)?(?:inline\s+)?(?:extern\s+)?'
    r'(?:HAL_StatusTypeDef|void|uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|'
    r'bool|char|float|double|size_t|'
    r'[a-zA-Z_]\w*(?:\s*\*)?)\s+'                      # 返回类型
    r'(\w+)\s*'                                         # 函数名 (group 1)
    r'\(([^)]*?)\)\s*;'                                 # 参数列表 + 分号
    r'(?!\s*\{)',
    re.MULTILINE,
)

# 已有关注释检测
COMMENT_BLOCK = re.compile(r'/\*+[^*]*\*+(?:[^/*][^*]*\*+)*/')
LINE_COMMENT = re.compile(r'//.*$', re.MULTILINE)


def parse_functions(content: str) -> list[dict]:
    functions = []
    for match in FUNC_PATTERN.finditer(content):
        name = match.group(1).strip()
        params_raw = match.group(2).strip()

        params = []
        if params_raw and params_raw != 'void':
            for p in params_raw.split(','):
                p = p.strip()
                if p:
                    tokens = p.split()
                    if tokens:
                        pname = tokens[-1].replace('*', '').strip()
                        ptype = ' '.join(t for t in tokens if t != tokens[-1])
                        params.append({'type': ptype, 'name': pname})

        # 提取返回值类型
        decl = content[match.start():match.end()]
        return_type = decl[:decl.index(name)].strip()
        return_type = re.sub(r'\s+', ' ', return_type)

        # 提取前面的注释
        before = content[max(0, match.start() - 800):match.start()].strip()
        comment = ''
        for c in COMMENT_BLOCK.findall(before):
            last_comment_end = before.rfind(c) + len(c)
            between = before[last_comment_end:].strip()
            if between == '' or between.count('\n') <= 2:
                comment = c

        # 提取 @brief
        brief = ''
        if comment:
            bm = re.search(r'@brief\s+(.+?)(?:\n\s*\*?\s*@|\n\s*\*/\s*$)', comment, re.DOTALL)
            if bm:
                brief = bm.group(1).strip()

        # 提取 @param
        params_doc = []
        for pm in re.finditer(r'@param(?:\[in\]|\[out\]|\[in,out\])?\s+(\w+)\s+(.+?)(?=\n\s*\*?\s*@|\n\s*\*/\s*$)', comment, re.DOTALL):
            params_doc.append({'name': pm.group(1), 'desc': pm.group(2).strip()})

        # 提取 @retval
        retval_doc = ''
        rm = re.search(r'@retval\s+(.+?)(?=\n\s*\*?\s*@|\n\s*\*/\s*$)', comment, re.DOTALL)
        if rm:
            retval_doc = rm.group(1).strip()

        functions.append({
            'name': name,
            'return_type': return_type,
            'params': params,
            'brief': brief,
            'params_doc': params_doc,
            'retval_doc': retval_doc,
            'line': match.start(),
        })

    return functions


def _group_by_prefix(funcs: list[dict]) -> dict:
    """按函数名前缀分组（HAL_、BSP_、app_ 等）"""
    groups = {}
    for f in funcs:
        prefix = f['name'].split('_')[0] if '_' in f['name'] else '_other'
        groups.setdefault(prefix.upper(), []).append(f)
    return groups


# ── Markdown 生成 ──


def generate_markdown(funcs: list[dict], title: str = "API 参考") -> str:
    """生成 Markdown API 文档"""
    lines = [f"# {title}", "", "## 函数清单", ""]
    lines.append("| 函数名 | 返回值 | 参数 | 说明 |")
    lines.append("|--------|--------|------|------|")

    for f in funcs:
        param_str = ", ".join(f"{p['type']} {p['name']}" for p in f['params']) if f['params'] else "void"
        brief_str = f['brief'][:40] + "..." if len(f['brief']) > 40 else f['brief']
        lines.append(f"| `{f['name']}` | `{f['return_type']}` | `{param_str}` | {brief_str} |")

    lines += ["", "---", "## 函数详情", ""]

    for f in funcs:
        lines.append(f"### {f['name']}")
        lines.append("")
        lines.append(f"```c")
        param_str = ", ".join(f"{p['type']} {p['name']}" for p in f['params']) if f['params'] else "void"
        lines.append(f"{f['return_type']} {f['name']}({param_str});")
        lines.append("```")
        lines.append("")

        if f['brief']:
            lines.append(f"**描述**: {f['brief']}")
            lines.append("")

        if f['params']:
            lines.append("**参数**:")
            lines.append("")
            lines.append("| 参数名 | 类型 | 说明 |")
            lines.append("|--------|------|------|")
            for p in f['params']:
                pdesc = ""
                for pd in f['params_doc']:
                    if pd['name'] == p['name']:
                        pdesc = pd['desc']
                        break
                lines.append(f"| `{p['name']}` | `{p['type']}` | {pdesc} |")
            lines.append("")

        if f['retval_doc']:
            lines.append(f"**返回值**: {f['retval_doc']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── 命令实现 ──


def cmd_build(target: str, output: str | None = None) -> int:
    path = Path(target)
    if path.is_dir():
        h_files = sorted(path.rglob('*.h'))
        title = f"API 参考 — {path.name}"
    elif path.is_file() and path.suffix == '.h':
        h_files = [path]
        title = f"API 参考 — {path.stem}"
    else:
        print(f"[X] 路径无效或非 .h 文件: {target}")
        return 1

    all_funcs = []
    for hf in h_files:
        content = hf.read_text(encoding='utf-8', errors='replace')
        funcs = parse_functions(content)
        for f in funcs:
            f['source'] = str(hf)
        all_funcs.extend(funcs)

    if not all_funcs:
        print(f"[i] 未找到函数声明: {target}")
        return 0

    md = generate_markdown(all_funcs, title)

    if output:
        Path(output).write_text(md, encoding='utf-8')
        print(f"[OK] API 文档已生成: {output}")
        print(f"     共 {len(all_funcs)} 个函数，来源 {len(h_files)} 个文件")
    else:
        print(md)

    return 0


def cmd_extract(file_path: str) -> int:
    path = Path(file_path)
    if not path.exists():
        print(f"[X] 文件不存在: {file_path}")
        return 1
    content = path.read_text(encoding='utf-8', errors='replace')
    funcs = parse_functions(content)
    print(json.dumps(funcs, ensure_ascii=False, indent=2))
    return 0


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 3:
        print_usage()
        return 1

    cmd = sys.argv[1]
    target = sys.argv[2]

    if cmd == 'build':
        output = None
        if '-o' in sys.argv:
            idx = sys.argv.index('-o')
            if idx + 1 < len(sys.argv):
                output = sys.argv[idx + 1]
        return cmd_build(target, output)
    elif cmd == 'extract':
        return cmd_extract(target)
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1


if __name__ == '__main__':
    sys.exit(main())
