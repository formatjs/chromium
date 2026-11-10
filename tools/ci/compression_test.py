"""Check declared parallel gzip preserves archive contents and determinism."""

import argparse
import gzip
from pathlib import Path
import struct
import tempfile
import unittest

from tools.ci.chromium import PLATFORMS, checksum, package_payload, stamp_payload, unpack


class CompressionTest(unittest.TestCase):
    def test_parallel_payload_roundtrip_matches_serial_for_every_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for target in PLATFORMS.values():
                with self.subTest(platform=target['id']):
                    directory = root / target['id']
                    bundle = directory / 'input'
                    executable = bundle / target['executable']
                    executable.parent.mkdir(parents=True)
                    header = bytearray(128)
                    arm = target['arch'] == 'arm64'
                    if target['os'] == 'linux':
                        header[:6] = b'\x7fELF\x02\x01'
                        struct.pack_into('<H', header, 18, 183 if arm else 62)
                    elif target['os'] == 'darwin':
                        header[:4] = b'\xcf\xfa\xed\xfe'
                        struct.pack_into('<I', header, 4, 0x100000C if arm else 0x1000007)
                    else:
                        header[:2] = b'MZ'
                        struct.pack_into('<I', header, 60, 64)
                        header[64:68] = b'PE\0\0'
                        struct.pack_into('<H', header, 68, 0xAA64 if arm else 0x8664)
                    executable.write_bytes(header)
                    executable.chmod(0o755)
                    data = bytes(range(256)) * 4096
                    (bundle / 'resources.pak').write_bytes(data)
                    serial = package_payload(bundle, directory / 'serial.gz', target)
                    with gzip.open(serial, 'rb') as stream:
                        reference = stream.read()
                    hashes = []
                    for index in range(2):
                        payload = package_payload(bundle, directory / f'parallel-{index}.gz',
                                                  target, compressor=COMPRESSOR)
                        with gzip.open(payload, 'rb') as stream:
                            self.assertEqual(stream.read(), reference)
                        hashes.append(checksum(payload))
                    self.assertEqual(hashes[0], hashes[1])
                    revision = '1' * 40
                    archive = stamp_payload(payload, directory / 'artifacts', target, revision)
                    installed = unpack(archive, directory / 'installed', target, revision)
                    self.assertEqual((installed / target['executable']).read_bytes(), header)
                    self.assertEqual((installed / 'resources.pak').read_bytes(), data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--compressor', type=Path, required=True)
    arguments, remaining = parser.parse_known_args()
    COMPRESSOR = arguments.compressor.resolve(strict=True)
    unittest.main(argv=[__file__, *remaining])
