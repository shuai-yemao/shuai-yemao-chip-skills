---
name: aes-module
description: |
  AES 加密解密开发指南。覆盖 AES 算法原理（ECB/CBC/GCM/CTR 模式）、
  密钥长度 AES-128/192/256、STM32 CRYP 硬件加密外设配置、
  软件 AES 库移植（mbedTLS/TinyCrypt）、AES-CBC 与固件 OTA 加密、
  硬编码密钥安全风险与缓解、性能基准。
  当用户提到 AES、加密、解密、AES-128、AES-256、AES-CBC、AES-GCM、
  STM32 CRYP、硬件加密、mbedTLS AES、TinyCrypt、OTA 加密、密钥管理、
  固件加密、AES 加速、CRYP 外设 时使用。
version: "1.0.0"
---

# AES 加密解密开发指南

## 适用场景

- 需要在嵌入式设备上对数据进行 AES 加密/解密
- 需要使用 STM32 CRYP 硬件加密外设加速 AES
- 需要移植软件 AES 库（mbedTLS/TinyCrypt）
- 需要为 OTA 固件实现 AES-256-CBC/GCM 加密
- 需要理解 AES 各模式（ECB/CBC/GCM/CTR）的适用场景
- 需要评估 AES 在 MCU 上的性能（吞吐量/时延）

## 必要输入

| 参数 | 说明 |
|------|------|
| AES 模式 | ECB / CBC / GCM / CTR / CCM |
| 密钥长度 | AES-128 / AES-192 / AES-256 |
| 实现方式 | 硬件 CRYP / 软件 mbedTLS / 软件 TinyCrypt |
| 密钥来源 | 固件硬编码 / Flash OTP / 密钥协商派生 |
| IV/Nonce | CBC 需要 16 字节 IV，GCM 需要 12 字节 Nonce |

## AES 模式对比

| 模式 | 安全性 | 并行性 | 密文长度 | 适用场景 |
|------|--------|--------|---------|---------|
| ECB | **不推荐** | 可并行 | 明文对齐 | 仅加密单块密钥 |
| CBC | 高 | 不可并行 | 明文对齐 | 固件加密/文件加密 |
| GCM | 最高(含认证) | 可并行 | 明文+Tag(16B) | 网络传输/安全通信 |
| CTR | 高 | 可并行 | 明文对齐 | 流加密/实时数据 |
| CCM | 高(含认证) | 不可并行 | 明文+Tag | 低功耗无线(IEEE 802.15.4) |

## 平台实现

### STM32 CRYP 硬件 AES（推荐，高性能）

```c
// STM32F4/H7/L4 系列内建 CRYP 硬件外设
// 处理速度可达 ~200MB/s（远快于软件实现）

void aes_cbc_encrypt_hw(uint8_t *plain, uint8_t *cipher, uint32_t len,
                         uint8_t *key, uint8_t *iv)
{
    HAL_CRYP_Init(&hcryp);
    hcryp.Init.KeySize = CRYP_KEYSIZE_256B;  // AES-256
    hcryp.Init.DataType = CRYP_DATATYPE_8B;

    CRYP_ConfigSet(&hcryp, CRYP_AES_CBC, CRYP_KEY_256, CRYP_ENCRYPT);

    // 设置 Key 和 IV
    CRYP_KeyConfig(&hcryp, key, CRYP_KEY_256);
    CRYP_IVConfig(&hcryp, iv);

    // 执行加密（DMA 或轮询）
    CRYP_DataProcess(&hcryp, plain, cipher, len);
}
```

**各系列 CRYP 外设差异**：
| 系列 | CRYP 型号 | 支持模式 | 备注 |
|------|----------|---------|------|
| STM32F4 | CRYP | AES-ECB/CBC/CTR | 无 GCM |
| STM32L4 | CRYP | AES-ECB/CBC/GCM/CCM | 支持认证加密 |
| STM32H7 | CRYP1/CRYP2 | AES-ECB/CBC/GCM/CCM/CTR | 双实例，DMA 支持 |

### mbedTLS 软件 AES（跨平台）

```c
#include "mbedtls/aes.h"

void aes_cbc_encrypt_sw(uint8_t *plain, uint8_t *cipher, uint32_t len,
                         uint8_t *key, uint8_t *iv)
{
    mbedtls_aes_context aes;
    uint8_t iv_copy[16];
    memcpy(iv_copy, iv, 16);  // mbedTLS 会修改 IV

    mbedtls_aes_init(&aes);
    mbedtls_aes_setkey_enc(&aes, key, 256);
    mbedtls_aes_crypt_cbc(&aes, MBEDTLS_AES_ENCRYPT, len, iv_copy, plain, cipher);
    mbedtls_aes_free(&aes);
}
```

### TinyCrypt（轻量，适合小内存 MCU）

```c
#include "tinycrypt/aes.h"

struct tc_aes_key_sched_struct aes_sched;
uint8_t cipher[16], plain[16] = { /* 16字节数据 */ };
uint8_t key[32] = { /* AES-256 密钥 */ };

tc_aes128_set_encrypt_key(&aes_sched, key);
tc_aes_encrypt(cipher, plain, &aes_sched);
```

## 密钥管理

| 方案 | 安全等级 | 适用 |
|------|---------|------|
| 固件硬编码 | 低 | 低成本消费产品 |
| XOR/ROT 混淆 | 中 | 防字符串提取 |
| Option Bytes OTP | 高 | 量产写入不可读 |
| CRYP 密钥寄存器 | 最高 | STM32L4/H7 硬件密钥存储 |

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| CRYP 忙(busy) | 前一次操作未完成 | 等待 CRYP_FLAG_CCF 或使用 DMA |
| 解密结果乱码 | Key/IV 不匹配或模式错误 | 核对双方 Key、IV、模式完全一致 |
| mbedTLS 返回 -0x2700 | 输入长度不是 16 字节倍数 | CBC 模式需 PKCS7 填充 |
| GCM Tag 验证失败 | 密文被篡改或 Key 不对 | 检查 Tag 比较逻辑 |

## 边界定义

- **不覆盖** RSA/ECC 非对称加密 → 使用 `rsa-module`
- **不覆盖** 哈希算法（SHA256/MD5）→ 使用 `crc-module`（CRC 部分）或 mbedTLS
- **不覆盖** TLS/SSL 协议栈 → 使用 `mqtt-module`（MQTT over TLS）
- 密钥安全是系统工程，硬件 AES 不解决密钥泄露问题

## 交接关系

- 上游：`firmware-sign`（固件签名+加密组合使用）
- 上游：`ota-package`（OTA 包 AES 加密）
- 互补：`rsa-module`（AES+RSA 混合加密：RSA 加密 AES Key）
- 互补：`crc-module`（CRC 完整性校验 + AES 加密双重保障）
- 参考：`chip-architecture`（CRYP 硬件支持选型）
