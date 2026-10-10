import base64
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from license_public_key import PUBLIC_KEY_HEX


def encode(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def verify(code, machine):
    payload, signature = ''.join(code.split()).split('.')
    raw = base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))
    sig = base64.urlsafe_b64decode(signature + '=' * (-len(signature) % 4))
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(sig, raw)
    data = json.loads(raw)
    if data.get('v') != 1 or data.get('machine') != machine or data.get('kind') not in ('day', 'permanent') or not isinstance(data.get('id'), str):
        raise ValueError('Invalid activation')
    return data
