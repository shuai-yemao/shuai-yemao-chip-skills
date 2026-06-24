"""
原理图数据解析器

将 read_schema 返回的原始 JSON 解析为结构化的分析数据模型。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_schematic_json(path: str | Path) -> dict[str, Any]:
    """从 JSON 文件加载原理图数据"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_schema(data: dict[str, Any]) -> dict[str, Any]:
    """
    解析原理图数据，返回结构化视图:

    {
        "adapter": str,
        "counts": {...},
        "parts": [...],           # 真实器件 (componentType == "part")
        "netports": [...],        # 网络端口
        "netflags": [...],        # 电源标识
        "sheets": [...],          # 图纸页
        "wires_by_net": {...},    # 按网络分组的导线
        "nets": [...],            # 去重网络列表
        "net_components": {...},  # 每个网络连接的器件列表
        "named_nets": {...},      # 已命名的网络 (netport/netflag)
    }
    """
    schema = data.get("schema", {})
    comps = schema.get("components", [])
    wires = schema.get("wires", [])

    # 按 componentType 分类
    parts = []
    netports = []
    netflags = []
    sheets = []
    for c in comps:
        ctype = c.get("componentType", "")
        if ctype == "part" and c.get("designator"):
            parts.append(c)
        elif ctype == "netport":
            netports.append(c)
        elif ctype == "netflag":
            netflags.append(c)
        elif ctype == "sheet":
            sheets.append(c)

    # 按网络分组导线
    wires_by_net: dict[str, list[dict]] = defaultdict(list)
    for w in wires:
        net_name = w.get("net", "")
        wires_by_net[net_name].append(w)

    # 去重网络列表
    nets = sorted(wires_by_net.keys(), key=lambda n: -len(wires_by_net[n]))

    # 每个网络连接的器件 (通过导线追踪)
    net_components: dict[str, set[str]] = defaultdict(set)
    for w in wires:
        net_name = w.get("net", "")
        # 导线的 (x, y) 坐标范围——目前无法直接确定连接到哪个器件
        # 这里仅标记该网络存在
        if net_name:
            net_components[net_name]  # 确保 key 存在

    # 已命名的网络 (netport + netflag)
    named_nets: dict[str, list[dict]] = defaultdict(list)
    for c in comps:
        net = c.get("net", "")
        if net and c.get("componentType") in ("netflag", "netport"):
            named_nets[net].append(c)

    return {
        "adapter": data.get("adapter", ""),
        "counts": data.get("counts", {}),
        "parts": parts,
        "netports": netports,
        "netflags": netflags,
        "sheets": sheets,
        "wires_by_net": dict(wires_by_net),
        "nets": nets,
        "net_components": {k: list(v) for k, v in net_components.items()},
        "named_nets": dict(named_nets),
        "_raw": data,
    }


def infer_component_category(part: dict[str, Any]) -> str:
    """
    根据器件属性推断器件类别:
    - MCU / IC
    - 连接器 (connector)
    - 电源 (power)
    - 传感器 (sensor)
    - 阻容 (passive)
    - 指示 (indicator)
    - 结构件 (mechanical)
    - 其他 (other)
    """
    name = (part.get("name") or "").lower()
    mfr_id = (part.get("manufacturerId") or "").lower()
    sub_part = (part.get("subPartName") or "").lower()
    designator = (part.get("designator") or "").upper()

    # 根据 designator 前缀判断
    if designator.startswith(("U", "IC")):
        # U 可能是 MCU 也可能是其他 IC
        if "stm32" in mfr_id or "stm32" in sub_part or "mcu" in sub_part:
            return "MCU"
        if "oled" in name or "lcd" in name or "display" in name:
            return "display"
        if "op" in name and ("amp" in name or "a" in name):
            return "IC"
        return "IC"
    if designator.startswith(("R", "RN")):
        return "resistor"
    if designator.startswith(("C", "CX")):
        return "capacitor"
    if designator.startswith(("L", "FB")):
        return "inductor"
    if designator.startswith(("D", "LED")):
        return "diode"
    if designator.startswith("Q"):
        return "transistor"
    if designator.startswith(("J", "P", "CN", "CON", "HDR")):
        return "connector"
    if designator.startswith(("SW", "S", "K")):
        return "switch"
    if designator.startswith(("F", "FU", "FUSE")):
        return "fuse"
    if designator.startswith(("Y", "X", "OSC")):
        return "crystal"
    if designator.startswith(("TP", "TEST")):
        return "testpoint"
    if designator.startswith(("SCREW", "MH", "MOUNT")):
        return "mechanical"
    if designator.startswith(("B", "BUZ", "LS")):
        return "transducer"

    return "other"


def get_voltage_rail(net_name: str) -> str | None:
    """判断网络名是否为电压轨"""
    if not net_name:
        return None
    upper = net_name.upper()
    known_rails = {
        "GND": "GND",
        "VSS": "GND",
        "VSSA": "GND",
        "AGND": "GND",
        "PGND": "GND",
        "3V3": "3.3V",
        "3.3V": "3.3V",
        "VDD": "3.3V",
        "VDDA": "3.3V",
        "VCC": "5V",
        "5V": "5V",
        "12V": "12V",
        "8.4V": "8.4V",
        "VBAT": "VBAT",
        "VREF": "VREF",
        "VREF+": "VREF",
        "VREF-": "GND",
    }
    return known_rails.get(upper, None)
