---
name: static-analysis
description: 对嵌入式 C/C++ 代码执行静态分析。封装 cppcheck 扫描未定义行为、内存泄漏、空指针、数组越界，支持 MISRA C 检查、增量基线对比、HTML/JSON/XML 导出、compile_commands.json 自动检测、修复模板。当用户提到静态扫描、cppcheck、MISRA、代码检查、内存泄漏、空指针、量产前质量检查时使用。
version: "1.0.0"
---

# static-analysis

对嵌入式 C/C++ 代码执行静态分析，使用 cppcheck 扫描未定义行为、内存泄漏、
空指针解引用、数组越界等问题，在烧录前发现潜在 Bug。

## 触发条件
- 用户说"静态扫描"、"代码检查"、"cppcheck"
- 编译通过但运行异常，怀疑未定义行为
- 代码 review 或量产前质量检查
- 用户询问代码是否有潜在问题
- 用户说"MISRA"、"代码规范检查"、"嵌入式代码审查"
- CI/CD 流水线中自动触发扫描
- 用户询问"有没有内存泄漏"、"有没有空指针"

## 使用前提
- 已安装 cppcheck（命令行可用）
- 可选：compile_commands.json（提升分析精度）

## 参数收集
- `src_dir`: 源码目录（默认当前目录）
- `include_dirs`: 头文件目录列表（可从 CMakeLists.txt 或 Makefile 提取）
- `defines`: 宏定义列表（如 STM32F4, USE_HAL_DRIVER）
- `std`: C 标准，c99 / c11 / c17（默认 c11）
- `output_file`: 报告输出路径（可选）
- `suppress`: 要抑制的警告 ID 列表
- `misra`: 是否启用 MISRA C 规则检查（需 cppcheck addon，默认 false）
- `jobs`: 并行扫描线程数（默认 CPU 核心数，`-j` 参数）
- `export`: 导出格式，html / xml / json（默认仅终端输出）
- `baseline`: 基线文件路径（只报告相对基线新增的问题，用于增量扫描）
- `compile_db`: compile_commands.json 路径（精确 include/define 推断）

## 执行流程

### Step 0 自动推断 compile_commands.json
若工程目录存在 `build/compile_commands.json`，优先使用 `--project=` 参数，
跳过手动 include/define 配置，分析精度更高。

```bash
# 自动检测路径
ls build/compile_commands.json && echo "使用 --project=build/compile_commands.json"
```

### Step 1 检查工具
```bash
cppcheck --version
```
未安装则提示：Windows 用 `winget install Cppcheck.Cppcheck`，Linux 用 `apt install cppcheck`。

### Step 2 构建分析命令
```bash
cppcheck \
  --enable=all \
  --std=c11 \
  --platform=arm32-wchar_t2 \
  --suppress=missingIncludeSystem \
  -I./Inc -I./Drivers/STM32F4xx_HAL_Driver/Inc \
  -DSTM32F407xx -DUSE_HAL_DRIVER \
  --xml --xml-version=2 \
  --output-file=cppcheck_report.xml \
  -j 4 \
  ./Src
```

### Step 3 解析 XML 报告
将 XML 转为人类可读格式，按严重程度分组：
- error（必须修复）
- warning（建议修复）
- style / performance / portability（可选优化）

### Step 4 输出报告
```
═══════════ 静态分析报告 (cppcheck) ═══════════
扫描目录: ./Src  |  扫描文件: 12  |  耗时: 1.3s

ERROR (必须修复) — 3 项
  main.c:45  nullPointer       对 ptr 解引用前未检查空指针
  uart.c:112 arrayIndexOutOfBounds  数组越界访问 buf[512]
  i2c.c:78   memleak           动态分配内存未释放

WARNING (建议修复) — 7 项
  ...

STYLE (可选) — 12 项
  ...

总计: 22 项问题  |  ERROR: 3  WARNING: 7  STYLE: 12
```

### Step 5 MISRA C 检查（可选）
当用户指定 `--misra` 时，追加运行以下命令：

```bash
cppcheck --addon=misra \
  --suppress=misra-c2012-1.1 \
  --std=c11 ./Src
```

MISRA 规则分为三级，输出时分级显示：
- **Mandatory**：强制要求，不可偏离
- **Required**：必须遵守，除非有正式偏差记录
- **Advisory**：建议遵守，可在项目层面豁免

