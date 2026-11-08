import copy
from contextlib import redirect_stderr
import io
from pathlib import Path
import struct
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from tools.ci.llvm_elf import compare_relinked_compiler
from tools.ci.prepare_llvm_bolt import compiler_actions, verify_relocation_actions


def executable():
    """Small ELF with mapped headers, code, build ID and nonloaded symbols."""
    data = bytearray(1536)
    names = b'\0.text\0.note.gnu.build-id\0.shstrtab\0.symtab\0.rela.text\0'
    data[:64] = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01' + bytes(9),
                           2, 62, 1, 0x400100, 64, 1024, 0, 64, 56, 2, 64, 6, 3)
    data[64:120] = struct.pack('<IIQQQQQQ', 1, 5, 0, 0x400000, 0x400000, 512, 512, 4096)
    data[120:176] = struct.pack('<IIQQQQQQ', 0x6474e551, 6, 0, 0, 0, 0, 0, 16)
    data[256:260] = b'\x31\xc0\xc3\x90'
    data[288:324] = struct.pack('<III', 4, 20, 3) + b'GNU\0' + bytes(range(20))
    data[512:512 + len(names)] = names
    rows = [(0,) * 10,
            (names.index(b'.text'), 1, 6, 0x400100, 256, 4, 0, 0, 16, 0),
            (names.index(b'.note'), 7, 2, 0x400120, 288, 36, 0, 0, 4, 0),
            (names.index(b'.shstrtab'), 3, 0, 0, 512, len(names), 0, 0, 1, 0),
            (names.index(b'.symtab'), 2, 0, 0, 768, 24, 3, 0, 8, 24),
            (names.index(b'.rela.text'), 4, 0, 0, 800, 24, 4, 1, 8, 24)]
    for i, row in enumerate(rows):
        data[1024 + i * 64:1088 + i * 64] = struct.pack('<IIQQQQIIQQ', *row)
    return data


class CompilerRelocationTest(unittest.TestCase):
    def compare(self, original, updated):
        with tempfile.TemporaryDirectory() as temporary:
            before, after = Path(temporary) / 'before', Path(temporary) / 'after'
            before.write_bytes(original)
            after.write_bytes(updated)
            return compare_relinked_compiler(before, after)

    def test_only_nonloaded_metadata_and_build_id_may_change(self):
        original = executable()
        updated = bytearray(original)
        updated[310] ^= 1  # GNU build ID descriptor.
        updated[768] ^= 1  # Nonloaded symbol table.
        result = self.compare(original, updated)
        self.assertTrue(result['loaded_code_data_bytes_match'])
        self.assertTrue(result['build_id_changed'])
        self.assertTrue(result['symbol_table_present'])
        self.assertEqual(result['text_relocation_sections'], ['.rela.text'])

    def test_loaded_code_padding_stack_permissions_and_note_header_are_protected(self):
        original = executable()
        for name, offset in [('code', 256), ('padding', 400), ('stack', 124), ('note', 288)]:
            with self.subTest(name=name):
                updated = bytearray(original)
                updated[offset] ^= 1
                with self.assertRaises(ValueError):
                    self.compare(original, updated)

    def test_truncated_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ELF range'):
            self.compare(executable(), executable()[:1100])

    def test_query_diagnostics_reject_partial_inventory_even_with_zero_exit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.compiler-preparation').mkdir()

            def failed_formatter(command, **kwargs):
                kwargs['stdout'].write('[]\n')
                kwargs['stderr'].write("ERROR: Starlark evaluation error: target lacks actions\n")
                return subprocess.CompletedProcess(command, 0)

            with patch('tools.ci.prepare_llvm_bolt.ROOT', root), patch(
                    'tools.ci.prepare_llvm_bolt.subprocess.run', side_effect=failed_formatter):
                error = io.StringIO()
                with redirect_stderr(error), self.assertRaisesRegex(ValueError, 'LLVM compiler action query failed'):
                    compiler_actions(['bazel'], [], root, 'baseline')
                self.assertIn('target lacks actions', error.getvalue())

    def test_compile_commands_and_environment_must_survive_relink(self):
        before = {('CppCompile', ('compiler.o',)): (['clang++', '-c', 'compiler.cpp'], {'LANG': 'C'}),
                  ('CppLink', ('llvm',)): (['clang++', 'compiler.o', '-o', 'llvm'], {'LANG': 'C'})}
        valid = copy.deepcopy(before)
        valid[('CppLink', ('llvm',))][0].insert(1, '-Wl,--emit-relocs')
        self.assertEqual(verify_relocation_actions(before, valid)['changed_link_actions'], ['CppLink'])
        for name in ['compile', 'environment', 'other_link_option', 'missing', 'no_relink']:
            with self.subTest(name=name):
                updated = copy.deepcopy(valid)
                if name == 'compile':
                    updated[('CppCompile', ('compiler.o',))][0].append('-march=native')
                elif name == 'environment':
                    updated[('CppLink', ('llvm',))][1]['LANG'] = 'en_US'
                elif name == 'other_link_option':
                    updated[('CppLink', ('llvm',))][0].append('-Wl,--icf=all')
                elif name == 'missing':
                    del updated[('CppCompile', ('compiler.o',))]
                else:
                    updated = before
                with self.assertRaises(ValueError):
                    verify_relocation_actions(before, updated)


if __name__ == '__main__':
    unittest.main()
