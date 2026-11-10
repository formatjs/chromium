#!/usr/bin/env python3
"""Import exact non-generated browser SDK sources and compiler settings."""
import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'chromium/tools'))
from import_mojo_runtime import compiler_configuration
sys.path.pop(0)
PREFIX = '//third_party/perfetto/'
SKIP = {'//third_party/perfetto/src/base:base', '//third_party/perfetto/src/base:perfetto_base_default_platform',
        '//third_party/perfetto/src/protozero:protozero'}


def sdk_configuration(graph):
    pending, seen, sources = ['//third_party/perfetto:libperfetto'], set(), set()
    configurations = set()
    while pending:
        label = pending.pop()
        if label in seen or not label.startswith(PREFIX[:-1]) or label in SKIP:
            continue
        seen.add(label)
        target = graph['targets'][label]
        if target['type'] == 'executable':
            continue
        pending.extend(target.get('deps', []))
        if target['type'] not in ('source_set', 'static_library'):
            continue
        files = [path for path in target.get('sources', []) if path.startswith(PREFIX) and path.endswith('.cc')]
        if files:
            configurations.add(tuple(tuple(graph['pool'][target[field]['pool']]) for field in ('defines', 'cflags', 'cflags_cc')))
            sources.update(path.removeprefix(PREFIX) for path in files)
    if len(configurations) != 1:
        raise ValueError('SDK compiler settings need per-target mapping')
    defines, cflags, cflags_cc = next(iter(configurations))
    return sources, defines, cflags, cflags_cc


def compiler_flags(cflags, cflags_cc):
    return compiler_configuration({}, {
        'cflags': list(cflags), 'cflags_cc': list(cflags_cc), 'defines': [],
    })[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('source', type=Path)
    parser.add_argument('--arm64-graph', type=Path)
    parser.add_argument('--windows-amd64-graph', type=Path)
    parser.add_argument('--windows-arm64-graph', type=Path)
    parser.add_argument('--darwin-arm64-graph', type=Path)
    args = parser.parse_args()
    graph = json.loads(gzip.decompress(args.graph.read_bytes()))
    source = args.source
    sources, defines, cflags, cflags_cc = sdk_configuration(graph)
    flags = compiler_flags(cflags, cflags_cc)
    defines = [value for value in defines if not value.startswith(('CR_LIBCXX_REVISION=', 'CR_SYSROOT_KEY=', 'USE_LIBCXX_MODULES'))]
    headers = sorted(str(path.relative_to(source)) for path in source.rglob('*') if path.is_file() and path.suffix in ('.h', '.inc') and path.relative_to(source).parts[0] in ('include', 'src'))
    python = sorted(str(path.relative_to(source)) for directory in ('python/generators/trace_processor_table', 'src/trace_processor/tables') for path in (source / directory).rglob('*.py'))
    tools = ['tools/gen_tp_table_headers.py', 'tools/gen_cc_proto_descriptor.py', 'tools/touch_file.py']
    exported = sorted(set(sources) | set(headers) | set(python) | set(tools))
    for path in exported:
        if not (source / path).is_file():
            raise ValueError(f'missing SDK source: {path}')
    data = {'SDK_SOURCES': sorted(sources), 'SDK_COPTS': flags, 'SDK_DEFINES': defines, 'SDK_HEADERS': headers, 'SDK_PYTHON': python}
    selected = {}
    variants = {
        'linux_arm64': args.arm64_graph,
        'windows_amd64': args.windows_amd64_graph,
        'windows_arm64': args.windows_arm64_graph,
        'darwin_arm64': args.darwin_arm64_graph,
    }
    values = {key: {'//conditions:default': data[key]}
              for key in ('SDK_SOURCES', 'SDK_COPTS', 'SDK_DEFINES')}
    for platform, path in variants.items():
        if not path:
            continue
        variant = json.loads(gzip.decompress(path.read_bytes()))
        platform_sources, platform_defines, platform_cflags, platform_cflags_cc = sdk_configuration(variant)
        for path in platform_sources:
            if not (source / path).is_file():
                raise ValueError('missing platform SDK source: ' + path)
        exported = sorted(set(exported) | platform_sources)
        platform_defines = [value for value in platform_defines if not value.startswith(
            ('CR_LIBCXX_REVISION=', 'CR_SYSROOT_KEY=', 'USE_LIBCXX_MODULES'))]
        for key, value in [('SDK_SOURCES', sorted(platform_sources)),
                           ('SDK_COPTS', compiler_flags(platform_cflags, platform_cflags_cc)),
                           ('SDK_DEFINES', platform_defines)]:
            values[key]['//bazel:' + platform] = value
    for key, choices in values.items():
        if len(choices) > 1:
            selected[key] = 'select({\n' + '\n'.join(
                ('Label(' + json.dumps(condition) + ')' if condition.startswith('//bazel:') else json.dumps(condition))
                + ': ' + json.dumps(value, indent=4) + ','
                for condition, value in choices.items()) + '\n})'
    if values['SDK_SOURCES'].get('//bazel:linux_arm64', values['SDK_SOURCES']['//conditions:default']) != values['SDK_SOURCES']['//conditions:default']:
        raise ValueError('Linux Perfetto source lists differ; update the native source adapter')
    source_variants = '{\n' + '\n'.join(
        ('Label(' + json.dumps(condition) + ')' if condition.startswith('//bazel:') else json.dumps(condition)) + ': [Label("//:" + path) for path in ' + json.dumps(paths, indent=4) + '],'
        for condition, paths in values['SDK_SOURCES'].items()) + '\n}'
    selected['SDK_SOURCES'] = 'select(SDK_SOURCE_VARIANTS)'
    prefix = ('"""Generated by tools/import_chromium_sdk.py from pinned browser graph."""\n\n'
              + 'SDK_SOURCE_VARIANTS = ' + source_variants
              + '\n\nSDK_LINUX_SOURCES = SDK_SOURCE_VARIANTS["//conditions:default"]\n\n')
    (ROOT / 'bcr/overlay/bazel/sdk_sources.bzl').write_text(prefix + '\n\n'.join(key + ' = ' + (selected[key] if key in selected else json.dumps(value, indent=4)) for key, value in data.items()) + '\n')
    path = ROOT / 'bcr/overlay/BUILD.bazel'
    text = path.read_text()
    begin, end = '# BEGIN CHROMIUM SDK INPUTS', '# END CHROMIUM SDK INPUTS'
    block = begin + '\nexports_files(' + json.dumps([p for p in exported if not p.startswith('python/')], indent=4) + ')\n' + end
    if begin in text:
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        text = before + block + after
    else:
        text += '\n' + block + '\n'
    path.write_text(text)
    package = ROOT / 'bcr/overlay/python'
    package.mkdir(parents=True, exist_ok=True)
    (package / 'BUILD.bazel').write_text('exports_files(' + json.dumps([p.removeprefix('python/') for p in python if p.startswith('python/')], indent=4) + ', visibility = ["//visibility:public"])\n')
    print(f'Imported {len(sources)} SDK C++ sources, {len(headers)} headers')


if __name__ == '__main__':
    main()
