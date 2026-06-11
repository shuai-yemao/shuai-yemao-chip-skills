#!/usr/bin/env python3
"""
外部文档导入工具 — 将联网搜索到的官方数据手册/博客/GitHub README 导入本地知识库。

支持的来源类型:
  - 网络文章 (URL → fetch_markdown → 分块 → 写入 KB)
  - 本地 PDF    (路径 → markitdown 转换 → 分块 → 写入 KB)
  - 纯文本      (stdin / --text → 分块 → 写入 KB)
  - GitHub 仓库 (URL → fetch README → 写入 KB)

输出: CherryStudio KnowledgeBase/imported_docs.db
      与主 KB 同 schema，kb_search.py 自动发现并纳入检索。

用法:
    # 从 URL 导入文章
    python import_to_kb.py --url "https://blog.csdn.net/xxx/article/123"
    python import_to_kb.py --url "https://www.st.com/resource/en/reference_manual/rm0090-stm32f4.pdf"
    python import_to_kb.py --url "https://github.com/BoschSensortec/BME280_driver"

    # 从本地文件导入
    python import_to_kb.py --file "./datasheets/STM32F407.pdf"

    # 批量导入
    python import_to_kb.py --batch urls.txt

    # 查看已导入文档
    python import_to_kb.py --list
    python import_to_kb.py --stats

    # 删除已导入文档
    python import_to_kb.py --remove "STM32F407"

环境变量:
    KB_IMPORT_DIR: 导入数据库目录 (默认: CherryStudio KnowledgeBase)
"""

import os
import sys
import json
import sqlite3
import re
import hashlib
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

def get_import_db_path() -> str:
    """获取导入知识库路径"""
    base = os.environ.get("KB_IMPORT_DIR")
    if not base:
        appdata = os.environ.get("APPDATA", os.path.expanduser("~/.config"))
        base = str(Path(appdata) / "CherryStudio" / "Data" / "KnowledgeBase")
    return str(Path(base) / "imported_docs.db")


DB_PATH = get_import_db_path()

# ═══════════════════════════════════════════════════════════════
# 数据库管理
# ═══════════════════════════════════════════════════════════════

def init_db(db_path: str = None):
    """初始化导入知识库 (与 CherryStudio 同 schema)"""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vectors (
            id              TEXT PRIMARY KEY,
            pageContent     TEXT UNIQUE,
            uniqueLoaderId  TEXT NOT NULL,
            source          TEXT NOT NULL,
            vector          F32_BLOB,
            metadata        TEXT
        )
    """)
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════
# 内容获取
# ═══════════════════════════════════════════════════════════════

def fetch_url_content(url: str) -> dict:
    """
    获取 URL 内容。返回:
      {"success": True, "content": str, "content_type": str, "title": str}
    或 {"success": False, "error": str}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
    }

    try:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=30)
        content_type = resp.headers.get("Content-Type", "").lower()

        if "pdf" in content_type:
            return {
                "success": False,
                "error": "PDF 文件需要先下载再导入，请使用 --file 参数",
                "url": url,
                "content_type": content_type,
            }

        raw = resp.read()

        # 尝试解码
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        # 提取标题
        title_match = re.search(r'<title[^>]*>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else urlparse(url).netloc

        # 去除 HTML 标签 (简单版本)
        content = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', ' ', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'&[a-z]+;', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()

        if len(content) < 100:
            return {"success": False, "error": "提取内容过短，可能是 JS 渲染页面，请尝试用浏览器获取"}

        return {
            "success": True,
            "content": content,
            "content_type": "text/html",
            "title": title[:200],
            "url": url,
        }

    except HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "url": url}
    except URLError as e:
        return {"success": False, "error": f"网络错误: {e.reason}", "url": url}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


def fetch_github_readme(repo_url: str) -> dict:
    """获取 GitHub 仓库的 README"""
    # 转换为 raw URL
    parsed = urlparse(repo_url)
    path = parsed.path.strip("/")
    parts = path.split("/")

    if len(parts) < 2:
        return {"success": False, "error": "无效的 GitHub 仓库 URL"}

    owner, repo = parts[0], parts[1]
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"

    result = fetch_url_content(raw_url)
    if result["success"]:
        result["title"] = f"GitHub: {owner}/{repo}"
        result["source_type"] = "github"
        return result

    # 尝试 master 分支
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
    result = fetch_url_content(raw_url)
    if result["success"]:
        result["title"] = f"GitHub: {owner}/{repo}"
        result["source_type"] = "github"
    return result


