# Devlog 使用参考

## 快速入门

### 1. 独立运行（交互模式）

```bash
python devlog.py -i --project D:\zhuomian\KEIL+Arduino+Vscode\Keil+STM32cubeMx\STM32F411CEU6\EmbeddedProject-Folder-Template-main\04_Software\01_Source_Code\08_UART_PRINTF_V1
```

### 2. 独立运行（参数模式）

```bash
python devlog.py --project /path/to/project \
    --work-done "实现了 printf 重定向到 USART1" \
    --problems-solutions "串口无输出 | USART1 时钟未使能 | 添加 __HAL_RCC_USART1_CLK_ENABLE()" \
    --features "printf 重定向" \
    --progress 80 \
    --achieved "printf 重定向、串口通信" \
    --pending "DMA 收发" \
    --next-steps "- 实现 USART1 DMA 收发"
```

### 3. Workflow 集成（full-cycle 流水线）

```bash
python workflow_runner.py --run full-cycle --build-system keil \
    --project /path/to/project/MDK-ARM --target TARGET \
    --port {SERIAL_PORT} --baud 115200 \
    --devlog-work-done "实现了 printf 重定向" \
    --devlog-problems "串口无输出 | USART1 时钟未使能 | 添加 __HAL_RCC_USART1_CLK_ENABLE()" \
    --devlog-progress 80 \
    --devlog-achieved "printf 重定向、串口通信" \
    --devlog-pending "DMA 收发" \
    --devlog-next-steps "- 实现 USART1 DMA 收发"
```

## 输出示例

生成的开发日志保存在 `<项目根>/docs/开发日志/2026-05-24-会话1.md`，内容结构：

```markdown
# 开发日志

## 会话信息
- **日期**: 2026-05-24
- **时间**: 20:00 — 22:30
- **项目**: UART_PRINTF_V1
- **分支**: main
- **最近提交**:
  - `abc1234 fix: 添加 USART1 时钟使能`

## 本次完成工作
- 实现了 printf 重定向到 USART1
- 修复了 USART1 时钟未使能的问题

## 遇到的问题及解决方案
| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 串口无输出 | USART1 时钟未使能 | 添加 __HAL_RCC_USART1_CLK_ENABLE() |

## 当前进度
- **整体进度**: 80%
- **已实现**: printf 重定向、串口通信
- **待完成**: DMA 收发
```

## git 信息自动收集

devlog 会自动执行以下 git 命令收集信息：
- `git rev-parse --abbrev-ref HEAD` → 当前分支
- `git log --oneline -5` → 最近 5 个提交
- `git status --short` → 未提交的文件变更

这些信息自动填入开发日志的「会话信息」和「文件变更」章节。
