#!/usr/bin/env python3
"""
芯片/传感器数据手册获取工具 — 从厂商官网下载文档并准备 KB 导入。

功能:
  1. 根据芯片型号匹配厂商官网 URL 模式
  2. 下载 PDF/HTML 数据手册到本地
  3. 生成 CherryStudio KnowledgeBase 可导入的文件路径

用法:
    # 查找并下载数据手册
    python fetch_datasheet.py --model "STM32F407VGT6" --type rm
    python fetch_datasheet.py --model "BME280" --mfr bosch
    python fetch_datasheet.py --model "MPU6050" --mfr invensense
    python fetch_datasheet.py --url "https://www.st.com/resource/en/datasheet/stm32f407vg.pdf"

    # 仅搜索，不下载
    python fetch_datasheet.py --model "ESP32-S3" --search-only

    # 列出已知厂商
    python fetch_datasheet.py --list-manufacturers
"""

import os
import sys
import json
import re
import hashlib
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlparse, quote
from urllib.error import URLError, HTTPError

# ═══════════════════════════════════════════════════════════════
# 厂商 URL 模式库 — 按芯片型号自动生成搜索 URL
# ═══════════════════════════════════════════════════════════════

MANUFACTURERS = {
    "st": {
        "name": "STMicroelectronics",
        "domain": "st.com",
        "doc_types": {
            "rm": "reference_manual",
            "ds": "datasheet",
            "an": "application_note",
            "es": "errata_sheet",
            "pm": "programming_manual",
            "tn": "technical_note",
        },
        "search_template": "site:st.com {model} {doc_type}",
        "url_patterns": [
            "https://www.st.com/resource/en/{doc_type}/{model_lower}.pdf",
            "https://www.st.com/resource/en/{doc_type}/cd{*}",
        ],
    },
    "espressif": {
        "name": "Espressif",
        "domain": "espressif.com",
        "doc_types": {
            "trm": "technical_reference_manual",
            "ds": "datasheet",
            "prog": "programming_guide",
        },
        "search_template": "site:espressif.com {model} {doc_type}",
        "url_patterns": [
            "https://www.espressif.com/sites/default/files/documentation/{model_lower}_{doc_type}_en.pdf",
        ],
    },
    "nxp": {
        "name": "NXP Semiconductors",
        "domain": "nxp.com",
        "doc_types": {
            "rm": "reference_manual",
            "ds": "datasheet",
            "an": "application_note",
            "um": "user_manual",
        },
        "search_template": "site:nxp.com {model} {doc_type}",
    },
    "ti": {
        "name": "Texas Instruments",
        "domain": "ti.com",
        "doc_types": {
            "ds": "datasheet",
            "ug": "user_guide",
            "an": "application_note",
            "errata": "errata",
        },
        "search_template": "site:ti.com {model} {doc_type}",
        "url_patterns": [
            "https://www.ti.com/lit/ds/symlink/{model}.pdf",
            "https://www.ti.com/lit/ug/*/{model}.pdf",
        ],
    },
    "nordic": {
        "name": "Nordic Semiconductor",
        "domain": "nordicsemi.com",
        "doc_types": {
            "ps": "product_specification",
            "ds": "datasheet",
            "sds": "softdevice_specification",
        },
        "search_template": "site:nordicsemi.com {model} {doc_type}",
    },
    "microchip": {
        "name": "Microchip Technology",
        "domain": "microchip.com",
        "doc_types": {
            "ds": "datasheet",
            "rm": "reference_manual",
            "an": "application_note",
        },
        "search_template": "site:microchip.com {model} {doc_type}",
    },
    "renesas": {
        "name": "Renesas Electronics",
        "domain": "renesas.com",
        "doc_types": {
            "ds": "datasheet",
            "um": "user_manual",
            "an": "application_note",
        },
        "search_template": "site:renesas.com {model} {doc_type}",
    },
    "gd": {
        "name": "GigaDevice",
        "domain": "gd32mcu.com",
        "doc_types": {
            "ds": "datasheet",
            "um": "user_manual",
        },
        "search_template": "site:gd32mcu.com {model} {doc_type}",
    },
    "wch": {
        "name": "WCH (沁恒微电子)",
        "domain": "wch.cn",
        "doc_types": {
            "ds": "datasheet",
            "rm": "reference_manual",
        },
        "search_template": "site:wch.cn {model} {doc_type}",
    },
    # ── 传感器厂商 ──
    "bosch": {
        "name": "Bosch Sensortec",
        "domain": "bosch-sensortec.com",
        "doc_types": {
            "ds": "datasheet",
            "an": "application_note",
        },
        "search_template": "site:bosch-sensortec.com {model} datasheet",
    },
    "invensense": {
        "name": "TDK InvenSense",
        "domain": "invensense.tdk.com",
        "doc_types": {
            "ds": "datasheet",
            "rm": "register_map",
        },
        "search_template": "site:invensense.tdk.com {model} datasheet",
    },
    "sensirion": {
        "name": "Sensirion",
        "domain": "sensirion.com",
        "doc_types": {
            "ds": "datasheet",
            "an": "application_note",
        },
        "search_template": "site:sensirion.com {model} datasheet",
    },
    "honeywell": {
        "name": "Honeywell",
        "domain": "honeywell.com",
        "doc_types": {
            "ds": "datasheet",
        },
        "search_template": "site:sensing.honeywell.com {model} datasheet",
    },
    "analog": {
        "name": "Analog Devices",
        "domain": "analog.com",
        "doc_types": {
            "ds": "datasheet",
            "an": "application_note",
        },
        "search_template": "site:analog.com {model} datasheet",
    },
    "tdk": {
        "name": "TDK Corporation",
        "domain": "tdk.com",
        "doc_types": {
            "ds": "datasheet",
        },
        "search_template": "site:tdk.com {model} datasheet",
    },
    "rohm": {
        "name": "ROHM Semiconductor",
        "domain": "rohm.com",
        "doc_types": {
            "ds": "datasheet",
        },
        "search_template": "site:rohm.com {model} datasheet",
    },
}

