"""
BOM 分析器

提取物料清单、器件分类、采购信息。
"""
from __future__ import annotations

from typing import Any

from schema_reader import infer_component_category


def analyze_bom(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    BOM 分析入口

    返回:
    {
        "total_parts": 38,
        "categories": { "MCU": [...], "connector": [...], ... },
        "bom_table": [ {ref, name, mfr, mfr_id, supplier_id, category}, ... ],
        "count_by_category": { "MCU": 1, "connector": 8, ... },
        "lcsc_parts": [ {ref, supplier_id, name}, ... ],
    }
    """
    parts = parsed.get("parts", [])

    # 分类所有器件
    categories: dict[str, list[dict]] = {}
    bom_rows = []
    for p in parts:
        cat = infer_component_category(p)
        if cat not in categories:
            categories[cat] = []

        row = {
            "ref": p.get("designator", "?"),
            "name": _resolve_name(p),
            "manufacturer": p.get("manufacturer", ""),
            "manufacturerId": p.get("manufacturerId", ""),
            "supplier": p.get("supplier", ""),
            "supplierId": p.get("supplierId", ""),
            "category": cat,
            "x": p.get("x", 0),
            "y": p.get("y", 0),
            "addIntoBom": p.get("addIntoBom", True),
            "datasheet": _get_datasheet(p),
        }
        categories[cat].append(row)
        bom_rows.append(row)

    # 统计
    count_by_cat = {cat: len(items) for cat, items in categories.items()}

    # LCSC 采购部件
    lcsc_parts = [
        r for r in bom_rows if r["supplierId"] and r["supplierId"].strip()
    ]

    return {
        "total_parts": len(parts),
        "categories": categories,
        "bom_table": bom_rows,
        "count_by_category": count_by_cat,
        "lcsc_parts": lcsc_parts,
    }


def _resolve_name(part: dict) -> str:
    """获取最可读的器件名称"""
    candidates = [
        part.get("name"),
        part.get("subPartName"),
        part.get("manufacturerId"),
    ]
    for c in candidates:
        if c and c.strip() and "=" not in c:
            # 去掉 .1 .2 等子部件序号
            return c.split(".")[0] if c.count(".") == 1 and len(c.split(".")[1]) <= 2 else c
    return part.get("designator", "?")


def _get_datasheet(part: dict) -> str:
    """从 otherProperty 中提取数据手册 URL"""
    other = part.get("otherProperty", {})
    if isinstance(other, dict):
        return other.get("Datasheet", "")
    return ""
