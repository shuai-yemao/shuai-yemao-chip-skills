---
name: coding-standards
description: |
  嵌入式 C 编码规范速查手册——合并自 MISRA C:2012（143 条规则）和立芯嵌入式 C 编码规范。
  涵盖规则优先级协议（MISRA Mandatory/Required > Advisory > 立芯风格）、
  各分类规则速查（标准 C 环境/标识符/类型/声明/初始化/表达式/控制流/函数/指针/预处理/标准库）、
  立芯代码风格规则（缩进/命名/注释/文件组织/返回值检查/内存安全/可移植性）、
  cppcheck MISRA 自动扫描集成、偏差记录模板。
  当用户提到编码规范、MISRA、立芯规范、代码风格、命名规范、缩进风格、编码标准、
  代码规范审查、合规检查、车规编码、ISO 26262、IEC 61508、ASIL 时使用。
  与 embedded-reviewer（审查官，用于代码 Review）、static-analysis（cppcheck 自动扫描）互补。
version: "1.0.0"
---

# 嵌入式 C 编码规范速查

> 合并立芯嵌入式 C 编码规范 + MISRA C:2012 核心规则。
> 注：完整 143 条 MISRA 规则在 **embedded-reviewer** 中按审查场景展开。
> 本 skill 是"写代码时查的规范手册"，embedded-reviewer 是"审代码时用的方法论"。

## 适用场景

- 写代码时需要快速查某个 MISRA 规则的具体要求
- 需要确认立芯编码规范对命名/缩进/注释的约定
- 需要为项目配置 cppcheck MISRA 检查
- 审查时遇到规范争议需要查原始规则
- 需要记录 MISRA 偏差（deviation）时的模板参考

## 必要输入

| 输入 | 说明 |
|------|------|
| 查询规则 | MISRA 规则号（如 R10.1）或关键词（如 "指针转换"） |
| 场景类型 | 编码/审查/偏差记录/cppcheck 配置 |
| 目标平台 | 编译器/工具链（影响 MISRA 规则适用性）|

## 规则优先级协议

两个规范源同时命中时，按以下优先级处理：

```
P0 — MISRA Mandatory        ─→ 安全正确性问题，必须先修
P1 — MISRA Required         ─→ 合规性问题，必须修
P2 — MISRA Advisory         ─→ 建议修
P3 — 立芯风格规则           ─→ 命名/格式/注释（安全合规之后处理）
```

冲突时 MISRA 优先。立芯规范有合理例外时在注释中说明。

## 场景抉择

| 场景 | 用哪个 skill |
|------|-------------|
| 「这段代码符合规范吗」「帮我过 MISRA」 | **本 skill**（规范速查） |
| 「帮我 Review 这段代码」「看看有没有坑」 | **embedded-reviewer**（审查方法论） |
| 「跑 cppcheck 扫描」 | **static-analysis**（工具扫描） |
| 「代码风格统一一下」 | **本 skill → 立芯风格章节** |
| 「完整的质量门禁」 | **static-analysis → embedded-reviewer → build-keil** |

## 依赖

- 本 skill 无需外部工具或脚本（纯知识参考）
- cppcheck MISRA 集成部分需要 `cppcheck` 工具（可选）

## 第一部分：MISRA C:2012 核心规则速查

### 按违规频率排序（Top 15 覆盖 80% 场景）

| # | 规则 | 严重度 | 说明 | 典型场景 |
|---|------|--------|------|---------|
| 1 | Dir 4.12 | Mandatory | 禁止动态内存分配 | malloc/free/realloc 均禁止 |
| 2 | R8.7 | Required | 函数和变量应 static（除非需外部可见） | 文件级函数/变量缺 static |
| 3 | R10.1 | Required | 禁止表达式中混用有符号和无符号 | int + uint 混合运算 |
| 4 | R11.3 | Required | 禁止整型强制转为指针 | memory-mapped I/O（→ 记偏差） |
| 5 | R12.1 | Advisory | 运算符优先级加括号明确 | 复杂表达式优先级混淆 |
| 6 | R14.3 | Required | 控制表达式应为布尔类型 | `if (x = func())` 笔误 |
| 7 | R15.5 | Advisory | 函数单一出口 | 多处 return 导致资源泄露 |
| 8 | R16.3 | Required | switch 每个 case 须 break | fallthrough 漏洞 |
| 9 | R17.2 | Required | 禁止递归 | 栈不可预测 |
| 10 | R21.1 | Required | 禁止风险标准库函数 | abort/exit/setjmp |
| 11 | R2.2 | Mandatory | 禁止不可达代码 | break 后的代码 |
| 12 | R9.1 | Mandatory | 变量使用前必须初始化 | 未初始化局部变量 |
| 13 | R13.2 | Required | 禁止序列点间多次副作用 | `a[i] = i++` |
| 14 | R18.1 | Required | 指针运算限于数组范围内 | 缓冲区越界 |
| 15 | R20.7 | Required | 宏参数须加括号 | 宏展开副作用 |