# ═══════════════════════════════════════════════════════════════
# 芯片型号 → 厂商自动识别
# ═══════════════════════════════════════════════════════════════

CHIP_PATTERNS = [
    # STM32
    (r'^STM32\w', 'st'),
    (r'^STM8\w', 'st'),
    (r'^LS[ML]\w', 'st'),
    (r'^VL53\w', 'st'),
    (r'^LIS[23]\w', 'st'),
    (r'^L3G\w', 'st'),
    (r'^MP34\w', 'st'),
    (r'^ISM330\w', 'st'),
    (r'^LSM[0-9]\w', 'st'),
    # ESP32
    (r'^ESP32\w*', 'espressif'),
    (r'^ESP8266\w*', 'espressif'),
    (r'^ESP\w', 'espressif'),
    # NXP
    (r'^I\.MX\s*RT?\w', 'nxp'),
    (r'^LPC\d{4}', 'nxp'),
    (r'^K\d{2}\w', 'nxp'),
    (r'^MK\d{2}\w', 'nxp'),
    # TI
    (r'^MSP430\w', 'ti'),
    (r'^CC\d{4}', 'ti'),
    (r'^TMS320\w', 'ti'),
    (r'^TM4C\d{3}', 'ti'),
    (r'^AM\d{3}', 'ti'),
    (r'^TMP\d{2}', 'ti'),
    (r'^HDC\d{4}', 'ti'),
    # Nordic
    (r'^NRF\d{4,5}', 'nordic'),
    (r'^NRF5\d{2}', 'nordic'),
    (r'^NRF9\d{1,2}', 'nordic'),
    # Microchip
    (r'^PIC\d{2}\w', 'microchip'),
    (r'^ATmega\d', 'microchip'),
    (r'^SAM\w', 'microchip'),
    # Renesas
    (r'^R[A-Z]\d{1,2}\w', 'renesas'),
    (r'^RA\d\w', 'renesas'),
    # GD
    (r'^GD32\w', 'gd'),
    (r'^GD32E\w', 'gd'),
    # WCH
    (r'^CH32\w', 'wch'),
    (r'^CH5\d{2}', 'wch'),
    (r'^CH34\d', 'wch'),
    # Sensors - Bosch
    (r'^BME\d{3}', 'bosch'),
    (r'^BMP\d{3}', 'bosch'),
    (r'^BMI\d{3}', 'bosch'),
    (r'^BNO\d{3}', 'bosch'),
    (r'^BHI\d{3}', 'bosch'),
    # Sensors - InvenSense/TDK
    (r'^MPU[0-9]\d{3}', 'invensense'),
    (r'^ICM[0-9]\d{3}', 'invensense'),
    (r'^ITG[0-9]\d{3}', 'invensense'),
    # Sensors - Sensirion
    (r'^SHT[0-9]\w', 'sensirion'),
    (r'^SGP\d{2}', 'sensirion'),
    (r'^SPS\d{2}', 'sensirion'),
    (r'^SCD\d{2}', 'sensirion'),
    # Sensors - Honeywell
    (r'^HMC\d{4}', 'honeywell'),
    (r'^HP[MS]\w', 'honeywell'),
    # Sensors - Analog Devices
    (r'^ADXL\d{3}', 'analog'),
    (r'^ADX[RS]\d{3}', 'analog'),
    (r'^ADE\d{4}', 'analog'),
    # Sensors - ROHM
    (r'^BH1[7]\d{2}', 'rohm'),
    (r'^BM1[34]\d{2}', 'rohm'),
    (r'^KX\d{3}', 'rohm'),
]


