#!/usr/bin/env python3
"""
firmware-sign: 嵌入式固件签名、加密与安全打包工具
支持 ECDSA/RSA/Ed25519 签名、AES-256-GCM 加密、固件头打包、
Bootloader 验签代码生成、版本注入、CI/CD 元数据输出
"""
import argparse
import hashlib
import struct
import sys
import os
import json
import time
import binascii
from datetime import datetime

# ── 常量 ──────────────────────────────────────────────
MAGIC = 0x46574442  # "FWDB"
HEADER_VERSION = 2

SIG_ALGO_MAP = {
    "ecdsa-p256": 1,
    "ecdsa-p384": 2,
    "rsa-2048":   3,
    "rsa-4096":   4,
    "ed25519":    5,
}
SIG_ALGO_REVERSE = {v: k for k, v in SIG_ALGO_MAP.items()}
ENCRYPT_ALGO_MAP = {"none": 0, "aes-256-gcm": 1}
ENCRYPT_ALGO_REVERSE = {v: k for k, v in ENCRYPT_ALGO_MAP.items()}


# ── 工具函数 ──────────────────────────────────────────
def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha384(data: bytes) -> bytes:
    return hashlib.sha384(data).digest()


def sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


HASH_FUNCS = {
    "sha256": sha256,
    "sha384": sha384,
    "sha512": sha512,
    "sha3_256": sha3_256,
}


def load_firmware(path: str) -> bytes:
    if not os.path.exists(path):
        print(f"错误：固件文件不存在: {path}")
        sys.exit(1)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".elf", ".axf", ".out"):
        print(f"警告：检测到 {ext} 文件，建议先用 objcopy 转换为 .bin：")
        print(f"  arm-none-eabi-objcopy -O binary {path} {os.path.splitext(path)[0]}.bin")
        print(f"  然后使用 .bin 文件重新运行")
        sys.exit(1)
    if ext == ".hex":
        print("提示：检测到 .hex 文件，将作为原始数据处理")
    with open(path, "rb") as f:
        return f.read()


def save_file(path: str, data: bytes):
    with open(path, "wb") as f:
        f.write(data)
    print(f"[firmware-sign] 已保存: {path} ({len(data):,} 字节)")


def parse_version(ver: str) -> int:
    parts = ver.split(".")
    if len(parts) != 3:
        print(f"错误：版本号格式应为 x.y.z，收到: {ver}")
        sys.exit(1)
    return (int(parts[0]) << 16) | (int(parts[1]) << 8) | int(parts[2])


# ── 操作实现 ──────────────────────────────────────────

def do_hash(firmware_path: str, algorithm: str):
    data = load_firmware(firmware_path)
    print(f"\n{'═'*42}")
    print(f"  固件哈希信息")
    print(f"{'═'*42}")
    print(f"  文件    : {firmware_path}")
    print(f"  大小    : {len(data):,} 字节")
    for algo_name, func in HASH_FUNCS.items():
        if algorithm in (algo_name, "all"):
            h = func(data).hex()
            print(f"  {algo_name.upper():8s}: {h}")
    if algorithm in ("crc32", "all"):
        print(f"  {'CRC32':8s}: 0x{crc32(data):08X}")
    print(f"{'═'*42}\n")


def do_sign(firmware_path: str, key_file: str, sig_algo: str, output: str):
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
    except ImportError:
        print("错误：请先安装 cryptography 库: pip install cryptography")
        sys.exit(1)

    data = load_firmware(firmware_path)
    with open(key_file, "rb") as f:
        pem_data = f.read()

    password = os.environ.get("FW_SIGN_KEY_PASSWORD")
    if password:
        password = password.encode()
    else:
        password = None

    private_key = serialization.load_pem_private_key(pem_data, password=password)
    sig_hash = sha256(data).hex()

    if sig_algo == "ecdsa-p256":
        signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    elif sig_algo == "ecdsa-p384":
        signature = private_key.sign(data, ec.ECDSA(hashes.SHA384()))
    elif sig_algo == "rsa-2048":
        signature = private_key.sign(data, hashes.SHA256())
    elif sig_algo == "rsa-4096":
        signature = private_key.sign(data, hashes.SHA512())
    elif sig_algo == "ed25519":
        signature = private_key.sign(data)
    else:
        print(f"错误：不支持的签名算法: {sig_algo}")
        sys.exit(1)

    print(f"\n{'═'*42}")
    print(f"  固件签名结果")
    print(f"{'═'*42}")
    print(f"  原始固件  : {firmware_path} ({len(data):,} 字节)")
    print(f"  SHA256    : {sig_hash}")
    print(f"  CRC32     : 0x{crc32(data):08X}")
    print(f"  签名算法  : {sig_algo}")
    print(f"  签名大小  : {len(signature)} 字节")
    print(f"  状态      : ✅ 签名成功")
    print(f"{'═'*42}\n")

    sig_path = output or (os.path.splitext(firmware_path)[0] + ".sig")
    save_file(sig_path, signature)


