#!/usr/bin/env python
"""Workflow 多 Agent 公共模块。

提供所有 Agent 共享的类型定义、工具函数和资源锁。
从原 workflow_runner.py 抽取，避免各 Agent 重复代码。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import subprocess
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

# ═══════════════════════════════════════════════════════════════
# 资源锁 — 防止多 Agent 竞争同一硬件/文件资源
# ═══════════════════════════════════════════════════════════════

LOCK_DIR = Path.home() / ".workflow_locks"

_RESOURCE_LOCKS: dict[str, str] = {}  # resource_type -> lock_path

# 资源类型定义
RESOURCE_TYPES = {
    "serial": "串口独占",      # 同一 COM 口只能一个进程用
    "jlink": "J-Link 探针独占", # J-Link 只能一个进程连
    "project": "工程目录独占",  # git/build 操作互斥
    "flash": "烧录通道独占",    # 烧录时禁止其他调试操作
    "git": "Git 操作互斥",     # git add/commit/push 互斥
}

# Agent 优先级（值越高越紧急）
AGENT_PRIORITY = {
    "fix-agent":    5,   # 修复闭环：最紧急
    "build-agent":  4,   # 编译/烧录：关键路径
    "release-agent":3,   # 发布：有时限
    "verify-agent": 2,   # 验证：串行依赖
    "dev-agent":    1,   # 开发：稳态工作
    "pm-agent":     0,   # 管理：后台任务
}


def _ensure_lock_dir():
    LOCK_DIR.mkdir(parents=True, exist_ok=True)


def _lock_path(resource: str, scope: str = "global") -> Path:
    """生成锁目录路径。resource=serial:{SERIAL_PORT}, scope=project_path"""
    safe = re.sub(r'[\\/:*?"<>|]', '_', f"{resource}_{scope}")
    return LOCK_DIR / f"{safe}.lockdir"


class ResourceLock:
    """目录级资源锁，防止多 Agent 竞争同一资源。

    基于 os.mkdir() 的原子性实现跨平台文件锁（Windows/macOS/Linux 均可用）。

    用法:
        with ResourceLock("serial", "{SERIAL_PORT}", timeout=30) as lock:
            if lock.acquired:
                # 安全使用串口
                ...
            else:
                print("串口被占用，跳过")
    """

    def __init__(self, resource_type: str, resource_name: str,
                 scope: str = "global", timeout: float = 30.0,
                 agent_priority: int = 0, wdt_timeout: float = 0):
        """wdt_timeout=0 表示不启用看门狗"""
        assert resource_type in RESOURCE_TYPES, f"未知资源类型: {resource_type}"
        self.lock_dir = _lock_path(resource_type, f"{resource_name}_{scope}")
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.timeout = timeout
        self.agent_priority = agent_priority
        self.wdt_timeout = wdt_timeout
        self.acquired = False

    def __enter__(self) -> "ResourceLock":
        _ensure_lock_dir()
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                os.mkdir(str(self.lock_dir))
                meta = {"pid": os.getpid(), "priority": self.agent_priority}
                try:
                    (self.lock_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
                except OSError:
                    pass
                # 看门狗启动：写首次 tick
                if self.wdt_timeout > 0:
                    wdt = {"tick": time.time(), "owner": f"pid={os.getpid()}"}
                    (self.lock_dir / "wdt.json").write_text(json.dumps(wdt), encoding="utf-8")
                self.acquired = True
                break
            except FileExistsError:
                # 看门狗检查：持有者是否超时未喂狗
                if self.wdt_timeout > 0:
                    wdt_path = self.lock_dir / "wdt.json"
                    if wdt_path.exists():
                        try:
                            wdt_data = json.loads(wdt_path.read_text(encoding="utf-8"))
                        except (OSError, json.JSONDecodeError):
                            wdt_data = {"tick": 0}
                        if time.time() - wdt_data.get("tick", 0) > self.wdt_timeout:
                            print(f"  [!] 看门狗: 锁 {self.lock_dir.stem} 超时({self.wdt_timeout}s)，强制回收")
                            # 强制回收锁
                            try:
                                ResourceLock._force_recover(self.lock_dir)
                                continue
                            except OSError:
                                pass
                # 检查是否是僵死锁
            except FileExistsError:
                # 检查是否是僵死锁
                try:
                    pf = self.lock_dir / "pid"
                    if pf.exists():
                        old_pid = int(pf.read_text(encoding="utf-8").strip())
                        if not ResourceLock._pid_exists(old_pid):
                            # 僵死锁，清理重试
                            try:
                                os.rmdir(str(self.lock_dir))
                            except OSError:
                                pass
                            continue
                except (ValueError, OSError):
                    pass
                # 优先级继承检测
                if self.agent_priority > 0:
                    try:
                        mf = self.lock_dir / "meta.json"
                        if mf.exists():
                            hm = json.loads(mf.read_text(encoding="utf-8"))
                            if hm.get("priority", 0) < self.agent_priority:
                                (self.lock_dir / "inherit.json").write_text(
                                    json.dumps({"inherited_by": self.agent_priority}), encoding="utf-8")
                    except (OSError, json.JSONDecodeError):
                        pass
                time.sleep(0.3)
        return self

    def __exit__(self, *args):
        if self.acquired:
            try:
                for fname in ["inherit.json", "meta.json", "wdt.json"]:
                    fp = self.lock_dir / fname
                    if fp.exists():
                        fp.unlink(missing_ok=True)
                os.rmdir(str(self.lock_dir))
            except OSError:
                pass
        self.acquired = False

    def watchdog_tick(self):
        """看门狗喂狗：更新 tick 时间戳（持锁方定期调用）"""
        if self.acquired and self.wdt_timeout > 0:
            wdt_path = self.lock_dir / "wdt.json"
            try:
                wdt = {"tick": time.time(), "owner": f"pid={os.getpid()}"}
                wdt_path.write_text(json.dumps(wdt), encoding="utf-8")
            except OSError:
                pass

    @staticmethod
    def _force_recover(lock_dir):
        """强制回收锁（看门狗超时后清理所有文件并删除目录）"""
        for f in lock_dir.iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(str(lock_dir))

    @staticmethod
    def effective_priority(lock_dir) -> int:
        """获取锁的有效优先级（含继承提升）"""
        meta_file = lock_dir / "meta.json"
        holder_prio = 0
        if meta_file.exists():
            try:
                holder_prio = json.loads(meta_file.read_text(encoding="utf-8")).get("priority", 0)
            except (OSError, json.JSONDecodeError):
                pass
        inherit_file = lock_dir / "inherit.json"
        if inherit_file.exists():
            try:
                inh = json.loads(inherit_file.read_text(encoding="utf-8")).get("inherited_by", 0)
                return max(holder_prio, inh)
            except (OSError, json.JSONDecodeError):
                pass
        return holder_prio

    @staticmethod
    def is_locked(resource_type: str, resource_name: str,
                  scope: str = "global") -> bool:
        ldir = _lock_path(resource_type, f"{resource_name}_{scope}")
        if not ldir.exists():
            return False
        try:
            os.rmdir(str(ldir))  # 能删掉说明锁无人持有
            os.mkdir(str(ldir))  # 恢复
            return False
        except OSError:
            return True  # 锁被持有

    @staticmethod
    def list_locks() -> list[dict]:
        """列出所有活跃锁"""
        _ensure_lock_dir()
        result = []
        for lf in sorted(LOCK_DIR.iterdir()):
            if lf.is_dir():
                pid_path = lf / "pid"
                try:
                    pid = int(pid_path.read_text(encoding="utf-8").strip()) if pid_path.exists() else -1
                    result.append({"name": lf.name, "pid": pid})
                except (ValueError, OSError):
                    result.append({"name": lf.name, "pid": -1})
        return result

    @staticmethod
    def cleanup_stale():
        """清理僵死锁（持有进程已不存在的）"""
        for lf in sorted(LOCK_DIR.iterdir()):
            if not lf.is_dir():
                continue
            pid_path = lf / "pid"
            try:
                if pid_path.exists():
                    pid = int(pid_path.read_text(encoding="utf-8").strip())
                    if not ResourceLock._pid_exists(pid):
                        pid_path.unlink(missing_ok=True)
                        os.rmdir(str(lf))
                else:
                    os.rmdir(str(lf))
            except (ValueError, OSError):
                try:
                    os.rmdir(str(lf))
                except OSError:
                    pass

    @staticmethod
    def watchdog_scan_all(max_age: float = 60.0) -> list[dict]:
        """扫描所有锁，看门狗超时检查。返回被强制回收的锁列表"""
        recovered = []
        if not LOCK_DIR.exists():
            return recovered
        for entry in LOCK_DIR.iterdir():
            if entry.suffix != ".lockdir":
                continue
            wdt_path = entry / "wdt.json"
            if not wdt_path.exists():
                continue
            try:
                wdt = json.loads(wdt_path.read_text(encoding="utf-8"))
                age = time.time() - wdt.get("tick", 0)
                if age > max_age:
                    lock_name = entry.stem
                    print(f"  [!] 看门狗: {lock_name} 超时(age={age:.0f}s > {max_age}s)")
                    try:
                        ResourceLock._force_recover(entry)
                        recovered.append({"lock": lock_name, "age": age})
                    except OSError as e:
                        print(f"  [X] 看门狗: {lock_name} 回收失败: {e}")
            except (OSError, json.JSONDecodeError):
                pass
        return recovered

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# ═══════════════════════════════════════════════════════════════
# 跨 Agent 通信 — 消息队列 (替换轮询 WorkflowState)
# ═══════════════════════════════════════════════════════════════

AGENT_QUEUE_DIR = Path.home() / ".agent_queues"

# 预定义队列名 → 消费者
AGENT_QUEUES = {
    "build":    "build-agent",     # 编译/烧录任务
    "dev":      "dev-agent",       # 开发任务
    "release":  "release-agent",   # 发布任务
    "fix":      "fix-agent",       # 修复任务
    "verify":   "verify-agent",    # 验证任务
    "pm":       "pm-agent",        # 管理任务
    "broadcast":"ALL",             # 广播：所有 Agent
}

# 队列消息优先级
MSG_PRIORITY = {"critical": 3, "high": 2, "normal": 1, "low": 0}


class AgentQueue:
    """文件级消息队列，参考 FreeRTOS xQueue 设计。

    跨进程（跨 Agent）通信用文件目录实现：
      ~/.agent_queues/<queue_name>/<seq_id>.msg

    每条消息为 JSON 文件，含 sender/type/payload/priority/timestamp。
    receive() 阻塞等待直到有新消息或超时。
    """

    _seq_counter: dict[str, int] = {}

    @staticmethod
    def send(queue_name: str, msg_type: str, payload: dict = None,
             sender: str = "unknown", priority: str = "normal") -> str:
        """发送消息到队列（非阻塞）"""
        AgentQueue._ensure_queue_dir(queue_name)
        seq = AgentQueue._seq_counter.get(queue_name, 0) + 1
        AgentQueue._seq_counter[queue_name] = seq

        msg = {
            "id": f"{int(time.time())}_{seq:06d}",
            "sender": sender,
            "type": msg_type,
            "payload": payload or {},
            "priority": MSG_PRIORITY.get(priority, 1),
            "timestamp": time.time(),
        }
        msg_path = AgentQueue._queue_dir(queue_name) / f"{msg['id']}.msg"
        msg_path.write_text(json.dumps(msg, ensure_ascii=False), encoding="utf-8")
        return msg["id"]

    @staticmethod
    def receive(queue_name: str, timeout: float = 30.0,
                peek: bool = False) -> dict | None:
        """从队列接收消息（阻塞，超时返回 None）

        peek=True 时只看不取（不移除文件）
        """
        AgentQueue._ensure_queue_dir(queue_name)
        deadline = time.time() + timeout

        while time.time() < deadline:
            msg_file = AgentQueue._find_oldest(queue_name)
            if msg_file:
                try:
                    msg = json.loads(msg_file.read_text(encoding="utf-8"))
                    if not peek:
                        msg_file.unlink(missing_ok=True)
                    return msg
                except (OSError, json.JSONDecodeError):
                    if not peek:
                        try:
                            msg_file.unlink(missing_ok=True)
                        except OSError:
                            pass
                    return None
            time.sleep(0.1)
        return None

    @staticmethod
    def receive_filtered(queue_name: str, msg_type: str = None,
                         min_priority: int = 0, timeout: float = 30.0) -> dict | None:
        """带过滤条件的接收，匹配 msg_type 和最低优先级"""
        AgentQueue._ensure_queue_dir(queue_name)
        deadline = time.time() + timeout

        while time.time() < deadline:
            qdir = AgentQueue._queue_dir(queue_name)
            candidates = []
            if qdir.exists():
                for f in sorted(qdir.iterdir()):
                    if f.suffix == ".msg":
                        try:
                            msg = json.loads(f.read_text(encoding="utf-8"))
                            prio_ok = msg.get("priority", 0) >= min_priority
                            type_ok = msg_type is None or msg.get("type") == msg_type
                            if prio_ok and type_ok:
                                candidates.append((f, msg))
                        except (OSError, json.JSONDecodeError):
                            pass
            if candidates:
                # 按优先级降序 + 时间升序
                candidates.sort(key=lambda x: (-x[1].get("priority", 0), x[1].get("timestamp", 0)))
                msg_file, msg = candidates[0]
                msg_file.unlink(missing_ok=True)
                return msg
            time.sleep(0.1)
        return None

    @staticmethod
    def purge(queue_name: str) -> int:
        """清空队列所有消息，返回清除数量"""
        qdir = AgentQueue._queue_dir(queue_name)
        count = 0
        if qdir.exists():
            for f in qdir.iterdir():
                if f.suffix == ".msg":
                    f.unlink(missing_ok=True)
                    count += 1
        return count

    @staticmethod
    def count(queue_name: str) -> int:
        """统计队列中待处理消息数"""
        qdir = AgentQueue._queue_dir(queue_name)
        if not qdir.exists():
            return 0
        return len([f for f in qdir.iterdir() if f.suffix == ".msg"])

    @staticmethod
    def list_messages(queue_name: str, limit: int = 10) -> list[dict]:
        """列出队列中所有消息摘要（不消费）"""
        qdir = AgentQueue._queue_dir(queue_name)
        if not qdir.exists():
            return []
        msgs = []
        for f in sorted(qdir.iterdir()):
            if f.suffix == ".msg":
                try:
                    msg = json.loads(f.read_text(encoding="utf-8"))
                    msgs.append({
                        "id": msg.get("id", ""),
                        "sender": msg.get("sender", ""),
                        "type": msg.get("type", ""),
                        "priority": msg.get("priority", 0),
                        "age": time.time() - msg.get("timestamp", time.time()),
                    })
                except (OSError, json.JSONDecodeError):
                    pass
            if len(msgs) >= limit:
                break
        return msgs

    # ── 内部方法 ──

    @staticmethod
    def _queue_dir(queue_name: str) -> Path:
        return AGENT_QUEUE_DIR / queue_name

    @staticmethod
    def _ensure_queue_dir(queue_name: str):
        d = AgentQueue._queue_dir(queue_name)
        d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _find_oldest(queue_name: str) -> Path | None:
        qdir = AgentQueue._queue_dir(queue_name)
        if not qdir.exists():
            return None
        msg_files = sorted([f for f in qdir.iterdir() if f.suffix == ".msg"])
        return msg_files[0] if msg_files else None


# ═══════════════════════════════════════════════════════════════
# Agent 中断系统 — 高优 Agent 打断低优 Agent 流水线
# ═══════════════════════════════════════════════════════════════

AGENT_SIGNAL_DIR = Path.home() / ".agent_signals"


class AgentInterrupt:
    """Agent 中断/抢占机制。

    高优先级 Agent 可发送中断信号打断低优先级 Agent 的流水线执行。
    被中断的 Agent 在当前步骤完成后挂起，释放资源锁，让高优 Agent 执行。

    中断信号为文件：~/.agent_signals/<target_agent>.sig
    """

    @staticmethod
    def send(target_agent: str, reason: str = "",
             sender: str = "unknown", priority: int = 5) -> str:
        """发送中断信号到目标 Agent"""
        AGENT_SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
        sig = {
            "target": target_agent,
            "sender": sender,
            "reason": reason,
            "priority": priority,
            "timestamp": time.time(),
            "id": f"intr_{int(time.time())}",
        }
        sig_path = AGENT_SIGNAL_DIR / f"{target_agent}.sig"
        sig_path.write_text(json.dumps(sig, ensure_ascii=False), encoding="utf-8")
        print(f"  [!] 中断信号: {sender} → {target_agent} ({reason})")
        return sig["id"]

    @staticmethod
    def check(agent_name: str) -> dict | None:
        """检查是否有中断信号（不消费），返回中断信息或 None"""
        sig_path = AGENT_SIGNAL_DIR / f"{agent_name}.sig"
        if not sig_path.exists():
            return None
        try:
            return json.loads(sig_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def ack(agent_name: str) -> bool:
        """确认并清除中断信号"""
        sig_path = AGENT_SIGNAL_DIR / f"{agent_name}.sig"
        if sig_path.exists():
            try:
                sig_path.unlink(missing_ok=True)
                return True
            except OSError:
                return False
        return False

    @staticmethod
    def list_pending() -> list[dict]:
        """列出所有待处理的中断"""
        if not AGENT_SIGNAL_DIR.exists():
            return []
        signals = []
        for f in AGENT_SIGNAL_DIR.iterdir():
            if f.suffix == ".sig":
                try:
                    s = json.loads(f.read_text(encoding="utf-8"))
                    signals.append(s)
                except (OSError, json.JSONDecodeError):
                    pass
        return signals

    @staticmethod
    def clear_all():
        """清除所有中断信号"""
        if AGENT_SIGNAL_DIR.exists():
            for f in AGENT_SIGNAL_DIR.iterdir():
                if f.suffix == ".sig":
                    f.unlink(missing_ok=True)

    @staticmethod
    def suspend_for_interrupt(agent_name: str, current_step: str,
                               lock_held: str = None) -> bool:
        """在步骤边界检查中断。收到中断时挂起当前操作。

        返回 True=收到中断并处理，False=无中断继续执行。
        """
        sig = AgentInterrupt.check(agent_name)
        if not sig:
            return False

        sender = sig.get("sender", "?")
        reason = sig.get("reason", "紧急抢占")
        prio = sig.get("priority", 0)

        print(f"\n{'!'*60}")
        print(f"  [!] 中断! {sender}(P{prio}) 抢占 {agent_name}({reason})")
        print(f"  当前步骤: {current_step}")
        if lock_held:
            print(f"  释放锁: {lock_held}")
        print(f"{'!'*60}\n")

        # 清除中断信号
        AgentInterrupt.ack(agent_name)
        return True


    @staticmethod
    def check_at_step(agent_name: str, step_index: int, total_steps: int,
                      step_label: str) -> bool:
        """步骤边界中断检查。放在每个 step 执行完后调用。

        返回 True=有中断且已处理（流水线应提前终止）
        """
        sig = AgentInterrupt.check(agent_name)
        if not sig:
            return False

        sender = sig.get("sender", "?")
        reason = sig.get("reason", "紧急抢占")
        prio = sig.get("priority", 0)
        print(f"\n{'!'*60}")
        print(f"  [!] 中断! {sender}(P{prio}) 抢占 {agent_name}")
        print(f"  挂起步骤: [{step_index+1}/{total_steps}] {step_label}")
        print(f"  原因: {reason}")
        print(f"  [i] 释放资源锁并挂起流水线")
        print(f"{'!'*60}\n")
        AgentInterrupt.ack(agent_name)
        return True


WORKFLOW_STATE_FILE = Path.home() / ".workflow_state.json"


class WorkflowState:
    """文件级共享状态，用于跨 Agent 传递 artifact/上下文。

    原理: 写入 ~/.workflow_state.json，所有 Agent 可读写。
    每个 key 代表一个全局变量（如 artifact_path、current_sprint）。
    """

    @staticmethod
    def _load() -> dict:
        if not WORKFLOW_STATE_FILE.exists():
            return {}
        try:
            return json.loads(WORKFLOW_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def _save(state: dict) -> None:
        WORKFLOW_STATE_FILE.write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def set(cls, key: str, value: Any) -> None:
        state = cls._load()
        state[key] = value
        cls._save(state)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls._load().get(key, default)

    @classmethod
    def delete(cls, key: str) -> None:
        state = cls._load()
        state.pop(key, None)
        cls._save(state)

    @classmethod
    def clear(cls) -> None:
        if WORKFLOW_STATE_FILE.exists():
            WORKFLOW_STATE_FILE.unlink()

    @classmethod
    def snapshot(cls) -> dict:
        """返回当前全部状态（用于日志/调试）"""
        return cls._load()


# 流水线链式触发表
# 定义完成后自动触发下一个流水线，实现跨 Agent 闭环
WORKFLOW_CHAINS: dict[str, dict] = {
    "sprint-dev": {
        "next": "sprint-wrap",
        "description": "Sprint 开发完成 → 自动进入 Sprint 收尾",
        "forward_args": ["project", "sprint"],
    },
    "fix-verify-commit": {
        "next": "build-flash-monitor",
        "description": "Bug 修复完成 → 自动编译烧录验证",
        "forward_args": ["project", "build_system", "target", "port", "baud"],
    },
    "release-prep": {
        "next": "release",
        "description": "发布准备完成 → 自动正式发布",
        "forward_args": ["project", "build_system"],
    },
}


def run_next_pipeline(pipeline_name: str, current_args,
                      forward_keys: list[str] | None = None) -> int:
    """从当前 Agent 调用协调器触发另一个流水线。

    参数:
        pipeline_name: 目标流水线名称
        current_args: 当前流水线的 argparse Namespace
        forward_keys: 需要转发给下一个流水线的参数名列表
    """
    coordinator = (
        Path(__file__).resolve().parent / "workflow_coordinator.py"
    )
    if not coordinator.exists():
        print(f"  [X] 协调器不存在: {coordinator}")
        return 1

    cmd = [sys.executable, str(coordinator), "--run", pipeline_name]

    # 转发关键参数
    if forward_keys and current_args:
        arg_map = vars(current_args)
        for key in forward_keys:
            val = arg_map.get(key)
            if val is not None:
                cli_key = key.replace("_", "-")
                if isinstance(val, bool):
                    if val:
                        cmd.append(f"--{cli_key}")
                elif isinstance(val, list):
                    cmd.append(f"--{cli_key}")
                    cmd.extend(str(v) for v in val)
                else:
                    cmd.append(f"--{cli_key}")
                    cmd.append(str(val))

    # 自动转发 dry-run（如果当前链是 dry-run，下游也 dry-run）
    if current_args and getattr(current_args, 'dry_run', False):
        cmd.append("--dry-run")

    print(f"\n  [i] 链式触发: 调用 {pipeline_name}")
    print(f"  $ {' '.join(cmd)}\n")

    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print(f"  [X] 链式流水线 {pipeline_name} 失败 (exit={proc.returncode})")
    else:
        print(f"  [OK] 链式流水线 {pipeline_name} 完成")
    return proc.returncode


def check_and_run_chain(pipeline_name: str, args) -> int:
    """流水线完成后检查是否有链式触发配置，有则自动执行。"""
    chain = WORKFLOW_CHAINS.get(pipeline_name)
    if not chain:
        return 0

    next_pipeline = chain.get("next")
    if not next_pipeline:
        return 0

    print(f"\n{'='*60}")
    print(f"  [链式触发] {pipeline_name} → {next_pipeline}")
    print(f"  {chain.get('description', '')}")
    print(f"{'='*60}")

    return run_next_pipeline(next_pipeline, args,
                             forward_keys=chain.get("forward_args"))


# ── 消息队列触发（Phase 2） ───────────────────────────────

# 队列名 → (目标 Agent 脚本, 默认流水线)
AGENT_QUEUE_ROUTES = {
    "build":   ("build_agent.py",   "build-flash-monitor"),
    "dev":     ("dev_agent.py",     "sprint-dev"),
    "fix":     ("fix_agent.py",     "fix-verify-commit"),
    "release": ("release_agent.py", "release"),
    "verify":  ("verify_agent.py",  "hw-integration"),
    "pm":      ("pm_agent.py",      "sprint-plan"),
}


def trigger_pipeline_via_queue(queue_name: str, pipeline: str = None,
                                args: list[str] = None, timeout: float = 30.0) -> bool:
    """通过消息队列触发流水线（异步，非阻塞）

    发送消息到目标 Agent 队列，Agent 的 queue_worker 会消费并执行。
    替代直接 subprocess 调用 run_next_pipeline()。

    返回 True 表示消息已入队（不保证流水线执行成功）
    """
    route = AGENT_QUEUE_ROUTES.get(queue_name)
    if not route:
        print(f"  [X] 未知队列: {queue_name}")
        return False

    agent_script, default_pipeline = route
    target_pipeline = pipeline or default_pipeline

    msg_id = AgentQueue.send(
        queue_name=queue_name,
        msg_type="run_pipeline",
        payload={"pipeline": target_pipeline, "args": args or []},
        sender="coordinator",
        priority="high",
    )
    print(f"  [→] 入队: {queue_name}/{target_pipeline} (msg={msg_id})")
    return True


def consume_queue(queue_name: str, agent_script: str,
                   timeout: float = 300.0) -> int:
    """队列消费循环：等待消息 → 执行流水线（单次调用）

    返回 0=无消息超时, 1=执行成功, -1=执行失败
    """
    msg = AgentQueue.receive(queue_name, timeout=min(timeout, 30.0))
    if msg is None:
        return 0  # 超时无消息

    msg_type = msg.get("type", "")
    payload = msg.get("payload", {})
    pipeline = payload.get("pipeline", "")
    msg_args = payload.get("args", [])

    if msg_type == "run_pipeline" and pipeline:
        print(f"  [←] 出队: {queue_name}/{pipeline}")
        # 构建命令行参数
        import subprocess
        scripts_dir = Path(__file__).resolve().parent
        cmd = [sys.executable, str(scripts_dir / agent_script),
               "--run", pipeline] + msg_args
        result = subprocess.run(cmd, capture_output=False, timeout=timeout)
        if result.returncode != 0:
            print(f"  [X] 流水线 {pipeline} 执行失败")
            return -1
        print(f"  [OK] 流水线 {pipeline} 完成")
        return 1
    else:
        print(f"  [-] 忽略未知消息: {msg_type}")
        return 0


# ═══════════════════════════════════════════════════════════════
# 结构错误提取 (从原 workflow_runner 抽取)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ErrorItem:
    """编译错误结构体"""
    source: str
    line: int | None
    col: int | None
    severity: str
    error_code: str
    message: str
    raw_line: str

    def location_str(self) -> str:
        parts = [self.source]
        if self.line is not None:
            parts.append(str(self.line))
        if self.col is not None:
            parts[-1] = f"{parts[-1]}:{self.col}"
        return ":".join(parts)

    def severity_icon(self) -> str:
        return {"error": "[X]", "fatal": "[X]", "warning": "[!]", "info": "[i]"}.get(
            self.severity, "[?]"
        )


@dataclass
class ErrorReport:
    """编译错误报告"""
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


_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(
        r"^(?P<file>[^\s:]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*"
        r"(?P<severity>error|warning|fatal error|note):\s*(?P<msg>.+)$",
        re.IGNORECASE
    ), "gcc"),
    (re.compile(
        r"^(?P<file>[^\s:]+)\((?P<line>\d+)\):\s*"
        r"(?P<severity>error|warning|fatal error):\s*(?:#(?P<code>\d+(?:-[A-Z])?):)?\s*(?P<msg>.+)$",
        re.IGNORECASE
    ), "keil"),
    (re.compile(
        r"^(?P<severity>Error|Warning|Fatal error)\[(?P<code>[^\]]+)\]:\s*"
        r"(?P<msg>.+?)\s+(?P<file>[^\s]+)\s+(?P<line>\d+)$",
        re.IGNORECASE
    ), "iar"),
    (re.compile(
        r"^(?P<severity>Error|Warn|Debug|Info)\s*:\s*(?:\[(?P<target>[^\]]+)\]\s*)?(?P<msg>.+)$",
    ), "openocd"),
    (re.compile(
        r"^[-]*\s*(?P<severity>ERROR|WARNING):\s*(?P<msg>.+)$",
    ), "jlink"),
    (re.compile(
        r"^(?P<file>make(?:\[\d+\])?|cmake):\s*\*+\s*\[(?P<target>[^\]]+)\]\s*"
        r"(?P<severity>Error)\s*(?P<code>\d+)$",
    ), "make"),
]


def extract_errors(output: str, stderr: str, step_type: str) -> ErrorReport:
    combined = f"{output}\n{stderr}"
    lines = combined.splitlines()
    report = ErrorReport(step_name=step_type)
    seen = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for pattern, source in _ERROR_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            groups = match.groupdict()
            file_path = groups.get("file", groups.get("target", ""))
            if not file_path or file_path == step_type:
                file_path = source
            line_num = None
            if "line" in groups and groups["line"]:
                try:
                    line_num = int(groups["line"])
                except (ValueError, TypeError):
                    pass
            col_num = None
            if "col" in groups and groups["col"]:
                try:
                    col_num = int(groups["col"])
                except (ValueError, TypeError):
                    pass
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
            error_code = groups.get("code", groups.get("target", ""))
            if not error_code:
                error_code = source.upper()
            message = (groups.get("msg") or "").strip()
            dedup_key = (file_path, line_num, severity, message[:80])
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            item = ErrorItem(
                source=file_path, line=line_num, col=col_num,
                severity=severity, error_code=error_code[:20],
                message=message, raw_line=stripped[:200],
            )
            if severity in ("error", "fatal"):
                report.total_errors += 1
            elif severity == "warning":
                report.total_warnings += 1
            report.items.append(item)
    report.raw_stderr = stderr
    if stderr:
        report.raw_last_lines = stderr.strip().splitlines()[-20:]
    return report


def print_error_report(report: ErrorReport, step_label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  错误报告 — [{step_label}]")
    print(f"{'='*60}")
    errors = report.errors
    warnings = report.warnings
    if errors:
        print(f"\n  [X] 错误 ({len(errors)} 个):")
        print(f"  {'-'*54}")
        for item in errors:
            loc = item.location_str()
            code_tag = f"[{item.error_code}] " if item.error_code and item.error_code != "GCC" else ""
            print(f"  {item.severity_icon()} {loc}")
            print(f"     {code_tag}{item.message}")
            print()
    if warnings:
        print(f"\n  [!]  警告 ({len(warnings)} 个):")
        print(f"  {'-'*54}")
        for item in warnings[:10]:
            loc = item.location_str()
            code_tag = f"[{item.error_code}] " if item.error_code and item.error_code != "GCC" else ""
            print(f"  [!]  {loc}")
            print(f"     {code_tag}{item.message}")
        if len(warnings) > 10:
            print(f"\n  ... 还有 {len(warnings) - 10} 个警告")
        print()
    print(f"  {'-'*54}")
    print(f"  总计: [X] {report.total_errors} 错误  [!]  {report.total_warnings} 警告")
    print(f"{'='*60}\n")
    if not report.items and report.raw_last_lines:
        print(f"  [?] 原始 stderr 内容 (末 {len(report.raw_last_lines)} 行):")
        print(f"  {'-'*54}")
        for line in report.raw_last_lines:
            print(f"  | {line}")
        print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# Step / Workflow 定义
# ═══════════════════════════════════════════════════════════════

STEP_LABELS = {
    "build": "编译", "flash": "烧录", "monitor": "串口监控",
    "capture": "日志采集", "record": "问题归档", "commit": "Git 提交",
    "debug": "GDB 调试", "devlog": "开发日志",
    "static-analysis": "静态分析", "map-analyze": "Map 分析",
    "firmware-sign": "固件签名", "ota-package": "OTA 打包",
    "aes-encrypt": "AES 加密", "push-ota": "OTA 推送(Ymodem/HTTP)",
    "wifi-config": "WiFi 配网配置", "mqtt-connect": "MQTT 连接",
    "cloud-verify": "云平台数据验证",
    "verify": "功能验证", "stress-test": "稳定性测试",
    "unit-test": "单元测试", "code-review": "代码审查",
    "peripheral-test": "外设测试", "sprint-plan": "Sprint 规划",
    "sprint-review": "Sprint 评审", "sprint-retro": "Sprint 回顾",
    "init-bsp": "BSP 初始化", "hw-integration": "硬件集成",
    "change-assess": "变更评估", "risk-log": "风险登记",
    "dashboard": "仪表盘", "arch-review": "架构评审",
    "oop-check": "OOP 合规检查",
    "refine": "需求细化", "research": "多源调研",
    "plan": "方案设计", "execute": "执行开发",
    "skill-scan": "技能扫描", "skill-fix": "技能修复",
    "schematic-review": "原理图审查",
    "skill-check": "技能变更检测", "skill-checkpoint": "技能版本节点",
}

STEP_ICONS = {
    "build": "🔨", "flash": "⚡", "monitor": "📡", "capture": "📥",
    "record": "📋", "commit": "📝", "debug": "🐛", "devlog": "📓",
    "static-analysis": "🔍", "map-analyze": "📊", "firmware-sign": "🔑",
    "ota-package": "📦", "aes-encrypt": "🔒", "push-ota": "📤",
    "wifi-config": "📶", "mqtt-connect": "🔗", "cloud-verify": "☁️",
    "verify": "✅", "stress-test": "💪",
    "unit-test": "🧪", "code-review": "👁", "peripheral-test": "🔌",
    "sprint-plan": "📐", "sprint-review": "📋", "sprint-retro": "🔄",
    "init-bsp": "🚀", "hw-integration": "🔗", "change-assess": "📊",
    "risk-log": "⚠️", "dashboard": "📈", "arch-review": "🏗",
    "oop-check": "🔒",
    "refine": "🎯", "research": "🔬",
    "plan": "📋", "execute": "⚙️",
    "skill-scan": "🔎", "skill-fix": "🛠️",
    "schematic-review": "📐",
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
    # ── 基础流水线（多 Agent 兼容）──
    "build-flash-monitor": {
        "description": "编译 → 烧录 → 串口监控（标准验证）",
        "steps": ["build", "flash", "monitor"],
        "agent": "build-agent",
    },
    "build-flash-debug": {
        "description": "编译 → 烧录 → GDB 调试",
        "steps": ["build", "flash", "debug"],
        "agent": "build-agent",
    },
    "full-cycle": {
        "description": "编译 → 烧录 → 串口监控 → 开发日志（完整验证闭环）",
        "steps": ["build", "flash", "monitor", "devlog"],
        "agent": "build-agent",
    },
    "fix-verify-commit": {
        "description": "编译 → 烧录 → 日志采集 → 问题归档 → Git 提交（Bug 修复闭环）",
        "steps": ["build", "flash", "capture", "record", "commit"],
        "agent": "fix-agent",
    },
    # ── Phase 1: 项目初始化 ──
    "init-project": {
        "description": "敏捷管理初始化: 创建 Backlog/Risk Register/docs 目录",
        "steps": ["init-bsp"],
        "agent": "pm-agent",
    },
    "sprint-plan": {
        "description": "Sprint 规划: 选择 Backlog → 生成 Sprint Plan 文档 → 设定 DoD",
        "steps": ["sprint-plan"],
        "agent": "pm-agent",
    },
    # ── Phase 2: Sprint 开发 ──
    "bsp-bringup": {
        "description": "BSP 初始化: 编译 → 烧录 → 功能验证 → 开发日志",
        "steps": ["build", "flash", "monitor", "devlog"],
        "agent": "dev-agent",
    },
    "add-peripheral": {
        "description": "外设添加: 编译 → 烧录 → 外设测试 → OOP 检查 → 开发日志",
        "steps": ["build", "flash", "peripheral-test", "oop-check", "devlog"],
        "agent": "dev-agent",
    },
    "sprint-dev": {
        "description": "Sprint 开发: 编译 → 静态分析 → 烧录 → 串口监控 → 验证 → 开发日志",
        "steps": ["build", "static-analysis", "flash", "monitor", "verify", "devlog"],
        "agent": "dev-agent",
    },
    "code-review-pipeline": {
        "description": "代码审查: 静态分析 → 代码审查 → 编译验证 → 功能验证",
        "steps": ["static-analysis", "code-review", "build", "verify"],
        "agent": "dev-agent",
    },
    "unit-test-pipeline": {
        "description": "单元测试: 静态分析 → 单元测试(主机端) → 编译",
        "steps": ["static-analysis", "unit-test", "build"],
        "agent": "dev-agent",
    },
    "arch-review": {
        "description": "架构评审: MCU 选型/引脚分配/系统设计 Review",
        "steps": ["arch-review"],
        "agent": "dev-agent",
    },
    # ── Phase 3: Sprint 管理 ──
    "sprint-wrap": {
        "description": "Sprint 收尾: 开发日志 → Sprint Review → Sprint Retro → Backlog 更新",
        "steps": ["devlog", "sprint-review", "sprint-retro"],
        "agent": "pm-agent",
    },
    "risk-log": {
        "description": "风险登记册更新",
        "steps": ["risk-log"],
        "agent": "pm-agent",
    },
    "change-assess": {
        "description": "变更影响评估: 变更说明文档 → 七层引脚审查清单",
        "steps": ["change-assess"],
        "agent": "pm-agent",
    },
    # ── Phase 4: 硬件验证 ──
    "hw-integration": {
        "description": "硬件集成测试: 编译 → 烧录 → 外设通信测试 → 稳定性测试",
        "steps": ["build", "flash", "peripheral-test", "stress-test"],
        "agent": "verify-agent",
    },
    "stress-test": {
        "description": "稳定性测试: 烧录 → 长时间日志采集 → 结果分析",
        "steps": ["flash", "stress-test"],
        "agent": "verify-agent",
    },
    "schematic-review": {
        "description": "原理图审查: BOM/电源树/引脚分配/网络拓扑/设计规则检查",
        "steps": ["schematic-review"],
        "agent": "verify-agent",
    },
    # ── Phase 5: 发布 ──
    "release-prep": {
        "description": "发布准备: 编译 → 静态分析 → .map 分析 → 固件签名 → OTA 打包",
        "steps": ["build", "static-analysis", "map-analyze", "firmware-sign", "ota-package"],
        "agent": "release-agent",
    },
    "release": {
        "description": "正式发布: 编译 → 固件签名 → OTA 打包 → 开发日志",
        "steps": ["build", "firmware-sign", "ota-package", "devlog"],
        "agent": "release-agent",
    },
    # ── Phase 5b: OTA 发布流水线 ──
    "ota-release": {
        "description": "OTA 全流程发布: 编译 → 签名 → AES 加密 → OTA 打包 → Ymodem/HTTP 推送",
        "steps": ["build", "firmware-sign", "aes-encrypt", "ota-package", "push-ota"],
        "agent": "release-agent",
    },
    # ── Phase 5c: 云接入配置流水线 ──
    "cloud-access": {
        "description": "云接入配置: WiFi 配网 → MQTT 连接 → 云平台数据验证",
        "steps": ["wifi-config", "mqtt-connect", "cloud-verify"],
        "agent": "dev-agent",
    },
    # ── 仪表盘 ──
    "dashboard": {
        "description": "项目仪表盘: 生成/更新 HTML 仪表盘",
        "steps": ["dashboard"],
        "agent": "dev-agent",
    },
    # ── Phase 0: 项目调研（前开发阶段）──
    "project-dev": {
        "description": "完整开发闭环: 需求细化 → 多源调研 → 方案设计 → 执行开发 → 开发日志",
        "steps": ["refine", "research", "plan", "execute", "devlog"],
        "agent": "dev-agent",
    },
    # ── Phase 7: 技能优化闭环 ──
    "skill-optimize": {
        "description": "技能优化: Darwin 评分 → 检索补全 → 修复 SKILL.md → 开发日志",
        "steps": ["skill-scan", "research", "skill-fix", "devlog"],
        "agent": "dev-agent",
    },
    # ── Phase 8: 技能系统版本管理 ──
    "skill-maintenance": {
        "description": "技能版���维护: 检测变更 → 创建版本节点(自动检查点, 每10分钟)",
        "steps": ["skill-check", "skill-checkpoint"],
        "agent": "dev-agent",
    },
}


def discover_step_label(step: str) -> str:
    if step in STEP_LABELS:
        return STEP_LABELS[step]
    known_prefixes = {
        "porting": "移植", "analyze": "分析",
        "document": "文档", "archive": "归档",
    }
    for prefix, label in known_prefixes.items():
        if step.startswith(prefix):
            suffix = step[len(prefix):].lstrip('-')
            if suffix:
                suffix_label = {"analyze": "分析", "execute": "执行",
                                "document": "文档", "report": "报告"}.get(suffix, suffix)
                return f"{label}{suffix_label}"
            return label
    return step


def discover_step_icon(step: str) -> str:
    if step in STEP_ICONS:
        return STEP_ICONS[step]
    icon_prefixes = {"porting": "📦", "analyze": "📊", "document": "📄", "archive": "🗄"}
    for prefix, icon in icon_prefixes.items():
        if step.startswith(prefix):
            return icon
    return "❓"


# ═══════════════════════════════════════════════════════════════
# 脚本路径解析
# ═══════════════════════════════════════════════════════════════

def resolve_script(build_system: str, step: str) -> Path | None:
    # 项目管理步
    if step in ("sprint-plan", "sprint-review", "sprint-retro",
                "risk-log", "change-assess", "init-bsp"):
        script = SKILLS_ROOT / "workflow" / "scripts" / "sprint_helper.py"
        return script if script.exists() else None

    # 仪表盘
    if step == "dashboard":
        for candidate in [
            SKILLS_ROOT / "obsidian-viz" / "references" / "init-project.bat",
            SKILLS_ROOT / "obsidian-viz" / "scripts" / "init_project.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # 知识库
    if step == "record":
        script = SKILLS_ROOT / "knowledge-base-search" / "scripts" / "record_issue.py"
        return script if script.exists() else None
    if step == "commit":
        return Path(sys.executable)
    if step == "devlog":
        for candidate in [SKILLS_ROOT / "devlog" / "scripts" / "devlog.py"]:
            if candidate.exists():
                return candidate
        return None

    # 静态分析
    if step == "static-analysis":
        for candidate in [
            SKILLS_ROOT / "static-analysis" / "scripts" / "static_analysis.py",
            SKILLS_ROOT / "static-analysis" / "static_analysis.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # 单元测试 (minunit)
    if step == "unit-test":
        candidate = SKILLS_ROOT / "doc-automation" / "scripts" / "minunit_runner.py"
        return candidate if candidate.exists() else None

    # Map 分析
    if step == "map-analyze":
        for candidate in [
            SKILLS_ROOT / "map-analyzer" / "scripts" / "map_analyzer.py",
            SKILLS_ROOT / "map-analyzer" / "map_analyzer.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # 固件签名
    if step == "firmware-sign":
        for candidate in [
            SKILLS_ROOT / "firmware-sign" / "scripts" / "firmware_signer.py",
            SKILLS_ROOT / "firmware-sign" / "firmware_sign.py",
            SKILLS_ROOT / "firmware-sign" / "scripts" / "firmware_sign.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # OTA 打包
    if step == "ota-package":
        for candidate in [
            SKILLS_ROOT / "ota-package" / "scripts" / "ota_packager.py",
            SKILLS_ROOT / "ota-package" / "ota_package.py",
            SKILLS_ROOT / "ota-package" / "scripts" / "ota_package.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    # Keil flash fallback
    if step == "flash" and build_system == "keil":
        primary = SKILLS_ROOT / "flash-keil" / "scripts" / "keil_flasher.py"
        if primary.exists():
            return primary
        for f in [
            SKILLS_ROOT / "flash-jlink" / "scripts" / "jlink_flasher.py",
            SKILLS_ROOT / "flash-jlink" / "flash_jlink.py",
        ]:
            if f.exists():
                return f
        return None

    # capture / peripheral-test / verify → monitor
    if step in ("capture", "peripheral-test", "verify"):
        step = "monitor"

    # 移植流水线
    if step == "porting-analyze":
        return SKILLS_ROOT / "code-porting" / "scripts" / "check_reg_compat.py"
    if step == "porting-document":
        return SKILLS_ROOT / "code-porting" / "scripts" / "gen_porting_report.py"

    # 压力测试
    if step == "stress-test":
        script = SKILLS_ROOT / "serial-monitor" / "scripts" / "serial_monitor.py"
        return script if script.exists() else None

    # 原理图审查 (pcb-analysis)
    if step == "schematic-review":
        for candidate in [
            SKILLS_ROOT / "pcb-analysis" / "scripts" / "pcb_analyzer.py",
        ]:
            if candidate.exists():
                return candidate
        return None

    mapping = SCRIPT_MAP.get(build_system)
    if not mapping or step not in mapping:
        return None
    return SKILLS_ROOT / mapping[step]


# ═══════════════════════════════════════════════════════════════
# 跨 Skill 边界冲突检测
# ═══════════════════════════════════════════════════════════════

CROSS_SKILL_RULES = {
    "missing-step-mapping": {
        "severity": "error",
        "condition": lambda bs, steps: any(
            s not in SCRIPT_MAP.get(bs, {})
            for s in steps if s not in (
                "record", "commit", "capture", "devlog",
                "static-analysis", "unit-test", "map-analyze",
                "firmware-sign", "ota-package", "verify",
                "stress-test", "code-review", "oop-check",
                "peripheral-test", "sprint-plan", "sprint-review",
                "sprint-retro",
                "init-bsp", "hw-integration", "change-assess",
                "risk-log", "dashboard", "arch-review",
                "skill-scan", "skill-fix", "schematic-review",
            )
        ),
        "message": "流水线中的某步骤在构建系统映射中不存在。",
        "fix": "确认 steps 是否在当前构建系统支持的步骤范围内",
    },
    "unknown-build-system": {
        "severity": "error",
        "condition": lambda bs, steps: bs not in SCRIPT_MAP,
        "message": f"不支持的构建系统类型。支持: {', '.join(SCRIPT_MAP.keys())}",
        "fix": "指定正确的 --build-system 参数",
    },
    "esp-build-vs-jlink": {
        "severity": "warning",
        "condition": lambda bs, steps: (
            "flash" in steps
            and SCRIPT_MAP.get(bs, {}).get("flash") == "flash-jlink"
        ),
        "message": "J-Link 主要用于 ARM Cortex-M 系列。ESP32 标准烧录方式为 USB-UART。",
        "fix": "对 ESP32 使用 --build-system platformio 或 idf",
    },
    "platformio-build-vs-openocd-debug": {
        "severity": "error",
        "condition": lambda bs, steps: bs == "platformio" and "debug" in steps
            and SCRIPT_MAP.get(bs, {}).get("debug") != "debug-platformio",
        "message": "PlatformIO 应使用 debug-platformio 进行调试。",
        "fix": "确保 SCRIPT_MAP 中 platformio 的 debug 映射为 debug-platformio",
    },
    "keil-build-platform-check": {
        "severity": "warning",
        "condition": lambda bs, steps: bs == "keil" and sys.platform != "win32",
        "message": "Keil MDK 仅 Windows 原生支持。",
        "fix": "在 Windows 执行，或将构建迁移到 build-cmake + ARM GCC",
    },
    "debug-requires-elf": {
        "severity": "warning",
        "condition": lambda bs, steps: "debug" in steps and "build" not in steps,
        "message": "流水线包含 debug 但不含 build 步骤。GDB 需要 .elf 文件（含调试符号）。",
        "fix": "添加 build 步骤到流水线，或通过 --artifact 指定已有的 .elf",
    },
    "jlink-serial-contention": {
        "severity": "warning",
        "condition": lambda bs, steps: "flash" in steps and "monitor" in steps,
        "message": "烧录和串口监控同时进行可能导致资源竞争。",
        "fix": "Agent 会自动使用 ResourceLock 管理串口/J-Link 资源",
    },
    "git-conflict-risk": {
        "severity": "warning",
        "condition": lambda bs, steps: "commit" in steps and "record" in steps,
        "message": "Git 提交和问题归档可能同时访问 Obsidian Vault。",
        "fix": "Agent 会自动使用 ResourceLock 管理 Git 资源",
    },
}


@dataclass
class ConflictResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def check_cross_skill_conflicts(
    build_system: str | None,
    workflow_name: str,
    verbose: bool = False,
) -> ConflictResult:
    wf = WORKFLOWS.get(workflow_name)
    if not wf:
        return ConflictResult(passed=False, errors=[f"未知 workflow: {workflow_name}"])
    steps = wf["steps"]
    errors = []
    warnings = []
    suggestions = []

    # 如果 build_system 为 None，检查流水线是否只包含 AI 推理步骤
    if build_system is None:
        _ai_steps_only = {"code-review", "arch-review", "oop-check",
                          "refine", "research", "plan", "execute",
                          "skill-scan", "skill-fix"}
        only_ai = all(s in _ai_steps_only for s in steps)
        if only_ai:
            return ConflictResult(passed=True, warnings=["仅 AI 推理步骤，无需构建系统"])
        else:
            return ConflictResult(passed=False, errors=["流水线需要 --build-system 参数"])

    if build_system not in SCRIPT_MAP:
        errors.append(f"不支持的构建系统 '{build_system}'。支持: {', '.join(SCRIPT_MAP.keys())}")
        return ConflictResult(passed=False, errors=errors)

    # AI 交互步骤不需要脚本，跳过
    _ai_steps = {"code-review", "arch-review", "oop-check",
                 "refine", "research", "plan", "execute",
                 "skill-scan", "skill-fix"}
    for step in steps:
        if step in _ai_steps:
            continue
        path = resolve_script(build_system, step)
        if not path or not path.exists():
            errors.append(f"步骤 [{STEP_LABELS.get(step, step)}] 的脚本不存在: {path or 'N/A'}")
            suggestions.append(
                f"请安装/注册对应的 skill 脚本: "
                f"{SCRIPT_MAP[build_system].get(step, 'unknown')}")

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

    suggestions = list(dict.fromkeys(suggestions))
    return ConflictResult(
        passed=len(errors) == 0, errors=errors,
        warnings=warnings, suggestions=suggestions,
    )


def print_conflict_report(result: ConflictResult) -> None:
    print("\n" + "=" * 50)
    if result.passed:
        print("[OK] 跨 Skill 边界检测: 通过")
        if result.warnings:
            print(f"\n[!]  {len(result.warnings)} 个警告:")
            for w in result.warnings:
                print(f"  [!] {w}")
    else:
        print("[X] 跨 Skill 边界检测: 失败")
        print(f"\n[X] {len(result.errors)} 个错误:")
        for e in result.errors:
            print(f"  [X] {e}")
        if result.warnings:
            print(f"\n[!]  {len(result.warnings)} 个警告:")
            for w in result.warnings:
                print(f"  [!] {w}")
        if result.suggestions:
            print(f"\n[~] 修复建议:")
            for s in result.suggestions:
                print(f"  -> {s}")
    print("=" * 50 + "\n")


def get_mapped_flash_skill(build_system: str) -> str:
    return {"keil": "flash-keil", "cmake": "flash-openocd",
            "platformio": "flash-platformio"}.get(build_system, "unknown")


def get_mapped_debug_skill(build_system: str) -> str:
    return {"keil": "debug-gdb-openocd", "cmake": "debug-gdb-openocd",
            "platformio": "debug-platformio"}.get(build_system, "unknown")


def infer_platform_hint(build_system: str) -> str:
    return {
        "keil": "ARM Cortex-M (STM32/GD32/nRF 等)",
        "cmake": "ARM Cortex-M 或 RISC-V（取决于构建配置）",
        "platformio": "取决于 platformio.ini 中的 platform 字段",
    }.get(build_system, "未知")


def extract_artifact(output: str) -> str | None:
    for line in output.splitlines():
        if "选定" in line:
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


def resolve_keil_project(project_arg: str) -> str:
    p = Path(project_arg)
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in (".uvprojx", ".uvproj"):
                return str(f)
        return project_arg
    return project_arg


# ═══════════════════════════════════════════════════════════════
# 步骤执行器
# ═══════════════════════════════════════════════════════════════

def run_step(name: str, cmd: list[str], inherit_io: bool = False,
             dry_run: bool = False) -> tuple[bool, str, str]:
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
            print(f"    [?] {line}")
    return proc.returncode == 0, stdout, stderr


# ═══════════════════════════════════════════════════════════════
# 动态流水线扫描
# ═══════════════════════════════════════════════════════════════

_DISCOVERED_PIPELINES: dict[str, dict] = {}
_PIPELINE_SOURCES: dict[str, str] = {}


def scan_all_skills_for_pipelines() -> dict[str, dict]:
    global _DISCOVERED_PIPELINES, _PIPELINE_SOURCES
    if _DISCOVERED_PIPELINES:
        return _DISCOVERED_PIPELINES
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
                continue
            if "steps" not in pipe_def:
                continue
            pipe_def.setdefault("description", f"{skill_name}: 自定义流水线")
            pipe_def.setdefault("phase", "Phase 6: 扩展流水线")
            discovered[pipe_name] = pipe_def
            sources[pipe_name] = skill_name
    _DISCOVERED_PIPELINES = discovered
    _PIPELINE_SOURCES = sources
    return discovered


def get_merged_workflows() -> dict[str, dict]:
    builtin = dict(WORKFLOWS)
    discovered = scan_all_skills_for_pipelines()
    builtin.update(discovered)
    return builtin


def get_pipeline_source(pipe_name: str) -> str:
    scan_all_skills_for_pipelines()
    return _PIPELINE_SOURCES.get(pipe_name, "builtin")


# ═══════════════════════════════════════════════════════════════
# 参数构造共享
# ═══════════════════════════════════════════════════════════════

def make_build_cmd(script: Path, args) -> list[str]:
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


def make_flash_cmd(script: Path, args, artifact: str | None) -> list[str]:
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


def make_monitor_cmd(script: Path, args) -> list[str]:
    cmd = [sys.executable, str(script), "--monitor"]
    if args.port:
        cmd += ["--port", args.port]
    if args.baud:
        cmd += ["--baud", str(args.baud)]
    return cmd


def make_debug_cmd(script: Path, args, artifact: str | None) -> list[str]:
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


def make_capture_cmd(script: Path, args) -> list[str]:
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


def make_record_cmd(args) -> list[str]:
    script = SKILLS_ROOT / "knowledge-base-search" / "scripts" / "record_issue.py"
    if not script.exists():
        return []
    cmd = [sys.executable, str(script), "append"]
    if args.issue:
        cmd += ["--file", args.issue]
    if args.result:
        cmd += ["--result", args.result]
    return cmd


def make_commit_cmd(args) -> list[str]:
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
        f"r=subprocess.run(['git','commit','-m',sys.argv[1]],cwd=r'{project_dir or '.'}',"
        f"capture_output=True,text=True); "
        f"print(r.stdout or r.stderr)",
        msg
    ]
    return cmd


def make_devlog_cmd(script: Path, args) -> list[str]:
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


def make_static_analysis_cmd(script: Path, args) -> list[str]:
    cmd = [sys.executable, str(script)]
    if args.project:
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            src_dir = p.parent.parent / "Core" / "Src"
            cmd += [str(src_dir) if src_dir.exists() else str(p.parent.parent)]
        elif p.name == "MDK-ARM":
            src_dir = p.parent / "Core" / "Src"
            cmd += [str(src_dir) if src_dir.exists() else str(p.parent)]
        else:
            cmd += [args.project]
    if args.verbose:
        cmd.append("-v")
    return cmd


def make_map_analyze_cmd(script: Path, args) -> list[str]:
    cmd = [sys.executable, str(script)]
    if args.project:
        p = Path(args.project)
        if p.suffix == ".uvprojx":
            cmd += ["--map", str(p.parent)]
        elif p.name == "MDK-ARM":
            cmd += ["--map", args.project]
        else:
            cmd += [args.project]
    if args.verbose:
        cmd.append("-v")
    return cmd


def make_sprint_cmd(script: Path, step: str, args) -> list[str]:
    cmd = [sys.executable, str(script)]
    cmd += ["--project", args.project or "."]
    if args.sprint:
        cmd += ["--sprint", str(args.sprint)]
    step_to_flag = {
        "sprint-plan": "--plan", "sprint-review": "--review",
        "sprint-retro": "--retro", "risk-log": "--risk --list",
        "change-assess": "--change --assess", "init-bsp": "--init-project",
    }
    flag = step_to_flag.get(step, "")
    if flag:
        cmd += flag.split()
    if step == "sprint-plan" and args.backlog_ids:
        cmd += ["--backlog-ids"] + [str(i) for i in args.backlog_ids]
    return cmd


def make_stress_test_cmd(script: Path, args) -> list[str]:
    duration = args.duration or 60
    cmd = [sys.executable, str(script), "--monitor", "--duration", str(duration)]
    if args.port:
        cmd += ["--port", args.port]
    if args.baud:
        cmd += ["--baud", str(args.baud)]
    if args.save:
        cmd += ["--save", args.save]
    return cmd


def make_dashboard_cmd(script: Path, args) -> list[str]:
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


# ═══════════════════════════════════════════════════════════════
# 参数解析器（各 Agent 共享）
# ═══════════════════════════════════════════════════════════════

def add_common_args(parser) -> argparse.ArgumentParser:
    """向解析器添加所有 Agent 共用的参数"""
    p = parser
    p.add_argument("--detect", action="store_true", help="探测环境")
    p.add_argument("--list", action="store_true", help="列出所有 workflow")
    p.add_argument("--run", help="执行指定 workflow")
    p.add_argument("--build-system", choices=["keil", "cmake", "platformio"], help="构建系统")
    p.add_argument("--project", help="工程路径")
    p.add_argument("--target", help="构建目标/环境/预设")
    p.add_argument("--port", help="串口（monitor 用）")
    p.add_argument("--baud", type=int, help="波特率")
    p.add_argument("--artifact", help="固件产物路径（可选）")
    p.add_argument("--flash-interface", help="烧录接口（OpenOCD）")
    p.add_argument("--flash-target", help="烧录目标（OpenOCD）")
    p.add_argument("--duration", type=int, default=10, help="capture/monitor 采集时长（秒）")
    p.add_argument("--save", help="日志文件保存路径（capture 用）")
    p.add_argument("--issue", help="Obsidian 问题记录文件路径（record 用）")
    p.add_argument("--result", help="实验验证结果（record 用）")
    p.add_argument("--commit-msg", help="Git 提交信息（commit 用）")
    # devlog
    p.add_argument("--devlog-project-name", help="项目名称")
    p.add_argument("--devlog-session-num", type=int, default=0, help="会话编号")
    p.add_argument("--devlog-start-time", help="会话开始时间")
    p.add_argument("--devlog-work-done", help="已完成工作内容")
    p.add_argument("--devlog-problems", help="遇到的问题及解决方案")
    p.add_argument("--devlog-features", help="新增/修改功能")
    p.add_argument("--devlog-progress", type=int, default=None, help="完成度百分比 0-100")
    p.add_argument("--devlog-achieved", help="已实现的内容")
    p.add_argument("--devlog-pending", help="未完成的内容")
    p.add_argument("--devlog-next-steps", help="下一步计划")
    p.add_argument("--devlog-notes", help="备注")
    p.add_argument("--devlog-output", help="开发日志输出路径")
    # sprint
    p.add_argument("--sprint", type=int, default=1, help="Sprint 编号")
    p.add_argument("--backlog-ids", nargs="*", type=int, default=None, help="Backlog ID 列表")
    # porting
    p.add_argument("--source-chip", help="源芯片/平台")
    p.add_argument("--target-chip", help="目标芯片/平台")
    p.add_argument("--layers", default="1,2,3,4,5,6,7", help="移植涉及层次")
    p.add_argument("--porting-type", choices=["mcu-port", "hal-migration", "toolchain",
                   "rtos", "library", "module"], default="mcu-port", help="移植类型")
    p.add_argument("--archive-obsidian", action="store_true", help="移植归档到 Obsidian")
    p.add_argument("--import-kb", action="store_true", help="移植导入知识库")
    p.add_argument("--tags", default="移植", help="知识库标签")
    p.add_argument("--output", default="docs/移植文档/", help="移植报告输出目录")
    p.add_argument("--dry-run", action="store_true", help="仅打印命令，不执行")
    p.add_argument("--skip-conflict-check", action="store_true", help="跳过跨 Skill 冲突检测")
    p.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    return p
