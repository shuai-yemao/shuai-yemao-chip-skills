#!/usr/bin/env python3
"""
docgen_annotate.py — 函数注释自动生成（P0）
============================================
从 C 头文件中提取函数声明，自动生成 Doxygen 风格注释。

功能:
  - scan:      扫描目录下所有 .h 文件，列出缺注释的函数
  - annotate:  为指定 .h 文件批量插入 Doxygen 注释
  - check:     检查 .h 文件中注释覆盖率

用法:
  python docgen_annotate.py scan <dir>           # 扫描目录
  python docgen_annotate.py annotate <file.h>    # 插入注释（原地修改）
  python docgen_annotate.py annotate <file.h> --dry-run  # 试运行（只输出）
  python docgen_annotate.py check <file.h>       # 检查覆盖率

注释格式（立芯嵌入式 C 规范）:
  /**
   * @brief  <自动推断>
   * @param  param1 参数说明
   * @param  param2 参数说明
   * @retval 返回值说明
   */
"""

import io
import os
import re
import sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── C 函数声明解析 ──────────────────────────────────────────────

# 匹配函数声明（非函数指针、非宏、非定义）
# 支持: 返回类型 函数名(参数);  以及跨行声明
# 排除: typedef, #define, static inline 实现体
FUNC_PATTERN = re.compile(
    r'(?:static\s+)?'                                # 可选 static
    r'(?:inline\s+)?'                                # 可选 inline
    r'(?:extern\s+)?'                                # 可选 extern
    r'[a-zA-Z_][\w\s\*]+\s+'                         # 返回类型
    r'(\w+)\s*'                                      # 函数名 (group 1)
    r'\('                                            # 左括号
    r'([^)]*?)'                                      # 参数列表 (group 2)
    r'\)\s*;'                                        # 右括号 + 分号
    r'(?!\s*\{)',                                    # 后面不是 { (排除实现)
    re.MULTILINE | re.DOTALL,
)

# 已有关注释检测（匹配 Doxygen /** ... */ 或 /* ... */）
COMMENT_BLOCK = re.compile(r'/\*+[^*]*\*+(?:[^/*][^*]*\*+)*/')

# 单行注释 // 检测
LINE_COMMENT = re.compile(r'//.*$', re.MULTILINE)

# 宏/变量/类型声明排除
EXCLUDE_PATTERNS = [
    re.compile(r'\btypedef\b'),
    re.compile(r'\bstruct\b\s+\w+\s*;'),
    re.compile(r'\benum\b'),
    re.compile(r'^#\s*(define|include|if|ifdef|ifndef|endif|else|pragma)'),
    re.compile(r'HAL_StatusTypeDef\s+\w+\s*;'),  # HAL 状态变量声明
]

# 常见 HAL 回调/弱函数名前缀（这些通常不需要注释）
WEAK_PREFIXES = ('__weak', 'WEAK')


def _is_excluded(line: str) -> bool:
    """判断是否应该排除"""
    stripped = line.strip()
    for pat in EXCLUDE_PATTERNS:
        if pat.search(stripped):
            return True
    if any(stripped.startswith(p) for p in WEAK_PREFIXES):
        return True
    return False


def parse_functions(content: str) -> list[dict]:
    """解析 C 头文件中的函数声明"""
    functions = []
    for match in FUNC_PATTERN.finditer(content):
        full_match = match.group(0)
        name = match.group(1).strip()
        params_raw = match.group(2).strip()

        # 排除宏/类型声明等
        if _is_excluded(full_match):
            continue

        # 跳过 HAL 弱定义回调
        if name.startswith('HAL_') and ('Callback' in name or 'Weak' in name):
            continue

        # 解析参数
        params = []
        if params_raw:
            for p in params_raw.split(','):
                p = p.strip()
                if p and p != 'void':
                    # 提取参数名（C 声明中最后一个 token）
                    tokens = p.split()
                    if len(tokens) >= 1:
                        pname = tokens[-1].replace('*', '').strip()
                        ptype = ' '.join(t for t in tokens if t != tokens[-1])
                        params.append({'type': ptype, 'name': pname})

        # 推断返回类型
        decl_before_name = full_match[:full_match.index(name)].strip()
        ret_type = decl_before_name.replace('extern', '').replace('static', '').replace('inline', '').strip()
        # 清理多余空格
        ret_type = re.sub(r'\s+', ' ', ret_type)
        is_void = 'void' in ret_type.strip() and len(ret_type.strip().split()) <= 1

        # 获取行号（通过搜索定位）
        line_no = 1
        pos = 0
        for i, char in enumerate(content):
            if char == '\n':
                line_no += 1
                pos = i
            if full_match in content[i:i+len(full_match)] and i > pos:
                line_no = content[:i].count('\n') + 1
                break

        functions.append({
            'name': name,
            'return_type': ret_type,
            'params': params,
            'is_void': is_void,
            'match': full_match,
            'line': line_no,
        })

    return functions


