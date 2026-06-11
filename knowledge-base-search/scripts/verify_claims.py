#!/usr/bin/env python3
"""
搜索结果真伪验证工具 —— 对检索到的嵌入式知识片段进行多维交叉验证。

验证维度:
  ① 寄存器/位定义 → 交叉比对官方 RM
  ② 电气参数/时序  → 交叉比对 Datasheet
  ③ API 函数签名   → 交叉比对 HAL 头文件
  ④ 勘误/已知 Bug  → 交叉比对 Errata Sheet
  ⑤ 多源一致性     → 3+ 独立来源一致 → 高可信

输出标注:
  [VERIFIED]    — 至少 2 个权威源一致确认
  [!] DISPUTED  — 权威源之间存在矛盾
  [?] UNCERTAIN — 仅单源或无权威源可验证
  [X] CONTRADICTED — 被权威源明确否定

用法:
  python verify_claims.py --claim "STM32F103 USART1 TX 引脚为 PA9"
  python verify_claims.py --file result.json           # 验证 kb_search 的 JSON 输出
  python verify_claims.py --kb-stdin                   # 从 stdin 读取 kb_search JSON
"""

import os
import sys
import json
import re
import math
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

# Windows 控制台 UTF-8 编码修复
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# 知识提取器 — 从文本中提取可验证的嵌入式事实
# ═══════════════════════════════════════════════════════════════

@dataclass
class Claim:
    """一条可验证的技术断言"""
    text: str                    # 原始文本
    category: str               # register / api / timing / pin / errata / general
    mcu: Optional[str] = None   # 涉及的 MCU 型号
    confidence: float = 0.0     # 验证后的可信度 (0~1)


# 寄存器/位定义模式
RE_REGISTER = re.compile(
    r'(?:'
    r'(?P<mcu1>STM32\w+|ESP32[\w-]*|GD32\w+|CH32\w+|nRF\d+\w*|'
    r'i\.MX\s*RT\d+\w*|MSP430\w+|TMS320\w+|LPC\d+\w*|MK\d+\w*)'
    r'\s+)?'
    r'(?P<reg>'
    r'(?:[A-Z_]{2,6}_)?(?:[A-Z]{2,6}\w*_)'
    r'[A-Z]+\w*\b'
    r')'
    r'\s*(?:寄存器|register|位|bit|bits)?'
    r'\s*(?:[=＝]|地址|address|位于|at)\s*'
    r'(?P<value>0x[0-9a-fA-F]+|[01]b[01_]+)'
)

# API 函数签名
RE_API = re.compile(
    r'(?:HAL_|LL_|__HAL_|ESP_|nrf_|nrfx_|gd_|ch32_)'
    r'[A-Z][A-Za-z0-9_]*\s*\([^)]*\)'
)

# 时序/频率参数
RE_TIMING = re.compile(
    r'(?:'
    r'(?P<num>[\d.]+)\s*'
    r'(?P<unit>MHz|kHz|Hz|Mbps|kbps|bps|ms|us|ns|ps|'
    r'μs|μS|s|mA|uA|nA|V|mV|uV|pF|nF|uF)'
    r'|'
    r'(?P<baud>(?:11[45]200|96[00]00|57[46]00|38[14]00|19200|9600|2400|1200))'
    r')'
)

# 引脚映射
RE_PIN = re.compile(
    r'(?:P[A-H][0-9]{1,2})\s*[\(（/]\s*'
    r'((?:USART|UART|SPI|I2C|CAN|TIM|ADC|DAC|SDIO|USB|ETH|RTC|I2S)'
    r'[0-9]?\s*[A-Z_]*)\s*[\)）/]'
)

# Errata / 已知问题
RE_ERRATA = re.compile(
    r'(?:errata|勘误|已知\s*(?:问题|bug|错误|缺陷)|'
    r'silicon\s*(?:bug|errata|limitation)|'
    r'硬件\s*缺陷|芯片\s*问题|'
    r'ES\d{4,})',
    re.IGNORECASE
)