### 关键指令 (Directives)

| Dir | 严重度 | 说明 |
|-----|--------|------|
| 1.1 | Required | 实现定义行为须记录文档 |
| 2.1 | Required | 零编译错误方可通过 |
| 3.1 | Required | 需求可追溯 |
| 4.1 | Required | 减少运行时故障 |
| 4.3 | Required | 汇编须封装在独立函数中 |
| 4.6 | Advisory | typedef 代替基础类型 |
| 4.10 | Required | 头文件须有包含保护 |
| 4.11 | Required | 库函数入参须校验 |
| 4.12 | **Mandatory** | **禁止动态内存分配** |

### 嵌入式高频违规分类

**分类 10 — 基本类型（8 条规则）**
- 核心：`essentially boolean` vs `essentially signed/unsigned` 不可混用
- 典型：`if (x & 0x01)` 应写为 `if ((x & 0x01) != 0u)`

**分类 11 — 指针转换（9 条规则）**
- 核心：不可去 const/volatile，不可函数指针转换
- BSP 例外：memory-mapped I/O 的 R11.3 应记录偏差

**分类 13 — 副作用（6 条规则）**
- 核心：表达式序列点之间同一对象最多被修改一次
- 高频：`a = b++ + c++;` → R13.2

**分类 17 — 函数（8 条规则）**
- 核心：禁止递归（R17.2），检查返回值（R17.7）

**分类 22 — 资源（10 条规则）**
- 核心：文件流必须关闭，errno 使用前须清零

> 完整规则展开见 **embedded-reviewer** 的审查启发式 5（MISRA Top 10 审查清单）。

## 第二部分：立芯嵌入式 C 编码规范

### 代码归属判断

| 类型 | 处理方式 |
|------|---------|
| 自研代码（App/Service/Bsp/Platform/Utils） | 全面执行规范 |
| 生成代码（Core/ 下 CubeMX 生成、Drivers/HAL） | 不动非 USER CODE 区域 |
| 第三方代码（FreeRTOS/lwIP/FatFS） | 保留原风格，只改必要逻辑 |

### 命名规范

| 对象 | 规则 |
|------|------|
| 文件名与函数名 | `snake_case` |
| 局部变量与参数 | `lowerCamelCase` |
| 文件级/全局可变状态 | `g_` + `lowerCamelCase` |
| 宏、枚举值、标签 | `UPPER_SNAKE_CASE` |
| typedef 类型名 | `PascalCase` |
| 静态函数 | `_` 前缀 + `snake_case` |

### 格式规则

- 缩进：4 空格，禁止 TAB
- 行宽：≤ 120 列
- 大括号：K&R 风格（函数左大括号独占一行，控制语句左大括号在行末）
- if/else/for/while/do/switch 一律显式加 `{}`
- switch：case 相对 switch 缩进一级，显式 break/return
- 文件组织顺序：文件头注释 → #include → 宏与常量 → 类型定义 → static 变量 → 内部声明 → static 函数 → 对外函数

### 文件头模板

```c
/******************************************************************************
 * Copyright (C) 2024 EternalChip, Inc.(Gmbh) or its affiliates.
 * All Rights Reserved.
 *
 * @file <filename>
 * @author <Author Name> | R&D Dept. | EternalChip 立芯嵌入式
 * @brief <Brief description>
 * @version V1.0 <YYYY-M-D>
 *****************************************************************************/
```

### 函数注释模板

```c
/**
 * @brief Initialize the debugging function section
 * @param[in]  param1 - input parameter description
 * @param[Out] param2 - output parameter description
 * @return None
 */
```

### 安全性规则

| 规则 | 说明 |
|------|------|
| 函数尽量只做一件事 | ≤ 50 行非空代码，嵌套 ≤ 4 层 |
| 返回值必须检查 | HAL API、OS 调用、内存分配、I/O 立即检查 |
| 外部输入须校验 | API 入参、文件数据、网络报文、IPC 数据 |
| assert 仅用于内部不变量 | 不用 assert 校验外部输入 |
| 资源释放收口 | `cleanup:` 标签统一 exit 路径 |
| 宏用 `do { } while (0)` | 多语句宏防止悬挂 else |
| 全局状态须 static | 跨 ISR/Task 访问须同步策略 |
| 指针运算用 uintptr_t | 不用 uint32_t 传指针 |
| size_t 保留长度语义 | 缩窄到 32 位前显式边界检查 |
| 生产代码统一日志接口 | 不留 printf，调试钩子用编译开关 |

