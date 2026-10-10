"""Owner-only command. Private key is never bundled into the customer EXE."""
import argparse
import json
from pathlib import Path
import uuid
from cryptography.hazmat.primitives import serialization
from activation_codes import encode
from license_public_key import PUBLIC_KEY_HEX


def main():
    parser = argparse.ArgumentParser(description='生成绑定机器码的一天续期码或永久激活码')
    parser.add_argument('--machine', required=True, help='客户软件显示的机器码')
    parser.add_argument('--kind', required=True, choices=['day', 'permanent'])
    args = parser.parse_args()
    machine = args.machine.strip().upper()
    if len(machine) != 32 or any(c not in '0123456789ABCDEF' for c in machine):
        parser.error('机器码应为 32 位字母数字，请完整复制')
    path = Path.home() / '.single-payment-admin/signing-key.pem'
    if not path.exists():
        parser.error('本机没有授权私钥，请恢复备份，不能随意生成新私钥')
    key = serialization.load_pem_private_key(path.read_bytes(), None)
    if key.public_key().public_bytes_raw().hex() != PUBLIC_KEY_HEX:
        parser.error('私钥与软件公钥不匹配')
    raw = json.dumps({'v': 1, 'id': uuid.uuid4().hex, 'machine': machine,
                      'kind': args.kind}, separators=(',', ':')).encode()
    print(encode(raw) + '.' + encode(key.sign(raw)))


if __name__ == '__main__':
    main()
