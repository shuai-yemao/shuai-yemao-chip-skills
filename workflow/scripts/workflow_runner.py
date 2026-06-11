#!/usr/bin/env python
"""Workflow 流水线编排工具。

为 `workflow` skill 提供预定义流水线执行入口，支持：

- 编译 + 烧录 + 串口监控（build-flash-monitor）
- 编译 + 烧录 + GDB 调试（build-flash-debug）
- 自动根据构建系统选择对应 skill 脚本
- 步骤间自动传递产物路径
- 跨 skill 边界冲突检查（构建-烧录-调试 兼容性验证）
- 失败时立即停止并报告
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent

# ── 动态流水线发现 ──
# 每个 skill 可在其目录下放 pipeline.json，自动注册到 workflow
# 不再需要手动修改 WORKFLOWS 字典

_DISCOVERED_PIPELINES: dict[str, dict] = {}  # {name: pipeline_def}
_PIPELINE_SOURCES: dict[str, str] = {}        # {name: skill_name}


def scan_all_skills_for_pipelines() -> dict[str, dict]:
    """扫描所有 skill 目录下的 pipeline.json，动态发现流水线。

    遍历 SKILLS_ROOT 下的每个子目录（每个 skill 一个目录），
    查找 pipeline.json，解析其中的 pipelines 定义。
    返回合并后的完整 WORKFLOWS 字典。
    """
    global _DISCOVERED_PIPELINES, _PIPELINE_SOURCES

    if _DISCOVERED_PIPELINES:
        return _DISCOVERED_PIPELINES  # 已经扫描过

    discovered = {}
    sources = {}

    if not SKILLS_ROOT.is_dir():
        return discovered

    for skill_dir in sorted(SKILLS_ROOT.iterdir()):
        if not skill_dir.is_dir():
            continue
        pipeline_file = skill_dir / "pipeline.json"
        if not pipeline_file.exists():
            continue

        try:
            with open(pipeline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  [!] 解析 {pipeline_file} 失败: {e}", file=sys.stderr)
            continue

        pipelines = data.get("pipelines", {})
        skill_name = skill_dir.name

        for pipe_name, pipe_def in pipelines.items():
            if pipe_name in discovered:
                # 冲突：已有同名流水线，丢弃
                print(f"  [!] 流水线 '{pipe_name}' 已存在（来自 {sources[pipe_name]}），"
                      f"跳过 {skill_name}", file=sys.stderr)
                continue

            # 确保 steps 存在
            if "steps" not in pipe_def:
                continue

            # 补全默认字段
            pipe_def.setdefault("description", f"{skill_name}: 无描述")
            pipe_def.setdefault("phase", "Phase 6: 扩展流水线")

            discovered[pipe_name] = pipe_def
            sources[pipe_name] = skill_name

    _DISCOVERED_PIPELINES = discovered
    _PIPELINE_SOURCES = sources

    if discovered:
        # 通知合并结果（仅 verbose 模式下）
        for name, src in sources.items():
            pass  # 信息在 list 命令中展示

    return discovered


def get_merged_workflows() -> dict[str, dict]:
    """返回内置 + 动态发现的合并流水线字典"""
    builtin = dict(WORKFLOWS)
    discovered = scan_all_skills_for_pipelines()
    builtin.update(discovered)
    return builtin


def get_pipeline_source(pipe_name: str) -> str:
    """返回流水线的来源 skill 名称"""
    sources = scan_all_skills_for_pipelines()
    return _PIPELINE_SOURCES.get(pipe_name, "builtin")


def discover_step_label(step: str) -> str:
    """动态发现步骤的中文标签"""
    # 内置标签
    if step in STEP_LABELS:
        return STEP_LABELS[step]
    # 从步骤名推断中文
    known_prefixes = {
        "porting": "移植",
        "analyze": "分析",
        "document": "文档",
        "archive": "归档",
    }
    for prefix, label in known_prefixes.items():
        if step.startswith(prefix):
            # porting-analyze → 移植分析
            suffix = step[len(prefix):].lstrip('-')
            if suffix:
                suffix_label = {"analyze": "分析", "execute": "执行",
                                "document": "文档", "report": "报告"}.get(suffix, suffix)
                return f"{label}{suffix_label}"
            return label
    return step  # 回退到英文


def discover_step_icon(step: str) -> str:
    """动态发现步骤图标"""
    if step in STEP_ICONS:
        return STEP_ICONS[step]
    icon_prefixes = {
        "porting": "🔄",
        "analyze": "🔬",
        "document": "📝",
        "archive": "📦",
    }
    for prefix, icon in icon_prefixes.items():
        if step.startswith(prefix):
            return icon
    return "•"


# ---------------------------------------------------------------------------
# 结构化错误提取
# ---------------------------------------------------------------------------
# 从编译器、烧录器、调试器的输出中提取文件路径、行号、错误类型。

@dataclass
class ErrorItem:
    """单条结构化错误"""
    source: str          # 来源（文件名或组件名）
    line: int | None     # 行号
    col: int | None      # 列号
    severity: str        # error / warning / fatal / info
    error_code: str      # 错误码（如 "C100", "#20", "UNDEFINSTR"）
    message: str         # 原始消息
    raw_line: str        # 原始行文本

    def location_str(self) -> str:
        parts = [self.source]
        if self.line is not None:
            parts.append(str(self.line))
        if self.col is not None:
            parts[-1] = f"{parts[-1]}:{self.col}"
        return ":".join(parts)

    def severity_icon(self) -> str:
        return {"error": "❌", "fatal": "💀", "warning": "⚠️", "info": "ℹ️"}.get(
            self.severity, "❓"
        )


@dataclass
class ErrorReport:
    """步骤的错误报告"""
    step_name: str
    total_errors: int = 0
    total_warnings: int = 0
    items: list[ErrorItem] = field(default_factory=list)
    raw_stderr: str = ""
    raw_last_lines: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return self.total_errors > 0

    @property
    def errors(self) -> list[ErrorItem]:
        return [it for it in self.items if it.severity in ("error", "fatal")]

    @property
    def warnings(self) -> list[ErrorItem]:
        return [it for it in self.items if it.severity == "warning"]


# ── 编译器/工具链错误/警告匹配模式 ──

_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    # GCC / ARM GCC / ESP-IDF 格式
    #   file.c:42:5: error: 'foo' undeclared
    #   ../Src/main.c:128:3: warning: implicit declaration
    #   /path/to/file.cpp:10: error: expected ';'
    (re.compile(
        r"^(?P<file>[^\s:]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
        r"(?P<severity>error|warning|fatal error|note):\s*(?P<msg>.+)$",
        re.IGNORECASE
    ), "gcc"),

    # Keil MDK / ARMCC / ARMCLANG 格式
    #   main.c(45): error:  #20: identifier "x" is undefined
    #   ..\Src\uart.c(128): warning:  #177-D: variable was declared
    (re.compile(
        r"^(?P<file>[^\s:]+)\((?P<line>\d+)\):\s*"
        r"(?P<severity>error|warning|fatal error):\s*(?:#(?P<code>\d+(?:-[A-Z])?):)?\s*(?P<msg>.+)$",
        re.IGNORECASE
    ), "keil"),

    # IAR EWARM 格式
    #   Error[Pe020]: identifier "x" is undefined  main.c 42
    #   Warning[Pe177]: variable was declared but never referenced  uart.c 128
    (re.compile(
        r"^(?P<severity>Error|Warning|Fatal error)\[(?P<code>[^\]]+)\]:\s*"
        r"(?P<msg>.+?)\s+(?P<file>[^\s]+)\s+(?P<line>\d+)$",
        re.IGNORECASE
    ), "iar"),

    # OpenOCD 格式
    #   Error: couldn't bind tcl to socket on port 6666: Address already in use
    #   Warn : Interface already configured, ignoring
    #   Error: [stm32f4x.cpu] clearing lockup after double fault
    (re.compile(
        r"^(?P<severity>Error|Warn|Debug|Info)\s*:\s*(?:\[(?P<target>[^\]]+)\]\s*)?(?P<msg>.+)$",
    ), "openocd"),

    # J-Link / JLinkExe 格式
    #   ERROR: Could not connect to target.
    #   ERROR: Failed to connect. Could not establish a connection to target.
    #   - ERROR: Could not measure total IR len. TDO is constant high.
    (re.compile(
        r"^[-]*\s*(?P<severity>ERROR|WARNING):\s*(?P<msg>.+)$",
    ), "jlink"),

    # 通用 Make / CMake 错误指示行
    #   make[2]: *** [Src/subdir/main.o] Error 1
    #   make: *** [all] Error 2
    (re.compile(
        r"^(?P<file>make(?:\[\d+\])?|cmake):\s*\*+\s*\[(?P<target>[^\]]+)\]\s*"
        r"(?P<severity>Error)\s*(?P<code>\d+)$",
    ), "make"),
]


def extract_errors(output: str, stderr: str, step_type: str) -> ErrorReport:
    """从步骤输出中提取结构化错误信息。

    支持 GCC/ARM GCC、Keil MDK(ARMCC/ARMCLANG)、IAR EWARM、
    OpenOCD、J-Link、Make/CMake 的错误/警告格式。

    Args:
        output: 步骤的 stdout 输出
        stderr: 步骤的 stderr 输出
        step_type: 步骤类型 (build/flash/debug/monitor)

    Returns:
        ErrorReport 包含所有提取的错误项
    """
    # 编译器输出通常在 stderr，但某些工具也输出到 stdout
    combined = f"{output}\n{stderr}"
    lines = combined.splitlines()

    report = ErrorReport(step_name=step_type)
    seen = set()  # 去重

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        for pattern, source in _ERROR_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue

            groups = match.groupdict()

            # 提取文件路径
            file_path = groups.get("file", groups.get("target", ""))
            if not file_path or file_path == step_type:
                # OpenOCD/J-Link 格式没有文件路径，使用 tool 名
                file_path = source

            # 提取行号
            line_num = None
            if "line" in groups and groups["line"]:
                try:
                    line_num = int(groups["line"])
                except (ValueError, TypeError):
                    pass

            # 提取列号
            col_num = None
            if "col" in groups and groups["col"]:
                try:
                    col_num = int(groups["col"])
                except (ValueError, TypeError):
                    pass

            # 归一化 severity
            sev_raw = (groups.get("severity", "error") or "error").lower()
            if sev_raw in ("fatal error", "fatal"):
                severity = "fatal"
            elif sev_raw in ("error", "err"):
                severity = "error"
            elif sev_raw in ("warning", "warn"):
                severity = "warning"
            elif sev_raw in ("info", "note", "debug"):
                severity = "info"
            else:
                severity = "error"

            # 错误码
            error_code = groups.get("code", groups.get("target", ""))
            if not error_code:
                error_code = source.upper()

            # 消息文本 — 对于 IAR 格式，需要翻转（IAR 正则中 msg 先于 file）
            message = (groups.get("msg") or "").strip()

            # 去重
            dedup_key = (file_path, line_num, severity, message[:80])
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            item = ErrorItem(
                source=file_path,
                line=line_num,
                col=col_num,
                severity=severity,
                error_code=error_code[:20],
                message=message,
                raw_line=stripped[:200],
            )

            if severity in ("error", "fatal"):
                report.total_errors += 1
            elif severity == "warning":
                report.total_warnings += 1

            report.items.append(item)

    # 存储原始 stderr 尾部供 raw 查阅
    report.raw_stderr = stderr
    if stderr:
        report.raw_last_lines = stderr.strip().splitlines()[-20:]

    return report


def print_error_report(report: ErrorReport, step_label: str) -> None:
    """打印结构化错误报告，展示文件位置、错误类型和详细信息。"""
    step_icon = STEP_ICONS.get(report.step_name, "•")

    print(f"\n{'─'*60}")
    print(f"  📋 错误分析 — [{step_label}]")
    print(f"{'─'*60}")

    errors = report.errors
    warnings = report.warnings

    # ── 错误汇总 ──
    if errors:
        print(f"\n  ❌ 错误 ({len(errors)} 条):")
        print(f"  {'─'*54}")
        for item in errors:
            loc = item.location_str()
            icon = item.severity_icon()
            code_tag = f"[{item.error_code}] " if item.error_code and item.error_code != "GCC" else ""
            print(f"  {icon} {loc}")
            print(f"     {code_tag}{item.message}")
            print()

    # ── 警告汇总 ──
    if warnings:
        print(f"\n  ⚠️  警告 ({len(warnings)} 条):")
        print(f"  {'─'*54}")
        for item in warnings[:10]:  # 限制 10 条警告
            loc = item.location_str()
            code_tag = f"[{item.error_code}] " if item.error_code and item.error_code != "GCC" else ""
            print(f"  ⚠️  {loc}")
            print(f"     {code_tag}{item.message}")
        if len(warnings) > 10:
            print(f"\n  ... 及其他 {len(warnings) - 10} 条警告")
        print()

    # ── 统计 ──
    print(f"  {'─'*54}")
    print(f"  总计: ❌ {report.total_errors} 错误  ⚠️  {report.total_warnings} 警告")
    print(f"{'─'*60}\n")

    # ── 原始 stderr 尾部（当没有结构化提取到错误时回退） ──
    if not report.items and report.raw_last_lines:
        print(f"  📜 原始 stderr 输出 (最后 {len(report.raw_last_lines)} 行):")
        print(f"  {'─'*54}")
        for line in report.raw_last_lines:
            print(f"  │ {line}")
        print(f"{'─'*60}\n")


# ── 步骤图标映射 ──

STEP_ICONS = {
    "build": "🔨",
    "flash": "⚡",
    "monitor": "📡",
    "capture": "📥",
    "record": "📝",
    "commit": "💾",
    "debug": "🐛",
    "devlog": "📝",
    "static-analysis": "🔍",
    "map-analyze": "📊",
    "firmware-sign": "🔐",
    "ota-package": "📦",
    "verify": "✅",
    "stress-test": "🔥",
    "unit-test": "🧪",
    "code-review": "👁️",
    "peripheral-test": "🔌",
    "sprint-plan": "📋",
    "sprint-review": "📹",
    "sprint-retro": "🔄",
    "init-bsp": "🔧",
    "hw-integration": "🖥️",
    "change-assess": "📝",
    "risk-log": "⚠️",
    "dashboard": "📊",
    "arch-review": "🏗️",
    "oop-check": "🏛️",
}

SCRIPT_MAP = {
    "keil": {
        "build": "build-keil/scripts/keil_builder.py",
        "flash": "flash-keil/scripts/keil_flasher.py",
        "debug": "debug-gdb-openocd/scripts/gdb_debugger.py",
        "monitor": "serial-monitor/scripts/serial_monitor.py",
    },
    "cmake": {
        "build": "build-cmake/scripts/cmake_builder.py",
        "flash": "flash-openocd/scripts/openocd_flasher.py",
        "debug": "debug-gdb-openocd/scripts/gdb_debugger.py",
        "monitor": "serial-monitor/scripts/serial_monitor.py",
    },
    "platformio": {
        "build": "build-platformio/scripts/platformio_builder.py",
        "flash": "flash-platformio/scripts/pio_flasher.py",
        "debug": "debug-platformio/scripts/pio_debugger.py",
        "monitor": "serial-monitor/scripts/serial_monitor.py",
    },
}

WORKFLOWS = {
    # ── 既有流水线（保持兼容） ──
    "build-flash-monitor": {
        "description": "编译 → 烧录 → 串口监控（标准开发）",
        "steps": ["build", "flash", "monitor"],
    },
    "build-flash-debug": {
        "description": "编译 → 烧录 → GDB 调试",
        "steps": ["build", "flash", "debug"],
    },
    "fix-verify-commit": {
        "description": "编译 → 烧录 → 捕获日志 → 归档问题 → Git 提交（Bug 修复闭环）",
        "steps": ["build", "flash", "capture", "record", "commit"],
    },
    "full-cycle": {
        "description": "编译 → 烧录 → 串口监控 → 开发日志（完整开发闭环）",
        "steps": ["build", "flash", "monitor", "devlog"],
    },

    # ── Phase 1: 项目初始化 ──
    "init-project": {
        "description": "敏捷管理初始化: 创建 Backlog/Risk Register/docs 目录",
        "steps": ["init-bsp"],
    },
    "sprint-plan": {
        "description": "Sprint 规划: 选择 Backlog 项 → 生成 Sprint Plan 文档 → 风险评估",
        "steps": ["sprint-plan"],
    },

    # ── Phase 2: Sprint 开发 ──
    "bsp-bringup": {
        "description": "BSP 初始化: 编译 → 烧录 → 串口验证 → 开发日志",
        "steps": ["build", "flash", "monitor", "devlog"],
    },
    "add-peripheral": {
        "description": "添加外设: 编译 → 烧录 → 外设验证 → OOP 检查 → 开发日志",
        "steps": ["build", "flash", "peripheral-test", "oop-check", "devlog"],
    },
    "sprint-dev": {
        "description": "Sprint 开发: 编译 → 静态分析 → 烧录 → 串口监控 → 验证 → 开发日志",
        "steps": ["build", "static-analysis", "flash", "monitor", "verify", "devlog"],
    },
    "code-review-pipeline": {
        "description": "代码审查: 静态分析 → 代码审查 → 修正编译 → 验证",
        "steps": ["static-analysis", "code-review", "build", "verify"],
    },
    "unit-test-pipeline": {
        "description": "单元测试: 静态分析 → 单元测试(主机端) → 编译",
        "steps": ["static-analysis", "unit-test", "build"],
    },
    "arch-review": {
        "description": "架构评审: 方案评估 → MCU 选型 → 引脚分配确认 → 系统设计 Review",
        "steps": ["arch-review"],
    },

    # ── Phase 3: Sprint 管理 ──
    "sprint-wrap": {
        "description": "Sprint 收尾: 开发日志 → Sprint Review → Sprint Retro → Backlog 更新",
        "steps": ["devlog", "sprint-review", "sprint-retro"],
    },
    "risk-log": {
        "description": "风险登记册更新",
        "steps": ["risk-log"],
    },
    "change-assess": {
        "description": "变更影响评估: 生成变更文档 → 七层审查清单",
        "steps": ["change-assess"],
    },

    # ── Phase 4: 硬件验证 ──
    "hw-integration": {
        "description": "硬件集成测试: 编译 → 烧录 → 外设通信测试 → 稳定性测试",
        "steps": ["build", "flash", "peripheral-test", "stress-test"],
    },
    "stress-test": {
        "description": "稳定性测试: 烧录 → 长时间日志采集 → 结果分析",
        "steps": ["flash", "stress-test"],
    },

    # ── Phase 5: 发布 ──
    "release-prep": {
        "description": "发布准备: 编译 → 静态分析 → .map 分析 → 固件签名 → OTA 打包",
        "steps": ["build", "static-analysis", "map-analyze", "firmware-sign", "ota-package"],
    },
    "release": {
        "description": "正式发布: 编译 → 固件签名 → OTA 打包 → 发布日志",
        "steps": ["build", "firmware-sign", "ota-package", "devlog"],
    },

    # ── 仪表盘 ──
    "dashboard": {
        "description": "项目仪表盘: 生成/更新 HTML 仪表盘",
        "steps": ["dashboard"],
    },
}

STEP_LABELS = {
    "build": "编译",
    "flash": "烧录",
    "monitor": "串口监控",
    "capture": "日志捕获",
    "record": "问题归档",
    "commit": "Git 提交",
    "debug": "GDB 调试",
    "devlog": "开发日志",
    "static-analysis": "静态分析",
    "map-analyze": "Map 分析",
    "firmware-sign": "固件签名",
    "ota-package": "OTA 打包",
    "verify": "功能验证",
    "stress-test": "稳定性测试",
    "unit-test": "单元测试",
    "code-review": "代码审查",
    "peripheral-test": "外设测试",
    "sprint-plan": "Sprint 规划",
    "sprint-review": "Sprint 评审",
    "sprint-retro": "Sprint 回顾",
    "init-bsp": "BSP 初始化",
    "hw-integration": "硬件集成",
    "change-assess": "变更评估",
    "risk-log": "风险登记",
    "dashboard": "仪表盘",
    "arch-review": "架构评审",
    "oop-check": "OOP 合规检查",
}


# ---------------------------------------------------------------------------
# 跨 Skill 边界冲突检查规则
# ---------------------------------------------------------------------------
# 每条规则定义一组 (build_system, step) → 禁止的 flash/debug 方式。
# 基于各 skill 的 "## 边界定义 → 不该激活" 中的冲突规则提取。

CROSS_SKILL_RULES = {

    # ── 构建系统与步骤映射完整性 ─────────────────────────────────
    # 原则：每个步骤在 SCRIPT_MAP 中必须有对应脚本路径

    "missing-step-mapping": {
        "severity": "error",
        "condition": lambda bs, steps: any(
            s not in SCRIPT_MAP.get(bs, {})
            for s in steps if s not in (
                "record", "commit", "capture", "devlog",
                "static-analysis", "unit-test", "map-analyze",
                "firmware-sign", "ota-package", "verify",
                "stress-test", "code-review", "peripheral-test",
                "sprint-plan", "sprint-review", "sprint-retro",
                "init-bsp", "hw-integration", "change-assess",
                "risk-log", "dashboard", "arch-review",
            )
        ),
        "message": (
            "流水线中的某个步骤在构建系统映射表中不存在。\n"
            "  检查 steps 是否包含当前构建系统不支持的步骤。"
        ),
        "fix": "检查 WORKFLOWS 定义，确保所有 steps 在 SCRIPT_MAP 或 resolve_script 中有对应处理。",
    },

    # ── 构建系统兼容性守门 ──────────────────────────────────────
    # 原则：build_system 必须是 SCRIPT_MAP 支持的

    "unknown-build-system": {
        "severity": "error",
        "condition": lambda bs, steps: bs not in SCRIPT_MAP,
        "message": (
            f"不支持的构建系统类型。\n"
            f"  支持的构建系统: {', '.join(SCRIPT_MAP.keys())}"
        ),
        "fix": "指定正确的 --build-system 参数。",
    },

    # ── ESP32 构建系统 vs J-Link 探针冲突 ───────────────────────
    # 来源: flash-jlink SKILL.md "不该激活 → 用户的目标板是 ESP32/ESP8266 系列"

    "esp-build-vs-jlink": {
        "severity": "warning",
        "condition": lambda bs, steps: (
            "flash" in steps
            and SCRIPT_MAP.get(bs, {}).get("flash") == "flash-jlink"
        ),
        "message": (
            "当前构建系统映射的 flash skill 为 flash-jlink。\n"
            "  J-Link 主要用于 ARM Cortex-M 系列（STM32/nRF/GD32）。\n"
            "  若目标为 ESP32，确认 J-Link 固件支持并通过 JTAG 连接。\n"
            "  ESP32 标准烧录方式为 USB-UART（idf.py flash）或 FT2232 JTAG。"
        ),
        "fix": "若为 ESP32 目标，使用 --build-system platformio 或 idf 配合对应烧录方式。",
    },

    # ── PlatformIO 构建系统不支持 OpenOCD 直连调试 ──────────────
    # 来源: debug-platformio SKILL.md 与 debug-gdb-openocd SKILL.md 边界定义

    "platformio-build-vs-openocd-debug": {
        "severity": "error",
        "condition": lambda bs, steps: bs == "platformio"
            and "debug" in steps
            and SCRIPT_MAP.get(bs, {}).get("debug") != "debug-platformio",
        "message": (
            "PlatformIO 工程应使用 debug-platformio 进行调试（自动管理 OpenOCD/J-Link GDB Server）。\n"
            "  debug-gdb-openocd 无法读取 platformio.ini 中的 debug_tool 配置。"
        ),
        "fix": "确保 SCRIPT_MAP 中 platformio 的 debug 映射为 debug-platformio。",
    },

    # ── Keil MDK 构建系统跨平台兼容性 ──────────────────────────
    # 来源: build-keil SKILL.md "不该激活 → 用户在非 Windows 平台上"

    "keil-build-platform-check": {
        "severity": "warning",
        "condition": lambda bs, steps: bs == "keil" and sys.platform != "win32",
        "message": (
            "Keil MDK 编译和烧录仅在 Windows 上原生支持。\n"
            f"  当前平台: {sys.platform}。"
        ),
        "fix": "在 Windows 上执行，或将工程迁移到 build-cmake + ARM GCC。",
    },

    # ── 调试步骤前置条件检查 ────────────────────────────────────
    # 来源: debug-gdb-openocd SKILL.md "必须提供包含符号的 ELF"

    "debug-requires-elf": {
        "severity": "warning",
        "condition": lambda bs, steps: (
            "debug" in steps and "build" not in steps
        ),
        "message": (
            "流水线包含 debug 但无 build 步骤。\n"
            "  GDB 调试需要 .elf 文件（含调试符号），请确保产物可用或通过 --artifact 指定。"
        ),
        "fix": "添加 build 步骤到流水线，或通过 --artifact 指定已有的 .elf 文件。",
    },
}


@dataclass
class ConflictResult:
    """跨 skill 边界冲突检查结果"""
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def get_mapped_flash_skill(build_system: str) -> str:
    """返回给定构建系统默认映射的 flash skill 名称"""
    mapping = {
        "keil": "flash-keil",
        "cmake": "flash-openocd",
        "platformio": "flash-platformio",
    }
    return mapping.get(build_system, "unknown")


def get_mapped_debug_skill(build_system: str) -> str:
    """返回给定构建系统默认映射的 debug skill 名称"""
    mapping = {
        "keil": "debug-gdb-openocd",
        "cmake": "debug-gdb-openocd",
        "platformio": "debug-platformio",
    }
    return mapping.get(build_system, "unknown")


def check_cross_skill_conflicts(
    build_system: str,
    workflow_name: str,
    verbose: bool = False,
) -> ConflictResult:
    """执行跨 skill 边界冲突检查。

    在流水线执行前验证所有 skill 组合的合法性，
    基于各 skill SKILL.md 中的 "## 边界定义 → 不该激活" 规则。

    返回 ConflictResult，包含 errors（阻断性）和 warnings（建议性）。
    """
    wf = get_merged_workflows().get(workflow_name)
    if not wf:
        return ConflictResult(
            passed=False,
            errors=[f"未知 workflow: {workflow_name}"],
        )

    steps = wf["steps"]
    errors = []
    warnings = []
    suggestions = []

    # 1. 检查映射表中是否有此构建系统
    if build_system not in SCRIPT_MAP:
        errors.append(
            f"不支持的构建系统 '{build_system}'。"
            f" 可用: {', '.join(SCRIPT_MAP.keys())}"
        )
        return ConflictResult(passed=False, errors=errors)

    # 2. 检查脚本存在性（跳过交互式/提示式步骤）
    for step in steps:
        if step in ("code-review", "arch-review"):
            continue  # 交互式/提示式步骤，由 skill 触发
        path = resolve_script(build_system, step)
        if not path or not path.exists():
            errors.append(
                f"步骤 [{STEP_LABELS.get(step, step)}] 的脚本不存在: "
                f"{path or 'N/A'}"
            )
            suggestions.append(
                f"请安装或注册对应的 skill 脚本: "
                f"{SCRIPT_MAP[build_system].get(step, 'unknown')}"
            )

    # 3. 执行跨 skill 边界规则检查
    for rule_name, rule in CROSS_SKILL_RULES.items():
        try:
            if rule["condition"](build_system, steps):
                severity = rule.get("severity", "error")
                msg = f"[{rule_name}] {rule['message']}"
                if severity == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)
                if rule.get("fix"):
                    suggestions.append(rule["fix"])
        except Exception as exc:
            if verbose:
                warnings.append(f"规则 [{rule_name}] 执行异常: {exc}")

    # 4. 去重 suggestions
    suggestions = list(dict.fromkeys(suggestions))

    passed = len(errors) == 0

    if verbose and not passed:
        print("\n⚠️  跨 Skill 边界冲突检查：")
        print(f"  Workflow: {workflow_name}")
        print(f"  构建系统: {build_system}")
        print(f"  步骤: {' → '.join(STEP_LABELS.get(s, s) for s in steps)}")
        print(f"  预期 Flash: {get_mapped_flash_skill(build_system)}")
        print(f"  预期 Debug: {get_mapped_debug_skill(build_system)}")

    return ConflictResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        suggestions=suggestions,
    )


def print_conflict_report(result: ConflictResult) -> None:
    """打印冲突检查报告"""
    print("\n" + "=" * 50)
    if result.passed:
        print("✅ 跨 Skill 边界冲突检查: 通过")
        if result.warnings:
            print(f"\n⚠️  {len(result.warnings)} 条警告:")
            for w in result.warnings:
                print(f"  • {w}")
    else:
        print("❌ 跨 Skill 边界冲突检查: 失败")
        print(f"\n🚫 {len(result.errors)} 条错误:")
        for e in result.errors:
            print(f"  ✗ {e}")
        if result.warnings:
            print(f"\n⚠️  {len(result.warnings)} 条警告:")
            for w in result.warnings:
                print(f"  • {w}")
        if result.suggestions:
            print(f"\n💡 修复建议:")
            for s in result.suggestions:
                print(f"  → {s}")
    print("=" * 50 + "\n")


# ── 构建系统 → MCU 平台推断（用于 skill-level 冲突提示） ──

def infer_platform_hint(build_system: str) -> str:
    """根据构建系统推断目标 MCU 平台"""
    hints = {
        "keil": "ARM Cortex-M（STM32/GD32/nRF 等）",
        "cmake": "ARM Cortex-M 或 RISC-V（取决于工具链配置）",
        "platformio": "取决于 platformio.ini 中的 platform 字段",
    }
    return hints.get(build_system, "未知")


@dataclass
class WorkflowResult:
    status: str  # success, failure, partial
    summary: str
    workflow: str = ""
    steps_completed: int = 0
    steps_total: int = 0
    failed_step: str | None = None
    failure_category: str | None = None
    evidence: list[str] = field(default_factory=list)
    error_report: ErrorReport | None = None  # 结构化错误报告


# ---------------------------------------------------------------------------
# 脚本路径解析
# ---------------------------------------------------------------------------

def resolve_script(build_system: str, step: str) -> Path | None:
    # ── 敏捷管理步骤：sprint_helper.py ──
    if step in ("sprint-plan", "sprint-review", "sprint-retro",
                "risk-log", "change-assess", "init-bsp"):
        script = SKILLS_ROOT / "workflow" / "scripts" / "sprint_helper.py"
        return script if script.exists() else None

    # ── 仪表盘：obsidian-viz ──
    if step == "dashboard":
        for candidate in [
            SKILLS_ROOT / "obsidian-viz" / "references" / "init-project.bat",
            SKILLS_ROOT / "obsidian-viz" / "scripts" / "init_project.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── 知识管理步骤 ──
    if step == "record":
        script = SKILLS_ROOT / "knowledge-base-search" / "scripts" / "record_issue.py"
        return script if script.exists() else None
    if step == "commit":
        return Path(sys.executable)
    if step == "devlog":
        for candidate in [
            SKILLS_ROOT / "devlog" / "scripts" / "devlog.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── 静态分析：static-analysis ──
    # 实际路径: static-analysis/static_analysis.py（根目录）
    if step == "static-analysis":
        for candidate in [
            SKILLS_ROOT / "static-analysis" / "scripts" / "static_analysis.py",
            SKILLS_ROOT / "static-analysis" / "static_analysis.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── 单元测试：unit-test (minunit) ──
    if step == "unit-test":
        candidate = SKILLS_ROOT / "doc-automation" / "scripts" / "minunit_runner.py"
        return candidate if candidate.exists() else None

    # ── Map 分析：map-analyzer ──
    # 实际路径: map-analyzer/map_analyzer.py（根目录）
    if step == "map-analyze":
        for candidate in [
            SKILLS_ROOT / "map-analyzer" / "scripts" / "map_analyzer.py",
            SKILLS_ROOT / "map-analyzer" / "map_analyzer.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── 固件签名：firmware-sign ──
    # 实际路径: firmware-sign/firmware_sign.py（根目录，下划线命名）
    if step == "firmware-sign":
        for candidate in [
            SKILLS_ROOT / "firmware-sign" / "scripts" / "firmware_signer.py",
            SKILLS_ROOT / "firmware-sign" / "firmware_sign.py",
            SKILLS_ROOT / "firmware-sign" / "scripts" / "firmware_sign.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── OTA 打包：ota-package ──
    # 实际路径: ota-package/ota_package.py（根目录，下划线命名）
    if step == "ota-package":
        for candidate in [
            SKILLS_ROOT / "ota-package" / "scripts" / "ota_packager.py",
            SKILLS_ROOT / "ota-package" / "ota_package.py",
            SKILLS_ROOT / "ota-package" / "scripts" / "ota_package.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # ── Flash 烧录：flash-keil 不在时 fallback 到 flash-jlink ──
    if step == "flash" and build_system == "keil":
        primary = SKILLS_ROOT / "flash-keil" / "scripts" / "keil_flasher.py"
        if primary.exists():
            return primary
        # fallback: 用 J-Link 直接烧（flash-keil 已移除）
        for f in [
            SKILLS_ROOT / "flash-jlink" / "scripts" / "jlink_flasher.py",
            SKILLS_ROOT / "flash-jlink" / "flash_jlink.py",
        ]:
            if f.exists():
                return f
        return None

    # ── capture 映射到 serial_monitor ──
    if step == "capture":
        step = "monitor"

    # ── 外设测试 / 功能验证 → serial-monitor ──
    if step in ("peripheral-test", "verify"):
        step = "monitor"

    # ── 移植流水线步骤 ──
    if step == "porting-analyze":
        return SKILLS_ROOT / "code-porting" / "scripts" / "check_reg_compat.py"
    if step == "porting-document":
        return SKILLS_ROOT / "code-porting" / "scripts" / "gen_porting_report.py"

    # ── 压力测试 ──
    if step == "stress-test":
        script = SKILLS_ROOT / "serial-monitor" / "scripts" / "serial_monitor.py"
        return script if script.exists() else None

    mapping = SCRIPT_MAP.get(build_system)
    if not mapping or step not in mapping:
        return None
    return SKILLS_ROOT / mapping[step]


def check_scripts(build_system: str, steps: list[str]) -> list[tuple[str, Path, bool]]:
    results = []
    for step in steps:
        path = resolve_script(build_system, step)
        if path:
            results.append((step, path, path.exists()))
        else:
            results.append((step, Path("N/A"), False))
    return results


# ---------------------------------------------------------------------------
# 产物路径提取
# ---------------------------------------------------------------------------

def extract_artifact(output: str) -> str | None:
    for line in output.splitlines():
        if "⭐ 首选" in line or "⭐ 首选" in line:
            m = re.search(r'\]\s+(.+?)\s+\(', line)
            if m:
                return m.group(1).strip()
    for line in output.splitlines():
        for ext in (".elf", ".axf", ".hex", ".bin"):
            if ext in line.lower():
                m = re.search(r'(\S+' + re.escape(ext) + r')', line, re.IGNORECASE)
                if m:
                    return m.group(1)
    return None


# ---------------------------------------------------------------------------
# 步骤命令构建
# ---------------------------------------------------------------------------

def resolve_keil_project(project_arg: str) -> str:
    """If project_arg is a directory, auto-scan for .uvprojx/.uvproj."""
    p = Path(project_arg)
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in (".uvprojx", ".uvproj"):
                return str(f)
        return project_arg  # fallback: pass dir, let build script fail with clear msg
    return project_arg


def build_build_cmd(script: Path, args) -> list[str]:
    cmd = [sys.executable, str(script)]
    if args.build_system == "keil":
        if args.project:
            cmd += ["--project", resolve_keil_project(args.project)]
        if args.target:
            cmd += ["--target", args.target]
    elif args.build_system == "cmake":
        if args.project:
            cmd += ["--source", args.project]
        if args.target:
            cmd += ["--preset", args.target]
    elif args.build_system == "platformio":
        if args.project:
            cmd += ["--project-dir", args.project]
        if args.target:
            cmd += ["--env", args.target]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_flash_cmd(script: Path, args, artifact: str | None) -> list[str]:
    cmd = [sys.executable, str(script)]
    if args.build_system == "keil":
        cmd.append("--flash")
        if args.project:
            cmd += ["--project", resolve_keil_project(args.project)]
        if args.target:
            cmd += ["--target", args.target]
    elif args.build_system == "cmake":
        cmd.append("--flash")
        if artifact:
            cmd += ["--artifact", artifact]
        if args.flash_interface:
            cmd += ["--interface", args.flash_interface]
        if args.flash_target:
            cmd += ["--target", args.flash_target]
    elif args.build_system == "platformio":
        cmd.append("--flash")
        if args.project:
            cmd += ["--project-dir", args.project]
        if args.target:
            cmd += ["--env", args.target]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_monitor_cmd(script: Path, args) -> list[str]:
    cmd = [sys.executable, str(script), "--monitor"]
    if args.port:
        cmd += ["--port", args.port]
    if args.baud:
        cmd += ["--baud", str(args.baud)]
    return cmd


def build_debug_cmd(script: Path, args, artifact: str | None) -> list[str]:
    cmd = [sys.executable, str(script)]
    if args.build_system == "platformio":
        if args.project:
            cmd += ["--project-dir", args.project]
        if args.target:
            cmd += ["--env", args.target]
    else:
        if artifact:
            cmd += ["--elf", artifact]
        if args.flash_interface:
            cmd += ["--interface", args.flash_interface]
        if args.flash_target:
            cmd += ["--target", args.flash_target]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_capture_cmd(script: Path, args) -> list[str]:
    """构建日志捕获命令（定时采集 + 保存到文件）"""
    duration = args.duration or 10
    cmd = [sys.executable, str(script), "--duration", str(duration), "--clear"]
    if args.port:
        cmd += ["--port", args.port]
    if args.baud:
        cmd += ["--baud", str(args.baud)]
    if args.save:
        cmd += ["--save", args.save]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_record_cmd(args) -> list[str]:
    """构建问题归档命令（调用 record_issue.py append）"""
    script = SKILLS_ROOT / "knowledge-base-search" / "scripts" / "record_issue.py"
    if not script.exists():
        return []
    cmd = [sys.executable, str(script), "append"]
    if args.issue:
        cmd += ["--file", args.issue]
    if args.result:
        cmd += ["--result", args.result]
    return cmd


def build_commit_cmd(args) -> list[str]:
    """构建 Git 提交命令"""
    msg = args.commit_msg or "fix: bug fix"
    project_dir = args.project
    if project_dir:
        p = Path(project_dir)
        if p.suffix == ".uvprojx":
            project_dir = str(p.parent)
        elif p.name == "MDK-ARM":
            project_dir = str(p.parent)
    cmd = [
        sys.executable, "-c",
        f"import subprocess, sys; "
        f"subprocess.run(['git','add','-A'],cwd=r'{project_dir or '.'}'); "
        f"r=subprocess.run(['git','commit','-m',sys.argv[1]],cwd=r'{project_dir or '.'}',capture_output=True,text=True); "
        f"print(r.stdout or r.stderr)",
        msg
    ]
    return cmd


def build_devlog_cmd(script: Path, args) -> list[str]:
    """构建开发日志生成命令"""
    cmd = [sys.executable, str(script)]
    if args.project:
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            cmd += ["--project", str(p.parent.parent)]
        elif p.name == "MDK-ARM":
            cmd += ["--project", str(p.parent)]
        else:
            cmd += ["--project", args.project]
    if args.devlog_project_name:
        cmd += ["--project-name", args.devlog_project_name]
    if args.devlog_session_num:
        cmd += ["--session-num", str(args.devlog_session_num)]
    if args.devlog_start_time:
        cmd += ["--start-time", args.devlog_start_time]
    if args.devlog_work_done:
        cmd += ["--work-done", args.devlog_work_done]
    if args.devlog_problems:
        cmd += ["--problems-solutions", args.devlog_problems]
    if args.devlog_features:
        cmd += ["--features", args.devlog_features]
    if args.devlog_progress is not None:
        cmd += ["--progress", str(args.devlog_progress)]
    if args.devlog_achieved:
        cmd += ["--achieved", args.devlog_achieved]
    if args.devlog_pending:
        cmd += ["--pending", args.devlog_pending]
    if args.devlog_next_steps:
        cmd += ["--next-steps", args.devlog_next_steps]
    if args.devlog_notes:
        cmd += ["--notes", args.devlog_notes]
    if args.devlog_output:
        cmd += ["--output", args.devlog_output]
    if args.verbose:
        cmd.append("-v")
    return cmd


# ── 新增步骤命令构建器 ──

def build_static_analysis_cmd(script: Path, args) -> list[str]:
    """构建静态分析命令"""
    cmd = [sys.executable, str(script)]
    if args.project:
        # 尝试找源目录
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            src_dir = p.parent.parent / "Core" / "Src"
            if src_dir.exists():
                cmd += [str(src_dir)]
            else:
                cmd += [str(p.parent.parent)]
        elif p.name == "MDK-ARM":
            src_dir = p.parent / "Core" / "Src"
            if src_dir.exists():
                cmd += [str(src_dir)]
            else:
                cmd += [str(p.parent)]
        else:
            cmd += [args.project]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_map_analyze_cmd(script: Path, args) -> list[str]:
    """构建 .map 分析命令"""
    cmd = [sys.executable, str(script)]
    if args.project:
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            map_file = p.parent / "*.map"
            cmd += ["--map", str(p.parent)]
        elif p.name == "MDK-ARM":
            cmd += ["--map", args.project]
        else:
            cmd += [args.project]
    if args.verbose:
        cmd.append("-v")
    return cmd


def build_sprint_cmd(script: Path, step: str, args) -> list[str]:
    """构建 Sprint 管理命令（plan/review/retro/risk/change/init）"""
    cmd = [sys.executable, str(script)]
    cmd += ["--project", args.project or "."]
    if args.sprint:
        cmd += ["--sprint", str(args.sprint)]

    step_to_flag = {
        "sprint-plan": "--plan",
        "sprint-review": "--review",
        "sprint-retro": "--retro",
        "risk-log": "--risk --list",
        "change-assess": "--change --assess",
        "init-bsp": "--init-project",
    }
    flag = step_to_flag.get(step, "")
    if flag:
        cmd += flag.split()

    if step == "sprint-plan" and args.backlog_ids:
        cmd += ["--backlog-ids"] + [str(i) for i in args.backlog_ids]
    return cmd


def build_stress_test_cmd(script: Path, args) -> list[str]:
    """构建稳定性测试命令（长时间日志采集）"""
    duration = args.duration or 60  # 默认 60 秒
    cmd = [sys.executable, str(script), "--monitor",
           "--duration", str(duration)]
    if args.port:
        cmd += ["--port", args.port]
    if args.baud:
        cmd += ["--baud", str(args.baud)]
    if args.save:
        cmd += ["--save", args.save]
    return cmd


def build_dashboard_cmd(script: Path, args) -> list[str]:
    """构建仪表盘生成命令"""
    cmd = [sys.executable, str(script)]
    if args.project:
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            cmd += [str(p.parent.parent)]
        elif p.name == "MDK-ARM":
            cmd += [str(p.parent)]
        else:
            cmd += [args.project]
    return cmd


# ---------------------------------------------------------------------------
# 步骤执行
# ---------------------------------------------------------------------------

def run_step(name: str, cmd: list[str], inherit_io: bool = False,
             dry_run: bool = False) -> tuple[bool, str, str]:
    """执行单个步骤，返回 (成功, stdout, stderr)。"""
    cmd_str = " ".join(cmd)
    if dry_run:
        print(f"  [dry-run] {cmd_str}")
        return True, "", ""

    print(f"  $ {cmd_str}")
    if inherit_io:
        proc = subprocess.run(cmd, cwd=os.getcwd())
        return proc.returncode == 0, "", ""

    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd(),
                          encoding="utf-8", errors="replace")
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.stdout:
        for line in proc.stdout.strip().splitlines():
            print(f"    {line}")
    if proc.returncode != 0 and proc.stderr:
        for line in proc.stderr.strip().splitlines()[-5:]:
            print(f"    ⚠️ {line}")
    return proc.returncode == 0, stdout, stderr


# ---------------------------------------------------------------------------
# Workflow 执行
# ---------------------------------------------------------------------------

def run_workflow(workflow_name: str, args) -> WorkflowResult:
    merged = get_merged_workflows()
    wf = merged.get(workflow_name)
    if not wf:
        return WorkflowResult(status="failure", summary=f"未知 workflow: {workflow_name}",
                              workflow=workflow_name, steps_completed=0, steps_total=0)
    steps = wf["steps"]
    total = len(steps)
    artifact: str | None = args.artifact

    print(f"\n🚀 执行流水线: {workflow_name}（{wf['description']}）")
    print(f"  构建系统: {args.build_system}")
    if args.project:
        print(f"  工程路径: {args.project}")
    print()

    # ── 跨 Skill 边界冲突检查 ──
    if not args.skip_conflict_check:
        conflict = check_cross_skill_conflicts(args.build_system, workflow_name,
                                               verbose=args.verbose)
        if not conflict.passed:
            print_conflict_report(conflict)
            return WorkflowResult(
                status="failure",
                summary="跨 skill 边界冲突检查失败",
                workflow=workflow_name,
                steps_completed=0,
                steps_total=total,
                failed_step="preflight-conflict-check",
                failure_category="cross-skill-conflict",
                evidence=conflict.errors,
            )
        elif conflict.warnings:
            # 警告级别不阻断，但打印提示
            for w in conflict.warnings:
                print(f"  ⚠️ {w}")
            print()

    for i, step in enumerate(steps):
        label = discover_step_label(step)
        script = resolve_script(args.build_system, step)
        if not script or not script.exists():
            print(f"\n❌ [{i+1}/{total}] {label} — 脚本不存在: {script}")
            return WorkflowResult(status="failure", summary=f"{label}脚本不存在",
                                  workflow=workflow_name, steps_completed=i, steps_total=total,
                                  failed_step=step, failure_category="environment-missing")

        print(f"\n{'='*50}")
        print(f"[{i+1}/{total}] {label}")
        print(f"{'='*50}")

        if step == "build":
            cmd = build_build_cmd(script, args)
        elif step == "flash":
            cmd = build_flash_cmd(script, args, artifact)
        elif step == "monitor":
            cmd = build_monitor_cmd(script, args)
        elif step == "capture":
            cmd = build_capture_cmd(script, args)
        elif step == "record":
            cmd = build_record_cmd(args)
            if not cmd:
                print(f"  ⚠️ record_issue.py 未找到，跳过记录步骤")
                continue
        elif step == "commit":
            cmd = build_commit_cmd(args)
        elif step == "devlog":
            cmd = build_devlog_cmd(script, args)
        elif step == "debug":
            cmd = build_debug_cmd(script, args, artifact)
        # ── 新步骤 ──
        elif step == "static-analysis":
            cmd = build_static_analysis_cmd(script, args)
        elif step == "map-analyze":
            cmd = build_map_analyze_cmd(script, args)
        elif step in ("sprint-plan", "sprint-review", "sprint-retro",
                       "risk-log", "change-assess", "init-bsp"):
            cmd = build_sprint_cmd(script, step, args)
        elif step == "stress-test":
            cmd = build_stress_test_cmd(script, args)
        elif step == "dashboard":
            cmd = build_dashboard_cmd(script, args)
        elif step == "unit-test":
            cmd = [sys.executable, str(script)]
            if args.project:
                p = Path(args.project)
                src = p.parent if p.suffix in (".uvprojx", ".uvproj") else p
                cmd += [str(src)]
        elif step == "oop-check":
            print(f"\n  ┌─ OOP 合规检查步骤 ────────────────────────────────┐")
            print(f"  │ 检查 BSP 驱动代码的面向对象合规性                          │")
            print(f"  │                                                       │")
            print(f"  │ 检查项:                                                │")
            print(f"  │   ① 封装: struct 是否隐藏在 .c 中(不透明句柄)              │")
            print(f"  │   ② 跨层: BSP 是否直接调 HAL 而非 Core 层 API            │")
            print(f"  │   ③ 方法命名: 是否有 On/Off/Toggle 等语义化方法            │")
            print(f"  │   ④ 注册表: 多个实例是否通过静态数组管理(避免堆碎片)          │")
            print(f"  │   ⑤ 有效电平: 是否通过参数可配而非硬编码                   │")
            print(f"  │   ⑥ NULL 安全: 所有方法是否检查 NULL 句柄                 │")
            print(f"  │                                                       │")
            print(f"  │ 手动检查: 打开 bsp_*.c / bsp_*.h 逐项核验                │")
            print(f"  │ 自动检查: 跟我说「OOP 检查 BSP 驱动代码」「审查 OOP」       │")
            print(f"  └───────────────────────────────────────────────────────┘")
            continue
        elif step == "arch-review":
            print(f"\n  ┌─ 架构评审步骤 ─────────────────────────────────────┐")
            print(f"  │ 已触发 embedded-architect（嵌入式架构师）                    │")
            print(f"  │                                                       │")
            print(f"  │ 评审范围:                                               │")
            print(f"  │   ① MCU 选型评审（余量模型）                              │")
            print(f"  │   ② 系统架构设计评审（分层解耦）                            │")
            print(f"  │   ③ 引脚分配/外设互斥审查                                 │")
            print(f"  │   ④ RTOS 任务划分评审                                    │")
            print(f"  │   ⑤ 时钟树/电源架构评审                                   │")
            print(f"  │   ⑥ 第一版 bring-up 策略                                 │")
            print(f"  │                                                       │")
            print(f"  │ 触发方式: 跟我说「架构评审」「帮我看看这个方案」              │")
            print(f"  └───────────────────────────────────────────────────────┘")
            continue
        elif step == "code-review":
            print(f"\n  ┌─ 代码审查步骤 ─────────────────────────────────────┐")
            print(f"  │ 已触发 embedded-reviewer（嵌入式审查官）                     │")
            print(f"  │                                                       │")
            print(f"  │ 审查范围:                                               │")
            print(f"  │   ① 七层引脚一致性审查                                   │")
            print(f"  │   ② ISR 安全三原则检查                                   │")
            print(f"  │   ③ DMA 缓冲区生命周期审查                                │")
            print(f"  │   ④ 并发竞态审查                                         │")
            print(f"  │   ⑤ MISRA 高频违规检查 (Top 10)                          │")
            print(f"  │   ⑥ 外设配置/启动代码审查                                 │")
            print(f"  │                                                       │")
            print(f"  │ 触发方式: 跟我说「Review 这段代码」或「帮我审查项目」          │")
            print(f"  └───────────────────────────────────────────────────────┘")
            continue
        elif step in ("peripheral-test", "verify"):
            cmd = build_monitor_cmd(script, args)
        elif step == "firmware-sign":
            cmd = [sys.executable, str(script)]
            if artifact:
                cmd += ["--input", artifact]
            if args.verbose:
                cmd.append("-v")
        elif step == "ota-package":
            cmd = [sys.executable, str(script)]
            if artifact:
                cmd += ["--input", artifact]
            if args.verbose:
                cmd.append("-v")

        # ── 移植流水线步骤 ──
        elif step == "porting-analyze":
            print(f"\n  ┌─ 移植差异分析 ─────────────────────────────────────┐")
            print(f"  │ 运行以下分析工具:                                      │")
            print(f"  │                                                       │")
            print(f"  │  ① check_reg_compat.py — 寄存器兼容性检查              │")
            print(f"  │     python .../code-porting/scripts/check_reg_compat.py │")
            print(f"  │     --src <源目录> --target <目标芯片>                   │")
            print(f"  │                                                       │")
            print(f"  │  ② cmp_vectors.py — 中断向量表对比                    │")
            print(f"  │     python .../code-porting/scripts/cmp_vectors.py      │")
            print(f"  │     --old <源startup> --new <目标startup>               │")
            print(f"  │                                                       │")
            print(f"  │  ③ diff_ld.py — 链接脚本差异分析                       │")
            print(f"  │     python .../code-porting/scripts/diff_ld.py          │")
            print(f"  │     --old <源脚本> --new <目标脚本>                     │")
            print(f"  │                                                       │")
            print(f"  │  ④ gen_macro_map.py — 宏定义映射表生成                 │")
            print(f"  │     python .../code-porting/scripts/gen_macro_map.py    │")
            print(f"  │     --source STM32F1 --target STM32F4                  │")
            print(f"  └───────────────────────────────────────────────────────┘")
            print(f"\n  [!] 请根据移植类型（MCU 换型 / 库移植 / 工具链迁移）")
            print(f"  参考 code-porting skill 的 7 层逐层移植策略执行。")
            print(f"  跟我说「开始移植 XX 到 XX」触发 code-porting skill。")
            continue

        elif step == "porting-document":
            report_script = (SKILLS_ROOT / "code-porting" / "scripts"
                             / "gen_porting_report.py")
            if not report_script.exists():
                print(f"\n  [!] gen_porting_report.py 未找到")
                print(f"  预期路径: {report_script}")
                print(f"  请手动生成移植报告并归档。")
                continue

            source_chip = getattr(args, 'source_chip', None) or '{{SRC}}'
            target_chip = getattr(args, 'target_chip', None) or '{{DST}}'
            layers = getattr(args, 'layers', '1,2,3,4,5,6,7')
            output  = getattr(args, 'output', 'docs/移植文档/')
            project = getattr(args, 'project', 'default')
            archive = getattr(args, 'archive_obsidian', False)
            do_import = getattr(args, 'import_kb', False)
            tags = getattr(args, 'tags', '移植')

            cmd = [sys.executable, str(report_script),
                   "--source-chip", source_chip,
                   "--target-chip", target_chip,
                   "--type", getattr(args, 'porting_type', 'mcu-port'),
                   "--layers", layers,
                   "--output", output,
                   "--project", project]

            if archive:
                cmd.append("--archive-obsidian")
            if do_import:
                cmd.append("--import-kb")
            if tags:
                cmd += ["--tags", tags]

            print(f"\n  [i] 生成移植报告 + 归档...")
            print(f"  也可手动运行:")
            print(f"  python {report_script} "
                  f"--source-chip {source_chip} --target-chip {target_chip}")

        else:
            continue

        is_interactive = step in ("monitor", "debug")
        ok, stdout, stderr = run_step(step, cmd, inherit_io=is_interactive, dry_run=args.dry_run)

        if step == "build" and not args.dry_run and ok:
            found = extract_artifact(stdout)
            if found:
                artifact = found
                print(f"\n  📦 产物: {artifact}")

        if not ok and not args.dry_run:
            # ── 提取结构化错误 ──
            error_report = extract_errors(stdout, stderr, step)
            print_error_report(error_report, label)

            print(f"\n❌ 步骤 [{label}] 失败，流水线中止")
            return WorkflowResult(
                status="failure",
                summary=f"{label}失败",
                workflow=workflow_name,
                steps_completed=i,
                steps_total=total,
                failed_step=step,
                failure_category="target-response-abnormal",
                evidence=(
                    [it.raw_line for it in error_report.errors[:10]]
                    if error_report.errors
                    else stderr.splitlines()[-5:] if stderr else []
                ),
                error_report=error_report,
            )

    return WorkflowResult(status="success", summary=f"流水线完成（{total} 步）",
                          workflow=workflow_name, steps_completed=total, steps_total=total)


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_report(result: WorkflowResult) -> None:
    icon = {"success": "✅", "failure": "❌", "partial": "⚠️"}.get(result.status, "❓")
    print(f"\n{'='*60}")
    print(f"📊 流水线报告: {icon} {result.summary}")
    print(f"  流水线: {result.workflow}")
    print(f"  进度: {result.steps_completed}/{result.steps_total}")
    if result.failed_step:
        print(f"  失败步骤: {result.failed_step}")
    if result.failure_category:
        print(f"  失败分类: {result.failure_category}")

    # ── 结构化错误摘要 ──
    er = result.error_report
    if er and er.has_errors:
        print(f"\n  {'─'*54}")
        print(f"  📋 错误明细 (结构化提取)")
        print(f"  {'─'*54}")
        for idx, item in enumerate(er.errors[:15]):
            loc = item.location_str()
            code = f" [{item.error_code}]" if item.error_code and item.error_code != "GCC" else ""
            print(f"  {idx+1}. {loc}{code}")
            print(f"     {item.message}")

        if len(er.errors) > 15:
            print(f"\n  ... 及其他 {len(er.errors) - 15} 条错误")

        if er.total_warnings > 0:
            print(f"\n  ⚠️  另含 {er.total_warnings} 条编译警告")

    elif er and er.total_warnings > 0 and result.status == "success":
        print(f"\n  ⚠️  编译警告: {er.total_warnings} 条（流水线继续执行）")

    # ── 回退：原始证据 ──
    if result.evidence and not (er and er.has_errors):
        print(f"\n  📝 原始输出 (最后 {len(result.evidence)} 行):")
        for line in result.evidence:
            print(f"  │ {line}")

    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Workflow 流水线编排工具",
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--detect", action="store_true", help="探测环境")
    p.add_argument("--list", action="store_true", help="列出可用 workflow")
    p.add_argument("--run", help="执行指定 workflow")
    p.add_argument("--check", action="store_true",
                   help="仅执行跨 skill 边界冲突检查，不运行流水线")
    p.add_argument("--skip-conflict-check", action="store_true",
                   help="跳过跨 skill 边界冲突检查（不推荐）")
    p.add_argument("--dry-run", action="store_true", help="仅打印命令，不实际执行")
    p.add_argument("--build-system", choices=["keil", "cmake", "platformio"],
                   help="构建系统")
    p.add_argument("--project", help="工程路径")
    p.add_argument("--target", help="构建目标/环境/预设")
    p.add_argument("--port", help="串口（monitor 用）")
    p.add_argument("--baud", type=int, help="波特率")
    p.add_argument("--artifact", help="固件产物路径（可选）")
    p.add_argument("--flash-interface", help="烧录接口（OpenOCD）")
    p.add_argument("--flash-target", help="烧录目标（OpenOCD）")
    p.add_argument("--duration", type=int, default=10,
                   help="capture/monitor 采集时长（秒，默认 10）")
    p.add_argument("--save", help="日志捕获保存路径（capture 步骤用）")
    p.add_argument("--issue", help="Obsidian 问题记录文件路径（record 步骤用）")
    p.add_argument("--result", help="本次实验结果描述（record 步骤用）")
    p.add_argument("--commit-msg", help="Git 提交信息（commit 步骤用）")

    # ── devlog 参数 ──
    p.add_argument("--devlog-project-name", help="项目名称（devlog 用）")
    p.add_argument("--devlog-session-num", type=int, default=0,
                   help="会话序号（devlog 用，默认自动检测）")
    p.add_argument("--devlog-start-time", help="会话开始时间（devlog 用）")
    p.add_argument("--devlog-work-done", help="本次完成工作内容（devlog 用）")
    p.add_argument("--devlog-problems", help="遇到的问题及解决方案（devlog 用）")
    p.add_argument("--devlog-features", help="功能/模块变更（devlog 用）")
    p.add_argument("--devlog-progress", type=int, default=None,
                   help="整体进度百分比 0-100（devlog 用）")
    p.add_argument("--devlog-achieved", help="已实现的内容（devlog 用）")
    p.add_argument("--devlog-pending", help="待完成的内容（devlog 用）")
    p.add_argument("--devlog-next-steps", help="下一步计划（devlog 用）")
    p.add_argument("--devlog-notes", help="备注（devlog 用）")
    p.add_argument("--devlog-output", help="开发日志输出路径（devlog 用）")

    # ── Sprint / 敏捷管理参数 ──
    p.add_argument("--sprint", type=int, default=1, help="Sprint 编号")
    p.add_argument("--backlog-ids", nargs="*", type=int, default=None,
                   help="Sprint 选中的 Backlog ID 列表")

    # ── 移植流水线参数 ──
    p.add_argument("--source-chip", help="源芯片/平台（移植流水线用）")
    p.add_argument("--target-chip", help="目标芯片/平台（移植流水线用）")
    p.add_argument("--layers", default="1,2,3,4,5,6,7",
                   help="移植涉及层数（移植流水线用）")
    p.add_argument("--porting-type",
                   choices=["mcu-port", "hal-migration", "toolchain",
                            "rtos", "library", "module"],
                   default="mcu-port", help="移植类型（移植流水线用）")
    p.add_argument("--archive-obsidian", action="store_true",
                   help="移植后归档到 Obsidian")
    p.add_argument("--import-kb", action="store_true",
                   help="移植后导入知识库")
    p.add_argument("--tags", default="移植",
                   help="知识库标签（移植流水线用）")
    p.add_argument("--output", default="docs/移植文档/",
                   help="移植报告输出目录")

    p.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    merged_workflows = get_merged_workflows()

    if args.list:
        print("\n📋 可用 Workflow（按阶段分组）:")

        # ── 内置流水线（按阶段分组）─
        builtin_phases = [
            ("既有流水线（兼容）", ["build-flash-monitor", "build-flash-debug",
                                     "fix-verify-commit", "full-cycle"]),
            ("Phase 1: 项目初始化", ["init-project", "sprint-plan"]),
            ("Phase 2: Sprint 开发", ["bsp-bringup", "add-peripheral", "sprint-dev",
                                       "code-review-pipeline", "unit-test-pipeline",
                                       "arch-review"]),
            ("Phase 3: Sprint 管理", ["sprint-wrap", "risk-log", "change-assess"]),
            ("Phase 4: 硬件验证", ["hw-integration", "stress-test"]),
            ("Phase 5: 发布", ["release-prep", "release"]),
            ("辅助工具", ["dashboard"]),
        ]

        # 收集已显示的流水线名称，避免重复
        shown = set()

        for phase_name, wf_names in builtin_phases:
            items = [(n, "builtin") for n in wf_names if n in merged_workflows]
            if not items:
                continue
            print(f"\n  ═══ {phase_name} ═══")
            for name, src in items:
                wf = merged_workflows[name]
                steps_str = " → ".join(discover_step_label(s) for s in wf["steps"])
                print(f"  {name}: {wf['description']}")
                print(f"     步骤: {steps_str}")
                shown.add(name)

        # ── 动态发现的流水线（按 phase 分组）──
        discovered = scan_all_skills_for_pipelines()
        if discovered:
            # 按 phase 分组
            by_phase: dict[str, list[tuple[str, str]]] = {}
            for name in discovered:
                if name in shown:
                    continue  # 不重复显示
                wf = discovered[name]
                phase = wf.get("phase", "扩展流水线")
                src = _PIPELINE_SOURCES.get(name, "unknown")
                by_phase.setdefault(phase, []).append((name, src))

            for phase, items in sorted(by_phase.items()):
                print(f"\n  ═══ {phase} ═══")
                for name, src in items:
                    wf = discovered[name]
                    steps_str = " → ".join(discover_step_label(s) for s in wf["steps"])
                    params = wf.get("required_params", {})
                    param_str = ""
                    if params:
                        param_str = "  [" + ", ".join(params.keys()) + "]"
                    print(f"  {name}: {wf['description']}")
                    print(f"     步骤: {steps_str}")
                    if param_str:
                        print(f"     参数: {param_str}")
                    print(f"     来源: {src}")

        print(f"\n  构建系统: {', '.join(SCRIPT_MAP.keys())}")
        print(f"  总流水线: {len(merged_workflows)}（{len(discovered)} 个由 skill 动态注册）")
        return 0

    if args.detect:
        print("\n📊 Workflow 环境探测：")
        print(f"  Skills 根目录: {SKILLS_ROOT}")
        discovered = scan_all_skills_for_pipelines()
        if discovered:
            print(f"\n  动态流水线: {len(discovered)} 条")
            for name in discovered:
                src = _PIPELINE_SOURCES.get(name, "?")
                print(f"    ✅ {name} (来自 {src})")
        for bs in SCRIPT_MAP:
            print(f"\n  [{bs}]")
            for step in ["build", "flash", "debug", "monitor"]:
                path = resolve_script(bs, step)
                exists = path and path.exists()
                icon = "✅" if exists else "❌"
                print(f"    {icon} {step}: {path}")
        return 0

    if not args.run:
        parser.print_help()
        return 1

    if args.run not in merged_workflows:
        print(f"❌ 未知 workflow: {args.run}")
        print(f"  可用: {', '.join(merged_workflows.keys())}")
        return 1

    # ── 非构建类流水线不需要 --build-system ──
    # 检查流水线是否包含构建步骤
    wf_steps = merged_workflows[args.run]["steps"]
    has_build_step = any(s in wf_steps for s in
                         ["build", "flash", "monitor", "debug", "capture"])

    if has_build_step and not args.build_system:
        print("❌ 此流水线需要 --build-system 参数（keil / cmake / platformio）")
        return 1

    # ── 独立冲突检查模式 ──
    if args.check:
        print(f"\n🔍 跨 Skill 边界冲突检查（独立模式）")
        print(f"  Workflow: {args.run}")
        print(f"  构建系统: {args.build_system}")
        conflict = check_cross_skill_conflicts(args.build_system, args.run,
                                               verbose=True)
        print_conflict_report(conflict)
        return 0 if conflict.passed else 1

    result = run_workflow(args.run, args)
    print_report(result)
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
