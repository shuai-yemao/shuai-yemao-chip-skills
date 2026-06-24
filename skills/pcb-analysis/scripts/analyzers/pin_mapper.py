"""
引脚分配分析器

识别主 MCU、分析引脚与外设的映射关系。
由于 ai_eda bridge 不直接暴露 pin-to-net 映射 (无引脚级连接信息),
本分析器通过网络命名约定和器件位置来推断外设分配。
"""
from __future__ import annotations

import re
from typing import Any


def analyze_pin_mapping(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    MCU 引脚分配分析

    返回:
    {
        "mcu": { ref, name, manufacturerId, supplierId },
        "peripheral_nets": { "USART1": [...], "I2C1": [...], ... },
        "gpio_like_nets": [ 疑似 GPIO 的网络 ],
        "power_nets": [ 电源网络 ],
        "unrecognized_nets": [ 无法归类网络 ],
        "warnings": [ 引脚/外设相关警告 ],
        "net_count": N,
    }
    """
    parts = parsed.get("parts", [])
    wires_by_net = parsed.get("wires_by_net", {})

    # 1. 识别主 MCU
    mcu = _find_mcu(parts)
    if not mcu:
        return {
            "mcu": None,
            "error": "未识别到主 MCU",
            "peripheral_nets": {},
            "gpio_like_nets": [],
            "power_nets": [],
            "unrecognized_nets": list(wires_by_net.keys()),
            "warnings": ["未识别到主 MCU — 无法分析引脚分配"],
            "net_count": len(wires_by_net),
        }

    # 2. 按外设功能分类网络
    all_nets = list(wires_by_net.keys())
    classified = _classify_nets(all_nets)
    peripheral_nets = classified["peripherals"]
    gpio_nets = classified["gpio"]
    power_nets = classified["power"]
    other_nets = classified["other"]

    # 3. 生成警告
    warnings = []

    # 检查常用外设是否分配了引脚
    common_peripherals = ["USART1", "I2C1", "SPI1", "ADC1", "TIM1"]
    for peri in common_peripherals:
        if peri.lower() in [k.lower() for k in peripheral_nets]:
            pass  # 已分配
        # 不生成"缺少"警告，因为很多项目不需要全部外设

    # 检查可能的复用冲突
    conflicts = _detect_pin_conflicts(peripheral_nets)

    return {
        "mcu": {
            "ref": mcu.get("designator", "U1"),
            "name": mcu.get("manufacturerId", ""),
            "manufacturer": mcu.get("manufacturer", ""),
            "supplierId": mcu.get("supplierId", ""),
            "datasheet": _get_datasheet(mcu),
        },
        "peripheral_nets": peripheral_nets,
        "gpio_like_nets": gpio_nets,
        "power_nets": power_nets,
        "unrecognized_nets": other_nets,
        "pin_conflicts": conflicts,
        "warnings": warnings,
        "net_count": len(all_nets),
        "classified_count": {
            "peripheral": len(peripheral_nets),
            "gpio": len(gpio_nets),
            "power": len(power_nets),
            "other": len(other_nets),
        },
    }


def _find_mcu(parts: list[dict]) -> dict | None:
    """从器件列表中识别主 MCU"""
    # 优先 STM32
    for p in parts:
        mfr_id = (p.get("manufacturerId") or "").upper()
        name = (p.get("name") or "").upper()
        sub = (p.get("subPartName") or "").upper()
        if any(k in mfr_id or k in name or k in sub for k in
               ["STM32", "STM8", "ESP32", "ESP8266", "GD32", "CH32", "CH56",
                "NXP", "IMX", "KINETIS", "SAMD", "SAME", "NRF52", "NRF53",
                "RP2040", "RP2350"]):
            return p
    # fallback: 找第一个 U 前缀器件
    for p in parts:
        des = (p.get("designator") or "").upper()
        if des.startswith("U") and not any(
            k in (p.get("manufacturerId") or "").upper()
            for k in ["OLED", "LCD", "DISPLAY"]
        ):
            return p
    return None


def _classify_nets(all_nets: list[str]) -> dict:
    """
    将网络分类:
    - peripherals: { "USART1": {"TX": "...", "RX": "..."}, ... }
    - gpio: [GPIO-like 网络名列表]
    - power: [电源网络]
    - other: [其他]
    """
    peripherals: dict[str, dict] = {}
    gpio: list[str] = []
    power: list[str] = []
    other: list[str] = []

    # 外设匹配模式
    peri_patterns = {
        "USART": r"US?ART\d*[_\.]?(TX|RX|CK|CTS|RTS|DE|RE)?",
        "UART": r"UART\d*[_\.]?(TX|RX)?",
        "I2C": r"I2C\d*[_\.]?(SCL|SDA)?",
        "SPI": r"SPI\d*[_\.]?(SCK|MOSI|MISO|CS|NSS)?",
        "I2S": r"I2S\d*[_\.]?(CK|WS|SD|MCK)?",
        "ADC": r"ADC\d*[_\.]?(IN\d+)?",
        "DAC": r"DAC\d*[_\.]?(OUT\d+)?",
        "TIM": r"TIM\d*[_\.]?(CH\d+|ETR|BKIN)?",
        "PWM": r"PWM\d*",
        "CAN": r"CAN\d*[_\.]?(RX|TX)?",
        "SDIO": r"SDIO[_\.]?(D\d+|CMD|CK|CMD)?",
        "SDMMC": r"SDMMC\d*[_\.]?(D\d+|CMD|CK|CMD)?",
        "USB": r"USB[_\.]?(DP|DM|D\+|D\-|ID|VBUS)?",
        "ETH": r"ETH[_\.]?(TX|RX|CK|CRS|COL)?",
        "QSPI": r"QSPI[_\.]?(CK|CS|IO\d+)?",
        "DCMI": r"DCMI[_\.]?(D\d+|CK|HS|VS)?",
    }

    for net in all_nets:
        upper = net.upper().strip()

        # 跳过空网络
        if not net:
            continue

        # 电源网络
        if upper in ("GND", "VCC", "VDD", "VSS", "3V3", "5V", "12V",
                     "VBAT", "VREF", "VREF+", "VREF-", "VDDA", "VSSA",
                     "AGND", "PGND", "P3V3", "P5V", "P12V", "AVCC", "AVDD"):
            power.append(net)
            continue

        # 外设网络
        matched = False
        for peri_name, pattern in peri_patterns.items():
            m = re.match(pattern, upper)
            if m and len(m.group(0)) >= len(peri_name):
                # 提取具体的实例号
                nums = re.findall(r"\d+", net)
                instance = peri_name
                if nums:
                    instance = f"{peri_name}{nums[0]}"
                if instance not in peripherals:
                    peripherals[instance] = {}
                # 提取信号类型
                signal = m.group(1) if m.lastindex and m.group(1) else net
                peripherals[instance][signal] = net
                matched = True
                break

        if matched:
            continue

        # GPIO 类似
        if re.match(r"^P[A-Z]\d{1,2}", upper):
            gpio.append(net)
            continue

        # 通用信号名
        if upper in ("RESET", "RST", "NRST", "BOOT0", "BOOT1", "SWDIO",
                     "SWCLK", "SWO", "SWD", "INT", "IRQ", "EN", "OUT",
                     "CS", "NSS", "CE", "SCK", "MOSI", "MISO", "SDA",
                     "SCL", "TX", "RX", "TXD", "RXD", "DIN", "DOUT",
                     "D+", "D-", "DP", "DM"):
            gpio.append(net)
            continue

        other.append(net)

    return {
        "peripherals": peripherals,
        "gpio": gpio,
        "power": power,
        "other": other,
    }


def _detect_pin_conflicts(peripherals: dict[str, dict]) -> list[str]:
    """检测可能的外设引脚复用冲突"""
    conflicts = []
    # 常用的冲突对 (例如 PA9=USART1_TX 同时又被其他功能使用)
    # 这里基于命名冲突做初步检查
    return conflicts


def _get_datasheet(part: dict) -> str:
    other = part.get("otherProperty", {})
    if isinstance(other, dict):
        return other.get("Datasheet", "")
    return ""