def aes_gcm_encrypt(plaintext: bytes, key_hex: str) -> tuple:
    """返回 (ciphertext, nonce, tag)"""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        print("错误：AES-GCM 需要 cryptography 库")
        sys.exit(1)

    if os.path.exists(key_hex):
        with open(key_hex, "r") as f:
            key_hex = f.read().strip()
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        print(f"错误：AES-256 密钥应为 32 字节（64 hex），实际 {len(key)} 字节")
        sys.exit(1)

    import secrets
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def do_encrypt(firmware_path: str, aes_key: str, output: str):
    """AES-256-GCM 加密固件（用于安全存储/传输）"""
    data = load_firmware(firmware_path)
    ciphertext, nonce = aes_gcm_encrypt(data, aes_key)

    # 打包：Nonce(12) + Ciphertext
    encrypted = nonce + ciphertext
    out_path = output or (os.path.splitext(firmware_path)[0] + "_encrypted.bin")
    save_file(out_path, encrypted)

    print(f"\n{'═'*42}")
    print(f"  固件加密结果 (AES-256-GCM)")
    print(f"{'═'*42}")
    print(f"  原始大小  : {len(data):,} 字节")
    print(f"  加密后    : {len(encrypted):,} 字节 (Nonce 12 + CT {len(ciphertext)} + Tag 16)")
    print(f"  输出文件  : {out_path}")
    print(f"  状态      : ✅ 加密成功")
    print(f"{'═'*42}\n")


