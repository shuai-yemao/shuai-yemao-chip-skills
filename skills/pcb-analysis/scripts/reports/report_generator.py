"""
报告生成器

将分析结果格式化为结构化的 ASCII 文本报告。
"""
from __future__ import annotations

from typing import Any


def generate_text_report(parsed: dict[str, Any],
                         bom: dict[str, Any],
                         power: dict[str, Any],
                         pinmap: dict[str, Any],
                         net: dict[str, Any],
                         conflict: dict[str, Any]) -> str:
    """生成完整的 ASCII 文本分析报告"""
    lines: list[str] = []
    width = 70

    def sep(title: str = ""):
        if title:
            lines.append("=" * width)
            lines.append(title)
            lines.append("=" * width)
        else:
            lines.append("-" * width)

    def kv(key: str, value: Any, indent: int = 0):
        pad = "  " * indent
        lines.append(f"{pad}{key}: {value}")

    # ==============================
    # HEADER
    # ==============================
    sep("PCB SCHEMATIC ANALYSIS REPORT")
    adapter = parsed.get("adapter", "unknown")
    counts = parsed.get("counts", {})
    kv("Adapter", adapter)
    kv("Components", counts.get("components", 0))
    kv("Wires", counts.get("wires", 0))
    kv("Nets (unique)", net.get("total_nets", 0))
    lines.append("")

    # ==============================
    # BOM
    # ==============================
    sep("BILL OF MATERIALS")
    kv("Total parts", bom.get("total_parts", 0))

    cat = bom.get("count_by_category", {})
    kv("By category", ", ".join(f"{k}={v}" for k, v in sorted(cat.items())))
    lines.append("")

    # BOM 表格
    if bom.get("bom_table"):
        lines.append(f"  {'Ref':6s} {'Name':35s} {'LCSC':12s} {'Category':12s}")
        lines.append(f"  {'-'*6} {'-'*35} {'-'*12} {'-'*12}")
        for row in bom["bom_table"]:
            ref = row["ref"]
            name = row["name"][:35]
            lcsc = row["supplierId"][:12] if row["supplierId"] else "-"
            cat_name = row["category"][:12]
            lines.append(f"  {ref:6s} {name:35s} {lcsc:12s} {cat_name:12s}")
    lines.append("")

    # ==============================
    # POWER TREE
    # ==============================
    sep("POWER TREE")
    rails = power.get("rails", {})
    if rails:
        kv("Voltage rails", len(rails))
        lines.append("")
        lines.append(f"  {'Rail':12s} {'Nets':30s} {'Wires':6s}")
        lines.append(f"  {'-'*12} {'-'*30} {'-'*6}")
        for rail_name, rail_data in sorted(rails.items()):
            net_str = ", ".join(rail_data["nets"][:5])
            if len(rail_data["nets"]) > 5:
                net_str += f" ...(+{len(rail_data['nets'])-5})"
            kv(rail_name, f"{net_str:30s} {rail_data['wire_count']:3d}w", indent=0)
            # 用 line 模拟固定列格式
    else:
        kv("Voltage rails", "None detected")
    lines.append("")

    if power.get("regulators"):
        kv("Regulators", len(power["regulators"]))
        for reg in power["regulators"]:
            kv("", f"{reg['ref']:6s} {reg['name']}")
    lines.append("")

    if power.get("warnings"):
        sep("POWER WARNINGS")
        for w in power["warnings"]:
            lines.append(f"  [!] {w}")
        lines.append("")

    # ==============================
    # PIN ASSIGNMENT
    # ==============================
    sep("MCU PIN ASSIGNMENT")
    mcu = pinmap.get("mcu")
    if mcu:
        kv("MCU", f"{mcu['name']} ({mcu['ref']})")
        if mcu.get("datasheet"):
            kv("Datasheet", mcu["datasheet"])
    else:
        kv("MCU", "Not detected")
        lines.append("")
        lines.append(f"  [!] {pinmap.get('error', 'Unknown')}")

    lines.append("")
    periph = pinmap.get("peripheral_nets", {})
    if periph:
        kv("Detected peripherals", len(periph))
        lines.append("")
        for peri_name, signals in sorted(periph.items()):
            signal_str = ", ".join(f"{k}={v}" for k, v in signals.items())
            lines.append(f"  {peri_name:15s}: {signal_str}")
    lines.append("")

    cls = pinmap.get("classified_count", {})
    kv("GPIO-like nets", cls.get("gpio", 0))
    kv("Power nets", cls.get("power", 0))
    kv("Unrecognized nets", cls.get("other", 0))
    lines.append("")

    # ==============================
    # NETWORK ANALYSIS
    # ==============================
    sep("NETWORK ANALYSIS")
    kv("Total networks", net.get("total_nets", 0))
    kv("Total wires", net.get("total_wires", 0))
    kv("Unnamed nets", net.get("unnamed_nets", 0))
    kv("Netports", net.get("netport_count", 0))
    kv("Netflags", net.get("netflag_count", 0))
    lines.append("")

    # Top nets by wire count
    top = net.get("top_nets_by_wire", [])
    if top:
        lines.append("  Top networks by wire count:")
        lines.append(f"  {'Net':25s} {'Wires':6s} {'Type':10s}")
        lines.append(f"  {'-'*25} {'-'*6} {'-'*10}")
        for n in top[:8]:
            lines.append(f"  {n['net']:25s} {n['wires']:4d}w  {n['type']:10s}")
    lines.append("")

    # Warnings
    if net.get("warnings"):
        sep("NETWORK WARNINGS")
        for w in net["warnings"]:
            lines.append(f"  [!] {w}")
        lines.append("")

    # ==============================
    # DESIGN RULE CHECK
    # ==============================
    sep("DESIGN RULE CHECK")
    summary = conflict.get("summary", {})
    kv("Errors", summary.get("errors", 0))
    kv("Warnings", summary.get("warnings", 0))
    kv("Infos", summary.get("infos", 0))
    lines.append("")

    issues = conflict.get("issues", [])
    if issues:
        for issue in issues:
            sev = {
                "error": "[X]",
                "warning": "[!]",
                "info": "[?]",
            }.get(issue["severity"], "[?]")
            cat = issue["category"].upper()
            msg = issue["message"]
            lines.append(f"  {sev} [{cat}] {msg}")
    else:
        lines.append("  No issues detected.")
    lines.append("")

    # ==============================
    # FOOTER
    # ==============================
    sep()
    lines.append("")

    return "\n".join(lines)


