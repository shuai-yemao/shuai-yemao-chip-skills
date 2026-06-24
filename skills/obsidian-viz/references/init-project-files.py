#!/usr/bin/env python3
"""
init-project-files.py — 嵌入式项目文档初始化 / 更新工具

用法:
  # 初始化（首次）
  init-project <项目目录>

  # 更新仪表盘资源占用（编译后执行）
  init-project <项目目录> --update

  # 仅创建日志/问题文件，不生成仪表盘
  init-project <项目目录> --no-dashboard

功能:
  1. 自动扫描 .uvprojx / .map / Core/Src/*.c
  2. 提取项目名、MCU、外设、引脚、Flash/RAM 占用
  3. 生成 docs/dashboard.html（项目仪表盘）
  4. 生成 docs/开发日志/ 目录 + 首条日志
  5. 生成 docs/问题跟踪.md
  --update: 保留手动编辑内容（引脚/问题/日志），仅刷新资源占用

依赖: Python 3.8+, 无三方库
"""

import os, sys, re, json, xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from shutil import copyfile

# ========== 工具函数 ==========

def find_uvprojx(proj_dir: Path) -> Path | None:
    """查找 .uvprojx 文件"""
    for f in proj_dir.rglob("*.uvprojx"):
        if ".cmsis" not in str(f):
            return f
    return None

def parse_uvprojx(uvprojx: Path) -> dict:
    """从 .uvprojx 解析项目名、MCU 型号"""
    info = {"name": uvprojx.stem, "mcu": "Unknown", "toolchain": "Unknown"}
    try:
        tree = ET.parse(uvprojx)
        root = tree.getroot()
        ns = {'ns': 'http://www.keil.com/uv4/project'}

        # MCU
        for device in root.iter('Device'):
            if device.text:
                info["mcu"] = device.text.strip()

        # Toolchain (AC5/AC6)
        for tads in root.iter('TargetArmAds'):
            cads = tads.find('Cads')
            if cads is not None:
                misc = cads.find('VariousControls')
                if misc is not None:
                    cc = misc.find('Define')
                    if cc is not None and cc.text:
                        if 'ARMCC' in (cc.text or '') or 'AC5' in (cc.text or ''):
                            info["toolchain"] = "ARM Compiler 5 (AC5)"
                        elif 'ARMCLANG' in (cc.text or '') or 'AC6' in (cc.text or ''):
                            info["toolchain"] = "ARM Compiler 6 (AC6)"
    except Exception:
        pass
    return info

def find_map_file(proj_dir: Path) -> Path | None:
    """查找最新的 .map 文件"""
    maps = list(proj_dir.rglob("*.map"))
    if not maps:
        return None
    maps.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    # 跳过 DebugConfig 目录的 map
    for m in maps:
        if "DebugConfig" not in str(m) and "build" not in str(m):
            return m
    return maps[0]

def parse_map(map_file: Path) -> dict:
    """解析 .map 获取 Code/RO/RW/ZI

    注意: ZI-data 包含堆栈预留（__heap/__stack），可能导致 total_ram
    超过物理 SRAM 大小。调用者需根据 MCU 实际 SRAM 上限扣减。
    """
    data = {"code": 0, "ro_data": 0, "rw_data": 0, "zi_data": 0, "total_rom": 0, "total_ram": 0}
    if not map_file or not map_file.exists():
        return data
    text = map_file.read_text(encoding='utf-8', errors='ignore')

    # Grand Totals 行: Code(inc.data) RO Data RW Data ZI Data
    m = re.search(r'(\d+)\s+\d+\s+(\d+)\s+(\d+)\s+(\d+)\s+Grand Totals', text)
    if m:
        data["code"] = int(m.group(1))
        data["ro_data"] = int(m.group(2))
        data["rw_data"] = int(m.group(3))
        data["zi_data"] = int(m.group(4))
        data["total_rom"] = data["code"] + data["ro_data"] + data["rw_data"]
        data["total_ram"] = data["rw_data"] + data["zi_data"]
    # fallback: 用 ROM/RAM Total 行
    if not data["total_rom"]:
        rom_m = re.search(r'Total ROM Size.*?(\d+)\s*\((\d+\.?\d*)\s*kB\)', text)
        if rom_m:
            data["total_rom"] = int(rom_m.group(1))
    return data

