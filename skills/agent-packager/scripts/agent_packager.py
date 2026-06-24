#!/usr/bin/env python3
"""
Agent Packager CLI — 嵌入式工作流 Agent 标准化打包与版本管理工具。

将 Chip 嵌入式 Agent 及其全套 skill 打包为工具无关的 .agentpkg 格式，
支持 CherryStudio / Continue.dev / Windsurf / Cursor / Claude Code 等宿主工具直接导入。

Usage:
    # 导出
    python agent_packager.py export --agent-dir <path> --skills-dir <path> -o <output>

    # 安装
    python agent_packager.py install -p <package.agentpkg> -t cherrystudio --interactive

    # 差分包
    python agent_packager.py diff --from <old.agentpkg> --to <new.agentpkg>

    # 版本管理
    python agent_packager.py info -p <package.agentpkg>
    python agent_packager.py check-update --current <pkg> --registry <url>
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="agent_packager",
        description="Agent Package 打包与版本管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── export ──
    p_export = subparsers.add_parser("export", help="导出 .agentpkg 包")
    p_export.add_argument("--agent-dir", required=True,
                          help="Agent 配置目录（含 SOUL.md/USER.md/FACT.md）")
    p_export.add_argument("--skills-dir", required=True,
                          help="Skills 根目录（含所有 skill 子目录）")
    p_export.add_argument("--output", "-o", required=True,
                          help="输出 .agentpkg 路径")
    p_export.add_argument("--version", "-v", default=None,
                          help="版本号（覆盖 manifest 中的版本）")
    p_export.add_argument("--include-mcp", action="store_true", default=False,
                          help="包含 MCP 服务器模板配置")
    p_export.add_argument("--sign", action="store_true", default=False,
                          help="对包进行 Ed25519 签名")
    p_export.add_argument("--private-key", default=None,
                          help="Ed25519 私钥路径（--sign 时需要）")
    p_export.add_argument("--exclude-skills", nargs="*", default=None,
                          help="打包时排除的 skill 名称列表（不包含在 .agentpkg 中）")

    # ── install ──
    p_install = subparsers.add_parser("install", help="安装 .agentpkg 到目标平台")
    p_install.add_argument("--package", "-p", required=True,
                           help=".agentpkg 包路径")
    p_install.add_argument("--target", "-t", required=True,
                           choices=["cherrystudio", "continue", "windsurf",
                                    "cursor", "claude-code", "project", "all"],
                           help="目标宿主平台（all=部署到所有已探测平台+项目目录）")
    p_install.add_argument("--agent-dir", default=None,
                           help="目标 Agent 目录（不指定则自动探测）")
    p_install.add_argument("--skills-dir", default=None,
                           help="目标 Skills 目录（不指定则自动探测）")
    p_install.add_argument("--interactive", "-i", action="store_true", default=False,
                           help="交互式配置向导")
    p_install.add_argument("--dry-run", action="store_true", default=False,
                           help="试运行（不实际写入）")
    p_install.add_argument("--verify-signature", action="store_true", default=False,
                           help="导入前验证 Ed25519 签名")
    p_install.add_argument("--public-key", default=None,
                           help="Ed25519 公钥路径（--verify-signature 时需要）")
    p_install.add_argument("--force", action="store_true", default=False,
                           help="跳过安全警告")

    # ── info ──
    p_info = subparsers.add_parser("info", help="查看包信息")
    p_info.add_argument("--package", "-p", required=True,
                        help=".agentpkg 包路径")

    # ── verify ──
    p_verify = subparsers.add_parser("verify", help="校验包完整性")
    p_verify.add_argument("--package", "-p", default=None,
                          help=".agentpkg 包路径")
    p_verify.add_argument("--installed", action="store_true", default=False,
                          help="校验已安装的版本")
    p_verify.add_argument("--target-dir", default=None,
                          help="已安装的 Agent 目标目录")

    # ── diff ──
    p_diff = subparsers.add_parser("diff", help="生成差分包")
    p_diff.add_argument("--from", dest="from_pkg", required=True,
                        help="源版本 .agentpkg 路径")
    p_diff.add_argument("--to", dest="to_pkg", required=True,
                        help="目标版本 .agentpkg 路径")
    p_diff.add_argument("--output", "-o", default=None,
                        help="输出 .agentpatch 差分包路径")

    # ── apply ──
    p_apply = subparsers.add_parser("apply", help="应用差分包升级")
    p_apply.add_argument("--patch", required=True,
                         help=".agentpatch 差分包路径")
    p_apply.add_argument("--target-dir", required=True,
                         help="目标 Agent 目录")

    # ── rollback ──
    p_rollback = subparsers.add_parser("rollback", help="回滚到指定版本")
    p_rollback.add_argument("--target-dir", required=True,
                            help="目标 Agent 目录")
    p_rollback.add_argument("--to", required=True,
                            help="回滚到的目标版本号")

    # ── check-update ──
    p_update = subparsers.add_parser("check-update", help="检查更新")
    p_update.add_argument("--current", required=True,
                          help="当前 .agentpkg 包路径")
    p_update.add_argument("--registry", required=True,
                          help="Registry URL")

    # ── generate-key ──
    p_key = subparsers.add_parser("generate-key", help="生成 Ed25519 签名密钥对")
    p_key.add_argument("--output", "-o", required=True,
                       help="输出目录")

    # ── list-versions ──
    p_list = subparsers.add_parser("list-versions", help="查看本地版本历史")
    p_list.add_argument("--target-dir", required=True,
                        help="目标 Agent 目录")

    # ── build-exe ──
    p_exe = subparsers.add_parser("build-exe", help="构建独立安装器 .exe（需 PyInstaller）")
    p_exe.add_argument("--package", "-p", default=None,
                       help=".agentpkg 包路径（默认自动查找）")
    p_exe.add_argument("--output", "-o", default="Chip-Setup.exe",
                       help="输出 .exe 路径（默认 Chip-Setup.exe）")
    p_exe.add_argument("--icon", default=None,
                       help="自定义图标 .ico 文件")

    args = parser.parse_args()
    return route(args)


def route(args):
    """路由到对应功能模块"""
    if args.command == "export":
        from packager_export import run_export
        return run_export(args)
    elif args.command == "install":
        from packager_install import run_install
        return run_install(args)
    elif args.command == "info":
        from packager_verify import run_info
        return run_info(args)
    elif args.command == "verify":
        from packager_verify import run_verify
        return run_verify(args)
    elif args.command == "diff":
        from packager_diff import run_diff
        return run_diff(args)
    elif args.command == "apply":
        from packager_diff import run_apply
        return run_apply(args)
    elif args.command == "rollback":
        from packager_version import run_rollback
        return run_rollback(args)
    elif args.command == "check-update":
        from packager_version import run_check_update
        return run_check_update(args)
    elif args.command == "generate-key":
        from packager_sign import run_generate_key
        return run_generate_key(args)
    elif args.command == "list-versions":
        from packager_version import run_list_versions
        return run_list_versions(args)
    elif args.command == "build-exe":
        from packager_build_exe import build_exe
        return build_exe(args.package, args.output, args.icon)
    return 1


if __name__ == "__main__":
    sys.exit(main())