def generate_json_report(parsed: dict[str, Any],
                         bom: dict[str, Any],
                         power: dict[str, Any],
                         pinmap: dict[str, Any],
                         net: dict[str, Any],
                         conflict: dict[str, Any]) -> str:
    """生成 JSON 格式报告 (供程序解析)"""
    import json
    report = {
        "meta": {
            "adapter": parsed.get("adapter", ""),
            "component_count": parsed.get("counts", {}).get("components", 0),
            "wire_count": parsed.get("counts", {}).get("wires", 0),
        },
        "bom": {
            "total_parts": bom.get("total_parts", 0),
            "count_by_category": bom.get("count_by_category", {}),
            "parts": bom.get("bom_table", []),
        },
        "power": {
            "rails": power.get("rails", {}),
            "regulators": power.get("regulators", []),
            "warnings": power.get("warnings", []),
        },
        "pin_mapping": {
            "mcu": pinmap.get("mcu"),
            "peripherals": pinmap.get("peripheral_nets", {}),
            "gpio_nets": pinmap.get("gpio_like_nets", []),
            "classified_counts": pinmap.get("classified_count", {}),
        },
        "network": {
            "total_nets": net.get("total_nets", 0),
            "total_wires": net.get("total_wires", 0),
            "unnamed_nets": net.get("unnamed_nets", 0),
            "top_nets": net.get("top_nets_by_wire", []),
            "warnings": net.get("warnings", []),
        },
        "design_rules": {
            "summary": conflict.get("summary", {}),
            "issues": conflict.get("issues", []),
        },
    }
    return json.dumps(report, indent=2, ensure_ascii=False)
