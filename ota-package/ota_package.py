#!/usr/bin/env python3
"""
ota-package: 嵌入式 OTA 固件包生成与测试工具
支持全量包、差分包(bsdiff)、压缩包(zlib)、分段包(chunked)、
ESP32 native OTA、A/B 分区元数据、内建 HTTP 测试服务器
"""
import argparse
import hashlib
import struct
import sys
import os
import json
import time
import binascii
import zlib
import shutil
from datetime import datetime

# ── 常量 ──────────────────────────────────────────────
MAGIC_OTAP = 0x4F544150  # "OTAP"
MAGIC_CHNK = 0x43484E4B  # "CHNK"
HEADER_SIZE = 64

BOARD_IDS = {
    "esp32":    0x00000001,
    "esp32s3":  0x00000002,
    "esp32c3":  0x00000003,
    "esp32s2":  0x00000004,
    "stm32":    0x00000010,
    "stm32f4":  0x00000011,
    "stm32f7":  0x00000012,
    "stm32h7":  0x00000013,
    "stm32g0":  0x00000014,
    "stm32l4":  0x00000015,
    "generic":  0x0000FFFF,
}

# ── 工具函数 ──────────────────────────────────────────
def crc32(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def crc16(data: bytes) -> int:
    """CRC-16-CCITT (用于 chunk 校验)"""
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def parse_version(version_str: str) -> int:
    parts = version_str.split(".")
    if len(parts) != 3:
        print(f"错误：版本号格式应为 x.y.z，收到: {version_str}")
        sys.exit(1)
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if any(v > 255 or v < 0 for v in (major, minor, patch)):
        print("错误：版本号每部分应在 0~255 之间")
        sys.exit(1)
    return (major << 16) | (minor << 8) | patch


def format_version(ver_int: int) -> str:
    return f"{(ver_int>>16)&0xFF}.{(ver_int>>8)&0xFF}.{ver_int&0xFF}"


def zlib_compress(data: bytes, level: int = 6) -> bytes:
    return zlib.compress(data, level)


def zlib_decompress(data: bytes) -> bytes:
    return zlib.decompress(data)


# ── 签名辅助 ──────────────────────────────────────────
def try_sign(data: bytes, sign_key: str) -> bytes:
    """尝试对数据签名，返回签名数据"""
    if not sign_key:
        return b""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        with open(sign_key, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        return private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    except ImportError:
        print("警告：cryptography 未安装，跳过签名 (pip install cryptography)")
        return b""


# ── 操作实现 ──────────────────────────────────────────

def do_full(firmware: str, version: str, board: str, output_dir: str,
            sign_key: str = None, compress: bool = True):
    """生成全量 OTA 包，可选 zlib 压缩"""
    os.makedirs(output_dir, exist_ok=True)
    with open(firmware, "rb") as f:
        fw_data = f.read()

    payload = fw_data
    flags = 0x0001  # bit0: full package

    # zlib 压缩（仅当压缩后更小时才启用）
    if compress and len(fw_data) > 1024:
        compressed = zlib_compress(fw_data)
        if len(compressed) < len(fw_data):
            payload = compressed
            flags |= 0x0004  # bit2: compressed
            reduction = (1 - len(compressed) / len(fw_data)) * 100
            print(f"[ota-package] zlib 压缩: {len(fw_data):,} → {len(compressed):,} 字节 ({reduction:.1f}% 减小)")
        else:
            print(f"[ota-package] 压缩无效（变大），使用原始数据")

    # 签名
    signature = try_sign(fw_data, sign_key)  # 始终对原始数据签名
    if signature:
        flags |= 0x0010  # bit4: signed

    # 构包头
    ver_int = parse_version(version)
    board_id = BOARD_IDS.get(board.lower(), 0xFFFF)
    timestamp = int(time.time())
    payload_hash = sha256(payload)

    # Magic(4)+Ver(4)+Ts(4)+Size(4)+CRC(4)+Board(4)+Flags(4)=28
    header = struct.pack(">IIIIIII", MAGIC_OTAP, ver_int, timestamp,
                         len(payload), crc32(payload), board_id, flags)
    header += payload_hash  # 32 bytes → total 60
    header += b"\x00" * (HEADER_SIZE - len(header))  # pad to 64

    ota_data = header + payload
    if signature:
        ota_data += struct.pack(">H", len(signature)) + signature

    # 输出
    base = os.path.splitext(os.path.basename(firmware))[0]
    ver_str = version.replace(".", "_")
    out_name = f"{base}_v{ver_str}.ota"
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, "wb") as f:
        f.write(ota_data)

    # 元数据 JSON
    meta = {
        "type": "full",
        "version": version,
        "board": board,
        "board_id": board_id,
        "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
        "original_size": len(fw_data),
        "payload_size": len(payload),
        "ota_size": len(ota_data),
        "compressed": bool(flags & 0x0004),
        "compression_ratio": f"{len(payload)/len(fw_data)*100:.1f}%" if flags & 0x0004 else "100%",
        "signed": bool(signature),
        "sha256": sha256(fw_data).hex(),
        "file": out_name,
    }
    meta_path = os.path.join(output_dir, f"{base}_v{ver_str}.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*46}")
    print(f"  OTA 全量包生成报告")
    print(f"{'═'*46}")
    print(f"  新固件    : {firmware} ({len(fw_data):,} 字节)")
    print(f"  版本号    : {version}")
    print(f"  目标板    : {board} (0x{board_id:08X})")
    print(f"  SHA256    : {meta['sha256'][:40]}...")
    print(f"  压缩      : {'✅ zlib' if flags & 0x0004 else '⬜ 原始'}")
    print(f"  签名      : {'✅ ECDSA-P256' if signature else '⬜ 未签名'}")
    print(f"  输出文件  : {out_path} ({len(ota_data):,} 字节)")
    print(f"  元数据    : {meta_path}")
    print(f"  状态      : ✅ OTA 包生成成功")
    print(f"{'═'*46}\n")


def do_delta(old_fw: str, new_fw: str, version: str, board: str, output_dir: str):
    """生成差分 OTA 包（bsdiff）"""
    try:
        import bsdiff4
    except ImportError:
        print("错误：差分包需要 bsdiff4 库，请安装: pip install bsdiff4")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)
    with open(old_fw, "rb") as f:
        old_data = f.read()
    with open(new_fw, "rb") as f:
        new_data = f.read()

    patch = bsdiff4.diff(old_data, new_data)
    old_hash = sha256(old_data)

    # 构包头（flags bit1: delta）
    ver_int = parse_version(version)
    board_id = BOARD_IDS.get(board.lower(), 0xFFFF)
    timestamp = int(time.time())
    flags = 0x0002
    patch_hash = sha256(patch)

    header = struct.pack(">IIIIIII", MAGIC_OTAP, ver_int, timestamp,
                         len(patch), crc32(patch), board_id, flags)
    header += patch_hash
    header += b"\x00" * (HEADER_SIZE - len(header))

    # 差分元数据区（追加在包头后）：旧固件 SHA256(32) + 新固件 SHA256(32) + 新固件大小(4) + patch 大小(4)
    new_hash = sha256(new_data)
    delta_meta = old_hash + new_hash + struct.pack(">II", len(new_data), len(patch))
    ota_data = header + delta_meta + patch

    base = os.path.splitext(os.path.basename(new_fw))[0]
    ver_str = version.replace(".", "_")
    out_name = f"{base}_v{ver_str}_delta.patch"
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, "wb") as f:
        f.write(ota_data)

    reduction = (1 - len(patch) / len(new_data)) * 100
    meta = {
        "type": "delta",
        "version": version,
        "board": board,
        "old_sha256": old_hash.hex(),
        "new_sha256": new_hash.hex(),
        "old_size": len(old_data),
        "new_size": len(new_data),
        "patch_size": len(patch),
        "ota_size": len(ota_data),
        "reduction": f"{reduction:.1f}%",
        "file": out_name,
    }
    meta_path = os.path.join(output_dir, f"{base}_v{ver_str}_delta.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*46}")
    print(f"  OTA 差分包生成报告")
    print(f"{'═'*46}")
    print(f"  旧固件    : {old_fw} ({len(old_data):,} 字节)")
    print(f"  新固件    : {new_fw} ({len(new_data):,} 字节)")
    print(f"  差分补丁  : {len(patch):,} 字节（体积减小 {reduction:.1f}%）")
    print(f"  输出文件  : {out_path}")
    print(f"  状态      : ✅ 差分包生成成功")
    print(f"{'═'*46}\n")


