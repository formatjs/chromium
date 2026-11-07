"""Verify NSS 3.61 integrity files without changing runtime signing."""

import hashlib
import struct

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dsa, utils


MODULES = {
    'bundle/lib/lib' + name + '.chk': 'bundle/lib/lib' + name + '.so'
    for name in ('freebl3', 'freeblpriv3', 'nssdbm3', 'softokn3')
}


def verify_checksum(data, module_sha256):
    if len(data) > 4096 or data[:4] != b'\xf1\xc5\x01\x02' or len(data) < 12:
        raise ValueError('Unsupported NSS integrity header')
    offset, key_type = struct.unpack('>II', data[4:12])
    if offset != 12 or key_type != 1:
        raise ValueError('Unsupported NSS integrity key type')
    items, parameters_end = [], 0
    for index in range(5):
        if offset + 4 > len(data):
            raise ValueError('Truncated NSS integrity item')
        length = int.from_bytes(data[offset:offset + 4], 'big')
        offset += 4
        if not 0 < length <= 512 or offset + length > len(data):
            raise ValueError('Invalid NSS integrity item length')
        items.append(data[offset:offset + length])
        offset += length
        if index == 2:
            parameters_end = offset
    if offset != len(data):
        raise ValueError('Trailing NSS integrity data')
    prime, subgroup, generator, public = (int.from_bytes(item, 'big') for item in items[:4])
    if prime.bit_length() != 2048 or subgroup.bit_length() != 256 or len(items[4]) != 64:
        raise ValueError('Unsupported NSS integrity parameters')
    signature = utils.encode_dss_signature(
        int.from_bytes(items[4][:32], 'big'), int.from_bytes(items[4][32:], 'big'))
    key = dsa.DSAPublicNumbers(public, dsa.DSAParameterNumbers(prime, subgroup, generator)).public_key()
    try:
        key.verify(signature, bytes.fromhex(module_sha256), utils.Prehashed(hashes.SHA256()))
    except InvalidSignature:
        raise ValueError('NSS integrity signature does not match module bytes') from None
    return {'verified': True, 'algorithm': 'DSA-SHA256', 'module_sha256': module_sha256,
            'parameters_sha256': hashlib.sha256(data[:parameters_end]).hexdigest()}
