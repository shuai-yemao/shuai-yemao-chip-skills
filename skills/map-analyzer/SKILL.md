---
name: map-analyzer
description: 解析 GCC/Keil/IAR .map 文件，分析 Flash/RAM 使用率、模块符号大小、版本对比 diff、风险预警与优化建议。支持彩色进度条、JSON/CSV 导出。当用户提到 .map 文件、内存分析、Flash/RAM 使用率、链接溢出、代码体积优化、region overflow、哪个文件占用内存最多时使用。
version: "1.0.0"
---

# map-analyzer

解析 GCC / Keil / IAR 链接器生成的 .map 文件，分析 Flash 和 RAM 使用情况，
检测内存溢出风险，按模块汇总符号大小，辅助固件体积优化。

## 触发条件
- 用户询问 Flash/RAM 使用率
- 用户看到链接报错"区域溢出"、"region overflow"
- 用户需要分析哪个模块/文件占用内存最多
- 编译完成后自动分析内存分布
- 用户说"内存分析"
- 用户说"链接溢出"
- 用户说"代码体积优化"
- 用户提到".map 文件"

## 参数收集
- `map_file`: .map 文件路径（必填，可从构建产物目录自动搜索）
- `flash_size`: 目标 Flash 总大小（字节，可选，用于计算使用率）
- `ram_size`: 目标 RAM 总大小（字节，可选）
- `top_n`: 显示最大符号的前 N 个（默认 20）
- `format`: 工具链格式，gcc（默认）/ keil / iar（不同工具链 .map 格式不同）
- `compare`: 对比另一个 .map 文件路径（用于版本间内存变化分析，可选）
- `export`: 导出格式，json / csv（可选，不填则仅终端输出）
- `threshold`: 超过此大小（字节）才显示在 Top N 中（默认 0，即不过滤）

## 执行流程

### Step 1 定位 .map 文件
优先使用传入路径，否则在工程 build/ 目录中递归搜索 *.map。

### Step 2 解析内存段
根据 `--format` 选择对应解析器：
- GCC：提取各 section 大小（.text / .rodata → Flash；.data / .bss / .heap / .stack → RAM）
- Keil：解析 `Image component sizes` 段（见下方说明）
- IAR：解析 `MODULE SUMMARY` 和 `ENTRY LIST` 段（见下方说明）

### Step 3 按文件/模块汇总
统计每个 .o 文件贡献的代码和数据大小，按 `--threshold` 过滤小符号。

### Step 4 输出报告
```
════════════════ 内存使用分析 ════════════════
Flash 使用: 45,312 / 65,536 字节 (69.1%) [绿色进度条]
RAM 使用:    8,192 / 20,480 字节 (40.0%) [绿色进度条]

各段明细:
  .text    : 42,156 字节
  .rodata  :  3,156 字节
  .data    :    256 字节
  .bss     :  7,936 字节

最大符号 Top 10:
  main.o          |  4,256 字节 | .text
  usb_device.o    |  3,104 字节 | .text
  ...
```

进度条颜色规则（ANSI，Windows 自动检测支持）：
- 使用率 < 70%  → 绿色
- 使用率 70~90% → 黄色
- 使用率 > 90%  → 红色

### Step 5 风险预警
- 使用率 > 80% → 触发优化建议（见下方"优化建议"章节）
- 使用率 > 90% → 警告
- 使用率 > 100% → 错误（链接必然失败）

### Step 6 版本对比（可选）
若提供 `--compare` 参数，执行两份 .map 文件的符号级 diff（见下方"版本对比"章节）。

### Step 7 导出（可选）
若提供 `--export json` 或 `--export csv`，将分析结果写入同名文件。

## 输出约定
- 内存使用率图表（带颜色进度条）
- 各 section 大小明细
- 按模块排序的 Top N 大符号（支持 threshold 过滤）
- 优化建议（使用率 > 80% 时自动触发）
- 版本对比 diff（提供 --compare 时）
- JSON / CSV 导出文件（提供 --export 时）

## 交接关系

- 上游：`build-keil` / `build-cmake`（编译链接后自动触发 .map 分析）
- 下游：发现内存溢出 → `stm32-hal-development` / `freertos-module`（优化代码体积）
- 辅助：`static-analysis`（结合代码质量检查）
- 工作流：`workflow` 构建流水线中自动调用

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| .map file not found | 工程未编译或无 .map 文件生成 | 先执行编译流程，确认链接完成后重试 |
| Unknown map format | 工具链格式参数错误 | 指定 `--format gcc` / `--format keil` / `--format iar` |
| Parse error: unexpected section | .map 文件被截断或损坏 | 重新编译生成新 .map 文件后再分析 |
| Flash/RAM size not specified | 未提供芯片 Flash/RAM 总量 | 通过 `--flash-size` 和 `--ram-size` 指定（字节） |
| No symbols to compare | --compare 指定的旧 .map 为空 | 确认对比文件是同一工程的有效旧版 .map |
| No .map files in directory | 搜索目录下没有 *.map | 检查工程输出目录（Objects/build/Release 等） |

## 边界定义

### 不该激活
- 用户需要的是固件本身的逻辑调试（而非内存布局分析）→ 使用 `debug-gdb-openocd` / `rtos-debug`
- 用户尚未完成编译链接（无 .map 文件生成）
- 用户只需要查看单个符号地址（`arm-none-eabi-nm` 足够）而非完整内存分析
- 用户提到 "map" 但指的是 C++ std::map 容器而非链接器 map 文件

