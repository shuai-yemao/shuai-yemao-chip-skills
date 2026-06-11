#!/usr/bin/env python3
"""
Export module: 扫描 Agent 配置 + 所有 skill → 打包 .agentpkg

流程:
  1. 扫描 Agent 目录 (SOUL.md/USER.md/FACT.md)
  2. 扫描 Skills 目录 (所有 enabled skill 的 SKILL.md + scripts + references)
  3. 扫描 Workflow 脚本
  4. 收集 MCP 模板配置
  5. 敏感信息脱敏 (路径/串口/SN/Token)
  6. 生成 manifest.json
  7. 计算所有文件 SHA256 checksums
  8. 打包为 tar.gz (.agentpkg)
  9. 可选 Ed25519 签名
"""

import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone


SENSITIVE_PATTERNS = [
    # 用户目录路径（Windows）- 使用 callable 避免 regex 替换字符串中的尾部反斜杠转义问题
    (re.compile(r"C:\\Users\\[^\\]+\\", re.IGNORECASE),
     lambda m: "{USER_HOME}\\"),
    (re.compile(r"{USER_HOME}/]+/", re.IGNORECASE),
     lambda m: "{USER_HOME}/"),
    # 串口号
    (re.compile(r"COM\d+", re.IGNORECASE), "{SERIAL_PORT}"),
    # Python 路径
    (re.compile(r"python3?\d*\.exe", re.IGNORECASE), "{PYTHON_EXE}"),
    # API Token / 密钥
    (re.compile(r'(api_key|api_token|secret|password)\s*[=:]\s*["\']?[A-Za-z0-9_-]{16,}', re.IGNORECASE),
     lambda m: m.group(1) + ': "{REDACTED}"'),
]


def run_export(args):
    """CLI 入口"""
    agent_dir = os.path.abspath(args.agent_dir)
    skills_dir = os.path.abspath(args.skills_dir)
    output_path = os.path.abspath(args.output)

    # 解析排除列表
    exclude_skills = set()
    if hasattr(args, "exclude_skills") and args.exclude_skills:
        for name in args.exclude_skills:
            for n in name.split(","):
                exclude_skills.add(n.strip())
        if exclude_skills:
            print(f"    排除 skill: {', '.join(sorted(exclude_skills))}")

    if not os.path.isdir(agent_dir):
        print(f"[X] Agent 目录不存在: {agent_dir}")
        return 1
    if not os.path.isdir(skills_dir):
        print(f"[X] Skills 目录不存在: {skills_dir}")
        return 1

    print(f"[*] 导出 Agent 包")
    print(f"    Agent 目录:  {agent_dir}")
    print(f"    Skills 目录: {skills_dir}")
    print(f"    输出路径:    {output_path}")

    with tempfile.TemporaryDirectory(prefix="agentpkg_") as tmpdir:
        # 1. 收集文件
        collected = collect_files(agent_dir, skills_dir, tmpdir, args.include_mcp, exclude_skills)

        # 2. 敏感信息脱敏
        sanitize_files(collected["file_list"], tmpdir)

        # 3. 生成 manifest.json
        version = args.version or detect_current_version(agent_dir)
        manifest = build_manifest(collected, version, args)
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"    Manifest:    {manifest['name']} v{manifest['version']}")

        # 4. 计算 checksums
        checksums = compute_checksums(tmpdir)
        checksum_path = os.path.join(tmpdir, ".checksums")
        with open(checksum_path, "w", encoding="utf-8") as f:
            for rel_path, sha256 in sorted(checksums.items()):
                f.write(f"{sha256}  {rel_path}\n")

        # 5. 打包 tar.gz
        package_path = os.path.abspath(output_path)
        _create_tar_gz(tmpdir, package_path)

        # 6. 可选签名
        if args.sign:
            from packager_sign import sign_package
            if not args.private_key:
                print("[!] 需要 --private-key 参数进行签名")
                return 1
            sign_package(package_path, args.private_key)
            print(f"    [+PACKAGE]  Ed25519 签名完成")

        # 7. 文件大小
        pkg_size = os.path.getsize(package_path)
        unit = "KB" if pkg_size < 1024 * 1024 else "MB"
        size_val = pkg_size / 1024 if unit == "KB" else pkg_size / (1024 * 1024)

        print(f"    [+PACKAGE]  {output_path}  ({size_val:.1f} {unit})")
        print(f"    Skills: {manifest['skills']['total']}, "
              f"分类: {len(manifest['skills']['categories'])}")

    return 0