def _infer_brief(name: str, return_type: str, params: list) -> str:
    """根据函数名推断 @brief 描述"""
    # 常见嵌入式命名模式
    name_lower = name.lower()

    patterns = {
        r'^init_?': '初始化',
        r'^deinit_?': '反初始化',
        r'^config_?': '配置',
        r'^read_?': '读取数据',
        r'^write_?': '写入数据',
        r'^send_?': '发送数据',
        r'^recv_?|^receive_?': '接收数据',
        r'^enable_?|^start_?': '使能/启动',
        r'^disable_?|^stop_?': '禁用/停止',
        r'^reset_?': '复位',
        r'^get_?': '获取参数/状态',
        r'^set_?': '设置参数',
        r'^is_?|^has_?': '检查状态',
        r'^wait_?': '等待',
        r'^poll_?': '轮询',
        r'^register_?': '注册',
        r'^unregister_?': '注销',
        r'^irq_?|^_irq_?|^interrupt_?': '中断处理',
        r'_callback$|_cb$': '回调函数',
        r'^assert_?': '断言检查',
        r'^error_?': '错误处理',
        r'^calc_?|^compute_?|^measure_?': '计算/测量',
        r'^parse_?|^decode_?': '解析/解码',
        r'^encode_?|^pack_?': '编码/打包',
        r'^open_?': '打开',
        r'^close_?': '关闭',
        r'^lock_?': '加锁',
        r'^unlock_?': '解锁',
    }

    for pattern, desc in patterns.items():
        if re.search(pattern, name_lower):
            return desc

    # 根据返回类型推断
    if 'void' in return_type and not params:
        return '执行操作'
    if name_lower.startswith('hal_'):
        return 'HAL 层接口'

    return '未命名函数'  # 占位，提醒手动补充


def _infer_param_desc(name: str, pname: str) -> str:
    """根据参数名推断 @param 描述"""
    pname_lower = pname.lower()

    desc_map = {
        'huart': 'UART 句柄',
        'hspi': 'SPI 句柄',
        'hi2c': 'I2C 句柄',
        'hcan': 'CAN 句柄',
        'hadc': 'ADC 句柄',
        'htim': '定时器句柄',
        'hdma': 'DMA 句柄',
        'hgpio': 'GPIO 句柄',
        'hflash': 'Flash 句柄',
        'husb': 'USB 句柄',

        'pdata': '数据缓冲区指针',
        'buffer': '数据缓冲区',
        'data': '数据缓冲区',
        'buf': '缓冲区',
        'size': '数据长度',
        'len': '数据长度',
        'length': '数据长度',
        'count': '计数',

        'timeout': '超时时间（ms）',
        'delay': '延迟时间（ms）',
        'period': '周期（ms）',

        'addr': '地址',
        'address': '地址',
        'reg': '寄存器地址',
        'channel': '通道号',
        'pin': '引脚号',
        'port': '端口号',
        'baudrate': '波特率',
        'prescaler': '预分频值',

        'flag': '标志位',
        'status': '状态',
        'cmd': '命令码',
        'command': '命令码',
        'mode': '模式选择',

        'callback': '回调函数指针',
        'arg': '回调参数',
        'context': '上下文指针',

        'enable': '使能标志',
        'config': '配置参数结构体指针',
        'handle': '操作句柄',
        'event': '事件类型',
        'priority': '优先级',
        'irq': '中断号',
    }

    # 精确匹配
    if pname_lower in desc_map:
        return desc_map[pname_lower]

    # 模糊匹配
    for key, desc in desc_map.items():
        if key in pname_lower or pname_lower in key:
            return desc

    return f'{pname} 说明'  # 占位