def scan_source_files(proj_dir: Path) -> dict:
    """扫描 Core/Src 中的外设初始化和引脚"""
    src_dir = proj_dir / "Core" / "Src"
    inc_dir = proj_dir / "Core" / "Inc"

    peripherals = []
    pins = []

    if src_dir.exists():
        for c_file in sorted(src_dir.glob("*.c")):
            content = c_file.read_text(encoding='utf-8', errors='ignore')

            # MX_xxx_Init() 外设初始化函数
            for mx in re.finditer(r'void\s+(MX_\w+_Init)\s*\(', content):
                peripherals.append({"name": mx.group(1), "file": c_file.name})

            # 引脚配置: HAL_GPIO_Init(GPIOx, &GPIO_InitStruct)
            for pin in re.finditer(r'HAL_GPIO_Init\((\w+),\s*&(\w+)\)', content):
                pins.append({"port": pin.group(1), "init": pin.group(2), "file": c_file.name})

    return {"peripherals": peripherals, "pins": pins}

def get_git_info(proj_dir: Path) -> dict:
    """获取 git 分支和最近提交"""
    git_dir = proj_dir / ".git"
    info = {"branch": "N/A", "last_commit": "N/A"}
    if not git_dir.exists():
        return info
    try:
        head_file = git_dir / "HEAD"
        if head_file.exists():
            head = head_file.read_text(encoding='utf-8', errors='ignore').strip()
            if head.startswith("ref:"):
                info["branch"] = head.split("/")[-1]
    except:
        pass
    return info

def guess_mcu_memory(mcu: str) -> dict:
    """根据 MCU 型号猜测 Flash/SRAM 大小"""
    mcu_upper = mcu.upper()
    if "F411" in mcu_upper:
        return {"flash": 512, "sram": 128, "flash_start": "0x08000000", "sram_start": "0x20000000"}
    elif "F103" in mcu_upper:
        return {"flash": 64, "sram": 20, "flash_start": "0x08000000", "sram_start": "0x20000000"}
    elif "F407" in mcu_upper or "F427" in mcu_upper:
        return {"flash": 1024, "sram": 128, "flash_start": "0x08000000", "sram_start": "0x20000000"}
    elif "H743" in mcu_upper or "H750" in mcu_upper:
        return {"flash": 2048, "sram": 512, "flash_start": "0x08000000", "sram_start": "0x24000000"}
    elif "G070" in mcu_upper or "G071" in mcu_upper:
        return {"flash": 128, "sram": 36, "flash_start": "0x08000000", "sram_start": "0x20000000"}
    else:
        return {"flash": 512, "sram": 128, "flash_start": "0x08000000", "sram_start": "0x20000000"}

# ========== 模板 ==========

DASHBOARD_TEMPLATE_PATH = Path(__file__).parent / "project-dashboard.html"

def read_template(path: Path) -> str:
    if not path.exists():
        print(f"[X] 模板不存在: {path}")
        sys.exit(1)
    return path.read_text(encoding='utf-8')

