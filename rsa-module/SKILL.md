---
name: rsa-module
description: |
  RSA 非对称加密开发指南。覆盖 RSA 算法原理、密钥生成与存储、
  签名验签流程（RSASSA-PKCS1-v1_5/PSS）、加密解密（OAEP）、
  mbedTLS RSA 实现、STM32 CRYP 硬件 RSA 加速、密钥长度与性能权衡、
  证书 X.509 解析、与 AES 结合的混合加密方案。
  当用户提到 RSA、非对称加密、公钥加密、数字签名、签名验签、
  RSA-2048、RSA-4096、私钥管理、公钥分发、X.509 证书、
  mbedTLS RSA、CRYP RSA、安全启动、Secure Boot 签名时使用。
version: "1.0.0"
---

# RSA 非对称加密开发指南

## 适用场景

- 需要在嵌入式 Bootloader 中验证固件签名（Secure Boot）
- 需要对固件包进行数字签名和验签
- 需要实现 RSA + AES 混合加密（RSA 加密 AES Key）
- 需要解析 X.509 证书中的 RSA 公钥
- 需要评估 RSA 密钥长度（2048/4096）在 MCU 上的性能

## 必要输入

| 参数 | 说明 |
|------|------|
| 密钥长度 | RSA-2048 / RSA-3072 / RSA-4096 |
| 操作类型 | 签名(Sign) / 验签(Verify) / 加密(Encrypt) / 解密(Decrypt) |
| 填充模式 | PKCS1-v1_5 / PSS(签名) / OAEP(加密) |
| 密钥来源 | PEM 文件 / DER 数组 / HSM |

## RSA 核心概念

### 密钥对

```
私钥 (Private Key): (n, d)   ← 存储安全区，用于签名/解密
公钥 (Public Key):  (n, e)   ← 分发到设备，用于验签/加密

RSA-2048: n = 2048 位 = 256 字节
RSA-4096: n = 4096 位 = 512 字节
```

### 签名验签流程

```
签名端（服务器）                    验签端（设备 Bootloader）
  │                                      │
  │  1. SHA256(firmware.bin) = hash      │
  │  2. RSA 签名(hash, 私钥) = sig       │
  │  3. 打包 firmware.bin + sig           │
  │     ─────────────────────────────────>│
  │                                      │  4. 提取 sig
  │                                      │  5. SHA256(firmware.bin) = hash
  │                                      │  6. RSA 验签(hash, sig, 公钥)
  │                                      │  7. 匹配 → 启动 / 不匹配 → 拒绝
```

## mbedTLS RSA 实现

### Bootloader 验签

```c
#include "mbedtls/rsa.h"
#include "mbedtls/pk.h"
#include "mbedtls/sha256.h"

int verify_firmware_signature(const uint8_t *fw, uint32_t fw_len,
                               const uint8_t *signature, uint32_t sig_len)
{
    int ret;
    mbedtls_pk_context pk;
    mbedtls_sha256_context sha;

    // 1. 初始化公钥上下文
    mbedtls_pk_init(&pk);

    // 2. 从 DER 数组加载公钥（编译进 Bootloader）
    ret = mbedtls_pk_parse_public_key(&pk, pubkey_der, pubkey_der_len);
    if (ret != 0) return -1;

    // 3. 计算固件哈希
    uint8_t hash[32];
    mbedtls_sha256_init(&sha);
    mbedtls_sha256_starts(&sha, 0);
    mbedtls_sha256_update(&sha, fw, fw_len);
    mbedtls_sha256_finish(&sha, hash);
    mbedtls_sha256_free(&sha);

    // 4. RSA 验签 (PKCS1-v1_5 + SHA256)
    ret = mbedtls_pk_verify(&pk, MBEDTLS_MD_SHA256, hash, 0,
                            signature, sig_len);

    mbedtls_pk_free(&pk);
    return (ret == 0) ? 0 : -1;
}
```

### 各平台 RSA 性能参考 (RSA-2048 验签)

| MCU | 频率 | 验签时间 | 备注 |
|-----|------|---------|------|
| STM32F103 | 72MHz | ~450ms | 纯软件 |
| STM32F411 | 100MHz | ~280ms | 纯软件 |
| STM32H743 | 480MHz | ~40ms | 纯软件 |
| STM32L4+CRYP | 120MHz | ~5ms | 硬件加速 |
| ESP32 | 240MHz | ~60ms | 软件 mbedTLS |
| ESP32-S3 | 240MHz | ~35ms | 软件 + HMAC 加速 |

## RSA vs ECDSA 选型

| 维度 | RSA-2048 | ECDSA P-256 |
|------|----------|-------------|
| 密钥长度 | 256 字节 | 32 字节 |
| 签名长度 | 256 字节 | 64 字节 |
| 验签速度 | 慢 | 快(约 10x) |
| 签名速度 | 很慢 | 快 |
| 安全等级 | 112-bit | 128-bit |

**建议**：新项目优先选 ECDSA P-256（`firmware-sign` skill 默认使用）。

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 验签失败(-0x4400) | 公钥/签名不匹配 | 核对公私钥对，确认签名算法 |
| PK 解析失败 | PEM/DER 格式错误 | 确认公钥格式正确 |
| MBEDTLS_ERR_RSA_INVALID_PADDING | 填充格式不匹配 | 签名用 PKCS1-v1_5 或 PSS，与签名端一致 |
| RSA 操作超时(MCU) | 计算量过大 | RSA-4096 在某些 MCU 上可能超时，改 ECDSA |

## 边界定义

- **不覆盖** ECDSA/Ed25519 签名算法 → 使用 `firmware-sign`
- **不覆盖** TLS/SSL 协议栈中的 RSA 证书链验证
- **不覆盖** HSM 硬件安全模块的集成（PKCS#11 接口）
- RSA-1024 已不安全，不使用
- **不覆盖** 密钥对生成（在安全服务器上离线生成）

## 交接关系

- 上游：`firmware-sign`（固件签名/验签的主入口，整合 RSA/ECDSA）
- 上游：`option-bytes`（签名后配置 RDP/PCROP 保护密钥）
- 互补：`aes-module`（RSA + AES 混合加密：RSA 加密 AES Key）
- 参考：`chip-architecture`（硬件 RSA 加速选型）
