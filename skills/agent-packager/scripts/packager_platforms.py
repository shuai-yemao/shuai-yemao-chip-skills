#!/usr/bin/env python3
"""
Platform adapters module: 目标平台路径映射 / 适配逻辑

各平台的配置路径与安装规范定义在此。
"""

import os
import sys

# ── 平台路径探测规则 ───────────────────────────────────────────

PLATFORM_CONFIGS = {
    "cherrystudio": {
        "name": "CherryStudio",
        "description": "桌面端 AI 编码助手",
        "docsUrl": "https://cherrystudio.ai/docs",

        "detect": {
            "windows": [
                lambda: os.path.join(os.environ.get("APPDATA", ""), "CherryStudio", "Data"),
                lambda: os.path.join(os.environ.get("LOCALAPPDATA", ""), "CherryStudio", "Data"),
            ],
            "linux": [
                lambda: os.path.join(os.path.expanduser("~"), ".config", "CherryStudio"),
                lambda: os.path.join(os.path.expanduser("~"), ".local", "share", "CherryStudio"),
            ],
            "macos": [
                lambda: os.path.join(os.path.expanduser("~"), "Library", "Application Support", "CherryStudio"),
            ],
        },

        "pathMapping": {
            "skills": "{base}/Skills",
            "agent": "{base}/Agents/{agent_id}",
            "workflow": "{base}/Skills/workflow/scripts",
        },

        "note": "安装后需在 CherryStudio 中重启或重新加载 skills 列表"
    },

    "continue": {
        "name": "Continue.dev",
        "description": "开源 AI 编码助手",
        "docsUrl": "https://docs.continue.dev",

        "detect": {
            "windows": [
                lambda: os.path.join(os.path.expanduser("~"), ".continue"),
            ],
            "linux": [
                lambda: os.path.join(os.path.expanduser("~"), ".continue"),
            ],
            "macos": [
                lambda: os.path.join(os.path.expanduser("~"), ".continue"),
            ],
        },

        "pathMapping": {
            "skills": "{base}/skills",
            "agent": "{base}/",
            "workflow": "{base}/scripts",
        },

        "note": "SOUL.md 内容需要合并到 ~/.continue/config.json 的 system prompt 字段。"
                "也可通过 Continue 的 Context Provider 机制加载。"
    },

    "windsurf": {
        "name": "Windsurf",
        "description": "AI IDE（原名 Codeium）",
        "docsUrl": "https://docs.windsurf.com",

        "detect": {
            "windows": [
                lambda: os.path.join(os.path.expanduser("~"), ".windsurf"),
            ],
            "linux": [
                lambda: os.path.join(os.path.expanduser("~"), ".windsurf"),
            ],
            "macos": [
                lambda: os.path.join(os.path.expanduser("~"), ".windsurf"),
            ],
        },

        "pathMapping": {
            "skills": "{base}/skills",
            "agent": "{base}/",
            "workflow": "{base}/scripts",
        },

        "note": "Windsurf 通过 rules 机制加载 Agent 配置。"
                "SOUL.md 可复制为 ~/.windsurf/rules.md。"
    },

    "cursor": {
        "name": "Cursor",
        "description": "AI IDE (AI-first code editor)",
        "docsUrl": "https://docs.cursor.com",
        "detect": {
            "windows": [
                lambda: os.path.join(os.environ.get("APPDATA", ""), "Cursor"),
                lambda: os.path.join(os.path.expanduser("~"), ".cursor"),
            ],
            "linux": [lambda: os.path.join(os.path.expanduser("~"), ".cursor")],
            "macos": [lambda: os.path.join(os.path.expanduser("~"), ".cursor")],
        },
        "pathMapping": {"skills": "{base}/skills-cursor", "agent": "{base}/", "workflow": "{base}/scripts-cursor"},
        "note": "Cursor 从 .cursorrules 加载 Agent 人格，skills-cursor/ 目录存放自定义命令。"
    },

    "claude-code": {
        "name": "Claude Code CLI",
        "description": "Anthropic 官方 CLI 编码助手",
        "docsUrl": "https://docs.anthropic.com/en/docs/claude-code",
        "detect": {
            "windows": [lambda: os.path.join(os.path.expanduser("~"), ".claude")],
            "linux": [lambda: os.path.join(os.path.expanduser("~"), ".claude")],
            "macos": [lambda: os.path.join(os.path.expanduser("~"), ".claude")],
        },
        "pathMapping": {"skills": "{base}/skills", "agent": "{base}/", "workflow": "{base}/scripts"},
        "note": "Claude Code 通过 CLAUDE.md 加载项目级配置。skills 目录需在 settings.json 中注册。"
    },

    "ccswitch": {
        "name": "CCSwitch",
        "description": "Claude Code 多 Profile 切换管理工具（Windows）",
        "docsUrl": "",
        "detect": {
            "windows": [
                lambda: os.path.join(os.path.expanduser("~"), ".agents", "skills"),
                lambda: os.path.join(os.environ.get("USERPROFILE", ""), ".agents", "skills"),
            ],
            "linux": [lambda: os.path.join(os.path.expanduser("~"), ".agents", "skills")],
            "macos": [lambda: os.path.join(os.path.expanduser("~"), ".agents", "skills")],
        },
        "pathMapping": {
            "skills": "{base}",
            "agent": "{base}/../{profile}",
            "workflow": "{base}/workflow/scripts",
        },
        "note": "CCSwitch skills 目录为 ~/.agents/skills/，所有 profile 共享."
                "SOUL.md 作为 CLAUDE.md 写入对应 profile 目录。"
    },

    "project": {
        "name": "项目级配置",
        "description": "当前项目根目录的入口文件",
        "docsUrl": "",
        "detect": {
            "windows": [lambda: os.getcwd()],
            "linux": [lambda: os.getcwd()],
            "macos": [lambda: os.getcwd()],
        },
        "pathMapping": {"claude-md": "{base}/CLAUDE.md", "cursorrules": "{base}/.cursorrules", "clinerules": "{base}/.clinerules"},
        "note": "在项目根目录创建 CLAUDE.md / .cursorrules / .clinerules，各工具自动读取。"
    },
}