def do_chunked(firmware: str, version: str, chunk_size: int, output_dir: str):
    """将固件拆分为分段包，适用于大固件分片传输"""
    os.makedirs(output_dir, exist_ok=True)
    with open(firmware, "rb") as f:
        fw_data = f.read()

    total_chunks = (len(fw_data) + chunk_size - 1) // chunk_size
    chunks = []
    for i in range(total_chunks):
        offset = i * chunk_size
        chunk_data = fw_data[offset:offset + chunk_size]
        chunk_header = struct.pack(">IIIH", MAGIC_CHNK, i, total_chunks, len(chunk_data))
        chunk_crc = struct.pack(">H", crc16(chunk_data))
        chunk = chunk_header + chunk_crc + chunk_data
        chunks.append(chunk)

    # 输出各 chunk
    base = os.path.splitext(os.path.basename(firmware))[0]
    for i, chunk in enumerate(chunks):
        out_path = os.path.join(output_dir, f"{base}_chunk_{i:04d}.bin")
        with open(out_path, "wb") as f:
            f.write(chunk)

    # 生成 manifest
    manifest = {
        "type": "chunked",
        "version": version,
        "firmware": os.path.basename(firmware),
        "total_size": len(fw_data),
        "total_chunks": total_chunks,
        "chunk_size": chunk_size,
        "sha256": sha256(fw_data).hex(),
        "crc32": f"0x{crc32(fw_data):08X}",
        "chunks": [
            {"index": i, "offset": i * chunk_size,
             "size": min(chunk_size, len(fw_data) - i * chunk_size),
             "file": f"{base}_chunk_{i:04d}.bin"}
            for i in range(total_chunks)
        ],
        "generated": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(output_dir, f"{base}_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*46}")
    print(f"  分段包生成报告")
    print(f"{'═'*46}")
    print(f"  固件      : {firmware} ({len(fw_data):,} 字节)")
    print(f"  总分片    : {total_chunks}")
    print(f"  分片大小  : {chunk_size} 字节")
    print(f"  输出目录  : {output_dir}/")
    print(f"  清单文件  : {manifest_path}")
    print(f"  状态      : ✅ 分段包生成成功")
    print(f"{'═'*46}\n")


def do_esp32(firmware: str, board: str, output_dir: str):
    """生成 ESP32 原生 OTA 包"""
    os.makedirs(output_dir, exist_ok=True)
    with open(firmware, "rb") as f:
        fw_data = f.read()

    # 验证 ESP image header
    if len(fw_data) < 24:
        print("错误：固件太小，非有效 ESP32 image")
        sys.exit(1)

    esp_magic = fw_data[0]
    if esp_magic != 0xE9:
        print("警告：ESP image magic byte 不匹配，可能非 ESP-IDF 生成")
        print("  继续打包，但建议用 idf.py build 生成的 .bin")

    base = os.path.splitext(os.path.basename(firmware))[0]
    out_path = os.path.join(output_dir, f"{base}_esp32_ota.bin")
    shutil.copy2(firmware, out_path)

    # OTA URL 描述 JSON（esp_https_ota 用）
    ota_json = {
        "version": "1.0.0",
        "chip": board,
        "firmware": f"{base}_esp32_ota.bin",
        "size": len(fw_data),
        "sha256": sha256(fw_data).hex(),
        "generated": datetime.now().isoformat(),
    }
    json_path = os.path.join(output_dir, f"{base}_ota.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ota_json, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*46}")
    print(f"  ESP32 OTA 包生成报告")
    print(f"{'═'*46}")
    print(f"  芯片      : {board}")
    print(f"  固件      : {firmware} ({len(fw_data):,} 字节)")
    print(f"  SHA256    : {ota_json['sha256']}")
    print(f"  OTA 包    : {out_path}")
    print(f"  OTA JSON  : {json_path} (可放置到 HTTP 服务器)")
    print(f"  状态      : ✅ ESP32 OTA 包就绪")
    print(f"{'═'*46}\n")


def do_ab_partition(firmware: str, version: str, active_slot: str, output_dir: str):
    """生成 A/B 分区 OTA 包，含 slot_manifest"""
    os.makedirs(output_dir, exist_ok=True)
    with open(firmware, "rb") as f:
        fw_data = f.read()

    slot = active_slot.upper()
    if slot not in ("A", "B"):
        print("错误：active_slot 必须是 A 或 B")
        sys.exit(1)

    target_slot = "B" if slot == "A" else "A"

    base = os.path.splitext(os.path.basename(firmware))[0]
    slot_file = f"{base}_slot_{target_slot.lower()}.bin"
    out_path = os.path.join(output_dir, slot_file)
    shutil.copy2(firmware, out_path)

    manifest = {
        "partition_scheme": "A/B",
        "active_slot": slot,
        "target_slot": target_slot,
        "version": version,
        "firmware_sha256": sha256(fw_data).hex(),
        "firmware_size": len(fw_data),
        "firmware_file": slot_file,
        "generated": datetime.now().isoformat(),
        "instructions": f"将 {slot_file} 写入 slot_{target_slot.lower()} 分区，验证成功后切换活动槽位",
    }
    manifest_path = os.path.join(output_dir, f"{base}_slot_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'═'*46}")
    print(f"  A/B 分区包生成报告")
    print(f"{'═'*46}")
    print(f"  活动槽位  : Slot {slot}")
    print(f"  目标槽位  : Slot {target_slot}")
    print(f"  版本      : {version}")
    print(f"  固件大小  : {len(fw_data):,} 字节")
    print(f"  输出文件  : {out_path}")
    print(f"  清单      : {manifest_path}")
    print(f"  状态      : ✅ A/B 分区包就绪")
    print(f"{'═'*46}\n")


def do_verify(ota_path: str):
    """验证 OTA 包完整性"""
    with open(ota_path, "rb") as f:
        ota_data = f.read()

    if len(ota_data) < HEADER_SIZE:
        print("错误：OTA 包太小，格式无效")
        sys.exit(1)

    magic, version, timestamp, fw_size, fw_crc, board_id, flags = struct.unpack(
        ">IIIIIII", ota_data[:28]
    )

    if magic != MAGIC_OTAP:
        print(f"❌ Magic 校验失败: 0x{magic:08X} (期望 0x{MAGIC_OTAP:08X})")
        sys.exit(1)

    payload = ota_data[HEADER_SIZE:HEADER_SIZE + fw_size]
    actual_crc = crc32(payload)
    actual_sha = sha256(payload).hex()
    expected_sha = ota_data[28:60].hex()

    print(f"\n{'═'*46}")
    print(f"  OTA 包验证报告")
    print(f"{'═'*46}")
    print(f"  Magic     : ✅ 0x{magic:08X}")
    print(f"  版本号    : {format_version(version)}")
    print(f"  时间戳    : {datetime.fromtimestamp(timestamp)}")
    print(f"  板型 ID   : 0x{board_id:08X}")
    print(f"  类型      : {'差分' if flags & 0x0002 else '全量'}{' (压缩)' if flags & 0x0004 else ''}{' (签名)' if flags & 0x0010 else ''}")

    crc_ok = actual_crc == fw_crc
    sha_ok = actual_sha == expected_sha
    print(f"  CRC32     : {'✅' if crc_ok else '❌'} 0x{actual_crc:08X}")
    print(f"  SHA256    : {'✅' if sha_ok else '❌'} {actual_sha[:40]}...")
    print(f"  整体状态  : {'✅ 验证通过' if (crc_ok and sha_ok) else '❌ 校验失败'}")
    print(f"{'═'*46}\n")


def do_server(firmware: str, output_dir: str, port: int, bind_addr: str):
    """启动内建 HTTP 测试服务器，提供 OTA 固件下载"""
    try:
        from http.server import HTTPServer, SimpleHTTPRequestHandler
    except ImportError:
        print("错误：需要 http.server 模块")
        sys.exit(1)

    # 确保有固件文件可提供
    serve_dir = os.path.abspath(output_dir)
    os.makedirs(serve_dir, exist_ok=True)

    if not os.path.exists(os.path.join(serve_dir, os.path.basename(firmware))):
        shutil.copy2(firmware, serve_dir)

    # 生成 version.json 端点文件
    with open(firmware, "rb") as f:
        fw_data = f.read()
    version_info = {
        "version": "1.0.0",
        "firmware_url": f"http://{bind_addr}:{port}/{os.path.basename(firmware)}",
        "size": len(fw_data),
        "sha256": sha256(fw_data).hex(),
        "force_update": False,
        "min_hardware_version": "1.0",
    }
    with open(os.path.join(serve_dir, "version.json"), "w") as f:
        json.dump(version_info, f, indent=2)

    class OTAHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=serve_dir, **kwargs)

        def log_message(self, format, *args):
            print(f"[OTA-Server] {self.address_string()} - {format % args}")

    server = HTTPServer((bind_addr, port), OTAHandler)
    print(f"\n{'═'*46}")
    print(f"  OTA 测试服务器已启动")
    print(f"{'═'*46}")
    print(f"  地址      : http://{bind_addr}:{port}")
    print(f"  固件      : http://{bind_addr}:{port}/{os.path.basename(firmware)}")
    print(f"  版本接口  : http://{bind_addr}:{port}/version.json")
    print(f"  服务目录  : {serve_dir}")
    print(f"  按 Ctrl+C 停止服务器")
    print(f"{'═'*46}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OTA-Server] 服务器已停止")
        server.server_close()


