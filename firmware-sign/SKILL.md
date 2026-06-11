---
name: firmware-sign
description: 固件签名、加密与安全打包工具。支持 ECDSA/RSA/Ed25519 数字签名、AES-256-GCM/CBC 加密、固件头打包、Bootloader 验签代码生成、版本注入、仅加密无签名模式。当用户提到固件签名、验签、secure boot、防篡改、量产加密、固件头、签名打包、AES-CBC 加密固件、仅加密、硬编码密钥时使用。
---

# firmware-sign

固件签名、加密与安全打包工具链。对嵌入式固件进行哈希校验、ECDSA/RSA/Ed25519 数字签名、
AES-256-GCM 加密存储、以及生成带签名头的量产固件包，同时生成 Bootloader 验签所需的 C 语言结构体。

## 触发条件
- "固件签名"、"firmware sign"、"签名"、"验签"、"打包固件"
- "防篡改"、"安全启动"、"secure boot"、"量产加密"
- "给固件加签名头"、"固件头"、"firmware header"
- "ECC 签名"、"RSA 签名"、"AES 加密固件"
- "生成 bootloader 验签代码"、"验签结构体"
- "AES-CBC"、"AES-256-CBC"、"CBC 模式加密"
- "仅加密"、"encrypt only"、"加密不签名"
- "硬编码密钥"、"key hardcoded"、"固件里写死密钥"
- "固件加密后不验签"、"低成本加密"、"防抄板加密"

## 参数收集
- firmware: 原始固件文件路径（.bin/.hex/.elf）
- operation: hash / sign / verify / pack / encrypt / gen-header / inject-version
- algorithm: sha256 / sha384 / sha512 / sha3_256 / crc32 / all
- sig_algo: ecdsa-p256（默认）/ ecdsa-p384 / rsa-2048 / rsa-4096 / ed25519
- key_file: 私钥文件路径（PEM 格式，sign/encrypt 操作使用）
- pub_key: 公钥文件路径（verify 操作使用）
- output: 输出文件路径
- header_size: 固件头大小（默认 256 字节）
- version: 注入的版本号（x.y.z 格式，inject-version 操作）
- version_offset: 版本注入的 bin 偏移（默认 0x200）
- aes_key: AES-256 密钥（hex 字符串或文件路径，encrypt 操作）
- aes_iv: AES IV/Nonce（hex 字符串，CBC 模式必填 32 hex chars = 16 字节，GCM 模式可选）
- encrypt_mode: gcm / cbc（默认 gcm）。cbc 用于与传统工程（如硬编码 Key/IV 的 STM32 Bootloader）兼容
- metadata_json: 是否输出 CI/CD 元数据 JSON（默认 true）

## 固件包格式（pack 操作）

```
┌─────────────────────────────────────────┐  偏移 0x000
│  Magic Number  (4 bytes)  0x46574442    │  "FWDB"
│  Header Ver    (2 bytes)                │
│  Sig Algo      (1 byte)                 │  0=无 1=ECDSA-P256 2=ECDSA-P384 3=RSA-2048 4=RSA-4096 5=Ed25519
│  Encrypt Algo  (1 byte)                 │  0=无 1=AES-256-GCM 2=AES-256-CBC
│  Version       (4 bytes)   uint32       │  major<<16 | minor<<8 | patch
│  Firmware Size (4 bytes)                │
│  CRC32         (4 bytes)                │
│  SHA256 Hash   (32 bytes)               │
│  Signature Len (2 bytes)                │
│  Signature     (N bytes, 可选)          │
│  AES IV/Nonce  (16 bytes, GCM:可选, CBC:必填)│  GCM nonce(12B) 或 CBC IV(16B)
│  AES Tag       (16 bytes, GCM 模式)    │  GCM auth tag（GCM 模式使用）
│  Reserved      (填充至 header_size)     │
├─────────────────────────────────────────┤  偏移 header_size
│  Firmware Data (原始/加密 .bin 数据)    │
└─────────────────────────────────────────┘
```

### Bootloader 验证流程（含签名）

```
1. 读取 Magic Number (0x46574442)，确认固件有效
2. 检查 Sig Algo / Encrypt Algo 标志
3. 如加密（Encrypt Algo == 1）：AES-256-GCM 解密（含认证标签验证）
4. 如加密（Encrypt Algo == 2）：AES-256-CBC 解密（需传入 IV，无认证标签）
5. 比对 SHA256 哈希（完整性验证）
6. 有签名？→ 验证签名（来源验证，按 Sig Algo）
7. 无签名？→ 跳步骤 6（仅加密无签名模式）
8. 校验通过后跳转执行（或复制到执行分区）
```

### 仅加密模式（Encrypt Only, No Signature）

用于低成本量产场景：固件只加密不签名，防止静态分析/反编译，
但不具备来源验证（无法防止伪造固件被加载）。

