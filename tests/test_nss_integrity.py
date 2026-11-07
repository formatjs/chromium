import copy
import gzip
import hashlib
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dsa, utils

from tools.ci.chromium import PLATFORMS, stamp_payload
from tools.ci.compare_payloads import payload_manifest, verified_contents_match
from tools.ci.nss_integrity import MODULES, verify_checksum


def checksum(key, module):
    numbers = key.public_key().public_numbers()
    parameters = numbers.parameter_numbers
    signed = key.sign(hashlib.sha256(module).digest(), utils.Prehashed(hashes.SHA256()))
    r, s = utils.decode_dss_signature(signed)
    items = [parameters.p.to_bytes(256, 'big'), parameters.q.to_bytes(32, 'big'),
             parameters.g.to_bytes(256, 'big'), numbers.y.to_bytes(256, 'big'),
             r.to_bytes(32, 'big') + s.to_bytes(32, 'big')]
    return b'\xf1\xc5\x01\x02' + struct.pack('>II', 12, 1) + b''.join(
        len(item).to_bytes(4, 'big') + item for item in items)


class NssIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = dsa.generate_private_key(2048)
        cls.second = cls.first.parameters().generate_private_key()

    def manifest(self, root, key, *, changed_code=False, changed_module=False,
                 changed_signature=False, changed_mode=False, omitted_checksum=False):
        entries = {'bundle/chrome': b'changed' if changed_code else b'compiled code'}
        for check, module in MODULES.items():
            content = ('compiled ' + module).encode()
            entries[module] = content + b'corruption' if changed_module else content
            entries[check] = checksum(key, content)
            if changed_signature:
                entries[check] = entries[check][:-1] + bytes([entries[check][-1] ^ 1])
        if omitted_checksum:
            del entries[next(iter(MODULES))]
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as archive:
            for name, content in sorted(entries.items()):
                member = tarfile.TarInfo(name)
                member.size = len(content)
                member.mode = 0o755 if changed_mode and name in MODULES else 0o644
                archive.addfile(member, io.BytesIO(content))
        payload = root / 'payload.gz'
        payload.write_bytes(gzip.compress(raw.getvalue(), mtime=0))
        path = stamp_payload(payload, root / 'output', PLATFORMS['linux-amd64'], '1' * 40)
        return {'manifest': payload_manifest(path, verify_nss=True)}

    def test_valid_randomized_signatures_preserve_all_other_tar_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.manifest(root, self.first)
            second = self.manifest(root, self.second)
        self.assertNotEqual(first['manifest']['tar_sha256'], second['manifest']['tar_sha256'])
        self.assertTrue(verified_contents_match(first, second))
        self.assertEqual(len(first['manifest']['nss_integrity']), 4)

    def test_module_signature_and_missing_file_corruption_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for change in ('changed_module', 'changed_signature', 'omitted_checksum'):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.manifest(Path(temporary), self.first, **{change: True})

    def test_code_metadata_and_parameter_changes_still_fail_equivalence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = self.manifest(root, self.first)
            for change in ('changed_code', 'changed_mode'):
                second = self.manifest(root, self.second, **{change: True})
                self.assertFalse(verified_contents_match(first, second))
        altered = copy.deepcopy(first)
        altered['manifest']['nss_integrity'][next(iter(MODULES))]['parameters_sha256'] = '0' * 64
        self.assertFalse(verified_contents_match(first, altered))

    def test_invalid_checksum_encoding_is_rejected(self):
        data = checksum(self.first, b'module')
        for invalid in (data[:10], data + b'extra', data[:12] + b'\xff' * 4 + data[16:]):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                verify_checksum(invalid, hashlib.sha256(b'module').hexdigest())
