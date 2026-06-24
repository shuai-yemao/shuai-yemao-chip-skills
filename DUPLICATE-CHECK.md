# Skills 与 Workflows 重复检查报告

## 重复清单

### 1. 固件开发相关

| Skills（chip-skills） | Workflows（chip-workflow） | 重复类型 |
|----------------------|---------------------------|----------|
| **build-cmake** | firmware-development/modules/build-management | 🔴 高度重复 |
| **build-iar** | firmware-development/modules/build-management | 🔴 高度重复 |
| **build-keil** | firmware-development/modules/build-management | 🔴 高度重复 |
| **build-idf** | firmware-development/modules/build-management | 🔴 高度重复 |
| **build-platformio** | firmware-development/modules/build-management | 🔴 高度重复 |
| **flash-jlink** | firmware-development/modules/build-management | 🟡 部分重复 |
| **flash-openocd** | firmware-development/modules/build-management | 🟡 部分重复 |
| **flash-keil** | firmware-development/modules/build-management | 🟡 部分重复 |
| **flash-platformio** | firmware-development/modules/build-management | 🟡 部分重复 |
| **flash-idf** | firmware-development/modules/build-management | 🟡 部分重复 |
| **gang-flash** | firmware-development/modules/build-management | 🟡 部分重复 |
| **debug-gdb-openocd** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **debug-platformio** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **embedded-debugger-framework** | firmware-development/modules/test-integration | 🟡 部分重复 |

### 2. 架构设计相关

| Skills（chip-skills） | Workflows（chip-workflow） | 重复类型 |
|----------------------|---------------------------|----------|
| **bootloader-design** | firmware-development/modules/architecture-design | 🟡 部分重复 |
| **embedded-system-design** | firmware-development/modules/architecture-design | 🟡 部分重复 |
| **lowpower-design** | firmware-development/modules/architecture-design | 🟡 部分重复 |

### 3. 测试相关

| Skills（chip-skills） | Workflows（chip-workflow） | 重复类型 |
|----------------------|---------------------------|----------|
| **rtos-debug** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **cmbacktrace-debug** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **segger-rtt-module** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **systemview-module** | firmware-development/modules/test-integration | 🟡 部分重复 |
| **static-analysis** | testing-cicd/modules/code-quality | 🟡 部分重复 |

### 4. 硬件设计相关

| Skills（chip-skills） | Workflows（chip-workflow） | 重复类型 |
|----------------------|---------------------------|----------|
| **pcb-analysis** | hardware-design | 🟡 部分重复 |

## 重复分析

### 高度重复（建议合并）

| Skills | 建议 |
|--------|------|
| build-cmake | 合并到 firmware-development 工作流 |
| build-iar | 合并到 firmware-development 工作流 |
| build-keil | 合并到 firmware-development 工作流 |
| build-idf | 合并到 firmware-development 工作流 |
| build-platformio | 合并到 firmware-development 工作流 |

### 部分重复（保留两者）

| Skills | Workflows | 建议 |
|--------|-----------|------|
| flash-* | firmware-development | Skills 提供具体烧录脚本，工作流提供流程管理 |
| debug-* | firmware-development | Skills 提供调试工具，工作流提供测试流程 |
| 设计相关 | firmware-development | Skills 提供设计指南，工作流提供架构流程 |

## 建议处理方案

### 方案 1：保留两者，明确分工

```
Skills（具体工具）          Workflows（流程管理）
├── build-cmake            ├── firmware-development
├── build-iar              │   ├── architecture-design
├── build-keil             │   ├── build-management
├── flash-jlink            │   ├── test-integration
├── debug-gdb-openocd      │   └── release-management
└── ...                    └── ...
```

**优点**：
- Skills 提供具体工具和脚本
- Workflows 提供完整流程编排
- 两者互补，不冲突

**缺点**：
- 用户可能困惑在哪里使用哪个
- 需要文档说明分工

### 方案 2：合并重复 Skills 到 Workflows

将高度重复的 Skills 合并到 firmware-development 工作流中：

```
firmware-development/
├── modules/
│   ├── architecture-design/
│   ├── build-management/
│   │   ├── cmake-builder.js    ← 合并 build-cmake
│   │   ├── iar-builder.js      ← 合并 build-iar
│   │   ├── keil-builder.js     ← 合并 build-keil
│   │   ├── idf-builder.js      ← 合并 build-idf
│   │   └── platformio-builder.js ← 合并 build-platformio
│   ├── test-integration/
│   └── release-management/
```

**优点**：
- 消除重复
- 集中管理
- 流程清晰

**缺点**：
- 工作量大
- 需要重构

### 方案 3：Skills 专注底层，Workflows 专注编排

```
Skills（底层能力）            Workflows（上层编排）
├── build-cmake            ├── firmware-development
├── build-iar              │   （调用 build-* skills）
├── flash-jlink            ├── hardware-design
├── debug-gdb-openocd      │   （调用 pcb-analysis skill）
└── pcb-analysis           └── testing-cicd
                              （调用 static-analysis skill）
```

**优点**：
- 职责清晰
- 可复用性强
- 符合模块化设计

**缺点**：
- 需要工作流支持 skill 调用
- 需要文档说明

## 最终建议

**推荐方案 1：保留两者，明确分工**

原因：
1. **Skills 提供工具**：具体的构建、烧录、调试脚本
2. **Workflows 提供流程**：完整的固件开发流程管理
3. **用户按需使用**：
   - 只需要构建 → 使用 `build-cmake` skill
   - 完整固件开发 → 使用 `firmware-development` workflow

### 文档说明

在 README 中添加说明：

```markdown
## Skills vs Workflows

| 类型 | 用途 | 示例 |
|------|------|------|
| **Skills** | 具体工具和脚本 | build-cmake, flash-jlink, debug-gdb-openocd |
| **Workflows** | 完整流程编排 | firmware-development, hardware-design |

**使用建议**：
- 只需要单一功能 → 使用 Skills
- 需要完整流程 → 使用 Workflows
- Workflows 内部会调用 Skills 完成具体任务
```
