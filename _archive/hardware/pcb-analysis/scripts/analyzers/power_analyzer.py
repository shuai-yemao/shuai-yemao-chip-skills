"""
电源树分析器

识别电压轨、追踪电源路径、分析电源器件。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from schema_reader import get_voltage_rail, infer_component_category


def analyze_power(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    电源树分析入口

    返回:
    {
        "rails": { "3.3V": {nets, component_count, parts}, ... },
        "power_parts": [ 电源相关器件 ],
        "regulators": [ LDO/DC-DC 列表 ],
        "power_indicators": [ LED 指示灯 ],
        "filter_caps": [ 滤波电容列表 ],
        "warnings": [ 电源设计警告 ],
    }
    """
    parts = parsed.get("parts", [])
    named_nets = parsed.get("named_nets", {})
    wires_by_net = parsed.get("wires_by_net", {})

    # 1. 识别电压轨
    rails: dict[str, dict[str, Any]] = {}
    for net_name in wires_by_net:
        rail = get_voltage_rail(net_name)
        if rail:
            if rail not in rails:
                rails[rail] = {
                    "nets": [],
                    "wire_count": 0,
                    "component_count": 0,
                }
            rails[rail]["nets"].append(net_name)
            rails[rail]["wire_count"] += len(wires_by_net[net_name])

    # 如果没有任何已知电源网络，尝试识别
    if not rails:
        rails = _discover_rails(named_nets, wires_by_net)

    # 2. 查找电源相关器件
    power_parts = []
    regulators = []
    power_indicators = []
    filter_caps = []
    power_keywords = [
        "AMS1117", "LM", "78", "79", "TPS", "XL", "MT", "MP", "SY",
        "DC-DC", "dcdc", "ldo", "LDO", "regulator", "REGULATOR",
        "buck", "boost", "charge", "battery", "BAT",
    ]

    for p in parts:
        name = _resolve_name(p)
        cat = infer_component_category(p)
        is_power = any(k in name.upper() for k in ["AMS1117", "LM78", "LM79", "LM31", "LM33",
                                                     "TPS", "XL", "MT", "MP", "SY", "LDO"])
        mfr_id = p.get("manufacturerId", "").upper()
        is_power = is_power or any(k in mfr_id for k in power_keywords)
        is_power = is_power or p.get("designator", "").upper().startswith("Q") and "mos" in name.lower()
        is_power = is_power or cat == "diode" and name.lower().startswith("ss")  # schottky

        if is_power:
            power_parts.append(p)
            if cat == "IC" or cat == "MCU":
                regulators.append(p)
            elif "indicator" in name.lower() or "led" in name.lower():
                power_indicators.append(p)

    # 3. 查找滤波电容 (C 前缀且靠近电源网络)
    for p in parts:
        if infer_component_category(p) == "capacitor":
            des = p.get("designator", "").upper()
            name = _resolve_name(p).lower()
            if any(n in name for n in ["uf", "pf", "nf", "f"]):
                filter_caps.append(p)

    # 4. 电源设计检查
    warnings = []
    # 检查是否有 GND
    if "GND" not in named_nets and "GND" not in wires_by_net:
        warnings.append("未检测到 GND 网络")

    # 检查是否有 3.3V/VDD
    has_3v3 = any(n in rails for n in ["3.3V", "3V3", "VDD"])
    if not has_3v3:
        # 检查是否存在 MCU 却没有 3.3V
        if any(p.get("manufacturerId", "").upper().startswith("STM") for p in parts):
            warnings.append("MCU 存在但未检测到 3.3V/VDD 电源轨")

    # 检查电源器件数量
    if not regulators:
        warnings.append("未检测到稳压器 (LDO/DC-DC) — 可能使用外部供电模块")

    return {
        "rails": rails,
        "power_parts": [
            {
                "ref": p.get("designator", "?"),
                "name": _resolve_name(p),
                "mfrId": p.get("manufacturerId", ""),
            }
            for p in power_parts
        ],
        "regulators": [
            {
                "ref": p.get("designator", "?"),
                "name": _resolve_name(p),
                "mfrId": p.get("manufacturerId", ""),
            }
            for p in regulators
        ],
        "power_indicators": [
            {
                "ref": p.get("designator", "?"),
                "name": _resolve_name(p),
            }
            for p in power_indicators
        ],
        "filter_caps_count": len(filter_caps),
        "warnings": warnings,
    }


def _discover_rails(
    named_nets: dict[str, list],
    wires_by_net: dict[str, list],
) -> dict[str, dict]:
    """通过命名网络推断电压轨"""
    rails: dict[str, dict] = {}
    voltage_nets = {
        "GND": "GND",
        "VCC": "5V",
        "VDD": "3.3V",
        "3V3": "3.3V",
        "5V": "5V",
        "12V": "12V",
        "VBAT": "VBAT",
        "VREF": "VREF",
        "VREF+": "VREF",
        "VSS": "GND",
        "AGND": "GND",
        "PGND": "GND",
    }
    for net_name in wires_by_net:
        upper = net_name.upper()
        if upper in voltage_nets:
            rail = voltage_nets[upper]
            if rail not in rails:
                rails[rail] = {"nets": [], "wire_count": 0}
            rails[rail]["nets"].append(net_name)
            rails[rail]["wire_count"] += len(wires_by_net[net_name])
    # fallback: 从 named_nets 也查一遍
    for net_name in named_nets:
        upper = net_name.upper()
        if upper in voltage_nets and net_name not in wires_by_net:
            rail = voltage_nets[upper]
            if rail not in rails:
                rails[rail] = {"nets": [], "wire_count": 0}
            rails[rail]["nets"].append(net_name)
    return rails


def _resolve_name(part: dict) -> str:
    """获取可读器件名"""
    for key in ("name", "subPartName", "manufacturerId"):
        val = part.get(key)
        if val and val.strip() and "=" not in val:
            return val.split(".")[0] if val.count(".") == 1 and len(val.split(".")[1]) <= 2 else val
    return part.get("designator", "?")