### 不该做
- **禁止**修改 .map 文件或链接脚本（.ld）
- **禁止**跨工具链格式混淆解析（不能将 Keil .map 用 GCC 解析器解析）
- **禁止**在 Flash/RAM 容量未提供时给出伪精确的使用率（仅给出原始字节数）

### 不该碰
- **不触碰** .map 文件：只读取解析，不修改
- **不触碰**链接脚本（.ld/.icf/.sct）：不修改 memory region 配置
- **不触碰**固件二进制产物（.elf/.bin/.hex）
- **不触碰**编译器/链接器优化参数

---

## Keil .map 解析说明

Keil MDK 生成的 .map 文件与 GCC 格式有显著差异，需单独处理。

**关键段：`Image component sizes`**

该段列出每个目标文件（.o）的各列大小，典型格式：

```
Image component sizes

      Code (inc. data)   RO Data    RW Data    ZI Data      Debug   Object Name

      1234       56        789         12        3456      78900   main.o
       567       12        123          0         456      12300   uart.o
```

列含义：
- `Code`：代码段大小（含内嵌数据 inc. data）
- `RO Data`：只读数据（归入 Flash）
- `RW Data`：已初始化读写数据（Flash 存储初始值，RAM 运行时使用）
- `ZI Data`：零初始化数据（BSS，归入 RAM）

Flash 占用 = Code + RO Data + RW Data
RAM 占用 = RW Data + ZI Data

**解析要点：**
1. 找到 `Image component sizes` 行后，跳过表头，逐行提取数字列
2. 注意表尾有 `Totals` 汇总行，可直接读取作为全局统计
3. 符号来源文件取最后一列 `Object Name`

---

## IAR .map 解析说明

IAR EWARM 生成的 .map 文件需解析两个关键段：

### MODULE SUMMARY 段

列出每个模块（.o 文件）的内存占用，典型格式：

```
*******************************************************************************
*** MODULE SUMMARY
***

    Module                ro code  ro data  rw data
    ------                -------  -------  -------
    main.o                   1234      456       78
    uart.o                    567       89        0
    -------------------------
    Total:                   1801      545       78
```

列含义：
- `ro code`：只读代码（归入 Flash）
- `ro data`：只读数据（归入 Flash）
- `rw data`：读写数据（初始值在 Flash，运行时在 RAM）

### ENTRY LIST 段

列出各符号的详细地址和大小，可用于 Top N 分析：

```
*******************************************************************************
*** ENTRY LIST
***

  Entry                 Address   Size  Type      Object
  -----                 -------   ----  ----      ------
  main                 0x00000100   0x234  Code    main.o [1]
  g_buffer             0x20000000  0x1000  Data    data.o [2]
```

**解析要点：**
1. `MODULE SUMMARY` 中 Flash = ro code + ro data + rw data，RAM = rw data
2. `ENTRY LIST` 用于提取符号级大小（Top N 列表）
3. IAR 的 ZI（零初始化）数据在部分版本中以 `zi data` 列出现

---

## 优化建议

当 Flash 或 RAM 使用率超过 **80%** 时，分析工具自动输出以下优化建议：

### Flash 优化建议

| 优化措施 | GCC 编译/链接选项 | 预期效果 |
|----------|-------------------|----------|
| 启用链接时优化 | `-flto` | 消除跨模块死代码，减小 5~20% |
| 去除未使用符号 | `-Wl,--gc-sections` + `-ffunction-sections -fdata-sections` | 精确裁剪未调用函数 |
| 压缩只读数据 | `-Os`（优化体积） | 代码整体缩小 |
| 压缩字符串 | 避免 `printf`，改用 `puts`/自定义日志 | 减少格式字符串体积 |
| 去除调试符号 | 链接时加 `-s` 或 `strip` | 减小 ELF，不影响运行 |
| 使用 `__attribute__((weak))` | 允许链接器丢弃默认实现 | 减少库函数冗余 |

### RAM 优化建议

| 优化措施 | 说明 |
|----------|------|
| 检查 BSS 中的大数组 | 使用 `--top` 查找大型全局/静态数组，评估是否可缩减 |
| 减小堆栈大小 | 在链接脚本中调低 `_Min_Stack_Size`，需确认最大调用深度 |
| 使用静态分配替代动态分配 | 减少堆（heap）碎片，避免 malloc 失败风险 |
| 复用缓冲区 | 不同功能的临时缓冲区可用 union 或时序复用 |
| 将只读数据移至 Flash | 常量表加 `const` 修饰，确保编译器不复制到 RAM |

---

## 版本对比

当通过 `--compare <旧版.map>` 提供两个 .map 文件时，工具输出符号级 diff：

### 输出格式

```
════════════════ 版本对比 diff ════════════════
基准文件: firmware_v1.0.map
对比文件: firmware_v1.1.map

[新增符号]  (+)
  new_feature.o       +2,048 字节  .text
  extra_table.o         +512 字节  .rodata

[删除符号]  (-)
  old_module.o        -1,024 字节  .text

[增大符号]  (↑)
  main.o              +256 字节  .text  (4,000 → 4,256)

[减小符号]  (↓)
  uart_driver.o        -64 字节  .text  (1,064 → 1,000)

Flash 变化: +1,728 字节 (+2.6%)
RAM   变化:   +256 字节 (+3.1%)
```

### 对比规则
1. 以文件名（.o）为键进行匹配
2. 仅一方有的文件视为新增/删除
3. 两方都有但大小不同视为增大/减小
4. 输出时按变化量绝对值降序排列
