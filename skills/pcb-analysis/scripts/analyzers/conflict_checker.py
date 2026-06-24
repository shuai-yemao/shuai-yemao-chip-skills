"""
设计规则冲突检查器

检查引脚冲突、电源问题、悬空网络等设计隐患。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from schema_reader import get_voltage_rail, infer_component_category


def check_conflicts(parsed: dict[str, Any],
                    bom_result: dict[str, Any] | None = None,
                    power_result: dict[str, Any] | None = None,
                    pin_result: dict[str, Any] | None = None,
                    net_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    综合设计规则检查

    返回:
    {
        "issues": [
            { "severity": "error"|"warning"|"info",
              "category": "power"|"pin"|"net"|"bom"|"general",
              "message": "...",
              "detail": "..." },
        ],
        "summary": { "errors": N, "warnings": N, "infos": N },
        "critical_issues": [...],
    }
    """
    issues: list[dict[str, str]] = []
    parts = parsed.get("parts", [])

    # ---- 1. BOM 检查 ----
    if bom_result:
        lcsc_parts = bom_result.get("lcsc_parts", [])
        # 查找缺少采购编号的器件
        for row in bom_result.get("bom_table", []):
            if not row.get("supplierId") and row.get("addIntoBom"):
                ref = row["ref"]
                if ref.startswith(("SCREW", "MH")):
                    continue  # 结构件不要求 LCSC 编号
                issues.append({
                    "severity": "warning",
                    "category": "bom",
                    "message": f"{ref}: 缺少 LCSC 采购编号 (supplierId)",
                    "detail": f"器件 {ref} ({row['name']}) 未指定 LCSC 型号",
                })

    # ---- 2. 电源检查 ----
    if power_result:
        rails = power_result.get("rails", {})
        regulators = power_result.get("regulators", [])
        warnings = power_result.get("warnings", [])
        for w in warnings:
            issues.append({
                "severity": "warning",
                "category": "power",
                "message": w,
                "detail": "",
            })

        if "GND" not in rails and "GND" not in str(rails):
            issues.append({
                "severity": "error",
                "category": "power",
                "message": "未检测到 GND 网络 — 原理图可能不完整",
                "detail": "所有电路都需要接地参考",
            })

        # 检查是否有 VDD 而没有对应去耦电容
        has_vdd = any("VDD" in r or "3V3" in r or "3.3V" in r for r in rails)
        if has_vdd:
            cap_count = sum(1 for p in parts if infer_component_category(p) == "capacitor")
            if cap_count == 0:
                issues.append({
                    "severity": "warning",
                    "category": "power",
                    "message": "未检测到任何电容 — 缺少电源去耦电容",
                    "detail": "建议在每个 IC 的电源引脚附近放置 100nF 去耦电容",
                })

        # 检查多重电源轨间是否有关联
        if len(rails) > 1:
            rail_names = list(rails.keys())
            if "3.3V" in rail_names and "5V" not in rail_names:
                pass  # 仅有 3.3V 也是可以的 (电池供电)
            if "5V" in rail_names and "3.3V" not in rail_names:
                if any("STM" in str(p.get("manufacturerId", "")).upper() for p in parts):
                    issues.append({
                        "severity": "error",
                        "category": "power",
                        "message": "STM32 MCU 需要 3.3V 供电，但未检测到 3.3V 电源轨",
                        "detail": "STM32 MCU 的标准 VDD 为 2.0V~3.6V，通常使用 3.3V",
                    })

    # ---- 3. 网络检查 ----
    if net_result:
        if net_result.get("unnamed_nets", 0) > 0:
            issues.append({
                "severity": "info",
                "category": "net",
                "message": f"存在 {net_result['unnamed_nets']} 个未命名网络",
                "detail": "未命名网络可能导致网表导出和查错困难",
            })

        single_wire = net_result.get("single_wire_nets", [])
        for sw in single_wire[:5]:
            issues.append({
                "severity": "info",
                "category": "net",
                "message": f"网络 '{sw['net']}' 只有一条导线 — 检查是否完整",
                "detail": "单线网络可能表示未完成的连接",
            })

    # ---- 4. 引脚检查 ----
    if pin_result:
        for w in pin_result.get("warnings", []):
            issues.append({
                "severity": "warning",
                "category": "pin",
                "message": w,
                "detail": "",
            })

    # ---- 5. 通用检查 ----
    # 检查重复的 designator
    des_list = [p.get("designator", "?") for p in parts if p.get("componentType") == "part"]
    des_counts = Counter(des_list)
    for des, count in des_counts.items():
        if count > 1 and des != "?":
            issues.append({
                "severity": "error",
                "category": "general",
                "message": f"发现重复的位号: {des} (出现 {count} 次)",
                "detail": "每个位号在 BOM 中只能出现一次",
            })

    # 检查是否有器件不在 BOM 中
    for p in parts:
        if p.get("componentType") == "part" and not p.get("addIntoBom", True):
            issues.append({
                "severity": "info",
                "category": "bom",
                "message": f"{p.get('designator', '?')} 未加入 BOM (addIntoBom=false)",
                "detail": "该器件不会出现在 BOM 和采购清单中",
            })

    # ---- 统计 ----
    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    info_count = sum(1 for i in issues if i["severity"] == "info")

    critical = [i for i in issues if i["severity"] == "error"]

    return {
        "issues": issues,
        "summary": {
            "errors": error_count,
            "warnings": warning_count,
            "infos": info_count,
            "total": len(issues),
        },
        "critical_issues": critical,
    }
