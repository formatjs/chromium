import ast
from pathlib import Path
import unittest


class OverlayCaptureSyntaxTest(unittest.TestCase):
    def test_all_platform_capture_literals_parse(self):
        root = Path(__file__).resolve().parents[1] / 'overlays/chromium'
        for path in sorted(root.rglob('*_sources.bzl')):
            with self.subTest(capture=str(path.relative_to(root))):
                # Captures use Python-compatible literals; this catches broken separators.
                ast.parse(path.read_text(), filename=str(path))