### Step 6 修复建议
对每个 ERROR 级别问题，给出具体修复代码示例。
对 `nullPointer`、`memleak`、`arrayIndexOutOfBounds` 三类问题，
打印对应的通用修复代码模板（含中文注释）。

## 增量扫描（基线对比）

适合 CI/CD 场景：只报告本次提交引入的新 Bug，避免历史遗留问题的干扰。

### 首次扫描（生成基线）
```bash
python static_analysis.py --src ./Src --baseline baseline.xml
# 扫描完成后，若 baseline.xml 不存在，自动将结果保存为基线
```

### 后续扫描（增量对比）
```bash
python static_analysis.py --src ./Src --baseline baseline.xml
# 若 baseline.xml 已存在，只输出相对基线新增的问题
```

### CI/CD 集成示例（GitHub Actions）
```yaml
- name: Static Analysis
  run: |
    python static_analysis.py \
      --src ./Src \
      --baseline .ci/baseline.xml \
      --export json \
      --jobs 4
```

## 嵌入式常见误报抑制

在项目根目录创建 `.cppcheck-suppress` 文件，逐文件配置抑制规则：

```
# .cppcheck-suppress 文件示例

[Src/stm32f4xx_hal_uart.c]
missingInclude
unusedFunction

[Src/main.c:42]
nullPointer  // 此处已通过断言保证非空
```

常见需要抑制的误报场景：
| 规则 ID | 场景 | 说明 |
|---------|------|------|
| `missingInclude` | HAL 驱动头文件 | 系统头文件路径未配置 |
| `unusedFunction` | ISR 中断服务函数 | 由硬件向量表调用，工具无法感知 |
| `nullPointer` | 断言保护后的指针 | 已通过 assert 确保非空 |
| `misra-c2012-1.1` | 编译器扩展语法 | 使用了 GCC 特定扩展 |

## 错误处理
| 情况 | 处理 |
|------|------|
| cppcheck 未找到 | 提示安装命令 |
| 头文件找不到 | 自动从 CMakeLists.txt 提取 include 路径重试 |
| 报告为空 | 检查 src_dir 是否包含 .c/.cpp 文件 |
| `addon misra not found` | 下载 misra.py addon：`pip install cppcheck-misra` 或从 cppcheck 官网获取 misra.py |
| `Too many errors` | 首次扫描建议先用 `--enable=error` 只看最严重的错误，逐步修复后再开启全量检查 |
| `Scanning takes too long` | 加 `-j 4` 并行扫描，或用 `--suppress=` 排除第三方库目录（如 Drivers/） |

## 边界定义

### 不该激活
- 用户需要的是动态分析（Valgrind、ASan、运行时内存检查）而非静态分析
- 用户的项目是纯 Python/Java/Go 等非 C/C++ 代码
- 用户需要的是代码格式化（clang-format）而非代码质量检查
- 用户只需要编译（build）→ 使用对应 build skill

### 不该做
- **禁止**修改被扫描的源码文件（只报告问题，不自动修复）
- **禁止**在无用户指定的情况下删除或覆盖已有的 baseline.xml
- **禁止**对第三方库代码（Drivers/、Middleware/、OS/）启用 MISRA 检查（易产生大量误报）
- **禁止**将 suppress 列表中的抑制规则自动删除

### 不该碰
- **不触碰**用户源码：只读取分析，绝不修改
- **不触碰**编译产物目录（build/、output/ 等）
- **不触碰** .cppcheck-suppress 文件以外的任何配置文件
- **不触碰** CI/CD 流水线配置（Jenkinsfile、.github/workflows 等）

## 输出约定
- 按严重程度分组的问题列表
- ERROR 级别问题的修复建议（含通用代码模板）
- MISRA 问题按 Mandatory / Required / Advisory 分级展示（启用时）
- 汇总统计（文件数、问题总数、各级别数量、扫描耗时）
- 可选导出：HTML 报告 / JSON 文件 / XML 文件

## 交接关系

- 上游：`build-keil` / `build-cmake`（编译通过后自动触发静态分析）
- 互补：`coding-standards`（编码规范速查）+ `embedded-reviewer`（人工审查）
- 下游：修复问题后重新编译 → `flash-jlink` / `flash-keil` 烧录验证
- CI/CD：`workflow` 流水线中自动集成增量扫描
