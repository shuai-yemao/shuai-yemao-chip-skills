#!/usr/bin/env python3
"""
rtos-debug: RTOS 感知调试启动器
支持 FreeRTOS / ThreadX / RT-Thread，通过 GDB + OpenOCD 分析任务状态
支持按需分析模式：all / tasks / heap / deadlock / hardfault
"""
import argparse
import subprocess
import tempfile
import os
import sys
import json
import datetime

RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
RESET  = "\033[0m"

# ═══════════════════════════════════════════════
# GDB 脚本片段 —— FreeRTOS
# ═══════════════════════════════════════════════

FREERTOS_TASKS = """
echo \\n=== [TASKS] 线程列表 ===\\n
info threads
echo \\n=== [TASKS] 当前任务 TCB ===\\n
print *pxCurrentTCB
echo \\n=== [TASKS] 就绪任务数 ===\\n
print uxCurrentNumberOfTasks
echo \\n=== [TASKS] 各任务栈水印 ===\\n
set $tasks = (TCB_t **)pxReadyTasksLists
echo \\n=== [TASKS] 当前任务栈水印 ===\\n
call uxTaskGetStackHighWaterMark(NULL)
"""

FREERTOS_HEAP = """
echo \\n=== [HEAP] 堆内存状态 ===\\n
print xFreeBytesRemaining
print xMinimumEverFreeBytesRemaining
echo \\n=== [HEAP] 堆统计 ===\\n
print xPortGetFreeHeapSize
"""

FREERTOS_DEADLOCK = """
echo \\n=== [DEADLOCK] 所有线程与等待对象 ===\\n
info threads
echo \\n=== [DEADLOCK] 当前任务事件列表 ===\\n
print pxCurrentTCB->xEventListItem
print pxCurrentTCB->xStateListItem
"""

FREERTOS_HARDFAULT = """
echo \\n=== [HARDFAULT] Fault 状态寄存器 ===\\n
monitor reg CFSR
monitor reg HFSR
monitor reg BFAR
monitor reg MMFAR
echo \\n=== [HARDFAULT] 栈帧 ===\\n
info frame
echo \\n=== [HARDFAULT] 栈顶 8 字 (hex) ===\\n
x/8xw $sp
echo \\n=== [HARDFAULT] LR (判断 MSP/PSP) ===\\n
info reg lr
"""

# ═══════════════════════════════════════════════
# GDB 脚本片段 —— ThreadX
# ═══════════════════════════════════════════════

THREADX_TASKS = """
echo \\n=== [ThreadX TASKS] 线程列表 ===\\n
info threads
echo \\n=== [ThreadX TASKS] 当前执行线程 ===\\n
print *_tx_thread_current_ptr
echo \\n=== [ThreadX TASKS] 线程创建计数 ===\\n
print _tx_thread_created_count
echo \\n=== [ThreadX TASKS] 就绪线程列表头 ===\\n
print _tx_thread_priority_list
"""

THREADX_HEAP = """
echo \\n=== [ThreadX HEAP] 字节池信息 ===\\n
print _tx_byte_pool_created
echo \\n=== [ThreadX HEAP] 块池信息 ===\\n
print _tx_block_pool_created
"""

THREADX_DEADLOCK = """
echo \\n=== [ThreadX DEADLOCK] 当前线程状态 ===\\n
print _tx_thread_current_ptr->tx_thread_state
echo \\n=== [ThreadX DEADLOCK] 挂起计数 ===\\n
print _tx_thread_current_ptr->tx_thread_suspend_count
echo \\n=== [ThreadX DEADLOCK] 等待对象 ===\\n
print _tx_thread_current_ptr->tx_thread_suspension_list
"""

THREADX_HARDFAULT = """
echo \\n=== [ThreadX HARDFAULT] Fault 状态寄存器 ===\\n
monitor reg CFSR
monitor reg HFSR
monitor reg BFAR
monitor reg MMFAR
echo \\n=== [ThreadX HARDFAULT] 栈帧 ===\\n
info frame
echo \\n=== [ThreadX HARDFAULT] 栈顶 8 字 ===\\n
x/8xw $sp
info reg lr
"""

# ═══════════════════════════════════════════════
# GDB 脚本片段 —— RT-Thread
# ═══════════════════════════════════════════════

RTTHREAD_TASKS = """
echo \\n=== [RT-Thread TASKS] 线程列表 ===\\n
info threads
echo \\n=== [RT-Thread TASKS] 当前线程 ===\\n
call rt_thread_self()
print *rt_current_thread
echo \\n=== [RT-Thread TASKS] 调度器状态 ===\\n
print rt_critical_level
"""

RTTHREAD_HEAP = """
echo \\n=== [RT-Thread HEAP] 系统节拍 ===\\n
call rt_tick_get()
print rt_tick
echo \\n=== [RT-Thread HEAP] 内存信息 ===\\n
print rt_system_heap
"""

RTTHREAD_DEADLOCK = """
echo \\n=== [RT-Thread DEADLOCK] 所有线程 ===\\n
info threads
echo \\n=== [RT-Thread DEADLOCK] 当前线程状态 ===\\n
print rt_current_thread->stat
"""

RTTHREAD_HARDFAULT = """
echo \\n=== [RT-Thread HARDFAULT] Fault 寄存器 ===\\n
monitor reg CFSR
monitor reg HFSR
monitor reg BFAR
monitor reg MMFAR
info frame
x/8xw $sp
info reg lr
"""

# ═══════════════════════════════════════════════
# 脚本组合
# ═══════════════════════════════════════════════