def identify_manufacturer(model: str) -> tuple[str | None, str | None]:
    """根据芯片型号自动识别厂商和文档类型提示"""
    model_upper = model.upper().replace('-', '').replace(' ', '')
    for pattern, mfr in CHIP_PATTERNS:
        if re.match(pattern, model_upper):
            doc_hint = None
            # 根据型号推断最可能需要的文档类型
            if re.match(r'^STM32F[4-7]', model_upper):
                doc_hint = "rm"  # F4/F7 系列优先查参考手册
            elif re.match(r'^STM32F[0-3]', model_upper):
                doc_hint = "ds"  # F0/F1/F3 系列优先查数据手册
            elif re.match(r'^ESP32\w', model_upper):
                doc_hint = "trm"
            elif re.match(r'^(BME|BMP|BMI|BNO|BHI|MPU|ICM|SHT|HMC|ADXL|BH1|LIS|LSM|VL53)', model_upper):
                doc_hint = "ds"  # 传感器优先查数据手册
            elif re.match(r'^nRF\d', model_upper):
                doc_hint = "ps"
            return mfr, doc_hint
    return None, None


def generate_search_queries(model: str, mfr: str, doc_type: str = "ds") -> list[dict]:
    """
    生成数据手册搜索查询。

    Returns: [{"query": str, "source": str, "url_hint": str}, ...]
    """
    mfr_info = MANUFACTURERS.get(mfr, {})
    name = mfr_info.get("name", mfr)
    domain = mfr_info.get("domain", "")
    doc_types = mfr_info.get("doc_types", {})

    doc_label = doc_types.get(doc_type, doc_type)
    queries = []

    # 1. 厂商官网精确搜索
    if domain:
        q = f"{model} {doc_label} filetype:pdf site:{domain}"
        queries.append({
            "query": q,
            "source": f"[{name} 官网]",
            "type": "official",
        })

    # 2. 型号 + datasheet 通用搜索
    q = f"{model} datasheet pdf"
    queries.append({
        "query": q,
        "source": "[通用搜索]",
        "type": "general",
    })

    # 3. 厂商文档仓库搜索 (GitHub)
    if mfr in ("st", "espressif", "nordic"):
        repo_hints = {
            "st": "STMicroelectronics",
            "espressif": "espressif",
            "nordic": "NordicSemiconductor",
        }
        q = f"{model} {doc_label} repo:{repo_hints[mfr]}"
        queries.append({
            "query": q,
            "source": f"[GitHub: {name} 官方仓库]",
            "type": "github",
        })

    return queries


# ═══════════════════════════════════════════════════════════════
# 下载工具
# ═══════════════════════════════════════════════════════════════