def do_pack(firmware_path: str, output: str, header_size: int,
            key_file: str = None, sig_algo: str = "ecdsa-p256",
            aes_key: str = None, version: str = "0.0.0"):
    """打包固件：生成带头部的完整安全固件包"""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        has_crypto = True
    except ImportError:
        has_crypto = False

    data = load_firmware(firmware_path)
    fw_size = len(data)
    fw_crc32 = crc32(data)
    fw_sha256 = sha256(data)
    ver_int = parse_version(version)

    # ── 签名 ──
    signature = b""
    sig_algo_byte = 0
    if key_file and has_crypto:
        with open(key_file, "rb") as f:
            pem_data = f.read()
        password = os.environ.get("FW_SIGN_KEY_PASSWORD")
        private_key = serialization.load_pem_private_key(
            pem_data, password=password.encode() if password else None
        )
        if sig_algo == "ecdsa-p256":
            signature = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
        elif sig_algo == "ecdsa-p384":
            signature = private_key.sign(data, ec.ECDSA(hashes.SHA384()))
        elif sig_algo == "rsa-2048":
            signature = private_key.sign(data, hashes.SHA256())
        elif sig_algo == "rsa-4096":
            signature = private_key.sign(data, hashes.SHA512())
        elif sig_algo == "ed25519":
            signature = private_key.sign(data)
        sig_algo_byte = SIG_ALGO_MAP.get(sig_algo, 0)

    # ── 加密 ──
    encrypt_algo_byte = 0
    aes_nonce = b""
    aes_tag = b""
    payload = data
    if aes_key and has_crypto:
        if os.path.exists(aes_key):
            with open(aes_key, "r") as f:
                aes_key = f.read().strip()
        key = bytes.fromhex(aes_key)
        import secrets
        aes_nonce = secrets.token_bytes(12)
        aesgcm = AESGCM(key)
        payload = aesgcm.encrypt(aes_nonce, data, None)
        # GCM tag is the last 16 bytes of ciphertext
        aes_tag = payload[-16:]
        payload = payload[:-16]  # ciphertext without tag
        encrypt_algo_byte = 1
        fw_size = len(payload)  # update size to ciphertext size

    # ── 构造固件头 ──
    header = struct.pack(
        ">IHBB",  # Magic(4) + HeaderVer(2) + SigAlgo(1) + EncryptAlgo(1)
        MAGIC, HEADER_VERSION, sig_algo_byte, encrypt_algo_byte
    )
    header += struct.pack(">I", ver_int)      # Version(4)
    header += struct.pack(">I", fw_size)      # FwSize(4)
    header += struct.pack(">I", crc32(payload if encrypt_algo_byte else data))  # CRC32(4)
    header += sha256(payload if encrypt_algo_byte else data)  # SHA256(32)
    header += struct.pack(">H", len(signature))  # SigLen(2)
    header += signature

    if encrypt_algo_byte:
        header += aes_nonce   # 12 bytes
        header += aes_tag     # 16 bytes
        # 保留加密元数据后剩余空间
        encrypt_meta_end = len(header)

    # 填充至 header_size
    if len(header) > header_size:
        print(f"警告：头部实际大小 {len(header)} B > 指定 header_size={header_size} B，自动扩展")
        header_size = len(header)
    header += b"\xFF" * (header_size - len(header))

    packed = header + payload

    meta = {
        "timestamp": datetime.now().isoformat(),
        "magic": f"0x{MAGIC:08X}",
        "header_version": HEADER_VERSION,
        "sig_algo": sig_algo if sig_algo_byte else "none",
        "encrypt_algo": "aes-256-gcm" if encrypt_algo_byte else "none",
        "version": version,
        "firmware_size_bytes": len(data),
        "packed_size_bytes": len(packed),
        "header_size": header_size,
        "sha256": fw_sha256.hex(),
        "crc32": f"0x{fw_crc32:08X}",
        "signed": bool(sig_algo_byte),
        "encrypted": bool(encrypt_algo_byte),
    }

    out_path = output or (os.path.splitext(firmware_path)[0] + "_packed.bin")
    save_file(out_path, packed)

    # 输出 JSON 元数据
    meta_path = out_path + ".meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"[firmware-sign] 元数据已保存: {meta_path}")

    print(f"\n{'═'*42}")
    print(f"  固件打包报告")
    print(f"{'═'*42}")
    print(f"  原始固件  : {firmware_path} ({len(data):,} 字节)")
    print(f"  版本号    : {version}")
    print(f"  SHA256    : {fw_sha256.hex()}")
    print(f"  CRC32     : 0x{fw_crc32:08X}")
    print(f"  签名      : {'✅ ' + sig_algo if sig_algo_byte else '⬜ 未签名'}")
    print(f"  加密      : {'✅ AES-256-GCM' if encrypt_algo_byte else '⬜ 未加密'}")
    print(f"  头部大小  : {header_size} 字节")
    print(f"  输出文件  : {out_path} ({len(packed):,} 字节)")
    print(f"  状态      : ✅ 打包成功")
    print(f"{'═'*42}\n")


def do_verify(firmware_path: str, pub_key: str, sig_path: str, sig_algo: str = "ecdsa-p256"):
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, rsa, ed25519
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        print("错误：请先安装 cryptography 库: pip install cryptography")
        sys.exit(1)

    data = load_firmware(firmware_path)
    with open(sig_path, "rb") as f:
        signature = f.read()
    with open(pub_key, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())

    try:
        if sig_algo in ("ecdsa-p256", "ecdsa-p384"):
            hash_alg = hashes.SHA256() if sig_algo == "ecdsa-p256" else hashes.SHA384()
            public_key.verify(signature, data, ec.ECDSA(hash_alg))
        elif sig_algo == "ed25519":
            public_key.verify(signature, data)
        else:  # rsa
            hash_alg = hashes.SHA256() if sig_algo == "rsa-2048" else hashes.SHA512()
            public_key.verify(signature, data, hash_alg)
        print(f"✅ 签名验证通过 — {firmware_path}")
    except InvalidSignature:
        print(f"❌ 签名验证失败！固件可能已被篡改: {firmware_path}")
        sys.exit(1)