# ═══════════════════════════════════════════════════════════════
# 文本分块
# ═══════════════════════════════════════════════════════════════

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    将文本按语义边界分块。优先在段落/句号处切分。

    chunk_size: 每块最大字符数 (参考手册段落较长)
    overlap: 块间重叠字符数
    """
    if len(text) <= chunk_size:
        return [text]

    # 按段落切分
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) <= chunk_size:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            # 如果单个段落超过 chunk_size，按句子切
            if len(para) > chunk_size:
                sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                sub = ""
                for s in sentences:
                    if len(sub) + len(s) <= chunk_size:
                        sub += s
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = s
                if sub:
                    # 与上一个 chunk 重叠
                    if chunks:
                        sub = chunks[-1][-overlap:] + "\n\n" + sub if overlap > 0 else sub
                    current = sub
                else:
                    current = ""
            else:
                # 重叠前一个 chunk 的尾部
                prefix = chunks[-1][-overlap:] + "\n\n" if chunks and overlap > 0 else ""
                current = prefix + para

    if current:
        chunks.append(current)

    return chunks


# ═══════════════════════════════════════════════════════════════
# 导入逻辑
# ═══════════════════════════════════════════════════════════════

def import_content(
    title: str,
    content: str,
    source_url: str = "",
    source_type: str = "web",
    tags: list[str] = None,
    db_path: str = None,
) -> dict:
    """
    将内容导入知识库。

    Args:
        title: 文档标题
        content: 文本内容
        source_url: 来源 URL
        source_type: 来源类型 (web/github/pdf/datasheet/blog)
        tags: 标签列表
        db_path: 数据库路径

    Returns:
        {"success": True, "chunks": int, "source": str}
    """
    conn = init_db(db_path)

    # 生成唯一 source 标识
    source_id = hashlib.md5((source_url or title).encode()).hexdigest()[:12]
    loader_id = f"ExternalImport_{source_type}_{source_id}"

    # 检查是否已导入
    existing = conn.execute(
        "SELECT COUNT(*) FROM vectors WHERE uniqueLoaderId = ?", (loader_id,)
    ).fetchone()[0]

    if existing > 0:
        conn.close()
        return {
            "success": False,
            "error": f"文档已存在 ({existing} chunks)，请先 --remove 再重新导入",
            "existing_chunks": existing,
        }

    # 分块
    chunks = chunk_text(content)
    if not chunks:
        conn.close()
        return {"success": False, "error": "内容为空，无法分块"}

    # 准备 metadata
    meta = json.dumps({
        "type": "ExternalImport",
        "source_type": source_type,
        "title": title,
        "url": source_url,
        "tags": tags or [],
        "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False)

    # 批量写入
    inserted = 0
    for i, chunk in enumerate(chunks):
        chunk_id = f"{loader_id}_{i}"
        try:
            conn.execute(
                """INSERT INTO vectors (id, pageContent, uniqueLoaderId, source, vector, metadata)
                   VALUES (?, ?, ?, ?, NULL, ?)""",
                (chunk_id, chunk, loader_id, source_url or title, meta),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            continue  # 重复内容跳过

    conn.commit()
    conn.close()

    return {
        "success": True,
        "chunks": inserted,
        "source": source_url or title,
        "title": title,
        "loader_id": loader_id,
    }


def list_imported(db_path: str = None) -> list[dict]:
    """列出所有已导入的文档"""
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        rows = conn.execute("""
            SELECT uniqueLoaderId, source, COUNT(*) as chunks,
                   MAX(json_extract(metadata, '$.imported_at')) as imported_at,
                   MAX(json_extract(metadata, '$.source_type')) as source_type
            FROM vectors
            GROUP BY uniqueLoaderId
            ORDER BY imported_at DESC
        """).fetchall()
        return [
            {
                "loader_id": r[0],
                "source": r[1],
                "chunks": r[2],
                "imported_at": r[3],
                "source_type": r[4] or "unknown",
            }
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def remove_imported(pattern: str, db_path: str = None) -> dict:
    """按 source 或 loader_id 模糊匹配删除已导入文档"""
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        rows = conn.execute(
            "SELECT uniqueLoaderId, source FROM vectors WHERE source LIKE ? OR uniqueLoaderId LIKE ?",
            (f"%{pattern}%", f"%{pattern}%"),
        ).fetchall()

        if not rows:
            conn.close()
            return {"success": False, "error": f"未匹配到任何文档: {pattern}"}

        loaders = list(set(r[0] for r in rows))
        sources = list(set(r[1] for r in rows))

        for lid in loaders:
            conn.execute("DELETE FROM vectors WHERE uniqueLoaderId = ?", (lid,))
        conn.commit()

        return {
            "success": True,
            "removed_loaders": len(loaders),
            "removed_chunks": len(rows),
            "sources": sources,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_stats(db_path: str = None) -> dict:
    """获取导入 KB 统计"""
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
        sources = conn.execute(
            "SELECT source, COUNT(*) FROM vectors GROUP BY uniqueLoaderId"
        ).fetchall()
        return {
            "total_chunks": total,
            "total_docs": len(sources),
            "sources": [
                {"title": s[0][:100], "chunks": s[1]} for s in sources
            ],
        }
    except sqlite3.OperationalError:
        return {"total_chunks": 0, "total_docs": 0, "sources": []}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="外部文档导入工具 — 将数据手册/博客文章/GitHub README 导入本地 KB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--url", "-u", default="",
                   help="要导入的 URL (支持网页/GitHub/PDF 链接)")
    p.add_argument("--file", "-f", default="",
                   help="要导入的本地文件路径 (.txt/.md)")
    p.add_argument("--text", "-t", default="",
                   help="直接导入文本内容")
    p.add_argument("--title", default="",
                   help="文档标题 (默认从 URL/文件名 提取)")
    p.add_argument("--batch", default="",
                   help="批量导入: 每行一个 URL 的文本文件")
    p.add_argument("--source-type", default="web",
                   choices=["web", "github", "pdf", "datasheet", "blog", "article"],
                   help="来源类型 (默认: web)")
    p.add_argument("--tags", default="", help="逗号分隔的标签")
    p.add_argument("--list", action="store_true", help="列出已导入文档")
    p.add_argument("--stats", action="store_true", help="显示导入统计")
    p.add_argument("--remove", default="", help="按名称删除已导入文档")
    p.add_argument("--db", default="",
                   help="自定义数据库路径 (默认: KB_IMPORT_DIR/imported_docs.db)")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    db_path = args.db or DB_PATH

    # --stats
    if args.stats:
        stats = get_stats(db_path)
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print(f"导入知识库: {db_path}")
            print(f"文档数: {stats['total_docs']}  片段数: {stats['total_chunks']}")
            for s in stats.get("sources", []):
                print(f"  [{s['chunks']:>4} chunks] {s['title'][:80]}")
        return

    # --list
    if args.list:
        docs = list_imported(db_path)
        if args.json:
            print(json.dumps(docs, ensure_ascii=False, indent=2))
        elif docs:
            print(f"已导入 {len(docs)} 个文档:\n")
            for d in docs:
                print(f"  [{d['source_type']:10s}] {d['imported_at'] or '?'}  "
                      f"{d['chunks']:>4} chunks  {d['source'][:70]}")
        else:
            print("(无已导入文档)")
        return

    # --remove
    if args.remove:
        result = remove_imported(args.remove, db_path)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            print(f"✓ 已删除 {result['removed_chunks']} chunks "
                  f"({result['removed_loaders']} 个文档)")
            for s in result["sources"]:
                print(f"  {s[:100]}")
        else:
            print(f"✗ {result['error']}", file=sys.stderr)
        return

    # --batch
    if args.batch:
        if not os.path.isfile(args.batch):
            print(f"✗ 文件不存在: {args.batch}", file=sys.stderr)
            sys.exit(1)
        with open(args.batch, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        results = []
        for url in urls:
            r = _import_single(url, args.title, args.source_type, args.tags, db_path)
            results.append(r)
            status = "✓" if r.get("success") else "✗"
            print(f"  {status} {r.get('title', url)[:70]}")
            if not r.get("success"):
                print(f"    错误: {r.get('error', '')}")
        return

    # --url / --file / --text
    if args.url:
        result = _import_single(args.url, args.title, args.source_type, args.tags, db_path,
                                is_github="github.com" in args.url)
    elif args.file:
        if not os.path.isfile(args.file):
            print(f"✗ 文件不存在: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        title = args.title or os.path.basename(args.file)
        result = import_content(title, content, args.file, args.source_type,
                                args.tags.split(",") if args.tags else None, db_path)
    elif args.text:
        content = args.text
        title = args.title or f"手动导入 {time.strftime('%Y-%m-%d %H:%M')}"
        result = import_content(title, content, "", "manual",
                                args.tags.split(",") if args.tags else None, db_path)
    else:
        p.print_help()
        return

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("success"):
        print(f"✓ 导入成功: {result.get('title', '')}")
        print(f"  片段数: {result.get('chunks', 0)}")
        print(f"  来源: {result.get('source', '')}")
        print(f"\n→ 已写入: {db_path}")
        print(f"→ kb_search.py 将自动发现此知识库")
    else:
        print(f"✗ 导入失败: {result.get('error', '未知错误')}", file=sys.stderr)
        sys.exit(1)


def _import_single(url: str, title: str, source_type: str, tags_str: str,
                   db_path: str, is_github: bool = False) -> dict:
    """导入单个 URL"""
    tags = [t.strip() for t in tags_str.split(",")] if tags_str else None

    # GitHub 仓库特殊处理
    if is_github and ("github.com" in url and "/blob/" not in url):
        result = fetch_github_readme(url)
        if result.get("success"):
            return import_content(
                result.get("title", title or url),
                result["content"],
                url,
                "github",
                tags,
                db_path,
            )
        # 回退到普通获取
        pass

    # 普通 URL
    result = fetch_url_content(url)
    if not result.get("success"):
        return result

    if not title:
        title = result.get("title", url)

    return import_content(title, result["content"], url, source_type, tags, db_path)


if __name__ == "__main__":
    main()
