"""
桥服务器生命周期管理

管理 ai_eda bridge server (aiohttp, port 8787) 的启动/停止/状态检查。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# 默认 ai_eda 项目路径
DEFAULT_AIEDA_PATH = Path(r"{USER_HOME}\projects\ai-eda\ai_eda")
SERVER_URL = "http://127.0.0.1:8787"
TOKEN_FILE_NAME = ".bridge_token"

# 超时设置
PLUGIN_WAIT_TIMEOUT_S = 60
SERVER_START_TIMEOUT_S = 15


def _get_aieda_path() -> Path:
    """获取 ai_eda 项目根目录 (优先环境变量)"""
    env_path = os.environ.get("AIEDA_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_AIEDA_PATH


def _get_token_path() -> Path:
    return _get_aieda_path() / "aieda_python" / TOKEN_FILE_NAME


def _load_token() -> str | None:
    """从磁盘加载 bridge token"""
    tp = _get_token_path()
    if tp.exists():
        return tp.read_text(encoding="utf-8").strip()
    return None


def _request(path: str, method: str = "GET", data: bytes | None = None) -> dict[str, Any]:
    """向桥服务器发送 HTTP 请求 (带 token)"""
    token = _load_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{SERVER_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {"ok": True, "result": None}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {exc.code}", "details": body}
    except (urllib.error.URLError, ConnectionResetError, OSError) as exc:
        return {"ok": False, "error": "Connection failed", "details": str(exc)}


def is_server_running() -> bool:
    """检查桥服务器是否正在运行"""
    result = _request("/healthz")
    return result.get("ok") is True


def is_plugin_connected() -> bool:
    """检查 LCEDA Pro 插件是否已连接"""
    result = _request("/status")
    return result.get("ok") is True and result.get("plugin_connected") is True


def get_status() -> dict[str, Any]:
    """获取桥服务器完整状态"""
    return _request("/status")


def start_server() -> bool:
    """启动桥服务器 (异步, 返回是否启动成功)"""
    if is_server_running():
        print("[OK] 桥服务器已在运行")
        return True

    aieda_path = _get_aieda_path()
    server_script = aieda_path / "server.py"
    if not server_script.exists():
        print(f"[X] 找不到 server.py: {server_script}")
        return False

    python_exe = r"{USER_HOME}\AppData\Local\Programs\Python\Python312\{PYTHON_EXE}"

    print("[*] 启动桥服务器 (port 8787)...")
    # 使用 subprocess.Popen 启动后台进程 (Windows 上隐藏控制台)
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    proc = subprocess.Popen(
        [python_exe, str(server_script)],
        cwd=str(aieda_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
    )

    # 等待服务器就绪 (轮询 /healthz)
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while time.time() < deadline:
        if is_server_running():
            print("[OK] 桥服务器已启动")
            # 检查 token 文件
            if _get_token_path().exists():
                print(f"     Token: {_load_token()[:12]}...")
            return True
        time.sleep(0.5)

    # 超时——输出 stderr 供诊断
    stdout, stderr = proc.communicate(timeout=2)
    print(f"[X] 桥服务器启动超时")
    if stderr:
        print(f"     stderr: {stderr.decode('utf-8', errors='replace')[:500]}")
    return False


def wait_for_plugin(timeout_s: float = PLUGIN_WAIT_TIMEOUT_S) -> bool:
    """等待 LCEDA Pro 插件连接"""
    print(f"[*] 等待插件连接 (超时 {timeout_s}s)...")
    print("    请在 LCEDA Pro 中: 打开原理图 → AI EDA → Start Bridge")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = get_status()
        if status.get("plugin_connected"):
            meta = status.get("plugin_meta", {})
            print(f"[OK] 插件已连接")
            if meta:
                print(f"     插件信息: {json.dumps(meta, ensure_ascii=False)}")
            return True
        time.sleep(1)

    print(f"[X] 等待插件连接超时 ({timeout_s}s)")
    print("    请确保:")
    print("      1. LCEDA Pro 已打开目标原理图")
    print("      2. 已安装 aieda-js 插件")
    print("      3. 已点击 AI EDA > Start Bridge")
    return False


def stop_server() -> bool:
    """停止桥服务器"""
    result = _request("/shutdown", method="POST")
    if result.get("ok"):
        print("[OK] 桥服务器已停止")
        # 清理 token 文件
        tp = _get_token_path()
        if tp.exists():
            tp.unlink(missing_ok=True)
        return True
    else:
        print(f"[!] 停止请求已发送: {result}")
        return True  # 即使返回值不对也乐观处理


def read_schema() -> dict[str, Any] | None:
    """通过桥服务器读取原理图数据"""
    from protocol import BridgeCommand  # type: ignore

    sys.path.insert(0, str(_get_aieda_path() / "aieda_python"))
    from client import BridgeClient  # type: ignore

    client = BridgeClient()
    cmd = BridgeCommand(action="read_schema", payload={"all_pages": True})
    result = client.send_command(cmd)

    if result.get("ok"):
        data = result.get("result", {})
        counts = data.get("counts", {})
        print(f"[OK] 原理图读取完成:")
        print(f"     器件: {counts.get('components', 0)}")
        print(f"     网络: {counts.get('wires', 0)}")
        return data
    else:
        print(f"[X] 读取原理图失败: {result.get('error', 'Unknown error')}")
        return None
