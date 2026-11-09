#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Import Chromium Variations protocol generation through BCR protoc."""

import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = '//components/variations/proto:proto_gen'
BUILD_DIR = '//out/bazel-import/'


def main():
    graph = json.loads(gzip.decompress(Path(sys.argv[1]).read_bytes()))
    target = graph['targets'][TARGET]
    compilers = {path for path in target['inputs'] if path.startswith(BUILD_DIR)
                 and Path(path).name == 'protoc'}
    if len(compilers) != 1:
        raise ValueError('expected one execution-platform protoc input')
    compiler = compilers.pop()
    sources = set()

    def file_label(path):
        if path == compiler:
            return ':protoc_tool'
        if path == '//third_party/protobuf/src/google/protobuf/descriptor.proto':
            return '@protobuf//:descriptor_proto_srcs'
        if not path.startswith('//') or path.startswith(BUILD_DIR):
            raise ValueError(f'unmapped proto input: {path}')
        sources.add(path[2:])
        return '//:' + path[2:]

    files = {file_label(path): path[2:] for path in sorted(set(target['inputs'] + [target['script']]))}
    outputs = {path.removeprefix(BUILD_DIR): path.removeprefix(BUILD_DIR) for path in target['outputs']}
    lines = [
        '"""Native Variations protocol generation; run tools/import_proto_actions.py."""', '',
        'load("@rules_cc//cc:cc_library.bzl", "cc_library")',
        'load(":python_action.bzl", "chromium_python_action")',
        'load(":tool_inputs.bzl", "chromium_tool_inputs")',
        'load(":protobuf_config.bzl", "chromium_protoc", "chromium_protobuf_library")', '',
        'def native_variations_proto(name):',
        '    """Generate and compile original Chromium Variations schemas.', '',
        '    Args:', '        name: C++ protocol library target.', '    """',
        '    chromium_protoc(', '        name = "protobuf_compiler",',
        '        tool = "@protobuf//:protoc",', '    )',
        '    chromium_protobuf_library(', '        name = "protobuf_lite_runtime",',
        '        dep = "@protobuf//:protobuf_lite",', '    )',
        '    chromium_tool_inputs(', '        name = "protoc_tool",',
        '        tool = ":protobuf_compiler",',
        '        allow_native_sharing = False,',
        '        logical_path = ' + json.dumps(compiler[2:]) + ',',
        *(['        additional_logical_paths = ["out/bazel-import/protoc"],']
          if compiler != BUILD_DIR + 'protoc' else []),
        '    )',
        '    chromium_python_action(', '        name = "variations_proto_gen",',
        '        srcs = ' + json.dumps(files) + ',',
        '        outs = ' + json.dumps(outputs) + ',',
        '        script = ' + json.dumps(target['script'][2:]) + ',',
        '        args = ' + json.dumps(target['args']) + ',',
        '        deps = [":protoc_tool"],', '    )',
        '    cc_library(', '        name = name,',
        '        srcs = ' + json.dumps([':' + path for path in outputs if path.endswith('.cc')]) + ',',
        '        hdrs = ' + json.dumps([':' + path for path in outputs if path.endswith('.h')]) + ',',
        '        includes = ["gen/components/variations/proto", "gen"],',
        '        copts = ["-std=c++20"],',
        '        deps = [":protobuf_lite_runtime"],', '    )', '',
    ]
    (ROOT / 'bcr/overlay/native/proto_actions.bzl').write_text('\n'.join(lines))
    path = ROOT / 'bcr/overlay/BUILD.bazel'
    text = path.read_text()
    start, end = '# BEGIN GENERATED PROTO INPUTS', '# END GENERATED PROTO INPUTS'
    block = start + '\nexports_files(' + json.dumps(sorted(sources), indent=4) + ')\n' + end
    if start in text:
        before, remaining = text.split(start, 1)
        _, after = remaining.split(end, 1)
        text = before + block + after
    else:
        text += '\n' + block + '\n'
    path.write_text(text)
    print(f'Imported {len(target["sources"])} schemas, {len(outputs)} generated outputs')


if __name__ == '__main__':
    main()