**适用场景**：
- 低成本消费电子产品，无公钥基础设施
- 防止竞品直接读 Flash 克隆固件
- 已有 AES-256 硬编码 Key 的存量 Bootloader（不支持签名验证）
- 资源受限 MCU（Cortex-M0/M0+），签名验证开销大

**安全等级**：
```
仅加密(CBC)        <  加密+Hash      <  加密+Hash+签名
防止静态分析          完整性验证         来源验证+防篡改
```

**Bootloader 仅加密验证代码**：
```c
/* AES-256-CBC 解密 — 标准 STM32 Bootloader 常用模式 */
bool OTA_Decrypt_Only(uint8_t *pkg, uint32_t total_len,
                       uint8_t *key, uint8_t *iv)
{
    OTA_Header_t *hdr = (OTA_Header_t *)pkg;
    if (hdr->magic != 0x46574442) return false;

    uint8_t *payload = pkg + sizeof(OTA_Header_t);
    uint32_t payload_len = total_len - sizeof(OTA_Header_t);

    // AES-256-CBC 解密（STM32 硬件加密或软件 AES 库）
    AES_CBC_Decrypt(payload, payload_len, key, iv);

    // 可选：CRC 校验
    uint32_t crc = CRC32_Calc(payload, hdr->fw_size);
    if (crc != hdr->crc32) return false;

    return true;
}
```

## 执行流程

### Step 1 验证输入文件 → Step 2 计算哈希 → Step 3 签名/加密 → Step 4 打包固件头 → Step 5 输出报告 + Bootloader 代码

## 密钥生成参考
```bash
# ECDSA P-256（推荐，快速，安全）
openssl ecparam -name prime256v1 -genkey -noout -out private_ecdsa_p256.pem
openssl ec -in private_ecdsa_p256.pem -pubout -out public_ecdsa_p256.pem

# ECDSA P-384
openssl ecparam -name secp384r1 -genkey -noout -out private_ecdsa_p384.pem
openssl ec -in private_ecdsa_p384.pem -pubout -out public_ecdsa_p384.pem

# RSA-2048
openssl genpkey -algorithm RSA -out private_rsa2048.pem -pkeyopt rsa_keygen_bits:2048
openssl rsa -in private_rsa2048.pem -pubout -out public_rsa2048.pem

# RSA-4096
openssl genpkey -algorithm RSA -out private_rsa4096.pem -pkeyopt rsa_keygen_bits:4096
openssl rsa -in private_rsa4096.pem -pubout -out public_rsa4096.pem

# Ed25519（最现代，极快）
openssl genpkey -algorithm ED25519 -out private_ed25519.pem
openssl pkey -in private_ed25519.pem -pubout -out public_ed25519.pem

# AES-256 密钥（hex）
openssl rand -hex 32 > aes256.key

# AES-256-CBC IV（16 字节 = 32 hex 字符）
openssl rand -hex 16 > aes256_cbc_iv.hex

# 或者一次性生成 Key + IV（CBC 模式）
python -c "import os; print('Key:', os.urandom(32).hex()); print('IV:', os.urandom(16).hex())"
```

## 错误处理
| 错误 | 解决方案 |
|------|---------|
| 私钥文件不存在 | 提供密钥生成命令 |
| cryptography 未安装 | `pip install cryptography` |
| 固件文件是 .elf | 用 objcopy 转 .bin：`arm-none-eabi-objcopy -O binary firmware.elf firmware.bin` |
| 验签失败 | 确认公私钥匹配，检查固件是否被修改 |
| RSA 签名过大 | header_size 自动扩展，或手动设置更大的值 |
| AES 密钥格式错误 | 密钥为 64 字符 hex 字符串 |
| AES-CBC IV 缺失 | CBC 模式必须提供 32 hex 字符的 IV（16 字节），可用 `openssl rand -hex 16` 生成 |
| AES-CBC 与 Bootloader 解密不一致 | 确认两端使用相同的 AES 实现（软件 lib / 硬件 CRYP 外设）、相同的 Key/IV 字节序 |
| 仅加密模式使用错误的包头 | 仅加密模式无需 Signature 字段，确认 Bootloader 解析时跳过了签名检查 |

## 安全注意
- 私钥文件严禁提交到版本控制系统（.gitignore）
- 量产环境建议使用 HSM 硬件安全模块保管私钥
- 不同产品批次应使用不同密钥
- AES 密钥应通过安全通道分发，不应硬编码在固件中
- Bootloader 中的公钥建议存储在写保护区域
- 仅加密（无签名）模式不防篡改，只防静态分析——攻击者可替换加密数据导致解密出错误固件

### 硬编码密钥的妥协与缓解措施