def collect_files(agent_dir, skills_dir, tmpdir, include_mcp, exclude_skills=None):
    """收集所有需要打包的文件"""
    if exclude_skills is None:
        exclude_skills = set()
    else:
        # 支持逗号分隔的字符串
        new_set = set()
        for item in exclude_skills:
            if isinstance(item, str) and "," in item:
                for n in item.split(","):
                    new_set.add(n.strip())
            else:
                new_set.add(item)
        exclude_skills = new_set

    collected = {
        "agent_files": [],
        "skill_dirs": [],
        "workflow_files": [],
        "file_list": [],
    }

    # ── Agent 配置文件 ──
    agent_target = os.path.join(tmpdir, "agent")
    os.makedirs(agent_target, exist_ok=True)

    # SOUL.md / USER.md（根目录）
    for fname in ["SOUL.md", "USER.md"]:
        src = os.path.join(agent_dir, fname)
        if os.path.isfile(src):
            dst = os.path.join(agent_target, fname)
            shutil.copy2(src, dst)
            collected["agent_files"].append(fname)

    # FACT.md（位于 memory/ 子目录）
    fact_src = os.path.join(agent_dir, "memory", "FACT.md")
    if os.path.isfile(fact_src):
        dst = os.path.join(agent_target, "FACT.md")
        shutil.copy2(fact_src, dst)
        collected["agent_files"].append("FACT.md (from memory/)")

    # ── Skills（跳过 exclude_skills）──
    skills_target = os.path.join(tmpdir, "skills")
    os.makedirs(skills_target, exist_ok=True)

    skill_names = []
    for entry in sorted(os.listdir(skills_dir)):
        if entry in exclude_skills:
            continue
        skill_path = os.path.join(skills_dir, entry)
        skill_sk = os.path.join(skill_path, "SKILL.md")
        if os.path.isdir(skill_path) and os.path.isfile(skill_sk):
            dst = os.path.join(skills_target, entry)
            shutil.copytree(skill_path, dst,
                            ignore=shutil.ignore_patterns("__pycache__", ".git"))
            skill_names.append(entry)
            collected["skill_dirs"].append(entry)

    # ── Workflow 脚本 ──
    workflow_src = os.path.join(skills_dir, "workflow", "scripts")
    workflow_target = os.path.join(tmpdir, "workflow", "scripts")
    if os.path.isdir(workflow_src):
        os.makedirs(os.path.join(tmpdir, "workflow"), exist_ok=True)
        shutil.copytree(workflow_src, workflow_target,
                        ignore=shutil.ignore_patterns("__pycache__"))

    # ── MCP 模板 ──
    if include_mcp:
        mcp_dir = os.path.join(tmpdir, "mcp")
        os.makedirs(mcp_dir, exist_ok=True)
        _gen_mcp_template(mcp_dir)

    # ── 收集所有文件相对路径 ──
    for root, _dirs, files in os.walk(tmpdir):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), tmpdir)
            if not rel.startswith("."):
                collected["file_list"].append(rel)

    print(f"    Agent 文件:  {len(collected['agent_files'])}")
    print(f"    Skills:      {len(collected['skill_dirs'])}")
    return collected


def sanitize_files(file_list, tmpdir):
    """对文件内容进行敏感信息脱敏"""
    count = 0
    for rel_path in file_list:
        full_path = os.path.join(tmpdir, rel_path)
        if not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue

        original = content
        for pattern, replacement in SENSITIVE_PATTERNS:
            if callable(replacement):
                content = pattern.sub(replacement, content)
            else:
                content = pattern.sub(replacement, content)

        if content != original:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            count += 1

    if count > 0:
        print(f"    脱敏文件:   {count}")


def build_manifest(collected, version, args):
    """构建 manifest.json"""
    from datetime import date

    skill_categories = _detect_skill_categories(collected["skill_dirs"])

    manifest = {
        "schemaVersion": "1.0",
        "name": "chip-embedded-agent",
        "version": version,
        "type": "embedded-agent",
        "description": "嵌入式工作流 Agent — STM32/ESP32 全流程开发（含 57 个技能 + 21 条流水线）",
        "author": "Chip",
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compatibility": {
            "platforms": ["windows", "linux", "macos"],
            "hosts": ["cherrystudio", "continue", "windsurf", "cursor", "claude-code", "project"],
            "minPythonVersion": "3.10"
        },
        "dependencies": {
            "tools": {
                "python": {
                    "version": ">=3.10",
                    "required": True,
                    "description": "Python 运行时"
                }
            },
            "mcpServers": {
                "github": {"required": False, "description": "GitHub API 操作"},
                "exa": {"required": False, "description": "Web 搜索"}
            },
            "externalTools": {
                "jlink": {
                    "required": False,
                    "platform": "windows",
                    "description": "J-Link Commander (烧录/调试)"
                },
                "keil": {
                    "required": False,
                    "platform": "windows",
                    "description": "Keil MDK UV4 (ARMCC 编译)"
                },
                "openocd": {
                    "required": False,
                    "description": "OpenOCD (烧录/调试)"
                }
            }
        },
        "skills": {
            "total": len(collected["skill_dirs"]),
            "categories": skill_categories,
            "required": [
                "stm32-hal-development", "build-keil", "flash-jlink",
                "workflow", "embedded-debugger-framework",
                "arm-core-registers", "mcu-peripheral-registers",
                "serial-monitor", "uart-module", "timer-module",
                "adc-module", "dma-module", "watchdog-module",
                "lowpower-design", "freertos-module", "rtos-debug"
            ],
            "optional": [
                "visa-debug", "motor-control", "can-debug",
                "modbus-debug", "fatfs-module", "usb-module"
            ]
        },
        "workflow": {
            "version": "3.1.0",
            "pipelines": 21,
            "agents": ["build", "dev", "pm", "verify", "release", "fix"]
        },
        "entryPoints": {
            "SOUL.md": "agent/SOUL.md",
            "workflowCoordinator": "workflow/scripts/workflow_coordinator.py",
            "primarySkill": "stm32-hal-development"
        },
        "hostConfig": {},
        "changelog": []
    }
    return manifest