def _infer_return_desc(name: str, return_type: str) -> str:
    """推断 @retval 描述"""
    rt = return_type.strip()

    # 常见嵌入式返回类型
    if 'HAL_StatusTypeDef' in rt or 'Status' in rt:
        return 'HAL_OK: 成功; HAL_ERROR: 错误; HAL_BUSY: 忙; HAL_TIMEOUT: 超时'
    if rt == 'void' or rt == '':
        return '无返回值'
    if 'int' in rt:
        return '≥0: 成功; <0: 错误码'
    if 'bool' in rt or rt == 'uint8_t':
        return 'true/false 或 OK/ERROR'
    if 'uint32_t' in rt or 'uint16_t' in rt:
        return '状态值/计数值'
    if 'char' in rt or 'char*' in rt:
        return '字符串指针，NULL 表示失败'
    if '指针' in rt or '*' in rt:
        return '有效指针: 成功; NULL: 失败'

    return f'{rt} 类型的返回值'


def _make_doxygen(func: dict) -> str:
    """生成 Doxygen 注释块"""
    brief = _infer_brief(func['name'], func['return_type'], func['params'])

    lines = ['/**']
    lines.append(f' * @brief  {brief}')

    # 推断是否应该标记 @note
    if func['name'].startswith('HAL_'):
        lines.append(f' * @note   HAL 库封装接口，线程安全的实现需加锁')

    # @param
    for p in func['params']:
        desc = _infer_param_desc(func['name'], p['name'])
        lines.append(f' * @param  {p["name"]} {desc}')

    # @retval
    ret_desc = _infer_return_desc(func['name'], func['return_type'])
    lines.append(f' * @retval {ret_desc}')

    lines.append(' */')

    return '\n'.join(lines)


def _has_comment_before(content: str, match_start: int) -> bool:
    """检查函数声明前是否已有关注释"""
    before = content[max(0, match_start - 500):match_start].strip()
    # 检查最后一个注释块
    comments = COMMENT_BLOCK.findall(before)
    if not comments:
        return False
    # 检查注释和函数之间没有其他代码
    last_comment_end = before.rfind(comments[-1]) + len(comments[-1])
    between = before[last_comment_end:].strip()
    return between == '' or between.count('\n') <= 2


def _has_line_comment_before(content: str, match_start: int) -> bool:
    """检查是否有单行注释前缀"""
    before = content[max(0, match_start - 300):match_start]
    lines_before = before.split('\n')
    if not lines_before:
        return False
    last_line = lines_before[-1].strip() if lines_before else ''
    # 连续多行的 // 注释
    comment_lines = 0
    for l in reversed(lines_before):
        if l.strip().startswith('//'):
            comment_lines += 1
        elif l.strip() == '':
            continue
        else:
            break
    return comment_lines >= 2


def _is_inside_comment_block(content: str, pos: int) -> bool:
    """检查 pos 是否在注释块内部"""
    # 扫描前面的内容，看 /* 和 */ 的配对
    before = content[:pos]
    opens = [m.start() for m in re.finditer(r'/\*', before)]
    closes = [m.start() for m in re.finditer(r'\*/', before)]
    return len(opens) > len(closes)


# ── 命令实现 ──────────────────────────────────────────────────


def cmd_scan(target_dir: str) -> int:
    """扫描目录下所有 .h 文件，列出缺注释的函数"""
    path = Path(target_dir)
    if not path.is_dir():
        print(f"[X] 目录不存在: {target_dir}")
        return 1

    h_files = sorted(path.rglob('*.h'))
    total_funcs = 0
    total_missing = 0

    print(f"扫描目录: {target_dir}")
    print(f"找到 {len(h_files)} 个 .h 文件\n")

    for hf in h_files:
        content = hf.read_text(encoding='utf-8', errors='replace')
        funcs = parse_functions(content)
        if not funcs:
            continue

        missing = []
        for f in funcs:
            match_start = content.find(f['match'])
            if match_start < 0:
                continue
            if _is_inside_comment_block(content, match_start):
                continue
            if not _has_comment_before(content, match_start):
                missing.append(f)

        total_funcs += len(funcs)
        total_missing += len(missing)

        if missing:
            print(f"  [{hf.relative_to(path)}]  {len(missing)}/{len(funcs)} 缺注释:")
            for f in missing:
                print(f"    L{f['line']:>4}  {f['return_type']:<25} {f['name']}({len(f['params'])}p)")

    print(f"\n统计: {total_funcs} 个函数，{total_missing} 个缺注释 "
          f"({total_missing/total_funcs*100:.0f}% 覆盖率缺口)" if total_funcs > 0 else "")
    return 0 if total_missing == 0 else 1