> 实际量产中，AES 密钥硬编码在 Bootloader 固件中是常见做法（尤其是无 HSM、无安全存储的低成本 MCU）。
> 完全不允许硬编码在工程层面是不现实的，应提供分级缓解方案。

| 级别 | 措施 | 防护效果 | 实现成本 |
|------|------|---------|---------|
| 基本 | Key 分散在多个 .c 文件中，用宏拼接 | 防止简单串口/strings 提取 | 低 |
| 中等 | Key 做 XOR/ROT 混淆，运行时还原 | 需要反汇编才能提取 | 中 |
| 进阶 | Key 存放在 Option Bytes 或 OTP 区域 | 离线提取需解密 Flash | 高 |
| 最高 | 使用 STM32 CRYP 硬件加解密，密钥仅存储在 CRYP 寄存器 | 无法软件提取密钥 | 高（需硬件支持） |

```c
/* 基本混淆示例：避免 Key 以明文字符串出现在 .rodata 中 */
#define KEY_PART1 0x31323132
#define KEY_PART2 0x31323132
#define KEY_PART3 0x31323132
#define KEY_PART4 0x31323132
/* 运行时拼接 */
static void assemble_key(uint8_t *key_out) {
    ((uint32_t *)key_out)[0] = KEY_PART1;
    ((uint32_t *)key_out)[1] = KEY_PART2;
    ((uint32_t *)key_out)[2] = KEY_PART3;
    ((uint32_t *)key_out)[3] = KEY_PART4;
}
```

**注意**：硬编码只能增加提取难度，不能完全防住有 JTAG/SWD 访问权限的攻击者。
真正需要防篡改的产品应使用签名 + 读保护（RDP Level 2 / PCROP）。

## CI/CD 集成
```bash
# 构建后自动签名打包
python firmware_sign.py pack --firmware build/firmware.bin \
    --key private_ecdsa_p256.pem --version 1.2.3 --output release/firmware_v1.2.3_signed.bin

# 同时生成 Bootloader 验签头文件
python firmware_sign.py gen-header --sig-algo ecdsa-p256 --output bootloader/fw_header.h

# 输出 JSON 元数据供 CI 使用
# 自动生成 firmware_v1.2.3_signed.meta.json
```

## 边界定义

### 不该激活
- 用户讨论的是代码签名（code signing）、应用商店签名、TLS 证书，而非**固件**签名
- 用户需要的是 JWT/OAuth Token 签名或区块链交易签名
- 用户只是提到"签名"但上下文是文件版本管理（git tag）、文档签署、邮件签名
- 用户没有固件文件（.bin/.hex/.elf）作为输入，纯概念讨论
- 用户需要的是 AES 加密封装格式的完整 OTA 包（应使用 ota-package skill）

### 不该做
- **严禁**将私钥内容写入日志、终端输出、报告文件或任何非预期输出
- **严禁**在无用户确认的情况下生成新密钥对覆盖已有密钥文件
- **严禁**为不同产品/批次使用相同密钥（应提示用户密钥管理策略）
- **禁止**对未经验证的固件文件签名（应先执行 hash 校验）
- **禁止**以明文方式将 AES 密钥嵌入生成的 Bootloader 头文件
- **仅加密模式**：禁止声称 "secure boot" 或 "防篡改"——仅加密模式不提供篡改保护
- **CBC 模式**：禁止在未提供 IV 的情况下加密——CBC 需要 IV，每次加密应使用随机 IV
- **CBC 模式**：避免使用固定 IV——固定 IV 导致相同明文产生相同密文（ECB 效应的弱化版）

### 不该碰
- **不触碰**系统密钥存储（如 Windows 证书存储、macOS Keychain、HSM）：只读取用户指定的 PEM 文件
- **不触碰**版本控制系统（.gitignore 配置是用户责任）
- **不触碰**远程签名服务（HSM、KMS、Vault 等）：仅本地文件签名
- **不触碰**硬件调试接口：纯软件工具，不连接任何硬件
- **CBC 模式**：不负责 Bootloader 侧 AES 实现的移植（可能用 STM32 CRYP 外设或软件 AES 库，需用户确认）
- **仅加密模式**：不负责将加密固件通过 Ymodem/UART 传输的集成（由 ota-package 覆盖）

## 输出约定

操作完成后输出：
- 生成的签名/加密固件包路径
- 固件哈希值（SHA256/CRC32）
- 签名结果（成功/失败 + 签名算法说明）
- Bootloader 验签头文件路径
- JSON 元数据文件（供 CI/CD 使用）

## 交接关系

- 上游：`build-keil` / `build-cmake`（编译出原始 .bin 后签名）
- 下游：`ota-package`（签名后的固件打包为 OTA 升级包）
- 辅助：`option-bytes`（签名后配合 RDP 保护使用）
- 安全：私钥管理建议使用 HSM，私钥文件严禁提交 git