def _detect_skill_categories(skill_names):
    """根据已安装 skill 列表推断分类统计"""
    categories = {
        "必备开发工具": 0,
        "开发板-ARM": 0,
        "开发板-RISC-V": 0,
        "常用模块": 0,
        "系统级设计": 0,
        "通信协议": 0,
        "操作系统": 0,
        "编码规范与代码质量": 0,
        "嵌入式项目文档与工作流": 0,
        "知识管理": 0,
        "中间件": 0,
    }

    # 关键词 → 分类映射
    mapping = {
        "必备开发工具": [
            "build-", "flash-", "debug-", "serial-monitor", "rtt-monitor",
            "static-analysis", "map-analyzer", "gang-flash",
            "firmware-sign", "ota-package", "option-bytes", "visa-debug",
            "agent-packager", "simplify",
        ],
        "开发板-ARM": [
            "stm32-hal-development", "stm32-spl-development",
            "arm-core-registers", "arm-memory-architecture",
            "arm-interrupt-exception", "mcu-peripheral-registers",
        ],
        "开发板-RISC-V": [
            "build-idf", "flash-idf",
        ],
        "常用模块": [
            "adc-module", "dma-module", "timer-module", "flash-module",
            "sram-module", "motor-control", "peripheral-driver",
            "watchdog-module", "usb-module", "i2c-bus", "spi-bus",
        ],
        "系统级设计": [
            "lowpower-design", "bootloader-design", "ota-update-system",
        ],
        "通信协议": [
            "can-debug", "modbus-debug",
        ],
        "操作系统": [
            "freertos-module", "rtos-debug",
        ],
        "编码规范与代码质量": [
            "coding-standards", "embedded-reviewer", "misra", "lixin",
        ],
        "嵌入式项目文档与工作流": [
            "workflow", "embedded-debugger-framework",
            "embedded-learning-path-framework", "devlog",
        ],
        "知识管理": [
            "knowledge-base-search", "kb-",
        ],
        "中间件": [
            "fatfs-module",
        ],
    }

    for name in skill_names:
        assigned = False
        for cat, keywords in mapping.items():
            for kw in keywords:
                if name.startswith(kw) or name == kw:
                    categories[cat] = categories.get(cat, 0) + 1
                    assigned = True
                    break
            if assigned:
                break

    # 过滤掉 0 值
    return {k: v for k, v in categories.items() if v > 0}


def compute_checksums(tmpdir):
    """计算目录下所有文件的 SHA256"""
    checksums = {}
    for root, _dirs, files in os.walk(tmpdir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, tmpdir)
            if rel_path.startswith("."):
                continue
            sha256 = hashlib.sha256()
            with open(full_path, "rb") as fp:
                for chunk in iter(lambda: fp.read(65536), b""):
                    sha256.update(chunk)
            checksums[rel_path] = sha256.hexdigest()
    return checksums


def _create_tar_gz(source_dir, output_path):
    """将目录打包为 tar.gz"""
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname="agent-package")


def _gen_mcp_template(mcp_dir):
    """生成 MCP 服务器配置模板"""
    mcp_config = {
        "mcpServers": {
            "github": {
                "type": "github",
                "token": "{GITHUB_TOKEN}",
                "description": "GitHub API — 请在此填入您的 GitHub Personal Access Token"
            },
            "exa": {
                "type": "exa",
                "apiKey": "{EXA_API_KEY}",
                "description": "Exa Web Search — 请在此填入您的 Exa API Key"
            }
        }
    }
    template_path = os.path.join(mcp_dir, "servers.json.template")
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2)

    # 同时生成 README 说明
    readme = """# MCP Server 配置说明

## 安装步骤

1. 将 `servers.json.template` 复制为 `servers.json`
2. 替换其中的 `{GITHUB_TOKEN}` 和 `{EXA_API_KEY}` 为实际值
3. 将 MCP 配置导入到目标工具的 MCP 配置文件中

## 不同工具的 MCP 配置位置

| 工具 | 配置路径 |
|------|---------|
| CherryStudio | 设置 → MCP 服务器 → 导入 |
| Cline | ~/.cline/mcp.json |
| Continue | ~/.continue/config.json |
"""
    with open(os.path.join(mcp_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)


def detect_current_version(agent_dir):
    """从 SOUL.md 或现有版本历史推断版本号"""
    # 默认版本
    return "1.0.0"


if __name__ == "__main__":
    import argparse

    class _Args:
        agent_dir = "."
        skills_dir = "."
        output = "test.agentpkg"
        version = "1.0.0"
        include_mcp = True
        sign = False
        private_key = None
    run_export(_Args())