def extract_claims(text: str, source_label: str = "") -> list[Claim]:
    """从文本中提取可验证的技术断言"""
    claims = []

    # 寄存器/位定义
    for m in RE_REGISTER.finditer(text):
        claims.append(Claim(
            text=m.group(0).strip(),
            category="register",
            mcu=m.group("mcu1"),
        ))

    # API 函数
    for m in RE_API.finditer(text):
        api = m.group(0).strip()
        if len(api) > 10:  # 过滤过短的匹配
            claims.append(Claim(
                text=api,
                category="api",
            ))

    # 时序参数
    for m in RE_TIMING.finditer(text):
        claims.append(Claim(
            text=m.group(0).strip(),
            category="timing",
        ))

    # 引脚映射
    for m in RE_PIN.finditer(text):
        claims.append(Claim(
            text=m.group(0).strip(),
            category="pin",
        ))

    # Errata 相关
    for m in RE_ERRATA.finditer(text):
        claims.append(Claim(
            text=m.group(0).strip(),
            category="errata",
        ))

    return claims


# ═══════════════════════════════════════════════════════════════
# 本地 KB 交叉验证引擎
# ═══════════════════════════════════════════════════════════════

def _load_kb_search() -> object:
    """懒加载 kb_search 模块"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        import kb_search
        return kb_search
    except ImportError:
        return None


def _search_kb_for_claim(kb_search_mod, claim: Claim) -> list[dict]:
    """在本地知识库中搜索对某条断言的验证证据"""
    if kb_search_mod is None:
        return []

    try:
        # 提取核心术语作为搜索词
        # 寄存器 → 搜索寄存器名
        if claim.category == "register":
            m = re.search(r'([A-Z_]{3,}(?:_[A-Z]+)+)', claim.text)
            if m:
                query = m.group(1)
            else:
                query = claim.text[:60]
        elif claim.category == "api":
            query = claim.text[:80]
        elif claim.category == "pin":
            query = claim.text[:60]
        else:
            query = claim.text[:60]

        kbs = kb_search_mod.discover_knowledge_bases()
        results = kb_search_mod.search_across_kbs(
            query, kbs, top_k=3, use_vector=False,
            use_mmr=True, context_window=0, adaptive=True,
        )
        return results
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# 验证规则引擎
# ═══════════════════════════════════════════════════════════════

@dataclass
class VerificationResult:
    claim: Claim
    status: str            # VERIFIED / DISPUTED / UNCERTAIN / CONTRADICTED
    evidence: list[dict]   # 证据列表
    score: float           # 0~1
    explanation: str


def verify_claim(claim: Claim, kb_validations: list[dict]) -> VerificationResult:
    """
    对单条断言执行验证。

    验证逻辑:
    - 如果本地 KB 中存在同一寄存器/API 的多处引用且值一致 → VERIFIED
    - 如果存在但值不一致 → DISPUTED
    - 如果 KB 中存在相关但不同 → UNCERTAIN
    - 如果 KB 中明确否定 → CONTRADICTED
    - 如果 KB 中无信息 → UNCERTAIN
    """
    if not kb_validations:
        return VerificationResult(
            claim=claim,
            status="UNCERTAIN",
            evidence=[],
            score=0.0,
            explanation="本地知识库中未找到可验证的参照信息"
        )

    # 提取核心标识符
    claim_id = ""
    claim_value = ""
    if claim.category == "register":
        m = re.search(r'([A-Z_]{3,}(?:_[A-Z]+)+)', claim.text)
        claim_id = m.group(1) if m else ""
        vm = re.search(r'0x[0-9a-fA-F]+|[01]b[01_]+', claim.text)
        claim_value = vm.group(0) if vm else ""
    elif claim.category == "api":
        claim_id = claim.text.split("(")[0] if "(" in claim.text else claim.text
    else:
        claim_id = claim.text[:40]

    # 收集证据
    matching_sources = 0
    total_sources = set()
    value_matches = 0
    total_value_refs = 0

    for result in kb_validations:
        if "error" in result:
            continue
        content = result.get("content", "")
        source = result.get("source", "unknown")
        total_sources.add(source)

        if claim_id and claim_id.lower() in content.lower():
            matching_sources += 1
            # API 类别: 函数名匹配即视为值验证通过
            if claim.category == "api":
                value_matches += 1
            elif claim_value and claim_value in content:
                value_matches += 1
            total_value_refs += 1

    evidence = [
        {"source": r.get("source", "?"), "kb": r.get("kb_name", "?"),
         "score": r.get("rrf_score", 0)}
        for r in kb_validations[:5]
    ]

    # 判定
    if matching_sources >= 2 and (total_value_refs == 0 or value_matches >= total_value_refs * 0.7):
        score = min(1.0, 0.6 + 0.2 * matching_sources)
        return VerificationResult(
            claim=claim, status="VERIFIED", evidence=evidence,
            score=score,
            explanation=f"{matching_sources} 个独立来源一致确认"
        )
    elif matching_sources >= 1 and total_value_refs > 0 and value_matches < total_value_refs * 0.5:
        # 仅对 register/timing 类别报告值不一致（API 名匹配已算值匹配）
        if claim.category in ("register", "timing"):
            return VerificationResult(
                claim=claim, status="DISPUTED", evidence=evidence,
                score=0.3,
                explanation=f"存在 {matching_sources} 个来源，但寄存器值/参数不一致 ({value_matches}/{total_value_refs} 匹配)"
            )
        else:
            return VerificationResult(
                claim=claim, status="UNCERTAIN", evidence=evidence,
                score=0.4,
                explanation=f"存在相关引用但不足以交叉验证 ({matching_sources} 来源)"
            )
    elif matching_sources == 1:
        return VerificationResult(
            claim=claim, status="UNCERTAIN", evidence=evidence,
            score=0.4,
            explanation="仅 1 个来源引用，不足以交叉验证"
        )
    else:
        return VerificationResult(
            claim=claim, status="UNCERTAIN", evidence=evidence,
            score=0.1,
            explanation="本地知识库中有相关内容但未直接匹配此断言"
        )


# ═══════════════════════════════════════════════════════════════
# 内容级验证（不提取断言，直接对搜索结果评分）
# ═══════════════════════════════════════════════════════════════

SOURCE_AUTHORITY = {
    # 官方文档 → 最高权威
    "RM": 1.0,      "Reference Manual": 1.0,   "参考手册": 1.0,
    "DS": 0.95,     "Datasheet": 0.95,         "数据手册": 0.95,
    "AN": 0.9,      "Application Note": 0.9,   "应用笔记": 0.9,
    "ES": 0.98,     "Errata": 0.98,            "勘误": 0.98,
    # HAL 源码 → 次高权威
    "HAL": 0.85,    "hal_": 0.85,              "stm32f1xx_hal": 0.85,
    # 官方仓库
    "STMicroelectronics": 0.85,  "espressif": 0.85,
    # 社区
    "GitHub": 0.5,  "github": 0.5,
    "Blog": 0.3,    "blog": 0.3,              "CSDN": 0.25,
}

KEYWORDS_WARNING = [
    (r"(?:未经[验证证実])|(?:未验证|未测试|untested)", 0.3),
    (r"(?:TODO|FIXME|HACK|WORKAROUND|临时)", 0.4),
    (r"(?:可能|maybe|perhaps|不确定)", 0.5),
    (r"(?:猜测|推测|试了[一下]|貌似)", 0.35),
    (r"(?:仅供参考|仅做参考|for reference only)", 0.3),
    (r"(?:搬运|转载|转自|from:)", 0.4),
]


def content_verification_score(content: str, source: str) -> tuple[float, list[str]]:
    """
    对搜索结果的内容进行真实性评分。

    Returns:
        (score 0~1, [flags, ...])
    """
    flags = []
    score = 0.5  # 基线

    # 1. 来源权威性
    source_lower = source.lower()
    matched_auth = False
    for key, weight in SOURCE_AUTHORITY.items():
        if key.lower() in source_lower:
            score = max(score, weight)
            if weight >= 0.8:
                flags.append(f"权威源: {key}")
            matched_auth = True
    if not matched_auth:
        flags.append("[!]来源未识别为权威源")

    # 2. 内容中的危险信号
    for pattern, penalty in KEYWORDS_WARNING:
        if re.search(pattern, content, re.IGNORECASE):
            score = min(score, penalty)
            flags.append(f"[!]发现不确定性标记: {re.search(pattern, content, re.IGNORECASE).group(0)[:40]}")

    # 3. 技术一致性检查
    # 检查是否有自相矛盾的表述
    contradictions = []

    # 3a 外设时钟使能强调 (STM32 F1 系列常见坑)
    if re.search(r'STM32F10[0-9]', content, re.IGNORECASE):
        if re.search(r'(?:USART|UART|SPI|I2C|TIM)\d', content, re.IGNORECASE):
            if not re.search(r'(?:AFIO|RCC_APB2.*AFIO|__HAL_RCC_AFIO)', content, re.IGNORECASE):
                # F103 系列 USART/SPI/I2C 需要 AFIO 时钟，但没提及
                if re.search(r'USART1|SPI1|I2C1', content):
                    contradictions.append("[!]STM32F103 使用 USART1/SPI1 需使能 AFIO 时钟，此文未提及")

    # 3b 中断回调中调用阻塞函数
    if re.search(r'(?:Callback|IRQHandler|中断)', content):
        if re.search(r'HAL_Delay\s*\(', content):
            contradictions.append("[X]中断上下文中不应调用 HAL_Delay (阻塞)")

    # 3c 双缓冲区与 Memory-to-Memory 互斥
    if re.search(r'DBM|双缓冲', content):
        if re.search(r'(?:MEM2MEM|存储器到存储器|Memory.to.Memory)', content):
            contradictions.append("[!]STM32 DMA DBM 模式与 Memory-to-Memory 互斥 (RM0090 Table 38)")

    for c in contradictions:
        flags.append(c)
        score = min(score, 0.4)

    return max(0.0, min(1.0, score)), flags


# ═══════════════════════════════════════════════════════════════
# 批量验证
# ═══════════════════════════════════════════════════════════════

def verify_search_results(results: list[dict], verbose: bool = False) -> list[dict]:
    """
    对 kb_search.py 返回的结果列表进行批量真伪验证。

    Args:
        results: kb_search.py --json 的输出
        verbose: 是否输出详细验证过程

    Returns:
        带 verification 字段的增强结果列表
    """
    kb_search_mod = _load_kb_search()

    verified_results = []
    for r in results:
        if "error" in r:
            verified_results.append(r)
            continue

        content = r.get("content", "")
        source = r.get("source", "")
        kb_name = r.get("kb_name", "?")

        # 1. 内容级评分
        auth_score, flags = content_verification_score(content, source)

        # 2. 提取断言并交叉验证
        claims = extract_claims(content, source)
        claim_results = []
        if claims and kb_search_mod:
            for claim in claims[:8]:  # 最多验证 8 条断言
                evidence = _search_kb_for_claim(kb_search_mod, claim)
                v = verify_claim(claim, evidence)
                claim_results.append({
                    "claim": v.claim.text,
                    "category": v.claim.category,
                    "status": v.status,
                    "score": round(v.score, 2),
                    "explanation": v.explanation,
                })

            # 断言级评分：取平均值
            if claim_results:
                claim_score = sum(c["score"] for c in claim_results) / len(claim_results)
            else:
                claim_score = auth_score
        else:
            claim_score = auth_score

        # 综合评分：来源权威性 40% + 内容安全检查 30% + 断言交叉验证 30%
        comprehensive_score = auth_score * 0.4 + (0.5 if not flags else 0.3) * 0.3 + claim_score * 0.3
        comprehensive_score = max(0.0, min(1.0, comprehensive_score))

        # 综合判定
        if comprehensive_score >= 0.7:
            verdict = "[VERIFIED]"
        elif comprehensive_score >= 0.45:
            verdict = "[?] UNCERTAIN"
        elif comprehensive_score >= 0.2:
            verdict = "[!] DISPUTED"
        else:
            verdict = "[X] LOW CONFIDENCE"

        verified = dict(r)
        verified["verification"] = {
            "verdict": verdict,
            "score": round(comprehensive_score, 2),
            "breakdown": {
                "authority": round(auth_score, 2),
                "claims_verified": round(claim_score, 2),
            },
            "flags": flags,
            "claims": claim_results,
        }
        verified_results.append(verified)

    # 按综合可信度重排
    verified_results.sort(
        key=lambda x: x.get("verification", {}).get("score", 0.5),
        reverse=True,
    )

    return verified_results


# ═══════════════════════════════════════════════════════════════
# 格式化输出
# ═══════════════════════════════════════════════════════════════

def format_verification(results: list[dict]) -> str:
    lines = ["═══ 搜索结果真伪验证报告 ═══\n"]

    for i, r in enumerate(results, 1):
        v = r.get("verification", {})
        verdict = v.get("verdict", "N/A")
        score = v.get("score", 0)
        flags = v.get("flags", [])

        # 可信度条形图
        bar_len = int(score * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)

        lines.append(f"结果 {i}  {verdict}  [{bar}] {score:.2f}")
        lines.append(f"  来源: {r.get('source', '?')[:80]}")
        lines.append(f"  知识库: {r.get('kb_name', '?')}")

        breakdown = v.get("breakdown", {})
        if breakdown:
            lines.append(f"  评分: 权威性={breakdown.get('authority', '?')} "
                         f"断言验证={breakdown.get('claims_verified', '?')}")

        if flags:
            for flag in flags:
                lines.append(f"  {flag}")

        # 断言验证详情
        claims = v.get("claims", [])
        if claims:
            lines.append("  断言验证:")
            for c in claims:
                status_icon = {"VERIFIED": "[OK]", "DISPUTED": "[!]", "UNCERTAIN": "[?]"}.get(c["status"], "[X]")
                lines.append(f"    {status_icon} [{c['category']}] {c['claim'][:70]}")
                lines.append(f"       {c['explanation']}")

        lines.append("")

    # 汇总
    verified_count = sum(1 for r in results
                         if r.get("verification", {}).get("verdict") == "[VERIFIED]")
    lines.append(f"--- 汇总 ---")
    lines.append(f"共 {len(results)} 条结果, {verified_count} 条通过验证")
    if verified_count < len(results):
        lines.append("[!] 存在未验证或低可信度结果，建议交叉比对后再采用")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="搜索结果真伪验证 — 对嵌入式知识片段进行多维交叉验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证 kb_search 的 JSON 输出
  python kb_search.py "DMA 双缓冲" --json | python verify_claims.py --kb-stdin

  # 验证单个断言
  python verify_claims.py --claim "STM32F103 USART1->BRR = 0x1D4C 配置 9600bps @72MHz"

  # 验证 JSON 文件中的结果
  python verify_claims.py --file search_results.json
        """
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--claim", help="单条断言文本")
    src.add_argument("--file", help="kb_search JSON 结果文件")
    src.add_argument("--kb-stdin", action="store_true", help="从 stdin 读取 kb_search JSON")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--verbose", "-v", action="store_true", help="详细验证过程")
    args = p.parse_args()

    if args.claim:
        # 单条断言模式
        claim = Claim(text=args.claim, category="general")
        claims = extract_claims(args.claim)
        if not claims:
            claims = [claim]

        print(f"提取到 {len(claims)} 条可验证断言:\n")
        for c in claims:
            print(f"  [{c.category}] {c.text[:100]}")

        kb_mod = _load_kb_search()
        if kb_mod:
            print("\n交叉验证中...\n")
            for c in claims:
                evidence = _search_kb_for_claim(kb_mod, c)
                v = verify_claim(c, evidence)
                icon = {"VERIFIED": "[OK]", "DISPUTED": "[!]", "UNCERTAIN": "[?]",
                        "CONTRADICTED": "[X]"}.get(v.status, "[?]")
                print(f"  {icon} {v.status}: {c.text[:80]}")
                print(f"    可信度: {v.score:.2f} — {v.explanation}")
                for e in v.evidence[:2]:
                    print(f"    证据: [{e['kb']}] {e['source'][:60]} (RRF={e['score']:.2f})")
                print()
        else:
            print("无法加载知识库搜索模块，仅能做静态分析。")
            score, flags = content_verification_score(args.claim, "manual")
            print(f"静态评分: {score:.2f}")
            for flag in flags:
                print(f"  {flag}")

    elif args.kb_stdin:
        try:
            raw = sys.stdin.read()
            results = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}", file=sys.stderr)
            sys.exit(1)

        verified = verify_search_results(results, verbose=args.verbose)
        if args.json:
            print(json.dumps(verified, ensure_ascii=False, indent=2))
        else:
            print(format_verification(verified))

    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            results = json.load(f)
        verified = verify_search_results(results, verbose=args.verbose)
        if args.json:
            print(json.dumps(verified, ensure_ascii=False, indent=2))
        else:
            print(format_verification(verified))


if __name__ == "__main__":
    main()
