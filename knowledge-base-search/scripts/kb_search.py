#!/usr/bin/env python3
"""
知识库检索工具 — 通用后端，解耦存储格式与检索逻辑。

检索管线:
  Query → BM25 + Vector → Adaptive RRF Fusion → MMR Dedup → Context Expansion → Top-K

核心技术 (参考开源方案):
  - RRF (Reciprocal Rank Fusion):  融合 BM25 与向量排序, k=60 标准常数
    参考: Cormack et al. 2009, ariel-frischer/kb, lancedb/lancedb
  - Adaptive RRF:  基于查询词 IDF 自动调节关键词/语义权重
    参考: stffns/vstash (BEIR benchmark, beats ColBERTv2 on 5/5 datasets)
  - MMR Dedup:  最大边际相关性去重, 避免同一文档冗余片段
    参考: stffns/vstash (NDCG@5 +1.8%, diversity 3.2→5.0 docs)
  - Context Expansion:  匹配片段 ±1 邻块, 提供 2.6x 更丰富上下文
    参考: stffns/vstash, ariel-frischer/kb

用法:
    python kb_search.py "查询关键词"                       # 搜索所有知识库
    python kb_search.py "查询" -k 10                      # Top 10
    python kb_search.py "查询" --kb "stm32"               # 仅搜索名称含 stm32 的 KB
    python kb_search.py --list-kbs                        # 列出所有可用的知识库
    python kb_search.py --source-stats                    # 查看所有 KB 概览

环境变量:
    KB_SEARCH_DIR:  知识库扫描目录（默认: CherryStudio KnowledgeBase）
"""

import os
import sys
import json
import sqlite3
import re
import math
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import hashlib

# Windows 控制台 UTF-8 编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class Chunk:
    """单个文档片段"""
    id: str
    content: str
    source: str           # 来源标识（文件路径或文档标题）
    metadata: dict = field(default_factory=dict)
    vector: Optional[bytes] = None


# ═══════════════════════════════════════════════════════════════
# 知识库适配器（抽象层）
# ═══════════════════════════════════════════════════════════════

class KBAdapter(ABC):
    """知识库后端抽象接口"""

    def __init__(self, name: str, path: str):
        self.name = name    # 知识库友好名称
        self.path = path    # 文件系统路径
        self._title_cache: dict = {}

    @abstractmethod
    def load_chunks(self) -> list[Chunk]:
        """从存储加载所有片段"""
        ...

    @abstractmethod
    def get_stats(self) -> dict:
        """返回知识库统计信息"""
        ...

    def extract_title(self, source: str) -> str:
        """从来源对应的第一条 chunk 提取文档标题"""
        if source in self._title_cache:
            return self._title_cache[source]
        # 默认实现：查找该 source 的第一条 chunk
        for c in self.load_chunks():
            if c.source == source:
                title_raw = c.content[:200]
                title_raw = title_raw.replace("\r", " ").replace("\n", " ")
                parts = [p.strip() for p in title_raw.split("  ") if len(p.strip()) > 15]
                title = parts[0] if parts else title_raw[:100]
                self._title_cache[source] = title.strip()
                return self._title_cache[source]
        self._title_cache[source] = os.path.basename(source)
        return self._title_cache[source]


