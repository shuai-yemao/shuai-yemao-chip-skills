#!/usr/bin/env python
"""J-Link RTT 日志分析工具。

替代 MCP keil_rtt_analyze，解析 JLinkRTTLogger 或 RTT Viewer 输出的日志文件。

用法:
  keil_rtt_analyzer.py --log JLinkLog.txt
  keil_rtt_analyzer.py --log JLinkLog.txt --filter-keywords error,fail
  keil_rtt_analyzer.py --log JLinkLog.txt --filter-tags boot,flash
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# elog 级别前缀
ELOG_PREFIX = {
    "A": "ASSERT",
    "E": "ERROR",
    "W": "WARN",
    "I": "INFO",
    "D": "DEBUG",
    "V": "VERBOSE",
}


def parse_elog_line(line: str) -> dict | None:
    """解析 elog 格式行: [tag] level message"""
    m = re.match(r'^\s*\[(\w+)\]\s+([A-Z])\s+(.*)', line)
    if m:
        return {"tag": m.group(1), "level": ELOG_PREFIX.get(m.group(2), m.group(2)),
                "message": m.group(3)}
    # 无 tag: level message
    m = re.match(r'^\s*([A-Z])\s+(.*)', line)
    if m and m.group(1) in ELOG_PREFIX:
        return {"tag": "", "level": ELOG_PREFIX[m.group(1)], "message": m.group(2)}
    return None


def analyze_rtt_log(log_path: str, filter_keywords: list[str] | None = None,
                    filter_tags: list[str] | None = None) -> dict:
    """分析 RTT 日志文件"""
    path = Path(log_path)
    if not path.exists():
        return {"error": f"文件不存在: {log_path}"}

    try:
        for enc in ["utf-8", "gbk", "latin-1"]:
            try:
                content = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return {"error": "无法解码日志文件"}
    except OSError as e:
        return {"error": str(e)}

    lines = content.splitlines()
    total = len(lines)

    # 分级统计
    by_level: dict[str, int] = {}
    elog_lines: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []
    tags: set[str] = set()
    has_elog = False

    for i, line in enumerate(lines, 1):
        elog = parse_elog_line(line)
        if elog:
            has_elog = True
            level = elog["level"]
            by_level[level] = by_level.get(level, 0) + 1
            if elog["tag"]:
                tags.add(elog["tag"])
            if level in ("ERROR", "ASSERT"):
                errors.append({"line": i, "content": line.strip(),
                               "tag": elog["tag"], "message": elog["message"]})
            elif level == "WARN":
                warnings.append({"line": i, "content": line.strip(),
                                 "tag": elog["tag"]})
            if filter_tags and elog["tag"] not in filter_tags:
                continue
            if filter_keywords and not any(k.lower() in line.lower()
                                           for k in filter_keywords):
                continue
            elog_lines.append(elog)
        else:
            stripped = line.strip()
            if not stripped:
                by_level["EMPTY"] = by_level.get("EMPTY", 0) + 1
            else:
                by_level["UNKNOWN"] = by_level.get("UNKNOWN", 0) + 1
                if any(k.lower() in stripped.lower()
                       for k in (filter_keywords or [])):
                    elog_lines.append({"level": "RAW", "message": stripped})

    # 检测缓冲区溢出
    buffer_overflows = []
    for i, line in enumerate(lines):
        if "overflow" in line.lower() or "buffer overflow" in line.lower():
            buffer_overflows.append({"line": i + 1, "content": line.strip()})

    # 提取时间线
    timeline = []
    for i, line in enumerate(lines):
        m = re.search(r'(\d{2}:\d{2}:\d{2}[.,]\d{3})', line)
        if m:
            timeline.append({"line": i + 1, "time": m.group(1),
                             "content": line.strip()})

    return {
        "total_lines": total,
        "has_elog": has_elog,
        "by_level": dict(sorted(by_level.items())),
        "errors": errors,
        "warnings": warnings,
        "tags": sorted(tags) if tags else None,
        "buffer_overflows": buffer_overflows,
        "timeline": timeline if timeline else None,
        "filtered": elog_lines if (filter_keywords or filter_tags) else None,
    }


def print_report(result: dict, verbose: bool = False) -> None:
    """打印分析报告"""
    if "error" in result:
        print(f"❌ {result['error']}")
        return

    print(f"\n📊 RTT 日志分析报告")
    print(f"  {'总行数:':<20} {result['total_lines']}")
    print(f"  {'ELOG 格式:':<20} {'是' if result['has_elog'] else '否'}")
    print(f"  {'缓冲区溢出:':<20} {len(result['buffer_overflows'])} 处")

    if result["tags"]:
        print(f"  {'ELOG Tags:':<20} {', '.join(result['tags'])}")

    print(f"\n  {'级别':<12} {'数量':<8}")
    print(f"  {'-'*11} {'-'*7}")
    for level, count in sorted(result["by_level"].items()):
        print(f"  {level:<12} {count:<8}")

    if result["errors"]:
        print(f"\n❌ 错误 ({len(result['errors'])} 条):")
        for e in result["errors"][:10]:
            tag_str = f"[{e['tag']}] " if e.get('tag') else ""
            print(f"  L{e['line']}: {tag_str}{e['content']}")
        if len(result["errors"]) > 10:
            print(f"  ... 还有 {len(result['errors']) - 10} 条未显示")

    if result["warnings"]:
        print(f"\n⚠️ 警告 ({len(result['warnings'])} 条):")
        for w in result["warnings"][:5]:
            print(f"  L{w['line']}: {w['content']}")

    if result["timeline"]:
        print(f"\n⏱ 时间线 ({len(result['timeline'])} 个时间戳):")
        for t in result["timeline"][:10]:
            print(f"  [{t['time']}] L{t['line']}: {t['content']}")

    if result["buffer_overflows"]:
        print(f"\n🚨 缓冲区溢出!")
        for bo in result["buffer_overflows"]:
            print(f"  L{bo['line']}: {bo['content']}")

    if verbose:
        print(f"\n📝 所有内容:")
        for i, line in enumerate(result.get("filtered", []), 1):
            print(f"  {line['level']}: {line['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="J-Link RTT 日志分析工具")
    parser.add_argument("--log", required=True, help="RTT 日志文件路径")
    parser.add_argument("--filter-keywords", help="关键字过滤 (逗号分隔)")
    parser.add_argument("--filter-tags", help="ELOG tag 过滤 (逗号分隔)")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    keywords = args.filter_keywords.split(",") if args.filter_keywords else None
    tags = args.filter_tags.split(",") if args.filter_tags else None

    result = analyze_rtt_log(args.log, keywords, tags)
    print_report(result, args.verbose)

    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
