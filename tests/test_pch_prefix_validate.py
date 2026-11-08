import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'overlays/chromium/bcr/overlay/native/pch_prefix_validate.py'
spec = importlib.util.spec_from_file_location('pch_prefix_validate', SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class PrefixValidationTest(unittest.TestCase):
    def test_preserves_include_order_before_source_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prefix = root / 'prefix.h'
            prefix.write_text('#include "a.h"\n#include "b.h"\n')
            source = root / 'source.cc'
            source.write_text('\n#include "a.h"\n\n#include "b.h"\nint value;\n')
            validator.validate(prefix, [source])
            for text in ['#include "b.h"\n#include "a.h"\n',
                         '#define MODE 1\n#include "a.h"\n#include "b.h"\n',
                         '#include "a.h"\n']:
                with self.subTest(text=text):
                    source.write_text(text)
                    with self.assertRaisesRegex(ValueError, 'PCH opening includes changed'):
                        validator.validate(prefix, [source])

    def test_rejects_prefix_with_preprocessor_state(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'prefix.h'
            prefix.write_text('#define MODE 1\n#include "a.h"\n')
            with self.assertRaisesRegex(ValueError, 'only include directives'):
                validator.validate(prefix, [])


if __name__ == '__main__':
    unittest.main()