def get_platform_config(target):
    """获取目标平台配置"""
    return PLATFORM_CONFIGS.get(target)


def detect_base_path(target):
    """自动探测目标平台的数据目录"""
    config = get_platform_config(target)
    if not config:
        return None

    # 确定当前操作系统
    if sys.platform == "win32":
        os_key = "windows"
    elif sys.platform == "darwin":
        os_key = "macos"
    else:
        os_key = "linux"

    detectors = config.get("detect", {}).get(os_key, [])
    for detect_fn in detectors:
        try:
            path = detect_fn()
            if path and os.path.isdir(path):
                return path
        except Exception:
            continue

    # 都找不到，返回默认路径
    if detectors:
        try:
            return detectors[0]()
        except Exception:
            pass
    return None


def resolve_path(target, mapping_key, base=None, **kwargs):
    """解析目标平台的路径"""
    config = get_platform_config(target)
    if not config:
        return None

    if base is None:
        base = detect_base_path(target)
    if not base:
        return None

    mapping = config.get("pathMapping", {})
    template = mapping.get(mapping_key)
    if not template:
        return None

    path = template.replace("{base}", base)
    for k, v in kwargs.items():
        path = path.replace(f"{{{k}}}", str(v))

    return path


def list_supported_platforms():
    """列出所有支持的平台"""
    return list(PLATFORM_CONFIGS.keys())


def get_platform_info(target):
    """获取平台可读信息"""
    config = get_platform_config(target)
    if not config:
        return None

    base = detect_base_path(target)
    return {
        "name": config["name"],
        "description": config["description"],
        "detected": bool(base),
        "basePath": base or "未找到（将使用默认路径）",
        "note": config["note"],
    }