def generate_dashboard(proj_info: dict, map_data: dict, src_info: dict, git_info: dict, mem: dict, proj_dir: Path) -> str:
    """填充仪表盘模板"""
    template = read_template(DASHBOARD_TEMPLATE_PATH)

    flash_pct = round(map_data["total_rom"] / (mem["flash"] * 1024) * 100, 1) if mem["flash"] else 0
    # RAM: ZI 包含堆栈预留，上限为物理 SRAM 大小
    raw_sram = map_data["total_ram"]
    sram_cap = mem["sram"] * 1024
    sram_used = min(raw_sram, sram_cap)
    sram_pct = round(sram_used / sram_cap * 100, 1) if sram_cap else 0
    flash_free = mem["flash"] - round(map_data["total_rom"] / 1024, 1)
    sram_free = mem["sram"] - round(sram_used / 1024, 1)

    # 引脚表行
    pin_rows = ""
    for p in src_info["pins"][:8]:
        pin_rows += f'      <tr><td>{p["port"]}</td><td>GPIO</td><td>-</td><td>-</td><td>{p["file"]}</td></tr>\n'
    if not pin_rows:
        pin_rows = '      <tr><td>PA9</td><td>USART1_TX</td><td>USART1</td><td>AF_PP AF7</td><td>扫描中</td></tr>\n'

    # 架构图 Mermaid
    arch_lines = ["graph TD"]
    arch_lines.append(f'    CPU["{proj_info["mcu"]}"]')
    for i, p in enumerate(src_info["peripherals"][:6]):
        name = p["name"].replace("MX_", "").replace("_Init", "")
        arch_lines.append(f'    CPU --> P{i}["{name}"]')
    arch_lines.append('    style CPU fill:#228be6,color:#fff')
    arch = "\n".join(arch_lines)

    # 替换标记
    repl = {
        "<!-- PROJECT_NAME -->": proj_info["name"],
        "<!-- MCU -->": proj_info["mcu"],
        "<!-- MCU_FULL -->": f'{proj_info["mcu"]}, Cortex-M4 @ 100MHz',
        "<!-- TOOLCHAIN -->": proj_info["toolchain"],
        "<!-- BUILD_STATUS -->": "0 Errors, 0 Warnings",
        "<!-- BUILD_TIME -->": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "<!-- BUILD_OUTPUT -->": f'{proj_info["name"]}.hex',
        "<!-- LAST_UPDATE -->": f"{datetime.now().strftime('%Y-%m-%d')} 项目初始化",
        "<!-- DEBUGGER -->": "J-Link / ST-Link (配置中)",
        "<!-- SERIAL -->": "USART1 @ 115200-8N1 (配置中)",
        "<!-- PROJECT_PATH -->": str(proj_dir.resolve()),
        "<!-- FLASH_START -->": mem["flash_start"],
        "<!-- FLASH_SIZE -->": f'{mem["flash"]} KB',
        "<!-- FLASH_USED -->": f'{round(map_data["total_rom"] / 1024, 1)} KB',
        "<!-- FLASH_FREE -->": f'{flash_free} KB',
        "<!-- FLASH_PCT -->": f"{flash_pct}%",
        "<!-- FLASH_PCT_NUM -->": str(flash_pct),
        "<!-- SRAM_START -->": mem["sram_start"],
        "<!-- SRAM_SIZE -->": f'{mem["sram"]} KB',
        "<!-- SRAM_USED -->": f'{round(sram_used / 1024, 1)} KB',
        "<!-- SRAM_FREE -->": f'{sram_free} KB',
        "<!-- SRAM_PCT -->": f"{sram_pct}%",
        "<!-- SRAM_PCT_NUM -->": str(sram_pct),
        "<!-- CODE_SIZE -->": f'{round(map_data["code"] / 1024, 1)} KB ({map_data["code"]} B)',
        "<!-- RO_SIZE -->": f'{round(map_data["ro_data"] / 1024, 1)} KB ({map_data["ro_data"]} B)',
        "<!-- RW_SIZE -->": f'{round(map_data["rw_data"] / 1024, 1)} KB ({map_data["rw_data"]} B)',
        "<!-- ZI_SIZE -->": f'{round(map_data["zi_data"] / 1024, 1)} KB ({map_data["zi_data"]} B)',
        "<!-- MERMAID_ARCH -->": arch,
    }

    for k, v in repl.items():
        template = template.replace(k, v)

    return template

DEVLOG_TEMPLATE = """---
创建日期: {date}
项目: {project}
分支: {branch}
---

# 开发日志: {date}

## 本次目标

>

## 完成内容

-

## 遇到的问题

| 问题 | 原因 | 方案 | 状态 |
|------|------|------|------|
|  |  |  | [!] |

## Flash/RAM

| 区域 | 占用 | 总量 | 占用率 |
|------|------|------|--------|
| Flash | {flash_used} | {flash_total} | {flash_pct} |
| SRAM | {sram_used} | {sram_total} | {sram_pct} |

---

## 下次待办

- [ ]
"""

BUG_TEMPLATE = """# 问题跟踪 — {project}

> 项目级问题追踪，P0=阻塞/P1=重要/P2=低优先级

## 待解决

| 优先级 | 问题 | 模块 | 发现日期 | 状态 |
|--------|------|------|----------|------|
| P1 | 示例问题 | - | {date} | [!] |

## 已解决

| 优先级 | 问题 | 模块 | 解决日期 | 方案 |
|--------|------|------|----------|------|
| - | - | - | - | - |
"""

# ========== 主流程 ==========