def download_file(url: str, output_dir: str, model: str = "") -> dict:
    """下载数据手册文件到本地"""
    os.makedirs(output_dir, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,text/html,*/*",
    }

    try:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=60)

        # 从 URL 或 Content-Disposition 推断文件名
        content_disp = resp.headers.get("Content-Disposition", "")
        filename_match = re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', content_disp)
        if filename_match:
            filename = filename_match.group(1)
        else:
            # 从 URL 提取
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename or "." not in filename:
                ext = ".pdf" if "pdf" in resp.headers.get("Content-Type", "") else ".html"
                safe_model = re.sub(r'[\\/*?:"<>|]', '_', model or 'datasheet')
                filename = f"{safe_model}{ext}"

        filepath = os.path.join(output_dir, filename)

        data = resp.read()
        with open(filepath, 'wb') as f:
            f.write(data)

        return {
            "success": True,
            "filepath": filepath,
            "filename": filename,
            "size": len(data),
            "content_type": resp.headers.get("Content-Type", "unknown"),
        }
    except HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "url": url}
    except URLError as e:
        return {"success": False, "error": f"网络错误: {e.reason}", "url": url}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(
        description="芯片/传感器数据手册获取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--model", "-m", default="",
                   help="芯片/传感器型号 (如 STM32F407VGT6, BME280, MPU6050)")
    p.add_argument("--mfr", "-f", default="",
                   help="厂商代码 (st/espressif/nxp/ti/nordic/bosch/invensense/...)")
    p.add_argument("--type", "-t", default="ds",
                   choices=["ds", "rm", "an", "es", "pm", "ps", "trm", "ug", "prog"],
                   help="文档类型 (ds=datasheet, rm=reference_manual, an=app_note)")
    p.add_argument("--url", "-u", default="",
                   help="直接指定 PDF 下载链接")
    p.add_argument("--output", "-o", default="",
                   help="输出目录 (默认: KB_DATA_DIR 或 ./datasheets)")
    p.add_argument("--search-only", action="store_true",
                   help="仅生成搜索查询，不下载")
    p.add_argument("--list-manufacturers", action="store_true",
                   help="列出所有支持的厂商")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    # --list-manufacturers
    if args.list_manufacturers:
        for code, info in sorted(MANUFACTURERS.items()):
            types = ", ".join(f"{k}({v})" for k, v in info["doc_types"].items())
            print(f"  {code:12s} → {info['name']:25s} 文档: {types}")
        return

    # --url 直接下载
    if args.url:
        output_dir = args.output or os.environ.get(
            "KB_DATA_DIR",
            os.path.join(os.path.dirname(__file__), "..", "datasheets")
        )
        result = download_file(args.url, output_dir, args.model)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif result["success"]:
            print(f"✓ 下载成功: {result['filepath']}")
            print(f"  大小: {result['size']:,} 字节")
            print(f"  类型: {result['content_type']}")
            print(f"\n→ 将此文件添加到 CherryStudio KnowledgeBase 即可索引")
        else:
            print(f"✗ 下载失败: {result['error']}", file=sys.stderr)
            sys.exit(1)
        return

    # --model 搜索
    if not args.model:
        p.print_help()
        return

    # 自动识别厂商
    mfr = args.mfr
    doc_hint = None
    if not mfr:
        mfr, doc_hint = identify_manufacturer(args.model)
    if not mfr:
        print(f"⚠ 无法自动识别 '{args.model}' 的厂商，请用 --mfr 手动指定", file=sys.stderr)
        print(f"  支持的厂商: {', '.join(sorted(MANUFACTURERS.keys()))}", file=sys.stderr)
        sys.exit(1)

    doc_type = args.type
    if doc_hint and args.type == "ds":
        doc_type = doc_hint

    queries = generate_search_queries(args.model, mfr, doc_type)

    if args.search_only:
        for i, q in enumerate(queries, 1):
            print(f"\n搜索 {i} {q['source']}:")
            print(f"  {q['query']}")
        return

    # 生成搜索查询供 Agent 使用
    mfr_info = MANUFACTURERS.get(mfr, {})
    result = {
        "model": args.model,
        "manufacturer": mfr_info.get("name", mfr),
        "manufacturer_code": mfr,
        "doc_type": doc_type,
        "auto_detected": mfr != args.mfr,
        "search_queries": queries,
        "note": "请使用 mcp__exa__web_search_exa 工具执行以下搜索，然后用 mcp__Uo38RGQK0kgxYuhEv48MX__fetch_markdown 获取文档内容",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"芯片: {args.model}")
        print(f"厂商: {mfr_info.get('name', mfr)} (代码: {mfr})")
        print(f"文档: {doc_type}  {'(自动识别)' if doc_hint else ''}")
        print(f"\n搜索查询 (请 Agent 使用 web_search_exa 并行执行):")
        for i, q in enumerate(queries, 1):
            print(f"  [{i}] {q['query']}  ← {q['source']}")


if __name__ == "__main__":
    main()
