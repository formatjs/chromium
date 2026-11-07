"""Platform patches must not modify shared archives or maintained overlays."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest


class RepositoryPath:
    def __init__(self, path):
        self.path = Path(path)

    def __str__(self):
        return str(self.path)

    @property
    def dirname(self):
        return RepositoryPath(self.path.parent)

    @property
    def basename(self):
        return self.path.name

    @property
    def is_dir(self):
        return self.path.is_dir()

    def get_child(self, child):
        return RepositoryPath(self.path / child)

    def readdir(self):
        return [RepositoryPath(path) for path in self.path.iterdir()]


class SourceProjectionTest(unittest.TestCase):
    def test_excluded_vendor_tree_keeps_archive_and_explicit_overrides(self):
        definition = Path(__file__).resolve().parents[1] / 'build/repositories.bzl'
        function = next(node for node in ast.parse(definition.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == '_sources_impl')
        environment = {'fail': lambda message: self.fail(message)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(definition), 'exec'), environment)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'archive'
            catalog = root / 'workspace/overlays.json'
            overlay = catalog.parent / 'overlays/chromium/bcr/overlay'
            overlay.mkdir(parents=True)
            catalog.write_text('{}')
            relative = 'third_party/protobuf/src/google/protobuf/repeated_field.h'
            original = source / relative
            original.parent.mkdir(parents=True)
            original.write_text('vendored header\n')
            sibling = source / 'third_party/protobuf/README.chromium'
            sibling.write_text('metadata\n')
            untouched = source / 'chrome/renderer/file.cc'
            untouched.parent.mkdir(parents=True)
            untouched.write_text('source\n')
            replacement = overlay / 'third_party/protobuf/src/overlay_marker.h'
            replacement.parent.mkdir(parents=True)
            replacement.write_text('explicit overlay\n')
            output = root / 'projected'
            output.mkdir()

            def symlink(path, name):
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(str(path), target_is_directory=path.is_dir)

            context = SimpleNamespace(
                attr=SimpleNamespace(catalog=catalog, archive=source / '__source__/anchor',
                                     overlay='chromium', variant='', patches=[],
                                     exclude_paths=['third_party/protobuf/src']),
                path=lambda path: RepositoryPath(path), watch_tree=lambda path: None,
                read=lambda path: Path(str(path)).read_text(), symlink=symlink,
            )
            environment['_sources_impl'](context)
            self.assertFalse((output / relative).exists())
            self.assertEqual(original.read_text(), 'vendored header\n')
            self.assertEqual((output / 'third_party/protobuf/README.chromium').read_text(), 'metadata\n')
            self.assertEqual((output / 'third_party/protobuf/src/overlay_marker.h').read_text(), 'explicit overlay\n')
            self.assertTrue((output / 'chrome').is_symlink())

    def test_platform_patch_uses_private_copy_and_preserves_shared_trees(self):
        definition = Path(__file__).resolve().parents[1] / 'build/repositories.bzl'
        function = next(node for node in ast.parse(definition.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == '_sources_impl')
        environment = {'fail': lambda message: self.fail(message)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(definition), 'exec'), environment)
        for overridden in [False, True]:
            with self.subTest(overridden=overridden), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / 'archive'
                catalog = root / 'workspace/overlays.json'
                overlay = catalog.parent / 'overlays/chromium/bcr/overlay'
                overlay.mkdir(parents=True)
                catalog.write_text('{}')
                for variant in ['darwin_arm64', 'windows_arm64']:
                    (catalog.parent / ('overlays/chromium/platforms/' + variant + '/overlay')).mkdir(parents=True)
                relative = 'chrome/browser/ui/startup.cc'
                original = source / relative
                original.parent.mkdir(parents=True)
                original.write_text('before\n')
                untouched = source / 'chrome/browser/ui/resources/value.txt'
                untouched.parent.mkdir(parents=True)
                untouched.write_text('shared\n')
                before = 'before'
                if overridden:
                    maintained = overlay / relative
                    maintained.parent.mkdir(parents=True)
                    maintained.write_text('overlay\n')
                    before = 'overlay'
                patch = root / 'quit.patch'
                patch.write_text(f'--- a/{relative}\n+++ b/{relative}\n@@ -1 +1 @@\n-{before}\n+after\n')
                for variant in ['darwin_arm64', 'windows_arm64']:
                    output = root / variant
                    output.mkdir()

                    def file(name, content, executable=True):
                        target = output / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content)
                        target.chmod(0o755 if executable else 0o644)

                    def symlink(path, name):
                        target = output / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.symlink_to(str(path), target_is_directory=path.is_dir)

                    def apply_patch(path, strip):
                        subprocess.run(['patch', '--batch', f'-p{strip}', '-i', str(path)],
                                       cwd=output, capture_output=True, check=True)

                    context = SimpleNamespace(
                        attr=SimpleNamespace(catalog=catalog, archive=source / '__source__/anchor',
                                             overlay='chromium', variant=variant,
                                             exclude_paths=[],
                                             patches=[patch] if variant == 'darwin_arm64' else []),
                        path=lambda path: RepositoryPath(path), watch_tree=lambda path: None,
                        read=lambda path: Path(str(path)).read_text(),
                        file=file, symlink=symlink, patch=apply_patch,
                    )
                    environment['_sources_impl'](context)
                    result = output / relative
                    self.assertEqual(result.read_text(), 'after\n' if variant == 'darwin_arm64' else before + '\n')
                    if variant == 'darwin_arm64':
                        self.assertFalse(result.is_symlink())
                        self.assertFalse(os.access(result, os.X_OK))
                        self.assertTrue((output / 'chrome/browser/ui/resources').is_symlink())
                self.assertEqual(original.read_text(), 'before\n')
                if overridden:
                    self.assertEqual(maintained.read_text(), 'overlay\n')
