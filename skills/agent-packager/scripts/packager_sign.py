#!/usr/bin/env python3
"""
Sign module: Ed25519 数字签名

功能:
  - run_generate_key: 生成 Ed25519 密钥对
  - sign_package: 对包进行签名
  - verify_signature: 验证签名
"""

import hashlib
import json
import os
import sys


def run_generate_key(args):
    """生成 Ed25519 密钥对"""
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, PublicFormat, NoEncryption
        )
    except ImportError:
        print("[X] 需要安装 cryptography 库：pip install cryptography")
        return 1

    # 生成密钥对
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # 导出私钥
    priv_path = os.path.join(output_dir, "private.pem")
    with open(priv_path, "wb") as f:
        f.write(private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ))
    os.chmod(priv_path, 0o600)  # 仅所有者可读

    # 导出公钥
    pub_path = os.path.join(output_dir, "public.pem")
    with open(pub_path, "wb") as f:
        f.write(public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))

    print(f"    [OK] Ed25519 密钥对已生成")
    print(f"    私钥: {priv_path}  (请妥善保管！)")
    print(f"    公钥: {pub_path}")

    return 0


def sign_package(pkg_path, private_key_path):
    """对 .agentpkg 添加 Ed25519 签名"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
    except ImportError:
        print("[!] 需要 cryptography：pip install cryptography，跳过签名")
        return False

    # 加载私钥
    with open(private_key_path, "rb") as f:
        private_key = load_pem_private_key(f.read(), password=None)

    # 对包文件内容签名
    sha256 = hashlib.sha256()
    with open(pkg_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    digest = sha256.digest()

    # 签名
    signature = private_key.sign(digest)

    # 写入签名文件（与 .agentpkg 同目录，生成 .sig 文件）
    sig_path = pkg_path + ".sig"
    with open(sig_path, "wb") as f:
        f.write(signature)

    print(f"    签名文件: {sig_path}")
    return True


def verify_signature(pkg_path, public_key_path):
    """验证 .agentpkg 的 Ed25519 签名"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
    except ImportError:
        print("[!] 需要 cryptography：pip install cryptography")
        return False

    # 读取签名
    sig_path = pkg_path + ".sig"
    if not os.path.isfile(sig_path):
        print(f"    [X] 签名文件缺失: {sig_path}")
        return False

    with open(sig_path, "rb") as f:
        signature = f.read()

    # 计算包文件 hash
    sha256 = hashlib.sha256()
    with open(pkg_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    digest = sha256.digest()

    # 加载公钥
    with open(public_key_path, "rb") as f:
        public_key = load_pem_public_key(f.read())

    # 验证
    try:
        public_key.verify(signature, digest)
        print("    [OK] Ed25519 签名验证通过")
        return True
    except Exception as e:
        print(f"    [X] 签名验证失败: {e}")
        return False
