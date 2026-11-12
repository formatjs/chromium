from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1] / 'overlays/chromium/bcr/overlay/native'


class SharedPrefixScopeTest(unittest.TestCase):
    def environment(self, repository):
        def fail(message):
            raise ValueError(message)

        return {
            'load': lambda *args, **kwargs: None,
            'Label': lambda value: SimpleNamespace(
                repo_name='chromium' if value.startswith('@chromium//') else repository),
            'native': SimpleNamespace(
                package_relative_label=lambda value: SimpleNamespace(repo_name=repository, package='native'),
                existing_rule=lambda name: None),
            'rule': lambda **kwargs: None,
            'attr': SimpleNamespace(label=lambda **kwargs: None, string=lambda: None),
            'ORIGINAL_PRODUCERS': {'bind': 'base_bind_complete_pch'},
            'SDK_OWNERS': {},
            'SHARED_PREFIX_IMPORTS': {'owner': {'source.cc': ':qualified_pch'}},
            'fail': fail,
        }

    def test_cross_repositories_do_not_declare_host_prefixes_or_route_imports(self):
        for repository in ['chromium_linux_arm64', 'chromium_darwin_arm64',
                           'chromium_windows_amd64', 'chromium_windows_arm64']:
            with self.subTest(repository=repository):
                environment = self.environment(repository)
                exec((ROOT / 'shared_prefixes.bzl').read_text(), environment)
                environment['shared_prefixes']()
                exec((ROOT / 'shared_prefix_imports.bzl').read_text(), environment)
                self.assertEqual(environment['qualified_shared_imports']('owner'), {})

    def test_host_retains_qualified_imports_and_missing_producer_validation(self):
        environment = self.environment('chromium')
        exec((ROOT / 'shared_prefixes.bzl').read_text(), environment)
        with self.assertRaisesRegex(ValueError, 'Missing original prefix producer: base_bind_complete_pch'):
            environment['shared_prefixes']()
        exec((ROOT / 'shared_prefix_imports.bzl').read_text(), environment)
        self.assertEqual(environment['qualified_shared_imports']('owner'),
                         {'source.cc': ':qualified_pch'})