# ── 主入口 ────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="嵌入式 OTA 固件包生成与测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s full --firmware firmware.bin --version 1.2.3 --board stm32
  %(prog)s full --firmware firmware.bin --version 1.2.3 --board stm32 --no-compress
  %(prog)s delta --firmware v2.0.bin --old-firmware v1.0.bin --board stm32
  %(prog)s chunked --firmware firmware.bin --version 1.0.0 --chunk-size 1024
  %(prog)s esp32 --firmware app.bin --board esp32
  %(prog)s ab-partition --firmware firmware.bin --version 1.3.0 --active-slot A
  %(prog)s server --firmware firmware.bin --port 8070
  %(prog)s verify --firmware firmware_v1_2_3.ota
        """
    )
    parser.add_argument("operation",
                        choices=["full", "delta", "chunked", "esp32", "ab-partition", "server", "verify"],
                        help="操作类型")
    parser.add_argument("--firmware", required=True, help="新版本固件 .bin 路径")
    parser.add_argument("--old-firmware", default=None, help="旧版本固件（delta 必填）")
    parser.add_argument("--version", default="1.0.0", help="固件版本号 x.y.z")
    parser.add_argument("--board", default="generic",
                        choices=list(BOARD_IDS.keys()))
    parser.add_argument("--output", default="ota_output", help="输出目录")
    parser.add_argument("--sign-key", default=None, help="签名私钥 PEM 文件（可选）")
    parser.add_argument("--no-compress", action="store_true", help="禁用 zlib 压缩")
    parser.add_argument("--chunk-size", type=int, default=4096, help="分段大小（默认 4096 字节）")
    parser.add_argument("--active-slot", default="A", help="A/B 分区当前活动槽位")
    parser.add_argument("--port", type=int, default=8070, help="HTTP 测试服务器端口")
    parser.add_argument("--bind", default="0.0.0.0", help="HTTP 测试服务器绑定地址")
    args = parser.parse_args()

    if args.operation == "full":
        do_full(args.firmware, args.version, args.board, args.output,
                args.sign_key, compress=not args.no_compress)
    elif args.operation == "delta":
        if not args.old_firmware:
            print("错误：delta 操作需要 --old-firmware")
            sys.exit(1)
        do_delta(args.old_firmware, args.firmware, args.version, args.board, args.output)
    elif args.operation == "chunked":
        do_chunked(args.firmware, args.version, args.chunk_size, args.output)
    elif args.operation == "esp32":
        do_esp32(args.firmware, args.board, args.output)
    elif args.operation == "ab-partition":
        do_ab_partition(args.firmware, args.version, args.active_slot, args.output)
    elif args.operation == "server":
        do_server(args.firmware, args.output, args.port, args.bind)
    elif args.operation == "verify":
        do_verify(args.firmware)


if __name__ == "__main__":
    main()