def init_project(proj_dir_str: str, skip_dashboard: bool = False):
    proj_dir = Path(proj_dir_str).resolve()
    if not proj_dir.exists() or not proj_dir.is_dir():
        print(f"[X] 目录不存在: {proj_dir}")
        sys.exit(1)

    print(f"[*] 扫描项目: {proj_dir}")

    # 自动发现
    uvprojx = find_uvprojx(proj_dir)
    proj_info = parse_uvprojx(uvprojx) if uvprojx else {"name": proj_dir.name, "mcu": "Unknown", "toolchain": "Unknown"}
    print(f"  [+] 项目名: {proj_info['name']}")
    print(f"  [+] MCU: {proj_info['mcu']}")

    map_file = find_map_file(proj_dir)
    map_data = parse_map(map_file)
    if map_data["total_rom"]:
        print(f"  [+] ROM: {map_data['total_rom']} B  RAM: {map_data['total_ram']} B")
    else:
        print(f"  [~] 未找到 .map 文件或为空，资源占用使用默认值")

    src_info = scan_source_files(proj_dir)
    print(f"  [+] 检测到 {len(src_info['peripherals'])} 个外设初始化, {len(src_info['pins'])} 个引脚配置")

    git_info = get_git_info(proj_dir)

    mem = guess_mcu_memory(proj_info["mcu"])

    # 提前计算 RAM cap（ZI 包含堆栈预留，上限为物理 SRAM）
    raw_sram = map_data["total_ram"]
    sram_cap = mem["sram"] * 1024
    sram_used_capped = min(raw_sram, sram_cap)

    # 创建 docs/ 目录
    docs_dir = proj_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [+] docs/ 目录已就绪: {docs_dir}")

    # 1. 仪表盘
    if not skip_dashboard:
        dashboard_path = docs_dir / "dashboard.html"
        if dashboard_path.exists():
            backup = dashboard_path.with_suffix(".html.bak")
            copyfile(dashboard_path, backup)
            print(f"  [~] 已有 dashboard.html，备份为 dashboard.html.bak")

        html = generate_dashboard(proj_info, map_data, src_info, git_info, mem, proj_dir)
        dashboard_path.write_text(html, encoding='utf-8')
        print(f"  [+] 仪表盘: {dashboard_path} ({dashboard_path.stat().st_size} bytes)")

    # 2. 开发日志目录 + 首条日志
    devlog_dir = docs_dir / "开发日志"
    devlog_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    existing_logs = list(devlog_dir.glob(f"{date_str}-*.md"))
    session_num = len(existing_logs) + 1

    flash_total = f'{mem["flash"]} KB'
    sram_total = f'{mem["sram"]} KB'
    flash_used = f'{round(map_data["total_rom"] / 1024, 1)} KB'
    sram_used = f'{round(sram_used_capped / 1024, 1)} KB'
    flash_pct = f'{round(map_data["total_rom"] / (mem["flash"] * 1024) * 100, 1)}%'
    sram_pct = f'{round(sram_used_capped / (mem["sram"] * 1024) * 100, 1)}%'

    devlog_content = DEVLOG_TEMPLATE.format(
        date=date_str,
        project=proj_info["name"],
        branch=git_info["branch"],
        flash_used=flash_used, flash_total=flash_total, flash_pct=flash_pct,
        sram_used=sram_used, sram_total=sram_total, sram_pct=sram_pct
    )
    devlog_path = devlog_dir / f"{date_str}-会话{session_num}.md"
    devlog_path.write_text(devlog_content, encoding='utf-8')
    print(f"  [+] 开发日志: {devlog_path}")

    # 3. 问题跟踪
    bug_path = docs_dir / "问题跟踪.md"
    if bug_path.exists():
        print(f"  [~] 问题跟踪已存在: {bug_path}")
    else:
        bug_content = BUG_TEMPLATE.format(project=proj_info["name"], date=date_str)
        bug_path.write_text(bug_content, encoding='utf-8')
        print(f"  [+] 问题跟踪: {bug_path}")

    print(f"\n[OK] 项目文档初始化完成!")
    print(f"     仪表盘: 双击 docs/dashboard.html 在浏览器打开")
    print(f"     日志:   编辑 docs/开发日志/ 下的 .md 文件")
    print(f"     问题:   编辑 docs/问题跟踪.md")