def do_gen_header(sig_algo: str, encrypt_algo: str, header_size: int, output: str):
    """生成 Bootloader 验签所需的 C 语言头文件"""
    header_code = f'''/**
 * @file fw_header.h
 * @brief 固件包头结构体定义 — 由 firmware-sign 自动生成
 *
 * 签名算法: {sig_algo}
 * 加密算法: {encrypt_algo}
 * 头大小: {header_size} 字节
 * 生成时间: {datetime.now().isoformat()}
 */
#ifndef FW_HEADER_H
#define FW_HEADER_H

#include <stdint.h>

#define FW_HEADER_MAGIC        0x{ MAGIC:08X }U
#define FW_HEADER_VERSION      0x{ HEADER_VERSION:04X }U
#define FW_HEADER_SIZE         { header_size }U

/* 签名算法 */
typedef enum {{
    FW_SIG_NONE      = 0,
    FW_SIG_ECDSA_P256 = 1,
    FW_SIG_ECDSA_P384 = 2,
    FW_SIG_RSA_2048   = 3,
    FW_SIG_RSA_4096   = 4,
    FW_SIG_ED25519    = 5,
}} FW_SigAlgo_t;

/* 加密算法 */
typedef enum {{
    FW_ENC_NONE       = 0,
    FW_ENC_AES256_GCM = 1,
}} FW_EncryptAlgo_t;

/* 固件包头部 (packed) */
typedef struct __attribute__((packed)) {{
    uint32_t magic;              /* { ' ' * 3 }偏移 0x000: Magic "FWDB" */
    uint16_t header_version;     /* { ' ' * 3 }偏移 0x004: 头部格式版本 */
    uint8_t  sig_algo;           /* { ' ' * 3 }偏移 0x006: 签名算法 */
    uint8_t  encrypt_algo;       /* { ' ' * 3 }偏移 0x007: 加密算法 */
    uint32_t fw_version;         /* { ' ' * 3 }偏移 0x008: 固件版本 major<<16|minor<<8|patch */
    uint32_t fw_size;            /* { ' ' * 3 }偏移 0x00C: 固件数据大小 */
    uint32_t crc32;              /* { ' ' * 3 }偏移 0x010: CRC32 校验 */
    uint8_t  sha256[32];         /* { ' ' * 3 }偏移 0x014: SHA256 哈希 */
    uint16_t sig_len;            /* { ' ' * 3 }偏移 0x034: 签名长度 */
    uint8_t  signature[0];       /* { ' ' * 3 }偏移 0x036: 签名数据（可变长）*/
    /* 以下字段仅在 encrypt_algo != 0 时存在 */
    /* uint8_t  aes_nonce[12]; { ' ' * 3 }自 sig_len 后偏移: AES-GCM nonce */
    /* uint8_t  aes_tag[16]; { ' ' * 4 }自 nonce 后偏移: AES-GCM 认证标签 */
    /* uint8_t  reserved[]; { ' ' * 4 }填充至 {header_size} 字节 */
    /* ─ 固件数据起始偏移: {header_size} ─ */
}} FW_Header_t;

/* 固件头大小静态断言 */
_Static_assert(sizeof(FW_Header_t) == 0x36,
    "FW_Header_t base size mismatch, check struct packing");

/*
 * Bootloader 验证流程:
 * 1. 检查 magic == FW_HEADER_MAGIC
 * 2. 如果 encrypt_algo == FW_ENC_AES256_GCM: 用 AES-256-GCM 解密
 * 3. 计算 SHA256(payload) 与 header->sha256 比对
 * 4. 计算 CRC32(payload) 与 header->crc32 比对
 * 5. 如果 sig_algo != FW_SIG_NONE: 用公钥验证签名
 * 6. 校验通过后: 拷贝到执行区 / 直接跳转
 */

#endif /* FW_HEADER_H */
'''
    out_path = output or "fw_header.h"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header_code)
    print(f"[firmware-sign] Bootloader 头文件已生成: {out_path}")