### 可移植性规则

- `stdint.h` 固定宽度类型代替 `int`/`long`
- 硬编码寄存器地址用宏 + `volatile` 指针
- 大小端敏感代码用 `__BYTE_ORDER__` 预处理
- 位域顺序由编译器决定，跨编译器不可移植 → 避免

## 第三部分：cppcheck MISRA 集成

### 基础命令

```bash
# 基础扫描
cppcheck --addon=misra --enable=all --inconclusive src/

# 带 compile_commands.json（推荐，含头文件）
cppcheck --addon=misra --project=compile_commands.json --enable=all

# 输出到 XML 供 CI 解析
cppcheck --addon=misra --enable=all --xml --xml-version=2 src/ 2> misra_report.xml
```

### 抑制语法

```c
// 单行抑制
int32_t x = (int32_t)ptr; // cppcheck-suppress misra-c2012-11.3

// 代码块抑制
// cppcheck-suppress-begin misra-c2012-11.3
volatile uint32_t *reg = (volatile uint32_t *)0x40000000;
// cppcheck-suppress-end misra-c2012-11.3
```

### 嵌入式项目建议默认抑制

| 规则 | 理由 |
|------|------|
| R2.3/2.4/2.5 | 未使用声明：三方代码中常见，工具链可检测 |
| R5.9 | 内部标识符唯一性：过严 |
| R8.9 | 内部对象 static：工具链可检测 |
| R11.3 | 指针整数转换：BSP 层 memory-mapped I/O 不可避（须偏差记录） |

## 第四部分：偏差 (Deviation) 记录模板

当 MISRA 规则确实无法遵守时（嵌入式高频：memory-mapped I/O、汇编），记录偏差而非忽略。

```markdown
## MISRA Deviation Record

| 字段 | 值 |
|------|-----|
| **Deviation ID** | DEV-YYYY-NNN |
| **Rule** | Rule 11.3 |
| **严重度** | Required |
| **位置** | `bsp_flash.c:flash_read_id()` |
| **违规** | Flash 基址整数强制转为指针 |
| **理由** | Memory-mapped I/O 必须通过指针转换，C 无替代方式 |
| **风险缓解** | ① 仅 BSP 层使用 ② 地址由链接脚本固定 ③ 每次构建自动检查 |
| **审查人** | |
| **批准日期** | |
```

## 输出约定

编码规范查询返回：
- 规则原文摘要 + 严重度 + 典型违规场景
- 立芯 vs MISRA 优先级对比
- 修复建议代码示例（如有）
- cppcheck 配置命令
- 偏差记录模板（需要时）

## 边界定义

### 不该激活
- 用户需要的是代码审查方法论（而非规范速查）-> 使用 `embedded-reviewer`
- 用户需要的是自动扫描工具（而非人工查规范）-> 使用 `static-analysis`
- 用户项目是非 C/C++ 语言（Python/Java/Go 等）

### 不该做
- **禁止**修改 CubeMX 非 USER CODE 区域的生成代码
- **禁止**大面积重命名稳定公共 API 来符合命名规范
- **禁止**为"看起来整齐"整文件格式化
- **禁止**以 MISRA 为由严重降低 ISR 性能（应走 deviation 流程）

### 不该碰
- **不触碰**第三方库的编码风格（FreeRTOS/lwIP/FatFS 保持原风格）
- **不触碰**编译器特定的扩展语法（GCC/ARMCC 差异由编译器开关处理）

## 错误处理与边界

| 场景 | 处理 |
|------|------|
| 规则冲突 | MISRA 优先于立芯，例外须注释 |
| 三方/生成代码 | 不强制改造，只分析不修改 |
| 功能安全认证 | MISRA 偏差须走正式 deviation 流程 |
| 仅需编译通过 | 不激活规范审查 |

### 不该做的

- 修改 CubeMX 非 USER CODE 区域
- 大面积重命名稳定公共 API
- 为"看起来整齐"整文件格式化
- 用 MISRA 为由严重降低 ISR 性能（→ deviation 记录）

## 交接关系

```
coding-standards (本 skill)
    ↓ "怎么写代码"
embedded-reviewer
    ↓ "怎么审代码"
static-analysis (cppcheck)
    ↓ "自动检查"
build-* (编译验证)
```

> 合并自：立芯嵌入式 C 编码规范 + MISRA C:2012 官方规范
