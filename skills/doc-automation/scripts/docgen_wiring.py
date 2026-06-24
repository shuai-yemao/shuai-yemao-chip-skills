#!/usr/bin/env python3
"""
docgen_wiring.py — 硬件连接说明生成（P1）
===========================================
从 CubeMX .ioc 文件、需求文档 Markdown 或内联注释提取 GPIO/外设引脚分配，生成接线表。

功能:
  - from-ioc:   从 .ioc 文件提取引脚配置
  - from-md:    从 C 头文件 Markdown 注释提取引脚定义表
  - from-req:   从需求文档 Markdown 提取硬件连接信息
  - generate:   从 JSON 生成接线说明 Markdown

用法:
  python docgen_wiring.py from-ioc <board.ioc> [-o output.md]
  python docgen_wiring.py from-md <file.h>    [-o output.md]
  python docgen_wiring.py from-req <req.md>   [-o output.md]
  python docgen_wiring.py generate <input.json> -o <output.md>
"""

import io, json, os, re, sys
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── .ioc 解析 ──

# .ioc 文件中的引脚配置行: PB8.I2C1_SCL=GPIO_AF4, GPIOP7_PULL_UP,PIN_SPEED_FAST
IOC_PIN_PATTERN = re.compile(
    r'^([A-Z]+\d+)\.(\w+)=(.*?)$',
    re.MULTILINE,
)

# IP 实例化行: I2C1.IPParameters=...
IOC_IP_PATTERN = re.compile(
    r'^(\w+)\.IPParameters=',
    re.MULTILINE,
)


def parse_ioc(file_path: str) -> dict:
    """解析 .ioc 文件，提取引脚配置和外设实例"""
    content = Path(file_path).read_text(encoding='utf-8', errors='replace')
    result = {
        'mcu': '',
        'pins': [],
        'peripherals': [],
    }

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # MCU 型号
        if line.startswith('Mcu.Family'):
            result['mcu'] = line.split('=', 1)[-1].strip()
        if line.startswith('Mcu.Name'):
            result['mcu'] = line.split('=', 1)[-1].strip()

        # 引脚配置
        m = IOC_PIN_PATTERN.match(line)
        if m:
            pin = m.group(1)
            signal = m.group(2)
            config_raw = m.group(3)
            result['pins'].append({
                'pin': pin,
                'signal': signal,
                'config': config_raw.split(',') if config_raw else [],
            })

        # 外设模式
        if 'Mode' in line and '.' in line:
            parts = line.split('.', 1)
            if len(parts) == 2 and parts[1].startswith('Mode'):
                result['peripherals'].append({
                    'ip': parts[0],
                    'mode': line.split('=', 1)[-1].strip(),
                })

    return result


# ── C 头文件注释解析 ──

# 引脚定义注释: @pin PB0 -> LED_RED
PIN_ANNOT_PATTERN = re.compile(
    r'@pin\s+(\w+)\s*[=:>\-]+\s*(.+)',
)

# @wire 外设 -> GPIO 表格
WIRE_ANNOT_PATTERN = re.compile(
    r'@wire\s+(\w+)\s*[=:>\-]+\s*(.+)',
)

# 外设引脚映射表格（Markdown 风格）
TABLE_PIN_PATTERN = re.compile(
    r'\|?\s*(RCC_|SPI|I2C|UART|USART|TIM|ADC|DAC|CAN|USB|ETH|SDIO|FMC|DCMI|GPIO)_?(\w*)\s*\|\s*([A-Z]\d+)\s*\|?\s*(.*?)\s*\|',
)


def parse_header_annotations(file_path: str) -> dict:
    """从 C 头文件注释提取引脚连接信息"""
    content = Path(file_path).read_text(encoding='utf-8', errors='replace')
    result = {
        'pins': [],
        'wires': [],
    }

    for line in content.splitlines():
        m = PIN_ANNOT_PATTERN.search(line)
        if m:
            result['pins'].append({
                'pin': m.group(1).strip(),
                'signal': m.group(2).strip(),
            })

        m = WIRE_ANNOT_PATTERN.search(line)
        if m:
            result['wires'].append({
                'peripheral': m.group(1).strip(),
                'connection': m.group(2).strip(),
            })

        m = TABLE_PIN_PATTERN.search(line)
        if m:
            peri = m.group(1) + (m.group(2) if m.group(2) else '')
            pin = m.group(3)
            desc = m.group(4).strip()
            result['pins'].append({
                'pin': pin,
                'signal': peri,
                'description': desc if desc else '',
            })

    return result


# ── 需求文档 Markdown 解析 ──

# 表格行提取：| PA0 | UART1_TX | 说明 |
TABLE_ROW_PATTERN = re.compile(
    r'^\|?\s*`?([A-Z]{1,2}\d+)`?\s*\|'
    r'\s*`?(\w[\w/]*)`?\s*\|'
    r'\s*(.*?)\s*\|',
    re.MULTILINE,
)

# 箭头/冒号映射：PB0 -> LED 或 PB0 → LED 或 PB0: I2C1_SCL
ARROW_MAP_PATTERN = re.compile(
    r'`?([A-Z]{1,2}\d+)`?\s*[=:：→\->]+\s*'
    r'`?(\w[\w/]*)`?\.?',
)

# @pin PB0 = I2C1_SCL (通用)
PIN_ANNOT_GENERAL = re.compile(
    r'@pin\s+(\w+)\s*[=:：]+\s*(.+)',
)