class SQLiteVectorKB(KBAdapter):
    """CherryStudio 格式：SQLite + vectors 表"""

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def load_chunks(self) -> list[Chunk]:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT id, pageContent, source, vector, metadata FROM vectors")
            rows = cur.fetchall()
            conn.close()
            return [
                Chunk(
                    id=r[0],
                    content=r[1],
                    source=r[2],
                    vector=r[3],
                    metadata=json.loads(r[4]) if r[4] else {},
                )
                for r in rows
            ]
        except Exception:
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM vectors")
            total = cur.fetchone()[0]
            cur.execute("""
                SELECT json_extract(metadata, "$.type") as type, COUNT(*)
                FROM vectors GROUP BY type
            """)
            types = {r[0] or "unknown": r[1] for r in cur.fetchall()}
            cur.execute("""
                SELECT source, COUNT(*) FROM vectors
                GROUP BY source ORDER BY COUNT(*) DESC LIMIT 20
            """)
            sources = []
            for r in cur.fetchall():
                title = self.extract_title(r[0])
                sources.append({"title": title, "chunks": r[1]})
            conn.close()
            return {"total_chunks": total, "loader_types": types, "top_sources": sources}
        except Exception:
            return {"error": "无法读取知识库"}

    @staticmethod
    def probe(path: str) -> bool:
        """检测文件是否为有效的 CherryStudio 向量库"""
        try:
            conn = sqlite3.connect(path)
            conn.execute("SELECT 1 FROM vectors LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False


class ObsidianMarkdownKB(KBAdapter):
    """Obsidian Vault — 扫描 .md 文件作为知识库"""

    # 需要跳过的目录名
    SKIP_DIRS = {".git", ".obsidian", ".trash", "_attachments", "node_modules",
                 ".github", "__pycache__", ".venv", "venv", ".DS_Store"}
    # 嵌入/嵌入式相关文件名的关键词过滤（可选，为 None 时加载全部）
    EMBEDDED_PATTERNS = [
        "stm32", "esp32", "mcu", "mcu ", "hal", "freertos", "rtos",
        "uart", "spi", "i2c", "can", "dma", "gpio", "adc", "dac",
        "pwm", "timer", "interrupt", "bootloader", "firmware",
        "嵌入式", "单片机", "驱动", "寄存器", "外设", "中断", "定时器",
        "cortex", "arm", "risc-v", "riscv", "jtag", "swd",
    ]

    def __init__(self, name: str, vault_path: str,
                 filter_embedded: bool = True, max_file_mb: float = 1.0):
        """
        Args:
            name: 知识库名称
            vault_path: Obsidian vault 根目录
            filter_embedded: True=仅加载嵌入式相关 .md, False=加载全部
            max_file_mb: 跳过超过此大小的 .md 文件
        """
        super().__init__(name, vault_path)
        self.filter_embedded = filter_embedded
        self.max_file_bytes = int(max_file_mb * 1024 * 1024)
        self._chunks: Optional[list[Chunk]] = None

    def _scan_markdown_files(self) -> list[Path]:
        """递归扫描 vault 中的 .md 文件"""
        md_files = []
        vault = Path(self.path)
        if not vault.is_dir():
            return md_files

        for md_path in vault.rglob("*.md"):
            # 跳过隐藏目录和排除目录
            parts = set(md_path.parent.parts)
            if parts & self.SKIP_DIRS:
                continue
            # 跳过 . 开头的目录
            if any(p.startswith(".") for p in md_path.relative_to(vault).parts):
                continue
            # 跳过过大文件
            try:
                if md_path.stat().st_size > self.max_file_bytes:
                    continue
            except OSError:
                continue

            if self.filter_embedded:
                # 检查文件名或路径是否匹配嵌入式关键词
                fname_lower = md_path.stem.lower()
                fpath_lower = str(md_path.relative_to(vault)).lower()
                combined = fname_lower + " " + fpath_lower
                if any(p in combined for p in self.EMBEDDED_PATTERNS):
                    md_files.append(md_path)
            else:
                md_files.append(md_path)

        return md_files

    def _chunk_markdown(self, text: str, source: str,
                        chunk_size: int = 800, overlap: int = 100) -> list[Chunk]:
        """
        将 Markdown 文本按标题/段落边界分块。

        优先在 ## / ### 标题处分块，保持语义完整性。
        """

        # 尝试按 ## 标题分块
        sections = re.split(r'\n(?=#{1,3}\s)', text)
        chunks = []
        current = ""
        source_id = hashlib.md5(source.encode()).hexdigest()[:12]

        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            if len(section) <= chunk_size:
                if current and len(current) + len(section) > chunk_size:
                    # flush current
                    chunk_id = f"obsidian_{source_id}_{len(chunks)}"
                    chunks.append(Chunk(
                        id=chunk_id, content=current.strip(),
                        source=source,
                        metadata={"type": "ObsidianVault", "file": source,
                                  "vault": self.name},
                    ))
                    # overlap: 取 current 尾部作为新块前缀
                    current = current[-overlap:] + "\n\n" + section if overlap else section
                else:
                    current = (current + "\n\n" + section) if current else section
            else:
                # section 本身超过 chunk_size，按段落再分
                if current:
                    chunk_id = f"obsidian_{source_id}_{len(chunks)}"
                    chunks.append(Chunk(
                        id=chunk_id, content=current.strip(),
                        source=source,
                        metadata={"type": "ObsidianVault", "file": source,
                                  "vault": self.name},
                    ))
                    current = ""

                paragraphs = re.split(r'\n\s*\n', section)
                sub = ""
                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue
                    if len(sub) + len(para) <= chunk_size:
                        sub += ("\n\n" + para) if sub else para
                    else:
                        if sub:
                            chunk_id = f"obsidian_{source_id}_{len(chunks)}"
                            chunks.append(Chunk(
                                id=chunk_id, content=sub.strip(),
                                source=source,
                                metadata={"type": "ObsidianVault", "file": source,
                                          "vault": self.name},
                            ))
                        # overlap
                        sub = sub[-overlap:] + "\n\n" + para if overlap and sub else para
                if sub:
                    current = sub

        # flush 最后一块
        if current.strip():
            chunk_id = f"obsidian_{source_id}_{len(chunks)}"
            chunks.append(Chunk(
                id=chunk_id, content=current.strip(),
                source=source,
                metadata={"type": "ObsidianVault", "file": source,
                          "vault": self.name},
            ))

        return chunks

    def load_chunks(self) -> list[Chunk]:
        if self._chunks is not None:
            return self._chunks

        md_files = self._scan_markdown_files()
        all_chunks = []
        for md_path in md_files:
            try:
                # 尝试多种编码
                for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                    try:
                        text = md_path.read_text(encoding=enc)
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                else:
                    text = md_path.read_text(encoding="utf-8", errors="replace")

                # 用相对路径作为 source 标识
                vault = Path(self.path)
                rel_path = str(md_path.relative_to(vault))
                chunks = self._chunk_markdown(text, rel_path)
                all_chunks.extend(chunks)
            except Exception:
                continue

        self._chunks = all_chunks
        return self._chunks

    def get_stats(self) -> dict:
        chunks = self.load_chunks()
        sources = {}
        for c in chunks:
            sources[c.source] = sources.get(c.source, 0) + 1

        return {
            "total_chunks": len(chunks),
            "total_files": len(sources),
            "top_sources": sorted(
                [{"title": k, "chunks": v} for k, v in sources.items()],
                key=lambda x: x["chunks"], reverse=True,
            )[:20],
            "filter_embedded": self.filter_embedded,
        }

    def extract_title(self, source: str) -> str:
        """从 .md 文件路径提取标题"""
        if source in self._title_cache:
            return self._title_cache[source]
        # 用文件名（去掉扩展名）作为标题
        title = Path(source).stem
        # 如果是相对路径，加上父目录前缀
        parent = Path(source).parent
        if parent.name and parent.name != ".":
            title = f"{parent.name}/{title}"
        self._title_cache[source] = title
        return title

    @staticmethod
    def probe(path: str) -> bool:
        """
        检测是否为有效的 Obsidian Vault。
        通过寻找路径下的 .obsidian 配置目录来判断。
        """
        vault_path = Path(path)
        if not vault_path.is_dir():
            return False
        # .obsidian 目录存在即认定为 vault
        if (vault_path / ".obsidian").is_dir():
            return True
        # 向上查找 .obsidian
        current = vault_path
        for _ in range(4):
            if (current / ".obsidian").is_dir():
                return True
            current = current.parent
        return False


# ═══════════════════════════════════════════════════════════════
# Obsidian Vault 自动发现
# ═══════════════════════════════════════════════════════════════

# 常见 Obsidian vault 位置（Windows / macOS / Linux）
_OBSIDIAN_CANDIDATE_DIRS = [
    # 环境变量显式指定
    lambda: os.environ.get("OBSIDIAN_VAULT_PATH"),
    # Windows 常见位置
    lambda: os.path.expandvars(r"%USERPROFILE%\Documents\Obsidian"),
    lambda: os.path.expandvars(r"%USERPROFILE%\Documents\Vault"),
    lambda: os.path.expandvars(r"%USERPROFILE%\Obsidian"),
    lambda: os.path.expandvars(r"%USERPROFILE%\OneDrive\Obsidian"),
    # macOS
    lambda: os.path.expanduser("~/Documents/Obsidian"),
    # Linux
    lambda: os.path.expanduser("~/Obsidian"),
]


def _find_obsidian_vaults() -> list[tuple[str, str]]:
    """
    自动发现系统中的 Obsidian Vault。

    Returns: [(name, path), ...] 名称和路径的列表
    """
    found = []

    # 1. 检查候选目录
    for candidate_fn in _OBSIDIAN_CANDIDATE_DIRS:
        try:
            candidate = candidate_fn()
        except Exception:
            continue
        if not candidate:
            continue
        base = Path(candidate)
        if not base.is_dir():
            continue

        # 候选目录本身是 vault（含 .obsidian）
        if (base / ".obsidian").is_dir():
            name = base.name
            found.append((name, str(base)))
            continue

        # 候选目录的子目录可能是 vault
        try:
            for sub in sorted(base.iterdir()):
                if sub.is_dir() and (sub / ".obsidian").is_dir():
                    found.append((sub.name, str(sub)))
        except PermissionError:
            continue

    # 2. 检查 obsidian.json (Obsidian 配置文件)
    obsidian_config_paths = [
        Path(os.environ.get("APPDATA", "")) / "obsidian" / "obsidian.json",
        Path(os.path.expanduser("~/.config/obsidian/obsidian.json")),
    ]
    for config_path in obsidian_config_paths:
        try:
            if config_path.is_file():
                config = json.loads(config_path.read_text())
                for vault_entry in config.get("vaults", {}).values():
                    vpath = vault_entry.get("path", "")
                    if vpath and Path(vpath).is_dir():
                        name = Path(vpath).name
                        if (name, vpath) not in found:
                            found.append((name, vpath))
        except Exception:
            continue

    return found


# ═══════════════════════════════════════════════════════════════
# 知识库发现
# ═══════════════════════════════════════════════════════════════

def get_default_kb_dir() -> Path:
    """默认知识库目录"""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~/.config"))
    return Path(appdata) / "CherryStudio" / "Data" / "KnowledgeBase"


def _make_kb_name(path: str, index: int) -> str:
    """从文件路径生成可读的知识库名称"""
    stem = Path(path).stem
    if stem and len(stem) >= 4:
        return stem
    return f"kb-{index + 1}"


def _try_create_adapter(path: str, is_vault_dir: bool = False) -> Optional[KBAdapter]:
    """尝试为路径创建对应的适配器"""
    # Obsidian Vault（目录模式）
    if is_vault_dir or ObsidianMarkdownKB.probe(path):
        name = Path(path).name
        return ObsidianMarkdownKB(name, path)
    # CherryStudio SQLite 向量库
    if SQLiteVectorKB.probe(path):
        return SQLiteVectorKB(_make_kb_name(path, 0), path)
    return None


def discover_knowledge_bases(search_dir: Optional[str] = None,
                              include_obsidian: bool = True) -> list[KBAdapter]:
    """
    自动发现搜索目录下的所有知识库。

    Args:
        search_dir: 扫描目录，为 None 时使用默认 CherryStudio 目录
        include_obsidian: 是否自动发现 Obsidian vault

    Returns:
        知识库适配器列表（按大小降序，大库优先）
    """
    adapters = []

    # ── CherryStudio KnowledgeBase 目录 ──
    if search_dir is None:
        search_dir = str(get_default_kb_dir())

    search_path = Path(search_dir)

    # 单文件模式
    if search_path.is_file():
        adapter = _try_create_adapter(str(search_path))
        if adapter:
            adapter.name = search_path.stem
            return [adapter]

    # 目录模式：扫描 SQLite .db 文件
    if search_path.is_dir():
        for f in sorted(search_path.iterdir(),
                        key=lambda x: x.stat().st_size if x.is_file() else 0,
                        reverse=True):
            if f.is_file():
                adapter = _try_create_adapter(str(f))
                if adapter:
                    adapter.name = _make_kb_name(str(f), len(adapters))
                    adapters.append(adapter)

    # ── Obsidian Vault 自动发现 ──
    if include_obsidian:
        obsidian_vaults = _find_obsidian_vaults()
        for vault_name, vault_path in obsidian_vaults:
            # 避免重复
            if any(a.path == vault_path for a in adapters):
                continue
            adapter = _try_create_adapter(vault_path, is_vault_dir=True)
            if adapter:
                adapter.name = f"obsidian:{vault_name}"
                adapters.append(adapter)

    return adapters


# ═══════════════════════════════════════════════════════════════
# BM25 检索引擎（存储格式无关）
# ═══════════════════════════════════════════════════════════════

def tokenize(text: str) -> list[str]:
    """中文 + 英文混合分词"""
    tokens = []
    eng_tokens = re.findall(r'[a-zA-Z0-9_][a-zA-Z0-9_.+-]*', text.lower())
    tokens.extend(eng_tokens)
    chinese = re.findall(r'[\u4e00-\u9fff]', text)
    tokens.extend(chinese)
    for i in range(len(chinese) - 1):
        tokens.append(chinese[i] + chinese[i + 1])
    return tokens


def tokenize_query(text: str) -> list[str]:
    """查询分词"""
    tokens = []
    eng_tokens = re.findall(r'[a-zA-Z0-9_][a-zA-Z0-9_.+-]*', text.lower())
    tokens.extend(eng_tokens)
    chinese = re.findall(r'[\u4e00-\u9fff]', text)
    tokens.extend(chinese)
    for i in range(len(chinese) - 1):
        tokens.append(chinese[i] + chinese[i + 1])
    return tokens


def compute_bm25(query_tokens: list[str], doc_tokens: list[str],
                 doc_freq: dict, total_docs: int, avg_doc_len: float,
                 k1: float = 1.5, b: float = 0.75) -> float:
    """BM25 分数计算"""
    doc_len = len(doc_tokens)
    score = 0.0
    tf = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    for qt in query_tokens:
        if qt not in tf:
            continue
        df = doc_freq.get(qt, 0)
        if df == 0:
            continue
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
        numerator = tf[qt] * (k1 + 1)
        denominator = tf[qt] + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf * numerator / denominator
    return score


def _build_index(chunks: list[Chunk]) -> tuple[list[list[str]], dict, int, float]:
    """对一组 chunk 建立 BM25 倒排索引"""
    doc_tokens_list = []
    doc_freq = {}
    total_tokens = 0
    for c in chunks:
        tokens = tokenize(c.content)
        doc_tokens_list.append(tokens)
        total_tokens += len(tokens)
        seen = set()
        for t in tokens:
            if t not in seen:
                doc_freq[t] = doc_freq.get(t, 0) + 1
                seen.add(t)
    avg_doc_len = total_tokens / len(chunks) if chunks else 0
    return doc_tokens_list, doc_freq, len(chunks), avg_doc_len


# ═══════════════════════════════════════════════════════════════
# RRF (Reciprocal Rank Fusion) — Cormack et al. 2009
# 行业标准: Azure AI Search, Elasticsearch, Weaviate, LanceDB
# ═══════════════════════════════════════════════════════════════

def reciprocal_rank_fusion(
    bm25_ranked: list[tuple[int, float]],   # [(chunk_idx, bm25_score), ...]
    vec_ranked: list[tuple[int, float]],     # [(chunk_idx, vec_score), ...]
    k: int = 60,
    vec_weight: float = 0.6,
    fts_weight: float = 0.4,
) -> list[tuple[int, float]]:
    """
    RRF 融合 BM25 和向量排序结果。

    Formula: RRF_score(d) = Σ w_i / (k + rank_i(d))

    - k=60 为 Cormack 论文确定的最优常数（10~100 范围内不敏感）
    - 在两个列表中排名都靠前的文档得分更高
    - 权重 w_i 支持自适应调节（via adaptive_rrf_weights）

    Returns: [(chunk_idx, rrf_score), ...] 按 RRF score 降序
    """
    rrf = {}
    for rank, (idx, _score) in enumerate(bm25_ranked, 1):
        rrf[idx] = rrf.get(idx, 0.0) + fts_weight / (k + rank)
    for rank, (idx, _score) in enumerate(vec_ranked, 1):
        rrf[idx] = rrf.get(idx, 0.0) + vec_weight / (k + rank)
    return sorted(rrf.items(), key=lambda x: x[1], reverse=True)


def adaptive_rrf_weights(
    query_tokens: list[str],
    doc_freq: dict,
    total_docs: int,
    base_vec: float = 0.6,
    base_fts: float = 0.4,
) -> tuple[float, float]:
    """
    自适应 RRF 权重 — 基于查询词 IDF 分析。

    核心洞察 (vstash paper):
      - 高 IDF（罕见/技术术语） → 提升关键词权重（精确匹配更重要）
      - 低 IDF（常见词汇）     → 提升向量权重（语义相似更重要）

    对于嵌入式参考手册场景（寄存器名、时序参数等），此优化尤为关键。

    Returns: (vec_weight, fts_weight) 归一化后的权重对
    """
    if not query_tokens or total_docs == 0:
        return base_vec, base_fts

    # 计算查询词的平均 IDF
    idfs = []
    for t in query_tokens:
        df = doc_freq.get(t, 0)
        if df > 0:
            idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
            idfs.append(idf)

    if not idfs:
        return base_vec, base_fts

    mean_idf = sum(idfs) / len(idfs)

    # sigmoid 映射: 将 mean_idf 映射为 fts_weight 的调节因子
    # median_idf 约为 log(N/1) ≈ log(18863) ≈ 9.8
    median_idf = math.log(total_docs) if total_docs > 1 else 1.0
    # sigmoid: 1/(1+exp(-x)), 其中 x = mean_idf - median_idf
    sigmoid = 1.0 / (1.0 + math.exp(-(mean_idf - median_idf)))

    # fts_weight 在 [0.15, 0.85] 范围内根据 IDF 调节
    fts_weight = 0.15 + 0.70 * sigmoid
    vec_weight = 1.0 - fts_weight

    return vec_weight, fts_weight


# ═══════════════════════════════════════════════════════════════
# MMR (Maximal Marginal Relevance) 去重
# vstash 报告: NDCG@5 +1.8%, diversity 3.2→5.0 unique docs
# ═══════════════════════════════════════════════════════════════

def _text_overlap_similarity(text_a: str, text_b: str) -> float:
    """基于文本 token 重叠的快速相似度 (纯 BM25 模式无向量时的回退)"""
    if not text_a or not text_b:
        return 0.0
    ta = set(tokenize(text_a))
    tb = set(tokenize(text_b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _chunk_seq_from_source(chunks: list, source: str) -> dict:
    """从同一 source 的 chunks 建立顺序索引 {chunk_id: seq_number}"""
    siblings = [c for c in chunks if c.source == source]
    return {c.id: i for i, c in enumerate(siblings)}


def mmr_dedup(
    candidates: list[dict],
    lambda_param: float = 0.5,
    use_vectors: bool = False,
    query_vec=None,
) -> list[dict]:
    """
    MMR (Maximal Marginal Relevance) 去重。

    公式: MMR(c) = score(c) - λ * max(sim(c, s) for s in selected)

    - λ=0.5: vstash 默认，平衡相关性与多样性
    - 同一文档的冗余片段被惩罚，鼓励跨文档多样性
    - 当最佳候选 MMR ≤ 0 时停止选择

    candidates: [{"idx": int, "score": float, "chunk": Chunk, ...}, ...]
    """
    if len(candidates) <= 1:
        return candidates

    selected = []
    remaining = list(candidates)

    while remaining:
        # 计算每个剩余候选的 MMR
        mmr_scores = []
        for c in remaining:
            score = c["score"]
            if selected:
                max_sim = 0.0
                for s in selected:
                    if use_vectors and c["chunk"].vector and s["chunk"].vector:
                        try:
                            sim = _vector_cosine_from_bytes(
                                c["chunk"].vector, s["chunk"].vector
                            )
                        except Exception:
                            sim = _text_overlap_similarity(
                                c["chunk"].content, s["chunk"].content
                            )
                    else:
                        sim = _text_overlap_similarity(
                            c["chunk"].content, s["chunk"].content
                        )
                    # same-document bonus: 同文档 chunks 天然相似度高
                    if c["chunk"].source == s["chunk"].source:
                        sim = max(sim, 0.3)  # baseline penalty for same doc
                    max_sim = max(max_sim, sim)
                score -= lambda_param * max_sim
            mmr_scores.append((score, c))

        best_score, best = max(mmr_scores, key=lambda x: x[0])
        if best_score <= 0:
            break
        selected.append(best)
        remaining.remove(best)

    return selected


def _vector_cosine_from_bytes(vec_a: bytes, vec_b: bytes) -> float:
    """两个 bytes 向量间的余弦相似度"""
    import struct
    n = min(len(vec_a), len(vec_b)) // 4
    if n == 0:
        return 0.0
    a = struct.unpack(f'{n}f', vec_a[:n * 4])
    b = struct.unpack(f'{n}f', vec_b[:n * 4])
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ═══════════════════════════════════════════════════════════════
# 上下文扩展 — 匹配块 ±1 相邻块
# vstash 报告: 2.64x 内容量, +0.12ms 开销
# ═══════════════════════════════════════════════════════════════

def expand_context(
    chunk_idx: int,
    chunks: list,
    window: int = 1,
) -> str:
    """
    扩展匹配块的上下文：包含 ±window 个相邻块。

    - 同一文档内的相邻块按 source 字段匹配
    - 按 chunk 在源文档中的顺序确定邻居
    - 返回拼接后的完整上下文文本
    """
    chunk = chunks[chunk_idx]
    source = chunk.source
    # 找到同一 source 的所有 chunks (保持原始顺序)
    siblings = [(i, c) for i, c in enumerate(chunks) if c.source == source]
    # 找到当前 chunk 在 siblings 中的位置
    pos = next((j for j, (i, _) in enumerate(siblings) if i == chunk_idx), None)
    if pos is None:
        return chunk.content

    start = max(0, pos - window)
    end = min(len(siblings), pos + window + 1)
    expanded = []
    for j in range(start, end):
        _, sib = siblings[j]
        prefix = f"[块 {j + 1}/{len(siblings)}] " if j != pos else f"▶ [块 {j + 1}/{len(siblings)}] "
        expanded.append(prefix + sib.content)
    return "\n\n".join(expanded)


def _vector_cosine(query_vec, doc_vec_bytes) -> float:
    """向量余弦相似度"""
    import struct
    n = len(query_vec)
    doc_vec = struct.unpack(f'{n}f', doc_vec_bytes[:n * 4])
    dot = sum(a * b for a, b in zip(query_vec, doc_vec))
    q_norm = math.sqrt(sum(a * a for a in query_vec))
    d_norm = math.sqrt(sum(b * b for b in doc_vec))
    if q_norm == 0 or d_norm == 0:
        return 0.0
    return dot / (q_norm * d_norm)


# ═══════════════════════════════════════════════════════════════
# 跨知识库检索
# ═══════════════════════════════════════════════════════════════

def search_across_kbs(
    query: str,
    kbs: list[KBAdapter],
    top_k: int = 5,
    use_vector: bool = False,
    mix_alpha: float = 0.3,
    use_mmr: bool = True,
    context_window: int = 1,
    adaptive: bool = True,
) -> list[dict]:
    """
    跨多个知识库检索 — 完整管线。

    Pipeline:
      Query → BM25 + Vector → Adaptive RRF Fusion → MMR Dedup → Context Expansion → Top-K

    Args:
        query:           查询字符串
        kbs:             知识库适配器列表
        top_k:           最终返回结果数
        use_vector:      启用向量搜索
        mix_alpha:       向量权重 (仅 non-adaptive 模式)
        use_mmr:         启用 MMR 去重
        context_window:  上下文扩展窗口 (0=关闭)
        adaptive:        启用自适应 RRF 权重 (基于查询 IDF)

    Returns:
        排序后的结果列表，每条含 kb_name 字段标识来源知识库
    """
    if not kbs:
        return [{"error": "没有可用的知识库"}]

    # ── 0. 预加载 embedding model ──
    model = None
    if use_vector:
        try:
            from sentence_transformers import SentenceTransformer
            for mn in ["BAAI/bge-large-zh-v1.5", "BAAI/bge-base-zh-v1.5"]:
                try:
                    m = SentenceTransformer(mn)
                    if m.get_sentence_embedding_dimension() == 1024:
                        model = m
                        break
                except Exception:
                    continue
        except ImportError:
            pass

    query_tokens = tokenize_query(query)
    query_vec = model.encode(query, normalize_embeddings=True) if model else None

    # ── 1. 跨所有 KB 收集 chunk 并建立索引 ──
    # 全局 chunk 列表（跨 KB 统一编号）
    global_chunks: list[Chunk] = []
    global_kb_names: list[str] = []
    # 合并后的 BM25 索引
    all_doc_tokens: list[list[str]] = []
    all_doc_freq: dict = {}
    all_total_tokens = 0

    kb_chunk_ranges: list[tuple[int, int, KBAdapter]] = []  # [(start, end, kb), ...]

    for kb in kbs:
        chunks = kb.load_chunks()
        if not chunks:
            continue
        start = len(global_chunks)
        doc_tokens, doc_freq, total_docs, _avg_len = _build_index(chunks)
        for i, c in enumerate(chunks):
            global_chunks.append(c)
            global_kb_names.append(kb.name)
            all_doc_tokens.append(doc_tokens[i])
        # 合并 doc_freq
        for t, df in doc_freq.items():
            all_doc_freq[t] = all_doc_freq.get(t, 0) + df
        all_total_tokens += sum(len(dt) for dt in doc_tokens)
        kb_chunk_ranges.append((start, len(global_chunks), kb))

    if not global_chunks:
        return [{"error": "知识库中没有数据"}]

    total_docs = len(global_chunks)
    avg_doc_len = all_total_tokens / total_docs if total_docs else 0

    # ── 2. BM25 评分 ──
    bm25_scores: list[tuple[int, float]] = []  # [(global_idx, bm25), ...]
    for i in range(total_docs):
        score = compute_bm25(query_tokens, all_doc_tokens[i],
                             all_doc_freq, total_docs, avg_doc_len)
        if score > 0:
            bm25_scores.append((i, score))
    bm25_scores.sort(key=lambda x: x[1], reverse=True)

    # ── 3. 向量评分（如启用）──
    vec_scores: list[tuple[int, float]] = []
    if query_vec is not None:
        for i in range(total_docs):
            c = global_chunks[i]
            if c.vector:
                try:
                    sim = _vector_cosine(query_vec, c.vector)
                    if sim > 0:
                        vec_scores.append((i, sim))
                except Exception:
                    pass
        vec_scores.sort(key=lambda x: x[1], reverse=True)

    # ── 4. Adaptive RRF 权重 ──
    if adaptive and vec_scores:
        vec_w, fts_w = adaptive_rrf_weights(
            query_tokens, all_doc_freq, total_docs
        )
    elif vec_scores:
        vec_w = mix_alpha
        fts_w = 1.0 - mix_alpha
    else:
        vec_w = 0.0
        fts_w = 1.0

    # ── 5. RRF 融合 ──
    if vec_scores:
        fused = reciprocal_rank_fusion(bm25_scores, vec_scores,
                                       vec_weight=vec_w, fts_weight=fts_w)
    else:
        # 纯 BM25 模式：归一化分数
        max_bm25 = bm25_scores[0][1] if bm25_scores else 1.0
        fused = [(idx, s / max_bm25) for idx, s in bm25_scores]

    # ── 6. 构建候选列表 ──
    # 取 RRF Top-N*3 作为 MMR 输入池 (over-fetch for diversity)
    pool_size = min(len(fused), top_k * 6)
    candidates = []
    for idx, rrf_score in fused[:pool_size]:
        kb_name = global_kb_names[idx]
        candidates.append({
            "idx": idx,
            "score": rrf_score,
            "chunk": global_chunks[idx],
            "kb_name": kb_name,
            "rrf_score": rrf_score,
        })

    # ── 7. MMR 去重 ──
    if use_mmr and len(candidates) > 1:
        candidates = mmr_dedup(candidates, use_vectors=bool(query_vec is not None))

    # ── 8. 上下文扩展 + 构建最终结果 ──
    results = []
    for c in candidates[:top_k]:
        chunk = c["chunk"]
        kb_name = c["kb_name"]
        # 找到对应的 kb adapter 用于 extract_title
        kb = next((k for s, e, k in kb_chunk_ranges
                   if s <= c["idx"] < e), kbs[0])

        content = chunk.content
        if context_window > 0:
            content = expand_context(c["idx"], global_chunks, context_window)

        results.append({
            "score": round(c["score"], 4),
            "content": content,
            "source": kb.extract_title(chunk.source),
            "source_raw": chunk.source,
            "kb_name": kb_name,
            "metadata": chunk.metadata,
            "rrf_score": round(c.get("rrf_score", c["score"]), 4),
            "adaptive_weights": {"vec": round(vec_w, 3), "fts": round(fts_w, 3)}
                if vec_scores else None,
        })

    return results


# ═══════════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════════

def format_results(results: list[dict]) -> str:
    """结果 → 可读文本"""
    if not results:
        return "(知识库无匹配结果)"
    if "error" in results[0]:
        return f"[错误] {results[0]['error']}"

    lines = [f"找到 {len(results)} 条相关片段 (检索管线: BM25 + RRF + MMR + 上下文扩展):\n"]
    for i, r in enumerate(results, 1):
        src_name = os.path.basename(r["source"]) if "\\" in r["source"] else r["source"]
        lines.append(f"─── 结果 {i}  (RRF: {r['score']:.4f})  KB: {r['kb_name']} ───")
        lines.append(f"来源: {src_name}")
        if r.get("adaptive_weights"):
            lines.append(f"自适应权重: 向量={r['adaptive_weights']['vec']:.2f} "
                         f"关键词={r['adaptive_weights']['fts']:.2f}")
        lines.append(f"内容: {r['content'][:800]}")
        if len(r['content']) > 800:
            lines.append(f"... (共 {len(r['content'])} 字符)")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def _filter_kbs(kbs: list[KBAdapter], pattern: str) -> list[KBAdapter]:
    """按名称模式过滤知识库"""
    if not pattern:
        return kbs
    p = pattern.lower()
    return [k for k in kbs if p in k.name.lower()]


def main():
    import argparse
    p = argparse.ArgumentParser(description="通用知识库检索工具")
    p.add_argument("query", nargs="?", default="", help="查询关键词")
    p.add_argument("-k", "--top-k", type=int, default=5, help="返回结果数")
    p.add_argument("--kb", dest="kb_filter", default="",
                   help="仅搜索名称包含此字符串的知识库")
    p.add_argument("--kb-dir", default=os.environ.get("KB_SEARCH_DIR"),
                   help="知识库扫描目录（默认: CherryStudio KnowledgeBase）")
    p.add_argument("--vector", action="store_true", help="启用向量混合搜索")
    p.add_argument("--alpha", type=float, default=0.3,
                   help="向量权重 (0=纯BM25, 1=纯向量) [非自适应模式]")
    p.add_argument("--no-mmr", action="store_true", help="禁用 MMR 去重")
    p.add_argument("--no-expand", action="store_true", help="禁用上下文扩展")
    p.add_argument("--no-adaptive", action="store_true", help="禁用自适应 RRF 权重")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--source-stats", action="store_true", help="显示知识库概览")
    p.add_argument("--list-kbs", action="store_true", help="列出可用知识库")
    p.add_argument("--no-obsidian", action="store_true",
                   help="不自动发现 Obsidian vault")
    p.add_argument("--obsidian-all", action="store_true",
                   help="Obsidian vault 加载所有 .md（默认仅加载嵌入式相关）")
    p.add_argument("--verify", action="store_true",
                   help="对搜索结果执行真伪交叉验证")
    args = p.parse_args()

    # 发现知识库
    kbs = discover_knowledge_bases(args.kb_dir, include_obsidian=not args.no_obsidian)

    # --obsidian-all: 切换 Obsidian KB 为全量加载
    if args.obsidian_all:
        for kb in kbs:
            if isinstance(kb, ObsidianMarkdownKB):
                kb.filter_embedded = False
                kb._chunks = None  # 清除缓存，重新加载

    if not kbs:
        print("未找到任何知识库。请检查 KB_SEARCH_DIR 环境变量或目录内容。", file=sys.stderr)
        sys.exit(1)

    # --list-kbs
    if args.list_kbs:
        print(f"发现 {len(kbs)} 个知识库:\n")
        for kb in kbs:
            stats = kb.get_stats()
            total = stats.get("total_chunks", "?")
            size_mb = os.path.getsize(kb.path) / (1024 * 1024) if os.path.isfile(kb.path) else 0
            print(f"  {kb.name:30s}  {str(total):>6s} chunks  {size_mb:.1f} MB")
        return

    # --source-stats
    if args.source_stats:
        target_kbs = _filter_kbs(kbs, args.kb_filter)
        for kb in target_kbs:
            stats = kb.get_stats()
            print(f"\n═══ {kb.name} ═══")
            print(f"总片段数: {stats.get('total_chunks', 'N/A')}")
            ltypes = stats.get("loader_types", {})
            if ltypes:
                print(f"加载器类型: {', '.join(f'{k}:{v}' for k, v in ltypes.items())}")
            srcs = stats.get("top_sources", [])
            if srcs:
                print("Top 文档来源:")
                for s in srcs[:15]:
                    title = s.get("title", "?")[:80] if isinstance(s, dict) else str(s)[:80]
                    cnt = s.get("chunks", "?") if isinstance(s, dict) else "?"
                    print(f"  [{cnt:>4}] {title}")
        return

    # 搜索
    if not args.query:
        p.print_help()
        return

    target_kbs = _filter_kbs(kbs, args.kb_filter)
    results = search_across_kbs(
        args.query, target_kbs, args.top_k,
        use_vector=args.vector, mix_alpha=args.alpha,
        use_mmr=not args.no_mmr,
        context_window=0 if args.no_expand else 1,
        adaptive=not args.no_adaptive,
    )

    # ── 真伪验证 ──
    if args.verify:
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from verify_claims import verify_search_results, format_verification
            results = verify_search_results(results, verbose=False)
        except ImportError:
            pass  # verify_claims.py 不存在，静默降级

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if args.verify:
            try:
                print(format_verification(results))
            except NameError:
                print(format_results(results))
        else:
            print(format_results(results))


if __name__ == "__main__":
    main()