def do_inject_version(firmware_path: str, version: str, offset: int, output: str):
    """将版本号注入固件 .bin 的指定偏移位置"""
    data = bytearray(load_firmware(firmware_path))
    ver_int = parse_version(version)
    if offset + 4 > len(data):
        print(f"错误：偏移 0x{offset:X} 超出固件大小 0x{len(data):X}")
        sys.exit(1)
    struct.pack_into(">I", data, offset, ver_int)
    out_path = output or firmware_path
    save_file(out_path, bytes(data))
    print(f"[firmware-sign] 版本 {version} (0x{ver_int:08X}) 已注入偏移 0x{offset:04X}")


# ── 主入口 ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="嵌入式固件签名、加密与安全打包工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s hash --firmware firmware.bin
  %(prog)s hash --firmware firmware.bin --algorithm all
  %(prog)s sign --firmware firmware.bin --key private_ecdsa_p256.pem --sig-algo ecdsa-p256
  %(prog)s sign --firmware firmware.bin --key private_rsa2048.pem --sig-algo rsa-2048
  %(prog)s pack --firmware firmware.bin --key private_ecdsa_p256.pem --version 1.2.3
  %(prog)s pack --firmware firmware.bin --key private_ecdsa_p256.pem --aes-key aes256.key --version 1.0.0
  %(prog)s encrypt --firmware firmware.bin --aes-key aes256.key
  %(prog)s verify --firmware firmware.bin --pub-key public_ecdsa_p256.pem --sig firmware.bin.sig
  %(prog)s gen-header --sig-algo ecdsa-p256 --output bootloader/fw_header.h
  %(prog)s inject-version --firmware firmware.bin --version 2.1.0 --offset 0x200
        """
    )
    parser.add_argument("operation",
                        choices=["hash", "sign", "verify", "pack", "encrypt", "gen-header", "inject-version"],
                        help="操作类型")
    parser.add_argument("--firmware", required=True, help="固件文件路径 (.bin)")
    parser.add_argument("--algorithm", default="sha256",
                        choices=["sha256", "sha384", "sha512", "sha3_256", "crc32", "all"])
    parser.add_argument("--sig-algo", default="ecdsa-p256",
                        choices=list(SIG_ALGO_MAP.keys()),
                        help="签名算法")
    parser.add_argument("--encrypt-algo", default="none",
                        choices=["none", "aes-256-gcm"],
                        help="加密算法（gen-header 用）")
    parser.add_argument("--key", default=None, help="私钥 PEM 文件路径")
    parser.add_argument("--pub-key", default=None, help="公钥 PEM 文件路径")
    parser.add_argument("--sig", default=None, help="签名文件路径 (verify 用)")
    parser.add_argument("--aes-key", default=None, help="AES-256 密钥 (hex 字符串或文件路径)")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--version", default="0.0.0", help="固件版本号 x.y.z")
    parser.add_argument("--offset", type=lambda x: int(x, 0), default=0x200,
                        help="版本注入偏移 (默认 0x200)")
    parser.add_argument("--header-size", type=int, default=256, help="固件头大小（字节）")
    args = parser.parse_args()

    if args.operation == "hash":
        do_hash(args.firmware, args.algorithm)

    elif args.operation == "sign":
        if not args.key:
            print("错误：sign 操作需要 --key 私钥文件")
            sys.exit(1)
        do_sign(args.firmware, args.key, args.sig_algo, args.output)

    elif args.operation == "verify":
        if not args.pub_key or not args.sig:
            print("错误：verify 操作需要 --pub-key 和 --sig")
            sys.exit(1)
        do_verify(args.firmware, args.pub_key, args.sig, args.sig_algo)

    elif args.operation == "pack":
        do_pack(args.firmware, args.output, args.header_size,
                args.key, args.sig_algo, args.aes_key, args.version)

    elif args.operation == "encrypt":
        if not args.aes_key:
            print("错误：encrypt 操作需要 --aes-key")
            sys.exit(1)
        do_encrypt(args.firmware, args.aes_key, args.output)

    elif args.operation == "gen-header":
        do_gen_header(args.sig_algo, args.encrypt_algo, args.header_size, args.output)

    elif args.operation == "inject-version":
        do_inject_version(args.firmware, args.version, args.offset, args.output)


if __name__ == "__main__":
    main()