def parse_requirements_doc(file_path: str) -> dict:
    """从需求文档 Markdown 提取硬件连接信息"""
    content = Path(file_path).read_text(encoding='utf-8', errors='replace')
    result = {
        'mcu': '',
        'pins': [],
        'wires': [],
        'source': file_path,
    }

    lines = content.splitlines()
    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # 跳过代码块和注释块
        if line_stripped.startswith('```') or line_stripped.startswith('<!--'):
            continue

        # MCU 型号
        mcu_m = re.search(
            r'(?:MCU|芯片|型号)\s*[:：]\s*(\w[\w\d]*)',
            line_stripped, re.IGNORECASE,
        )
        if mcu_m and not result['mcu']:
            result['mcu'] = mcu_m.group(1)

        # ── 表格解析 ──
        # 检测表头：引脚 | 信号 | ...
        if re.search(r'(引脚|PIN|Pin|GPIO)\s*[|]\s*(信号|Signal|功能|外设)', line_stripped, re.IGNORECASE):
            for j in range(i + 2, min(i + 50, len(lines))):
                row = lines[j].strip()
                if not row or row.startswith('|--') or row.startswith('|---'):
                    continue
                if not row.startswith('|') and '|' not in row:
                    break
                m = TABLE_ROW_PATTERN.search(row)
                if m:
                    result['pins'].append({
                        'pin': m.group(1).upper(),
                        'signal': m.group(2),
                        'description': m.group(3).strip(),
                    })

        # ── 箭头映射 PBx -> SIGNAL ──
        m = ARROW_MAP_PATTERN.search(line_stripped)
        if m:
            pin = m.group(1).upper()
            signal = m.group(2)
            if re.match(r'[A-Z]{1,2}\d+', pin):
                result['pins'].append({
                    'pin': pin,
                    'signal': signal,
                    'description': '',
                })

        # ── @pin 注释 ──
        m = PIN_ANNOT_GENERAL.search(line_stripped)
        if m:
            result['pins'].append({
                'pin': m.group(1).upper(),
                'signal': m.group(2).strip(),
                'description': '',
            })

    # ── 去重 ──
    seen = set()
    unique_pins = []
    for p in result['pins']:
        key = (p['pin'], p['signal'])
        if key not in seen:
            seen.add(key)
            unique_pins.append(p)
    result['pins'] = unique_pins

    return result


# ── Markdown 生成 ──


def generate_wiring_doc(data: dict, title: str = "硬件连接说明") -> str:
    """生成接线说明 Markdown"""
    lines = [f"# {title}", ""]

    if data.get('mcu'):
        lines.append(f"**MCU**: {data['mcu']}")
        lines.append("")

    # 引脚分配表
    if data.get('pins'):
        lines.append("## 引脚分配表")
        lines.append("")
        lines.append("| 引脚 | 信号 | 说明/配置 |")
        lines.append("|------|------|----------|")
        for p in data['pins']:
            sig = p.get('signal', '')
            desc = p.get('description', '') or p.get('config_desc', '')
            lines.append(f"| `{p['pin']}` | `{sig}` | {desc} |")
        lines.append("")

    # 外设模式
    if data.get('peripherals'):
        lines.append("## 外设模式配置")
        lines.append("")
        peri_groups = {}
        for p in data['peripherals']:
            peri_groups.setdefault(p['ip'], []).append(p['mode'])
        for ip, modes in sorted(peri_groups.items()):
            lines.append(f"- **{ip}**: {', '.join(modes)}")
        lines.append("")

    # 外设连线
    if data.get('wires'):
        lines.append("## 外设连线表")
        lines.append("")
        for w in data['wires']:
            lines.append(f"- **{w['peripheral']}** → {w['connection']}")
        lines.append("")

    # 硬件注意事项
    lines.append("## 硬件注意事项")
    lines.append("")
    lines.append("- 确认 VDD/VSS 电源去耦电容（100nF + 10µF per pair）")
    lines.append("- NRST 引脚外部上拉 10kΩ 到 VDD")
    lines.append("- BOOT0 引脚下拉 10kΩ 到 GND（正常启动模式）")
    lines.append("- VDDA 模拟供电：VDD 或独立 3.3V + 去耦")
    lines.append("- 晶振负载电容按 datasheet 推荐值配置")
    lines.append("")

    return "\n".join(lines)


# ── CLI ──


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 3:
        print_usage()
        return 1

    cmd = sys.argv[1]
    target = sys.argv[2]

    output = None
    if '-o' in sys.argv:
        idx = sys.argv.index('-o')
        if idx + 1 < len(sys.argv):
            output = sys.argv[idx + 1]

    if cmd == 'from-ioc':
        data = parse_ioc(target)
        md = generate_wiring_doc(data)

    elif cmd == 'from-md':
        data = parse_header_annotations(target)
        md = generate_wiring_doc(data)

    elif cmd == 'from-req':
        data = parse_requirements_doc(target)
        md = generate_wiring_doc(data)

    elif cmd == 'generate':
        if not output:
            print("[X] generate 模式需要 -o <output.md>")
            return 1
        data = json.loads(Path(target).read_text(encoding='utf-8'))
        md = generate_wiring_doc(data)
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1

    if output:
        Path(output).write_text(md, encoding='utf-8')
        print(f"[OK] 接线说明已生成: {output}")
        if 'pins' in data:
            print(f"     共 {len(data['pins'])} 个引脚")
    else:
        print(md)

    return 0


if __name__ == '__main__':
    sys.exit(main())