def build_gdb_script(rtos: str, analysis: str) -> str:
    header = (
        "set pagination off\n"
        "target remote :3333\n"
        "monitor reset halt\n"
        "echo \\n=== RTOS 调试会话已启动 ===\\n\n"
        "set print pretty on\n"
        "set print elements 0\n"
    )
    footer = "\necho \\n=== 分析完成，进入交互模式 ===\\n\n"

    if rtos == "threadx":
        T, H, D, F = THREADX_TASKS, THREADX_HEAP, THREADX_DEADLOCK, THREADX_HARDFAULT
    elif rtos == "rtthread":
        T, H, D, F = RTTHREAD_TASKS, RTTHREAD_HEAP, RTTHREAD_DEADLOCK, RTTHREAD_HARDFAULT
    else:
        T, H, D, F = FREERTOS_TASKS, FREERTOS_HEAP, FREERTOS_DEADLOCK, FREERTOS_HARDFAULT

    body_map = {
        "all":       T + H + D + F,
        "tasks":     T,
        "heap":      H,
        "deadlock":  T + D,
        "hardfault": F,
    }
    return header + body_map.get(analysis, T) + footer


def colorize_output(text: str) -> str:
    colored = []
    for line in text.splitlines():
        if line.lstrip().startswith("$") and "=" in line:
            try:
                val_str = line.split("=", 1)[1].strip()
                val = int(val_str)
                if val <= 64:
                    line = f"{RED}{line}  <-- ⚠ 栈溢出风险{RESET}"
                elif val <= 128:
                    line = f"{YELLOW}{line}  <-- 栈使用偏高{RESET}"
            except ValueError:
                pass
        colored.append(line)
    return "\n".join(colored)


def check_tools():
    missing = []
    for tool in ["arm-none-eabi-gdb"]:
        try:
            subprocess.run([tool, "--version"], capture_output=True, timeout=5)
        except FileNotFoundError:
            missing.append(tool)
    if missing:
        print(f"错误：以下工具未找到: {', '.join(missing)}")
        sys.exit(1)


def start_openocd(openocd_cfg: str, gdb_port: int = 3333):
    cmd = ["openocd", "-f", openocd_cfg,
           "-c", f"gdb_port {gdb_port}",
           "-c", "init", "-c", "reset halt"]
    print(f"[rtos-debug] 启动 OpenOCD: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    import time; time.sleep(2)
    if proc.poll() is not None:
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else "(无输出)"
        print(f"错误：OpenOCD 启动失败")
        print(stderr)
        sys.exit(1)
    return proc


def run_gdb_debug(elf: str, rtos: str, analysis: str,
                  save_report: bool, gdb_port: int, openocd_proc=None):
    script_content = build_gdb_script(rtos, analysis)
    # 替换默认端口为实际端口
    script_content = script_content.replace(":3333", f":{gdb_port}")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".gdb", delete=False, encoding="utf-8"
    ) as f:
        f.write(script_content)
        gdb_script = f.name

    cmd = ["arm-none-eabi-gdb", "-batch", "-x", gdb_script, elf]
    print(f"[rtos-debug] 启动 GDB: {' '.join(cmd)}")
    print(f"[rtos-debug] RTOS: {rtos} | 分析: {analysis}")

    try:
        if save_report:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=120)
            output = result.stdout + result.stderr
            colored = colorize_output(output)
            print(colored)
            _save_report(elf, rtos, analysis, output)
        else:
            result = subprocess.run(cmd, text=True, timeout=120)
    finally:
        os.unlink(gdb_script)
        if openocd_proc:
            openocd_proc.terminate()
            print("[rtos-debug] OpenOCD 已停止")


def _save_report(elf: str, rtos: str, analysis: str, raw_output: str):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(elf)),
        f"rtos_debug_{rtos}_{analysis}_{timestamp}.json"
    )
    # 提取关键指标
    stats = {}
    for key in ["uxCurrentNumberOfTasks", "xFreeBytesRemaining",
                "xMinimumEverFreeBytesRemaining", "CFSR", "BFAR"]:
        m = re.search(rf'{key}\s*=\s*([^\n]+)', raw_output, re.IGNORECASE)
        if m:
            stats[key] = m.group(1).strip()

    report = {
        "timestamp": timestamp, "elf": elf, "rtos": rtos,
        "analysis": analysis, "key_stats": stats, "raw_output": raw_output,
    }
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(f"[rtos-debug] 报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="RTOS 感知调试工具 (FreeRTOS/ThreadX/RT-Thread)")
    parser.add_argument("--elf", required=True, help="含调试符号的 .elf 文件路径")
    parser.add_argument("--rtos", default="freertos",
                        choices=["freertos", "threadx", "rtthread"])
    parser.add_argument("--openocd-cfg", default=None,
                        help="OpenOCD 配置文件（不填则假设已运行在 :3333）")
    parser.add_argument("--gdb-port", type=int, default=3333, help="GDB 端口")
    parser.add_argument("--analysis", default="all",
                        choices=["all", "tasks", "heap", "deadlock", "hardfault"])
    parser.add_argument("--save-report", action="store_true",
                        help="保存分析报告为 JSON 文件")
    args = parser.parse_args()

    if not os.path.exists(args.elf):
        print(f"错误：.elf 文件不存在: {args.elf}")
        sys.exit(1)

    check_tools()

    openocd_proc = None
    if args.openocd_cfg:
        openocd_proc = start_openocd(args.openocd_cfg, args.gdb_port)

    print(f"[rtos-debug] RTOS: {args.rtos} | ELF: {args.elf}")
    run_gdb_debug(args.elf, args.rtos, args.analysis,
                  args.save_report, args.gdb_port, openocd_proc)


if __name__ == "__main__":
    main()