def cmd_annotate(file_path: str, dry_run: bool = False) -> int:
    """为 .h 文件插入 Doxygen 注释"""
    path = Path(file_path)
    if not path.exists():
        print(f"[X] 文件不存在: {file_path}")
        return 1
    if path.suffix not in ('.h', '.c'):
        print(f"[X] 仅支持 .h/.c 文件: {path.suffix}")
        return 1

    original = path.read_text(encoding='utf-8', errors='replace')
    content = original
    funcs = parse_functions(content)

    if not funcs:
        print(f"[i] 未找到可解析的函数声明: {file_path}")
        return 0

    # 从后往前插入（避免位置偏移）
    funcs_sorted = sorted(funcs, key=lambda f: content.find(f['match']), reverse=True)

    inserted = 0
    for f in funcs_sorted:
        match_start = content.find(f['match'])
        if match_start < 0:
            continue
        if _is_inside_comment_block(content, match_start):
            continue
        if _has_comment_before(content, match_start):
            continue

        doxygen = _make_doxygen(f)
        indent = ''
        # 保持与函数声明相同的缩进
        line_start = content.rfind('\n', 0, match_start) + 1
        if line_start > 0:
            indent = ' ' * (match_start - line_start)

        doc_indent = '\n'.join(indent + l if l != '/**' else indent + '/**'
                                for l in doxygen.split('\n'))

        content = content[:match_start] + doc_indent + '\n' + indent + content[match_start:]
        inserted += 1

    if inserted == 0:
        print(f"[i] 所有函数已有注释或无需处理: {file_path}")
        return 0

    if dry_run:
        print(f"[DRY-RUN] 将插入 {inserted} 个注释到: {file_path}")
        print(f"\n--- 差异预览 ---")
        _show_diff(original, content)
        print(f"\n--- 预览结束 ---")
    else:
        path.write_text(content, encoding='utf-8')
        print(f"[OK] 已插入 {inserted} 个注释: {file_path}")
        print(f"     已注释 {len(funcs)}/{len(funcs)} 个函数")

    return 0


def cmd_check(file_path: str) -> int:
    """检查注释覆盖率"""
    path = Path(file_path)
    if not path.exists():
        print(f"[X] 文件不存在: {file_path}")
        return 1

    content = path.read_text(encoding='utf-8', errors='replace')
    funcs = parse_functions(content)

    if not funcs:
        print(f"[i] 未找到函数声明: {file_path}")
        return 0

    documented = 0
    undocumented = []

    for f in funcs:
        match_start = content.find(f['match'])
        if match_start < 0:
            continue
        if _has_comment_before(content, match_start):
            documented += 1
        else:
            undocumented.append(f)

    total = len(funcs)
    coverage = documented / total * 100 if total > 0 else 0

    print(f"文件: {file_path}")
    print(f"总计: {total} 个函数")
    print(f"已注释: {documented}")
    print(f"缺注释: {len(undocumented)}")
    print(f"覆盖率: {coverage:.0f}%\n")

    if undocumented:
        print("缺少注释的函数:")
        for f in undocumented:
            print(f"  L{f['line']:>4}  {f['name']}({len(f['params'])}p)")

    return 0 if coverage >= 80 else 1


def _show_diff(original: str, modified: str):
    """简单文本 diff 输出"""
    import difflib
    diff = difflib.unified_diff(
        original.splitlines(True),
        modified.splitlines(True),
        fromfile='original',
        tofile='modified',
    )
    for line in diff:
        if line.startswith('+'):
            print(f"\033[32m{line}\033[0m", end='')
        elif line.startswith('-'):
            print(f"\033[31m{line}\033[0m", end='')
        elif line.startswith('@@'):
            print(f"\033[36m{line}\033[0m", end='')
        else:
            print(line, end='')


# ── CLI ───────────────────────────────────────────────────────


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 3:
        print_usage()
        return 1

    cmd = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else '.'

    if cmd == 'scan':
        return cmd_scan(target)
    elif cmd == 'annotate':
        dry_run = '--dry-run' in sys.argv
        return cmd_annotate(target, dry_run)
    elif cmd == 'check':
        return cmd_check(target)
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1


if __name__ == '__main__':
    sys.exit(main())
