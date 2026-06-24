"""
网络拓扑分析器

分析网络连接关系、扇出统计、连通性。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from schema_reader import get_voltage_rail, infer_component_category


def analyze_network(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    网络拓扑分析

    返回:
    {
        "total_nets": N,                    # 总网络数
        "total_wires": N,                   # 总导线数
        "net_summary": [ {net, wires, type, component_count}, ... ],
        "top_nets_by_wire": [...],          # 按导线数排序
        "single_wire_nets": [...],          # 只有一根导线的网络 (可疑)
        "unnamed_nets": N,                  # 未命名的网络数
        "netport_list": [...],              # 所有 netport
        "netflag_list": [...],              # 所有 netflag
        "warnings": [...],
    }
    """
    parts = parsed.get("parts", [])
    wires_by_net = parsed.get("wires_by_net", {})
    named_nets = parsed.get("named_nets", {})
    netports = parsed.get("netports", [])
    netflags = parsed.get("netflags", [])

    total_nets = len(wires_by_net)
    total_wires = sum(len(w) for w in wires_by_net.values())

    # 网络概要
    net_summary = []
    for net_name, wires in sorted(wires_by_net.items(), key=lambda x: -len(x[1])):
        rail = get_voltage_rail(net_name)
        row = {
            "net": net_name or "<unnamed>",
            "wires": len(wires),
            "type": "power" if rail else ("named" if net_name else "unnamed"),
            "voltage_rail": rail or "",
            "component_count": 0,  # 数据限制无法精确计算
        }
        net_summary.append(row)

    # 按导线数排序 top 网络
    top_nets = sorted(net_summary, key=lambda r: -r["wires"])[:10]

    # 单线网络 (可能的设计遗漏)
    single_wire = [n for n in net_summary if n["wires"] == 1 and n["net"] != "<unnamed>"]

    # 未命名网络
    unnamed_count = sum(1 for n in wires_by_net if not n)

    # Netport 列表
    netport_list = [
        {
            "net": np.get("net", ""),
            "x": np.get("x", 0),
            "y": np.get("y", 0),
        }
        for np in netports
    ]

    # Netflag 列表
    netflag_list = [
        {
            "net": nf.get("net", ""),
            "x": nf.get("x", 0),
            "y": nf.get("y", 0),
        }
        for nf in netflags
    ]

    # 警告
    warnings = []
    if total_nets == 0:
        warnings.append("未检测到任何网络")
    if unnamed_count > 0:
        warnings.append(f"存在 {unnamed_count} 个未命名的网络 — 建议命名")
    if len(single_wire) > 3:
        warnings.append(f"存在 {len(single_wire)} 个单线网络 — 检查是否缺少连接")

    # 尝试分组 netport 按信号方向
    netport_grouped: dict[str, list] = defaultdict(list)
    for np in netports:
        net_name = np.get("net", "")
        if net_name:
            netport_grouped[net_name].append(np)

    return {
        "total_nets": total_nets,
        "total_wires": total_wires,
        "net_summary": net_summary,
        "top_nets_by_wire": top_nets,
        "single_wire_nets": single_wire,
        "unnamed_nets": unnamed_count,
        "netport_count": len(netports),
        "netflag_count": len(netflags),
        "netport_grouped": {k: len(v) for k, v in netport_grouped.items()},
        "warnings": warnings,
    }