def update_dashboard(proj_dir_str: str):
    """--update 模式：保留手动编辑，仅刷新资源占用"""
    proj_dir = Path(proj_dir_str).resolve()
    dashboard = proj_dir / "docs" / "dashboard.html"
    if not dashboard.exists():
        print(f"[X] 仪表盘不存在，请先运行 init-project 初始化: {dashboard}")
        return
    print(f"[*] 更新仪表盘: {proj_dir.name}")
    map_file = find_map_file(proj_dir)
    map_data = parse_map(map_file)
    if not map_data["total_rom"]:
        print(f"  [~] 未找到 .map 文件或数据为空，跳过资源更新")
        return
    uvprojx = find_uvprojx(proj_dir)
    proj_info = parse_uvprojx(uvprojx) if uvprojx else {"name": proj_dir.name, "mcu": "Unknown"}
    mem = guess_mcu_memory(proj_info["mcu"])
    raw_sram = map_data["total_ram"]
    sram_cap = mem["sram"] * 1024
    sram_used = min(raw_sram, sram_cap)
    flash_pct = round(map_data["total_rom"] / (mem["flash"] * 1024) * 100, 1) if mem["flash"] else 0
    sram_pct = round(sram_used / sram_cap * 100, 1) if sram_cap else 0
    flash_free = mem["flash"] - round(map_data["total_rom"] / 1024, 1)
    sram_free = mem["sram"] - round(sram_used / 1024, 1)

    flash_used_kb = f'{round(map_data["total_rom"] / 1024, 1)} KB'
    sram_used_kb = f'{round(sram_used / 1024, 1)} KB'
    flash_pct_str = f"{flash_pct}%"
    sram_pct_str = f"{sram_pct}%"

    html = dashboard.read_text(encoding='utf-8')
    count = 0

    # 策略 1: data-key 属性（模板 v3.1.1+）
    data_map = {
        "FLASH_USED": flash_used_kb, "FLASH_FREE": f'{flash_free} KB',
        "FLASH_PCT": flash_pct_str, "FLASH_SIZE": f'{mem["flash"]} KB',
        "SRAM_USED": sram_used_kb, "SRAM_FREE": f'{sram_free} KB',
        "SRAM_PCT": sram_pct_str, "SRAM_SIZE": f'{mem["sram"]} KB',
    }
    for key, val in data_map.items():
        pattern = rf'(data-key="{key}">)([^<]*)'
        new_html, n = re.subn(pattern, rf'\g<1>{val}', html)
        if n > 0:
            html = new_html
            count += 1

    # 策略 2: gauge 调用 g('gaugeFlash',数值,...)
    gauge_repl = {"gaugeFlash": str(flash_pct), "gaugeRam": str(sram_pct)}
    for gid, val in gauge_repl.items():
        pattern = rf"(g\('{gid}',)\d+\.?\d*"
        new_html, n = re.subn(pattern, rf'\g<1>{val}', html)
        if n > 0:
            html = new_html
            count += 1

    # 策略 3: 构建信息行 data-key
    build_repl = {
        "CODE_SIZE": f'{round(map_data["code"] / 1024, 1)} KB ({map_data["code"]} B)',
        "RO_SIZE": f'{round(map_data["ro_data"] / 1024, 1)} KB ({map_data["ro_data"]} B)',
        "RW_SIZE": f'{round(map_data["rw_data"] / 1024, 1)} KB ({map_data["rw_data"]} B)',
        "ZI_SIZE": f'{round(map_data["zi_data"] / 1024, 1)} KB ({map_data["zi_data"]} B)',
    }
    for key, val in build_repl.items():
        pattern = rf'(data-key="{key}">)([^<]*)'
        new_html, n = re.subn(pattern, rf'\g<1>{val}', html)
        if n > 0:
            html = new_html
            count += 1

    # 策略 4: BUILD_TIME 直接替换
    bt_pattern = r'(<!-- BUILD_TIME -->)'
    bt_repl = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_html, n = re.subn(bt_pattern, bt_repl, html)
    if n > 0:
        html = new_html
        count += 1

    dashboard.write_text(html, encoding='utf-8')
    print(f"  [+] 已更新 {count} 项资源数据: Flash={flash_pct}%, SRAM={sram_pct}%")
    print(f"  [~] 手动编辑内容（引脚/问题/日志/参考）已保留")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skip_dash = "--no-dashboard" in sys.argv
    update_mode = "--update" in sys.argv

    if not args:
        print("[X] 请指定项目目录")
        sys.exit(1)

    if update_mode:
        update_dashboard(args[0])
    else:
        init_project(args[0], skip_dashboard=skip_dash)
