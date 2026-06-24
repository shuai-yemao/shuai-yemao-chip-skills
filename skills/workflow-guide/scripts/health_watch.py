#!/usr/bin/env python3
"""
Chip 健康评分监控与告警工�?====================================
持续监控系统健康评分，当评分骤降时触发告警�?
功能:
  - record:    记录当前健康评分到历�?  - check:     对比最新两次评分，骤降则告�?  - history:   查看评分趋势
  - watch:     持续监控模式（定时检查）
  - alert:     手动触发告警测试

评分骤降判定:
  - 下降 >= 20%: 严重告警 (ERROR)
  - 下降 >= 10%: 警告 (WARNING)
  - 下降 < 10%: 正常波动

用法:
  python health_watch.py record              # 记录当前评分
  python health_watch.py check               # 检查评分变�?  python health_watch.py history             # 查看趋势
  python health_watch.py history --json      # JSON 格式输出
  python health_watch.py watch               # 持续监控
  python health_watch.py watch --interval 300  # �?5 分钟检查一�?  python health_watch.py alert --drop 25     # 模拟 25% 骤降告警
"""

import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 路径 ──────────────────────────────────────────────────────

WATCH_DIR = Path.home() / ".Chip-watch"
SCORE_HISTORY = WATCH_DIR / "score_history.json"
HEALTH_SCRIPT = None  # will resolve

ALERT_THRESHOLD_CRITICAL = 20  # >=20% drop �?critical
ALERT_THRESHOLD_WARNING = 10   # >=10% drop �?warning

NOTIFY_SCRIPT = None


def _resolve_health_script() -> Path | None:
    candidates = [
        Path.home() / "AppData" / "Roaming" / "CherryStudio" / "Data"
        / "Skills" / "workflow-guide" / "scripts" / "system_health.py",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def _ensure_watch_dir():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    if not SCORE_HISTORY.exists():
        SCORE_HISTORY.write_text(json.dumps({
            "records": [],
        }, indent=2), encoding="utf-8")


def _load_history() -> dict:
    _ensure_watch_dir()
    return json.loads(SCORE_HISTORY.read_text(encoding="utf-8"))


def _save_history(history: dict):
    SCORE_HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_health_check() -> dict | None:
    """运行 health check 并解析评�?""
    hs = _resolve_health_script()
    if not hs:
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(hs), "--report"],
            capture_output=True, text=False, timeout=30,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")

        # 从输出中提取评分
        import re
        score_m = re.search(r"评分:\s*(\d+)%\s*\[(.+?)\]", stdout)
        pass_m = re.search(r"通过:\s*(\d+)/(\d+)", stdout)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": int(score_m.group(1)) if score_m else 0,
            "grade": score_m.group(2) if score_m else "未知",
            "passed": int(pass_m.group(1)) if pass_m else 0,
            "total": int(pass_m.group(2)) if pass_m else 0,
            "exit_code": result.returncode,
            "raw_output": stdout[:500],
        }
    except Exception as e:
        return {"error": str(e)}


def _send_notification(title: str, message: str):
    """尝试发送通知（通过 claw notify 或桌面通知�?""
    try:
        # 写入通知文件（供外部 cron 读取�?        notify_file = WATCH_DIR / "last_alert.json"
        notify_file.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "message": message,
        }, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 打印到控制台
    print(f"\n  �? [{title}]")
    print(f"     {message}")


# ── 命令实现 ──────────────────────────────────────────────────


