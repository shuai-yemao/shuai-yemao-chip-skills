---
name: doc-automation
description: 嵌入式文档自动化工具集——从嵌入式 C 工程代码和配置中自动生成函数注释、API 文档、硬件接线说明、minunit 单元测试骨架和移植指南。所有脚本零外部依赖（仅 Python 标准库）。当用户提到生成文档、API 文档、函数注释、Doxygen、接线说明、单元测试、minunit、移植指南、docgen、注释生成、测试骨架时使用。
version: "1.0.0"
---

# 嵌入式文档自动化

从嵌入式 C 工程代码和配置中自动生成各类文档，减少手动维护文档的工作量。

## 适用场景

- 需要为工程中的 .h 文件自动生成 Doxygen 格式的函数注释
- 需要从 .h 文件生成结构化的 Markdown API 文档
- 需要从 CubeMX .ioc 文件或头文件注释生成硬件接线表
- 需要从 .h 文件生成 minunit 单元测试骨架代码
- 需要对比两套 .h 接口生成移植映射表和指南

## 必要输入

| 参数 | 说明 | 默认值 |
|------|------|--------|
| 扫描目录 | 要扫描的 .h 文件所在目录 | 当前目录 |
| --dry-run | 试运行模式，不实际写入 | false |
| --output | 输出文件路径 | 自动生成 |
| --target | 目标文件(.h) | 必填（单文件操作） |

## 依赖

- Python 3.8+
- 所有脚本零外部依赖（仅使用标准库）
- docgen_test.py 生成的测试文件需要链接 minunit.h
- minunit_runner.py 要求 gcc 在 PATH 中

## 执行步骤

### 生成函数注释
```bash
python scripts/docgen_annotate.py scan <dir>          # 扫描缺注释函数
python scripts/docgen_annotate.py annotate <file.h>    # 插入 Doxygen 注释
python scripts/docgen_annotate.py check <file.h>       # 检查注释覆盖率
```

### 生成 API 文档
```bash
python scripts/docgen_api.py build <file.h> [-o api.md]   # 单文件
python scripts/docgen_api.py build <dir>   [-o api.md]    # 递归目录
```

### 生成硬件接线表
```bash
python scripts/docgen_wiring.py from-ioc <board.ioc> [-o wiring.md]   # 从 .ioc
python scripts/docgen_wiring.py from-md <file.h>   [-o wiring.md]     # 从头文件
python scripts/docgen_wiring.py from-req <req.md>  [-o wiring.md]     # 从需求文档
```

### 生成单元测试骨架
```bash
python scripts/docgen_test.py minunit <file.h> [-o test_file.c]   # 生成测试骨架
python scripts/docgen_test.py check <file.h> <test.c>              # 检查覆盖率
python scripts/minunit_runner.py <project_dir>                     # 编译并运行
```

### 生成移植指南
```bash
python scripts/docgen_porting.py diff <old.h> <new.h> [-o report.md]   # 接口差异
python scripts/docgen_porting.py guide <old.h> <new.h>                  # 移植指南
python scripts/docgen_porting.py map <old.h> <new.h> [-o map.json]      # 映射表
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 没有找到 .h 文件 | 扫描目录不含头文件 | 确认目录路径，确保 .h 文件存在 |
| 注释覆盖率低 | 大量函数缺注释 | 使用 annotate 自动插入后人工复核 |
| 测试编译失败 | 外部 HAL 依赖缺失 | 编写 mock stub 替代实际 HAL 调用 |
| gcc not found | 编译器未安装或不在 PATH | 安装 GCC 工具链并加入 PATH |
| .ioc 解析失败 | 文件格式异常或 CubeMX 版本不兼容 | 检查 .ioc XML 格式完整性 |

## 输出约定

- 注释生成：插入 Doxygen 注释后的 .h 文件（--dry-run 时仅打印差异）
- API 文档：结构化 Markdown 文件（函数列表 + 签名 + 参数 + 返回值）
- 接线表：Markdown 表格（引脚号 ↔ 外设功能 ↔ 连接目标）
- 测试骨架：minunit 格式的 .c 测试文件
- 移植报告：接口差异 Markdown + JSON 映射表

## 边界定义

### 不该激活
- 用户需要的是纯粹的代码编写而非文档生成
- 用户需要的是用户手册/产品文档等非代码文档
- 用户需要在 Keil/IAR IDE 中手动添加注释
- 用户工程不含 .h 文件或工程过小不需要自动化

### 不该做
- **禁止**修改 .h 文件中的业务逻辑代码（只插入注释块）
- **禁止**覆盖用户已有的测试文件（除非指定 --force）
- **禁止**自动删除已有注释（仅插入缺失注释）
- **禁止**假定自动生成的注释准确无误（必须人工复核）

### 不该碰
- **不触碰** .c 源文件（除非注释生成）
- **不触碰** CubeMX 自动生成的 .ioc 文件
- **不触碰**用户的测试数据和验证结果

## 交接关系

- 上游：`stm32-hal-development`（HAL 工程开发完成后生成文档）
- 下游：`build-cmake`（编译验证测试代码）
- 互补：`static-analysis`（代码质量检查）+ `coding-standards`（编码规范）
- 测试：生成的 minunit 代码通过 `workflow` 中的测试流水线运行
