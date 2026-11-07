import hashlib
import io
import struct
import unittest

from tools.ci.pdb_diagnostics import summarize


class PdbDiagnosticsTest(unittest.TestCase):
    def pdb(self, cwd=b'/buildbuddy-execroot/one', types=b'types'):
        module = bytearray(64)
        struct.pack_into('<H', module, 34, 4)
        module.extend(b'* Linker *\0\0')
        module.extend(b'\0' * (-len(module) % 4))
        dbi = bytearray(64)
        struct.pack_into('<I', dbi, 24, len(module))
        dbi.extend(module)
        streams = [None, b'info', types, dbi, b'cwd\0' + cwd + b'\0exe\0lld-link\0pdb\0chrome.pdb\0']
        data = bytearray(8 * 512)
        data[:32] = b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0'
        directory = struct.pack('<I5I4I', 5, *(0xffffffff if s is None else len(s) for s in streams), 4, 5, 6, 7)
        struct.pack_into('<6I', data, 32, 512, 1, 8, len(directory), 0, 2)
        struct.pack_into('<I', data, 2 * 512, 3)
        data[3 * 512:3 * 512 + len(directory)] = directory
        for page, stream in enumerate(streams[1:], 4):
            data[page * 512:page * 512 + len(stream)] = stream
        return data

    def test_localizes_linker_environment_variation(self):
        before, after = self.pdb(), self.pdb(cwd=b'/buildbuddy-execroot/two')
        a, b = summarize(io.BytesIO(before), len(before)), summarize(io.BytesIO(after), len(after))
        self.assertEqual(a['sha256'], hashlib.sha256(before).hexdigest())
        self.assertNotEqual(a['sha256'], b['sha256'])
        self.assertEqual([k for k in a['streams'] if a['streams'][k] != b['streams'][k]], ['4'])
        self.assertEqual(b['streams']['4']['module'], '* Linker *')
        self.assertEqual(b['streams']['4']['environment_paths']['cwd'], '/buildbuddy-execroot/two')

    def test_type_stream_changes_remain_visible(self):
        before, after = self.pdb(), self.pdb(types=b'changed types')
        a, b = summarize(io.BytesIO(before), len(before)), summarize(io.BytesIO(after), len(after))
        self.assertNotEqual(a['streams']['2']['sha256'], b['streams']['2']['sha256'])
        self.assertEqual(a['streams']['4'], b['streams']['4'])

    def test_rejects_truncation_and_invalid_page_maps(self):
        data = self.pdb()
        with self.assertRaisesRegex(ValueError, 'Truncated PDB'):
            summarize(io.BytesIO(data[:-1]), len(data))
        struct.pack_into('<I', data, 2 * 512, 1000)
        with self.assertRaisesRegex(ValueError, 'page index'):
            summarize(io.BytesIO(data), len(data))


if __name__ == '__main__':
    unittest.main()