def cmd_record() -> int:
    """记录当前健康评分"""
    print("[*] 运行健康检�?..")
    result = _run_health_check()
    if not result:
        print("[X] 健康检查脚本未找到或执行失�?)
        return 1

    if "error" in result:
        print(f"[X] 健康检查失�? {result['error']}")
        return 1

    history = _load_history()
    records = history["records"]

    # 添加记录
    records.append({
        "timestamp": result["timestamp"],
        "score": result["score"],
        "grade": result["grade"],
        "passed": result["passed"],
        "total": result["total"],
    })

    # 只保留最�?100 �?    if len(records) > 100:
        records[:] = records[-100:]

    _save_history(history)

    print(f"[OK] 评分记录: {result['score']}% [{result['grade']}] "
          f"({result['passed']}/{result['total']})")
    return 0


def cmd_check(threshold_critical: int = ALERT_THRESHOLD_CRITICAL,
              threshold_warning: int = ALERT_THRESHOLD_WARNING) -> int:
    """检查评分变�?""
    history = _load_history()
    records = history["records"]

    if len(records) < 2:
        print("[i] 需要至�?2 次记录才能比较变�?)
        print("    运行 'record' 命令记录评分")
        return 0

    latest = records[-1]
    previous = records[-2]

    current_score = latest["score"]
    prev_score = previous["score"]
    drop = prev_score - current_score

    print(f"  上次评分: {prev_score}% ({previous['timestamp'][:19]})")
    print(f"  当前评分: {current_score}% ({latest['timestamp'][:19]})")
    print(f"  变化:     {'�? if drop > 0 else '�?} {abs(drop)}%")
    print(f"  趋势:     {latest['grade']}")

    if drop >= threshold_critical:
        msg = (f"健康评分骤降 {drop}%! {prev_score}% �?{current_score}% "
               f"[{latest['grade']}]\n"
               f"建议立即运行 system_health.py --report 查看详情\n"
               f"如需回滚: system_snapshot.py restore --latest")
        _send_notification("健康评分严重下降", msg)
        return 2
    elif drop >= threshold_warning:
        msg = (f"健康评分下降 {drop}%: {prev_score}% �?{current_score}%\n"
               f"建议检查是否有配置变更")
        _send_notification("健康评分下降", msg)
        return 1
    else:
        if drop > 0:
            print(f"[OK] 评分小幅下降 {drop}%（正常波动范围内�?)
        else:
            print(f"[OK] 评分稳定或提�?{abs(drop)}%")
        return 0


def cmd_history(json_output: bool = False) -> int:
    """查看评分趋势"""
    history = _load_history()
    records = history["records"]

    if not records:
        print("[i] 无评分记�?)
        print("    运行 'record' 命令开始记�?)
        return 0

    if json_output:
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return 0

    print(f"\n  健康评分趋势 ({len(records)} 条记�?")
    print(f"  {'─' * 50}")

    for i, r in enumerate(records):
        ts = r["timestamp"][:19]
        score = r["score"]
        grade = r["grade"]
        bar = "�? * (score // 5) + "�? * ((100 - score) // 5)
        marker = " �?当前" if i == len(records) - 1 else ""
        print(f"  {ts}  {bar} {score:>3}% [{grade:<4}]{marker}")

    # 统计
    scores = [r["score"] for r in records]
    print(f"\n  最�? {max(scores)}%  最�? {min(scores)}%  "
          f"平均: {sum(scores)//len(scores)}%")

    if len(scores) >= 2:
        first, last = scores[0], scores[-1]
        total_change = last - first
        if total_change > 0:
            print(f"  总体趋势: �?+{total_change}%（提升）")
        elif total_change < 0:
            print(f"  总体趋势: �?{total_change}%（下降）")
        else:
            print(f"  总体趋势: 稳定")
    return 0


def cmd_watch(interval: int = 300) -> int:
    """持续监控模式"""
    print(f"[*] 启动健康评分监控 (interval={interval}s)")
    print(f"    告警阈�? critical>={ALERT_THRESHOLD_CRITICAL}%, "
          f"warning>={ALERT_THRESHOLD_WARNING}%")
    print(f"    �?Ctrl+C 停止\n")

    cycle = 0
    while True:
        cycle += 1
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 检�?#{cycle}...")

        # 记录
        result = _run_health_check()
        if result and "score" in result:
            history = _load_history()
            history["records"].append({
                "timestamp": result["timestamp"],
                "score": result["score"],
                "grade": result["grade"],
                "passed": result["passed"],
                "total": result["total"],
            })
            if len(history["records"]) > 100:
                history["records"] = history["records"][-100:]
            _save_history(history)
            print(f"  Score: {result['score']}% [{result['grade']}]")

            # 检查骤�?            if len(history["records"]) >= 2:
                prev = history["records"][-2]
                drop = prev["score"] - result["score"]
                if drop >= ALERT_THRESHOLD_CRITICAL:
                    _send_notification(
                        "健康评分严重下降",
                        f"{prev['score']}% �?{result['score']}% "
                        f"(↓{drop}%) [{result['grade']}]"
                    )
                elif drop >= ALERT_THRESHOLD_WARNING:
                    _send_notification(
                        "健康评分下降",
                        f"{prev['score']}% �?{result['score']}% (↓{drop}%)"
                    )

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n[*] 监控已停�?(共检�?{cycle} �?")
            break

    return 0


def cmd_alert(drop_sim: int = 20) -> int:
    """模拟告警（测试用�?""
    # 创建一个模拟记�?    history = _load_history()
    records = history["records"]

    if records:
        last = records[-1]
        sim_score = max(0, last["score"] - drop_sim)
    else:
        sim_score = 50

    sim_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": sim_score,
        "grade": "模拟",
        "passed": 0,
        "total": 0,
    }

    records.append(sim_record)
    if len(records) > 100:
        records[:] = records[-100:]
    _save_history(history)

    msg = (f"[TEST] 模拟评分骤降: 上次 {records[-2]['score'] if len(records)>=2 else '?'}% "
           f"�?{sim_score}% (↓{drop_sim}%)")
    _send_notification("测试告警", msg)
    print(f"[OK] 测试告警已触�? {msg}")
    return 0


# ── CLI ───────────────────────────────────────────────────────


def print_usage():
    print(__doc__)


def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    cmd = sys.argv[1]

    if cmd == "record":
        return cmd_record()
    elif cmd == "check":
        return cmd_check()
    elif cmd == "history":
        json_output = "--json" in sys.argv
        return cmd_history(json_output)
    elif cmd == "watch":
        interval = 300
        for i, a in enumerate(sys.argv[2:], 2):
            if a == "--interval" and i + 1 < len(sys.argv):
                try:
                    interval = int(sys.argv[i + 1])
                except ValueError:
                    pass
        return cmd_watch(interval)
    elif cmd == "alert":
        drop = 20
        for i, a in enumerate(sys.argv[2:], 2):
            if a == "--drop" and i + 1 < len(sys.argv):
                try:
                    drop = int(sys.argv[i + 1])
                except ValueError:
                    pass
        return cmd_alert(drop)
    else:
        print(f"[X] 未知命令: {cmd}")
        print_usage()
        return 1


if __name__ == "__main__":
    sys.exit(main())
