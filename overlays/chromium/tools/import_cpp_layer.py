#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Import complete captured C++ layers into the combined Chromium build."""
import argparse
import ast
from functools import cache
import gzip
import hashlib
import json
import os
import posixpath
import re
import shlex
from pathlib import Path

from import_base import replace_block, sort_archive_files, starlark_literal
from import_mojo_runtime import compiler_configuration, TARGETS as MOJO_RUNTIME_TARGETS

ROOT = Path(__file__).resolve().parents[1]
BUILD = '//out/bazel-import/'
QUICHE = 'net/third_party/quiche/src/'
PREFIXES = ('//net:', '//net/', '//sql:', '//base/version_info:',
            '//components/network_time/', '//components/miracle_parameter/',
            '//components/sqlite_proto:', '//components/unexportable_keys:',
            '//components/performance_manager/scenario_api:', '//ui/base/glib:')
REUSED = {
    '//build/rust/allocator:allocator': '//build/rust/allocator:allocator',
    '//build/rust/allocator:allocator_impls': '//build/rust/allocator:allocator_impls',
    '//build/rust/allocator:alloc_error_handler_impl': '//build/rust/allocator:alloc_error_handler_impl',
    '//build/rust/allocator:allocator_impls_ffi': '//native/rust:allocator_impls_ffi',
    '//build/rust/allocator:alloc_error_handler_impl_ffi': '//native/rust:alloc_error_handler_impl_ffi',
    '//build/rust/allocator:buildflags': ':rust_allocator_buildflags',
    '//third_party/fast_float:fast_float': '@fast_float//:fast_float',
    '//third_party/libxslt:libxslt': ':libxslt',
    '//third_party/ced:ced': '//third_party/ced:ced',
    '//third_party/rust/font_types/v0_10:lib': '//native/rust:font_types',
    '//third_party/rust/read_fonts/v0_35:lib': '//native/rust:read_fonts',
    '//third_party/rust/skrifa/v0_37:lib': '//native/rust:skrifa',
    '//build/rust:cxx_cppdeps': '//third_party/rust/chromium_crates_io/vendor/cxx-v1:core-lib',
    '//third_party/cpuinfo:cpuinfo': '@cpuinfo//:cpuinfo',
    '//third_party/fxdiv:fxdiv': '@fxdiv//:FXdiv',
    '//third_party/flatbuffers:flatbuffers': '@flatbuffers//:runtime_cc',
    '//net/third_party/quiche:quiche': ':quiche',
    '//net/third_party/quiche:net_quic_proto': ':quic_proto',
    '//net/third_party/uri_template:uri_template': ':uri_template',
    '//base:base': ':base', '//base:i18n': ':base_i18n', '//crypto:crypto': ':crypto',
    '//url:url': ':url', '//third_party/abseil-cpp:absl': '//third_party/abseil-cpp:absl',
    '//third_party/boringssl:boringssl': '//third_party/boringssl',
    '//third_party/zlib:zlib': '//third_party/zlib', '//third_party/icu:icu': '//third_party/icu:icu',
    '//third_party/icu:icudata': '//third_party/icu:icu',
    '//third_party/icu:icui18n': '//third_party/icu:icu',
    '//third_party/icu:icuuc': '//third_party/icu:icu',
    '//third_party/icu:icuuc_private': '//third_party/icu:icu',
    '//third_party/icu:icuuc_public': '//third_party/icu:icu',
    '//third_party/brotli:dec': '@brotli//:brotlidec',
    '//third_party/brotli:enc': '@brotli//:brotlienc',
    '//third_party/brotli:common': '@brotli//:brotlicommon',
    '//third_party/protobuf:protobuf_lite': ':protobuf_lite_runtime',
    '//third_party/protobuf:protobuf_full': ':protobuf_full_runtime',
    '//third_party/sqlite:sqlite': ':chromium_sqlite',
    '//third_party/re2:re2': '@re2//:re2',
    '//third_party/zstd:decompress': '@zstd//:zstd',
    '//third_party/simdutf:simdutf': '@simdutf//:simdutf',
    '//third_party/wayland:wayland_client': '@wayland//:wayland_client',
    '//third_party/wayland:wayland_util': '@wayland//:wayland_client',
    '//third_party/wayland:wayland_cursor': '@wayland//:wayland_cursor',
    '//third_party/wayland:wayland_egl': '@wayland//:wayland_egl',
    '//third_party/wayland:wayland_scanner': '@wayland//:wayland_scanner',
    '//mojo/public/cpp/bindings:default_construct_tag': ':mojo_cpp_bindings',
    '//base:sanitizer_buildflags': ':all_buildflags',
    '//build:branding_buildflags': ':all_buildflags',
    '//build:chromeos_buildflags': ':all_buildflags',
    '//crypto:buildflags': ':all_buildflags', '//url:buildflags': ':all_buildflags',
    '//build:buildflag_header_h': '//build:buildflag',
}
# LLVM supplies its real standard library; generator tools are mapped as tools.
PROVIDED = {
    '//buildtools/third_party/libc++:all_modules',
    '//buildtools/third_party/libc++:custom_headers',
    '//buildtools/third_party/libc++:libcxx_headers',
    '//build/config:executable_deps', '//build/config:shared_library_deps', '//third_party/protobuf:protoc',
    '//tools/grit:grit_sources', '//tools/gritsettings:default_resource_ids',
}


def name(label):
    return 'network_' + hashlib.sha256(label.encode()).hexdigest()[:16]


def foreach_arguments(arguments, source, outputs):
    """Expand GN source substitutions in the action's toolchain output tree."""
    substitutions = {'{{source}}': '../../' + source[2:],
                     '{{source_name_part}}': Path(source).stem}
    if any('{{source_gen_dir}}' in argument for argument in arguments):
        roots = set()
        for output in outputs:
            relative = output.removeprefix(BUILD)
            if relative.startswith('gen/'):
                roots.add('gen')
            elif '/gen/' in relative:
                roots.add(relative.split('/gen/', 1)[0] + '/gen')
        if len(roots) != 1:
            raise ValueError('ambiguous GN source_gen_dir output tree: ' + repr(outputs))
        substitutions['{{source_gen_dir}}'] = roots.pop() + '/' + str(Path(source[2:]).parent)
    for token, value in substitutions.items():
        arguments = [argument.replace(token, value) for argument in arguments]
    if any('{{' in argument for argument in arguments):
        raise ValueError('unmapped GN source substitution: ' + repr(arguments))
    return arguments


def header_resolver(source_root, include_directories):
    """Cache immutable checkout probes while retaining local include context."""
    @cache
    def exists(relative):
        return (source_root / relative).is_file()

    @cache
    def search(include):
        for directory in include_directories:
            candidate = posixpath.join(directory, include)
            if exists(candidate):
                return candidate
        return None

    def resolve(source, include):
        if exists(include):
            return include
        local = posixpath.join(posixpath.dirname(source), include)
        return local if exists(local) else search(include)

    return resolve


def reuse_host_targets(targets, reused, provided, providers=None):
    """Keep ordinary host dependencies separate from cross-V8 generators."""
    for label in targets:
        original, separator, toolchain = label.partition('(')
        if not separator:
            continue
        if toolchain not in (
                '//build/toolchain/linux:clang_x64)',
                '//build/toolchain/linux:clang_x64_for_rust_host_build_tools)',
                '//build/toolchain/linux:clang_x64_v8_arm64)'):
            continue
        if original in PROVIDED:
            provided.add(label)
        cross_v8 = toolchain.endswith(':clang_x64_v8_arm64)')
        # Cross-V8 libraries must retain their captured target architecture.
        if original not in reused:
            continue
        dependency = reused[original]
        if dependency == ':all_buildflags':
            reused[label] = dependency
            continue
        host_support = (original in REUSED
                        or original.startswith('//base/allocator/partition_allocator/src/partition_alloc:')
                        or dependency.startswith(('@', '//native/rust:'))) or dependency in (
            ':libvpx_public', ':ffmpeg_opus',
        ) or original in (
            '//build/win:default_exe_manifest',
            '//third_party/perfetto:libperfetto',
            '//third_party/rust/temporal_capi:temporal_capi',
            '//third_party/zlib/google:compression_utils_portable',
        )
        if cross_v8 and not host_support:
            continue
        if dependency.startswith(':') and providers is not None:
            if original in providers:
                dependency = providers[original]
            elif re.fullmatch(r':[a-z][a-z0-9_]*_[0-9a-f]{16}', dependency):
                continue
        if dependency.startswith(':'):
            dependency = '@chromium//native' + dependency
        elif dependency.startswith('//'):
            dependency = '@chromium' + dependency
        reused[label] = dependency


def browser_runtime_roots(graph):
    """Add runtime libraries and Vulkan manifests; resources use the asset catalog."""
    runtime_files = {path for path in graph.get('runtime_files', {}).get('//chrome:chrome', [])
                     if path.endswith(('.dll', '.so', '.dylib', '_icd.json'))
                     or path.startswith(BUILD + 'angledata/')}
    return sorted(label for label, target in graph['targets'].items()
                  if runtime_files.intersection(target.get('outputs', [])))


@cache
def native_library_providers(overlay):
    """Resolve GN identities across native and platform layer boundaries."""
    providers = {}
    pattern = re.compile(r'^    "(//[^"\n]+)": \{\n        "name": "([^"\n]+)"', re.M)
    for source in sorted((overlay / 'native').glob('*_sources.bzl')):
        providers.update({label: ':' + name for label, name in pattern.findall(source.read_text())})
    return providers


def native_graphics_providers(overlay):
    """Read providers from the native overlay, not the cross-import staging tree."""
    providers = {}
    for component in ('geometry', 'dawn', 'dawn_native', 'linux_ui', 'gpu_service', 'gpu_protocol', 'compositor', 'network', 'fonts', 'codecs', 'pthreadpool', 'ml', 'ffmpeg', 'skia', 'angle_runtime', 'swiftshader', 'vulkan_loader',
                      'vulkan_validation', 'vulkan_tools'):
        tree = ast.parse((overlay / 'native' / (component + '_sources.bzl')).read_text())
        records = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign) and node.targets[0].id == 'LIBRARIES')
        providers.update({label: ':' + library['name'] for label, library in records.items()
                          if library['kind'] in ('source_set', 'static_library', 'shared_library')})
    return providers


def resource_asset_inputs(source_root, resource):
    """Find checked-in files referenced by Windows resource scripts."""
    pending = [source_root / resource.removeprefix('//')]
    seen, assets = set(), set()
    while pending:
        script = pending.pop()
        if script in seen or not script.is_file():
            continue
        seen.add(script)
        text = script.read_text(errors='replace')
        for filename in re.findall(r'"([^"\r\n]+\.(?:ico|bmp|cur|manifest|bin|png|rc|dlg|h))"', text, re.I):
            path = Path(os.path.abspath(script.parent / filename.replace('\\', '/')))
            if not path.is_relative_to(source_root) or not path.is_file():
                continue
            assets.add('//' + path.relative_to(source_root).as_posix())
            if path.suffix.lower() in ('.rc', '.dlg', '.h'):
                pending.append(path)
    return assets


def declare_message_compiler_assets(targets, source_root):
    """Declare binary message tables omitted from GN's message compiler outputs."""
    source_root = source_root.absolute()
    for target in targets.values():
        if target.get('script') != '//build/win/message_compiler.py':
            continue
        instances = target.get('source_outputs', {'': [path.removeprefix(BUILD)
                    for path in target.get('outputs', [])]})
        for source, outputs in instances.items():
            arguments = foreach_arguments(target['args'], source, outputs)
            headers = arguments[arguments.index('-h') + 1]
            resources = arguments[arguments.index('-r') + 1]
            directory = 'third_party/win_build_output/' + re.sub(r'^(?:[^/]+/)?gen/', 'mc/', headers)
            checked = source_root / directory
            additions = set()
            for output in list(outputs):
                if not output.endswith('.rc'):
                    continue
                resource = '//' + directory + '/' + Path(output).name
                for asset in resource_asset_inputs(source_root, resource):
                    if asset.lower().endswith('.bin'):
                        relative = (source_root / asset[2:]).relative_to(checked)
                        additions.add(posixpath.join(resources, relative.as_posix()))
            for output in sorted(additions):
                if output not in outputs:
                    outputs.append(output)
                if BUILD + output not in target['outputs']:
                    target['outputs'].append(BUILD + output)


def protocol_inputs(source_root, protocols):
    """Follow PDL includes in the checkout's logical namespace."""
    root = Path(os.path.abspath(source_root))
    pending = [root / path.removeprefix('//') for path in protocols]
    seen, inputs = set(), set()
    while pending:
        path = Path(os.path.abspath(pending.pop()))
        relative = path.relative_to(root)
        if path in seen:
            continue
        seen.add(path)
        inputs.add('//' + relative.as_posix())
        pending.extend(path.parent / included.strip()
                       for included in re.findall(r'^include (.+)$', path.read_text(), re.MULTILINE))
    return inputs


def reuse_host_graphics(graph, reference, libraries, providers):
    """Share native support libraries when captured configurations match."""
    suffix = '(//build/toolchain/linux:clang_x64_v8_arm64)'
    prefixes = ('//third_party/angle/', '//third_party/angle:', '//third_party/swiftshader/',
                '//third_party/vulkan-loader/', '//third_party/vulkan-validation-layers/',
                '//third_party/vulkan-tools/', '//third_party/fontconfig:',
                '//third_party/freetype:', '//third_party/harfbuzz-ng:',
                '//third_party/libpng:', '//third_party/libxml:', '//third_party/tflite:',
                '//third_party/fft2d:', '//third_party/xnnpack:', '//third_party/ruy:',
                '//third_party/eigen3:', '//third_party/gemmlowp:', '//third_party/farmhash:',
                '//third_party/neon_2_sse:',
                '//third_party/pthreadpool:',
                '//base/version_info:', '//components/miracle_parameter/',
                '//components/network_time/', '//components/performance_manager/scenario_api:',
                '//components/unexportable_keys:', '//sql:', '//third_party/dawn/',
                '//third_party/libyuv:', '//third_party/pffft:', '//ui/base/glib:',
                '//ui/base:features', '//ui/gfx/geometry:',
                '//services/viz/public/mojom:singleplanar_format',
                '//third_party/libwebp:', '//third_party/libjpeg_turbo:', '//third_party/wuffs:',
                '//third_party/ffmpeg:', '//skia:', '//net:', '//third_party/webrtc/', '//components/viz/common:shared_image_format')
    fields = ('type', 'sources', 'defines', 'cflags', 'cflags_cc', 'cflags_c',
              'asmflags', 'include_dirs', 'libs', 'ldflags', 'outputs', 'deps')

    def signature(capture, target):
        def normalize(value):
            if isinstance(value, dict) and 'pool' in value:
                return normalize(capture['pool'][value['pool']])
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, str):
                return (value.replace(suffix, '')
                        .replace('//out/bazel-import/clang_x64_v8_arm64/', BUILD)
                        .replace('clang_x64_v8_arm64/gen/', 'gen/'))
            return value
        return [normalize(target.get(field, [])) for field in fields]

    count = 0
    for label, library in libraries.items():
        if not label.startswith(prefixes) or not label.endswith(suffix):
            continue
        original = label.removesuffix(suffix)
        target = graph['targets'][label]
        native = reference['targets'].get(original)
        provider = providers.get(original)
        if (not native or not provider
                or target['type'] not in ('source_set', 'static_library', 'shared_library')
                or signature(graph, target) != signature(reference, native)):
            continue
        for field in ('srcs', 'hdrs', 'copts', 'defines', 'includes', 'linkopts'):
            library[field] = []
        library.pop('c_copts', None)
        library.pop('asm_copts', None)
        if target['type'] == 'shared_library':
            primary = next(path for path in library['outputs']
                           if path.endswith('.so') or ('.so.' in path and not path.endswith('.TOC')))
            library['kind'] = 'shared_library_import'
            library['shared_library'] = '@chromium//native:' + Path(primary).name
            library['deps'] = []
        else:
            library['kind'] = 'group'
            library['deps'] = ['@chromium//native' + provider if provider.startswith(':') else provider]
        count += 1
    return count



def host_webui_resource_copy(graph, reference):
    """Reuse identical host WebUI resource declarations from the native build."""
    suffix = '(//build/toolchain/linux:clang_x64_v8_arm64)'
    prefix = 'clang_x64_v8_arm64/'
    root = '//ui/webui/resources:resources_grit'
    if root + suffix not in graph['targets']:
        return None

    def normalize(capture, value):
        if isinstance(value, dict) and 'pool' in value:
            return normalize(capture, capture['pool'][value['pool']])
        if isinstance(value, list):
            return [normalize(capture, item) for item in value]
        if isinstance(value, str):
            if value == 'SHARED_INTERMEDIATE_DIR=clang_x64_v8_arm64':
                return 'SHARED_INTERMEDIATE_DIR=.'
            return value.replace(suffix, '').replace(prefix, '')
        return value

    roots = {
        root: '//ui/webui/resources:build_grd',
        '//third_party/blink/public:devtools_inspector_resources_grit':
            '//third_party/devtools-frontend/src:generate_devtools_inspector_overlay_resources',
        '//third_party/blink/public/strings:permission_element_generated_strings_grit':
            '//third_party/blink/public/strings:generate_permission_element_strings_mono_grd',
    }
    paths = []
    for resource, producer in roots.items():
        if resource + suffix not in graph['targets']:
            continue
        for label in [resource, producer]:
            native = reference['targets'][label]
            host = graph['targets'][label + suffix]
            for field in ['type', 'script', 'args', 'inputs', 'sources', 'outputs', 'deps']:
                native_value = normalize(reference, native.get(field, []))
                host_value = normalize(graph, host.get(field, []))
                if label == resource and field == 'args':
                    # GRIT defaults to Linux; cross captures spell it out.
                    for arguments in [native_value, host_value]:
                        if '-t' in arguments and arguments[arguments.index('-t') + 1] == 'linux':
                            index = arguments.index('-t')
                            del arguments[index:index + 2]
                if native_value != host_value:
                    raise ValueError('host WebUI resource configuration differs: ' + label + ' ' + field)
        paths.extend(path.removeprefix(BUILD) for path in reference['targets'][resource]['outputs']
                     if path.endswith(('.h', '.cc')))
    return dict(
        name='browser_host_webui_resource_declarations',
        srcs={'@chromium//native:' + path: path for path in paths},
        outputs={prefix + path: path for path in paths},
    )


def deduplicate_source_sets(libraries):
    """Keep repeated archive sources in their source-set dependency."""
    by_name = {':' + value['name']: value for value in libraries.values()}
    for library in libraries.values():
        if library['kind'] != 'static_library':
            continue
        pending = list(library['deps'])
        visited = set()
        owned = set()
        while pending:
            dependency = pending.pop()
            if dependency in visited or dependency not in by_name:
                continue
            visited.add(dependency)
            target = by_name[dependency]
            if target['kind'] == 'source_set':
                owned.update(target['srcs'])
            pending.extend(target['deps'])
        library['srcs'] = [source for source in library['srcs'] if source not in owned]


def protobuf_plugin_dependencies(label, dependencies):
    """Use compiler plugin APIs without linking every language generator."""
    apis = {
        '//third_party/protobuf-javascript:protoc-gen-js': [
            '@protobuf//src/google/protobuf/compiler:code_generator',
        ],
        '//components/proto_extras:proto_extras_plugin': [
            '@protobuf//src/google/protobuf/compiler:code_generator',
            '@protobuf//src/google/protobuf/compiler:importer',
            '@protobuf//src/google/protobuf/compiler/cpp:names',
        ],
    }.get(label.split('(', 1)[0])
    if apis is None:
        return dependencies
    return [replacement for dependency in dependencies
            for replacement in (apis if dependency == '@protobuf//:protoc_lib' else [dependency])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--native-overlay', type=Path, default=ROOT / 'bcr/overlay',
                        help='Linux AMD64 overlay supplying shared host graphics providers')
    parser.add_argument('--root', action='append', default=[], help='Additional captured GN roots for this layer')
    parser.add_argument('--assets-only', action='store_true', help='Import browser resource prerequisites before browser assembly')
    parser.add_argument('--layer', choices=['network', 'geometry', 'dawn', 'fonts', 'codecs', 'skia', 'paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'pthreadpool', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser', 'blink_rust'], default='network')
    args = parser.parse_args()
    layer = args.layer
    prefixes = PREFIXES if layer == 'network' else ('//ui/gfx/geometry:', '//ui/gfx/geometry/mojom:', '//ui/gfx/range:', '//ui/gfx/range/mojom:')
    roots = ['//net:net'] if layer == 'network' else ['//ui/gfx/geometry:geometry_skia', '//ui/gfx/geometry/mojom:mojom', '//ui/gfx/range/mojom:mojom']
    if layer == 'dawn':
        prefixes = ('//third_party/dawn/',)
        roots = ['//third_party/dawn/include/dawn:cpp_headers', '//third_party/dawn/src/dawn:proc']
    if layer == 'fonts':
        prefixes = ('//third_party/freetype:', '//third_party/fontconfig:', '//third_party/harfbuzz-ng:', '//third_party/libpng:', '//third_party/libxml:', '//build/config/freetype:')
        roots = ['//third_party/freetype:freetype', '//third_party/harfbuzz-ng:harfbuzz-ng', '//third_party/fontconfig:fontconfig']
    if layer == 'codecs':
        prefixes = ('//third_party/libjpeg_turbo:', '//third_party/libwebp:', '//third_party/wuffs:', '//third_party:')
        roots = ['//third_party:jpeg', '//third_party/libwebp:libwebp', '//third_party/wuffs:wuffs']
    if layer == 'skia':
        prefixes = ('//skia:', '//gpu/config:', '//ui/base:')
        roots = ['//skia:skia', '//skia:bridge_rust_side_cxx_generated', '//skia:rust_png_ffi_cxx_generated']
    if layer == 'paint':
        prefixes = ('//cc/base:', '//cc/debug:', '//cc/paint:', '//components/crash/core/common:',
                    '//gpu/command_buffer/common:', '//skia/public/mojom:', '//ui/gfx',
                    '//ui/base:', '//ui/linux:', '//ui/display/types:',
                    '//third_party/crashpad/crashpad/', '//printing/buildflags:',
                    '//gpu/vulkan:', '//device/vr/buildflags:')
        roots = ['//cc/paint:paint']
    if layer == 'gfx':
        prefixes = ('//ui/gfx', '//ui/base:', '//third_party/libdrm:',
                    '//build/config/linux/libdrm:', '//third_party/libsync:',
                    '//third_party/zlib/google:', '//components/viz/common:shared_image_format',
                    '//services/viz/public/mojom:singleplanar_format', '//components/crash/core/common:')
        roots = ['//ui/gfx:gfx']
    if layer == 'tint':
        prefixes = ('//third_party/dawn/',)
        roots = ['//third_party/dawn/src/tint/api:api']
    if layer == 'dawn_native':
        prefixes = ('//third_party/dawn/',)
        roots = ['//third_party/dawn/src/dawn/native:native']
    if layer == 'vulkan_loader':
        prefixes = ('//third_party/vulkan-loader/',)
        roots = ['//third_party/vulkan-loader/src:libvulkan']
    if layer == 'vulkan_validation':
        prefixes = ('//third_party/vulkan-validation-layers/', '//third_party/vulkan-utility-libraries/')
        roots = ['//third_party/vulkan-validation-layers/src:vulkan_validation_layers', '//third_party/vulkan-validation-layers/src:vulkan_gen_json_files']
    if layer == 'swiftshader':
        prefixes = ('//third_party/swiftshader/',)
        roots = ['//third_party/swiftshader/src/Vulkan:swiftshader_libvulkan', '//third_party/swiftshader/src/Vulkan:icd_file']
    if layer == 'vulkan_tools':
        prefixes = ('//third_party/vulkan-tools/',)
        roots = ['//third_party/vulkan-tools/src:VkICD_mock_icd']
    if layer == 'angle_runtime':
        prefixes = ('//third_party/angle', '//third_party/vulkan_memory_allocator:')
        roots = ['//third_party/angle:libEGL', '//third_party/angle:libGLESv2']
    if layer == 'gpu_protocol':
        prefixes = ('//gpu/command_buffer/common:', '//gpu/command_buffer/client:',
                    '//components/viz/common:shared_image_format', '//ui/gl:gl_enums',
                    '//services/viz/public/mojom:singleplanar_format')
        roots = ['//gpu/command_buffer/common:' + target for target in ['common', 'gles2', 'gles2_utils']]
        roots += ['//gpu/command_buffer/client:gles2_interface']
    if layer == 'x11':
        prefixes = ('//ui/gfx/x', '//ui/events/platform:', '//ui/events:platform_event')
        roots = ['//ui/gfx/x:x']
    if layer == 'linux_buffers':
        prefixes = ('//ui/gfx/linux:', '//ui/ozone:native_pixmap_usage', '//third_party/minigbm:')
        roots = ['//ui/gfx/linux:gpu_memory_buffer_support_x11']
    if layer == 'browser_services':
        prefixes = ('//services/metrics/public/', '//services/tracing/public/',
                    '//components/prefs:', '//components/variations', '//components/system_cpu:',
                    '//components/tracing:', '//components/version_info:', '//third_party/metrics_proto:',
                    '//third_party/protobuf-javascript:', '//sandbox/policy/mojom:', '//url/mojom:')
        roots = ['//services/metrics/public/cpp:metrics_cpp', '//services/tracing/public/cpp:cpp']
    if layer == 'linux_ui':
        prefixes = ('//ui/', '//components/device_event_log:', '//components/headless/screen_info:', '//components/stylus_handwriting/win:', '//ipc:')
        roots = ['//ui/gl:gl']
    if layer == 'ozone':
        prefixes = ('//ui/', '//components/dbus', '//components/headless/',
                    '//components/exo/wayland/protocol:', '//components/url_formatter',
                    '//dbus:', '//device/udev_linux:', '//services/tracing/public/cpp:',
                    '//services/service_manager/public/', '//gpu/vulkan:', '//ipc:',
                    '//third_party/wayland-protocols:')
        roots = ['//ui/ozone:ozone', '//ui/gl/init:init']
    if layer == 'gpu_service':
        prefixes = ('//gpu/', '//components/viz/common', '//components/persistent_cache:',
                    '//components/crash/core/common:', '//ipc:', '//third_party/dawn/',
                    '//third_party/libyuv:', '//components/metal_util:', '//components/gwp_asan/client:', '//components/gwp_asan/common:', '//services/viz/public/mojom:',
                    '//services/webnn/public/mojom:', '//third_party/blink/public/common/tokens:',
                    '//third_party/blink/public/common:common_export', '//url/ipc:', '//ui/base/clipboard:')
        roots = ['//gpu/command_buffer/service:gles2']
    if layer == 'browser_v8':
        prefixes = ('//v8:', '//v8/src/inspector:', '//v8/third_party/inspector_protocol:',
                    '//third_party/zlib/google:')
        roots = ['//v8:v8']
    if layer == 'media':
        prefixes = ('//media:', '//media/', '//gpu/ipc/service:', '//components/leveldb_proto', '//components/pref_registry:', '//third_party/ffmpeg:ffmpeg_features', '//components/keyed_service/core:', '//components/services/storage/public/', '//third_party/libgav1:', '//third_party/leveldatabase:', '//third_party/widevine/cdm:', '//ui/events:keyboard_hook')
        roots = ['//media:media', '//media/filters:symphonia_glue_cxx_generated']
    if layer == 'blink_rust':
        prefixes = ('//third_party/blink/',)
        roots = ['//third_party/blink/renderer/platform:font_format_check_cxx_generated', '//third_party/blink/common/rust_crash:rs_cxx_generated']
    if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        prefixes = ('//',)
        roots = ['//third_party/blink/renderer/platform:platform', '//third_party/blink/renderer/platform:font_format_check_cxx_generated', '//third_party/blink/common/rust_crash:rs_cxx_generated']
    if layer in ('blink_core', 'blink_modules', 'content', 'browser'):
        roots = ['//chrome:chrome', '//components/qr_code_generator:qr_code_generator_ffi_glue_cxx_generated', '//components/user_data_importer/utility:zip_ffi_glue_cxx_generated'] if layer == 'browser' else ['//content:content'] if layer == 'content' else ['//third_party/blink/renderer/modules:modules'] if layer == 'blink_modules' else ['//third_party/blink/renderer/core:core']
    if layer == 'compositor':
        prefixes = ('//',)
        roots = ['//cc:cc']
    if layer == 'gpu_client':
        prefixes = ('//gpu/ipc/', '//gpu/command_buffer/client:', '//gpu/command_buffer/common:', '//components/viz/common', '//components/viz/client')
        roots = ['//gpu/ipc/client:client', '//components/viz/common:common', '//components/viz/client:client']
    if layer == 'ffmpeg':
        prefixes = ('//third_party/ffmpeg:',)
        roots = ['//third_party/ffmpeg:ffmpeg']
    if layer == 'ml':
        prefixes = tuple('//third_party/' + project + ':' for project in
                         ['tflite', 'xnnpack', 'ruy', 'eigen3', 'gemmlowp', 'farmhash', 'neon_2_sse', 'fft2d'])
        roots = ['//third_party/tflite:tflite', '//third_party/tflite:tflite_builtin_op_resolver']
    if layer == 'pthreadpool':
        prefixes = ('//third_party/pthreadpool:',)
        roots = ['//third_party/pthreadpool:pthreadpool']
    roots.extend(args.root)
    if args.assets_only and layer != 'browser':
        parser.error('--assets-only requires --layer browser')
    browser_asset_roots = []
    if layer == 'browser':
        catalog = json.loads((ROOT / 'native/browser_asset_roots.json').read_text())
        if hashlib.sha256(args.graph.read_bytes()).hexdigest() != catalog['graph_sha256']:
            raise ValueError('browser asset roots belong to another graph')
        browser_asset_roots = catalog['roots']
        roots = browser_asset_roots if args.assets_only else roots + browser_asset_roots
    extra_provided = {'//third_party/icu:copy_icudata'} if layer == 'browser_v8' else set()
    existing_action_hashes = set()
    existing_action_names = {}
    existing_asset_providers = {}
    if layer in ('blink_core', 'blink_modules', 'content', 'browser'):
        for filename in ['webui_targets.json', 'devtools_inspector_targets.json', 'perfetto_proto_targets.json']:
            catalog = json.loads((ROOT / 'bcr/overlay/native' / filename).read_text())
            existing_asset_providers.update({label: value if value.startswith('//') else ':' + value
                                             for label, value in catalog.get('native', catalog).items()})
            existing_action_hashes.update(hashlib.sha256(label.encode()).hexdigest()[:16]
                                          for label in catalog.get('native', catalog))
    reused = dict(REUSED)
    reused['//third_party/microsoft_dxheaders:dxguids'] = '@chromium_directx_headers//:dxguids'
    reused.update({label: '@protobuf//:protoc_lib' for label in [
        '//third_party/protobuf:protoc_lib',
        '//third_party/protobuf:protoc_cpp',
    ]})
    if layer == 'browser':
        reused.update({
            '//base/allocator/partition_allocator/src/partition_alloc:' + part:
            '//base/allocator/partition_allocator/src/partition_alloc:' + part
            for part in ['allocator_base', 'allocator_core', 'allocator_shim', 'raw_ptr']
        })
        reused.update({label: '//third_party/icu:icu' for label in [
            '//third_party/icu:icui18n_hidden_visibility',
            '//third_party/icu:icuuc_private_hidden_visibility',
            '//third_party/icu:icuuc_public',
        ]})
    reused.update({
        '//ipc:message_support': ':mojo_ipc_messages',
        '//mojo/public/cpp/bindings:bindings': ':mojo_cpp_bindings',
        '//mojo/public/cpp/bindings:struct_traits': ':mojo_cpp_bindings',
        '//mojo/public/interfaces/bindings:bindings_headers': ':mojo_binding_headers',
    })
    if layer == 'gfx':
        reused['//third_party/angle:includes'] = '@chromium_angle//:headers'
        v8_catalog = ROOT / 'bcr/overlay/native/browser_v8_sources.bzl'
        if v8_catalog.is_file():
            tree = ast.parse(v8_catalog.read_text())
            records = next(ast.literal_eval(node.value) for node in tree.body
                           if isinstance(node, ast.Assign) and node.targets[0].id == 'LIBRARIES')
            portable = '//third_party/zlib/google:compression_utils_portable'
            if portable in records:
                reused[portable] = ':' + records[portable]['name']
    if layer == 'geometry':
        # Share the full Chromium Skia provider.
        reused['//skia:skia'] = ':skia'
    reused.update({
        '//base/allocator/partition_allocator:raw_ptr': '//base/allocator/partition_allocator/src/partition_alloc:raw_ptr',
        '//third_party/vulkan-headers/src:vulkan_headers': '@vulkan_headers//:vulkan_headers',
    })
    reused.update({
        '//third_party/nasm:nasm': '@nasm//:nasm',
        '//third_party/icu:icuuc': '//third_party/icu:icu',
        '//third_party/fontconfig:fontconfig_fontations_ffi': '//native/rust:fontconfig_ffi',
    })
    if layer == 'skia':
        reused.update({
            '//skia:bridge_rust_side': '//native/rust:skia_fontations',
            '//skia:rust_png_ffi': '//native/rust:skia_png',
            '//build/config/freetype:freetype': ':freetype',
            '//third_party/fontconfig:fontconfig': ':fontconfig',
            '//third_party/harfbuzz-ng:harfbuzz-ng': ':harfbuzz',
            '//third_party/libpng:libpng': ':libpng',
            '//third_party/libwebp:libwebp': ':webp',
            '//third_party/libwebp:libwebp_webp': ':codec_headers',
            '//third_party:jpeg': ':jpeg',
            '//third_party/wuffs:wuffs': ':wuffs',
            '//third_party/expat:expat': '@libexpat//:libexpat',
            '//third_party/dawn/include/dawn:cpp_headers': ':dawn_cpp_headers',
            '//third_party/dawn/src/dawn:proc': ':dawn_proc',
            '//build/rust:cxx_cppdeps': '//third_party/rust/chromium_crates_io/vendor/cxx-v1:core-lib',
            '//third_party/rust/font_types/v0_10:lib': '//native/rust:font_types',
            '//third_party/rust/read_fonts/v0_35:lib': '//native/rust:read_fonts',
            '//third_party/rust/skrifa/v0_37:lib': '//native/rust:skrifa',
            '//third_party/rust/png/v0_18:lib': '//native/rust:png',
        })
    if layer in ('paint', 'gfx', 'tint', 'dawn_native', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        # Share already imported Chromium implementations, including exact target flags.
        previous_layers = None
        if layer in ('gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            previous_layers = ['paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'pthreadpool', 'ml', 'ffmpeg']
            if layer in ('media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
                previous_layers += ['gpu_client']
            if layer in ('compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
                previous_layers += ['media']
            if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
                previous_layers += ['compositor', 'blink_rust']
            if layer in ('blink_core', 'blink_modules', 'content', 'browser'):
                previous_layers += ['blink_platform'] + (['blink_core', 'blink_modules', 'content'] if layer == 'browser' else ['blink_core', 'blink_modules'] if layer == 'content' else ['blink_core'] if layer == 'blink_modules' else [])
        for previous in ['network', 'geometry', 'dawn', 'fonts', 'codecs', 'skia'] + (previous_layers if previous_layers is not None else ['paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service'] if layer == 'browser_v8' else ['paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone'] if layer == 'gpu_service' else ['paint', 'gfx', 'angle_runtime', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui'] if layer == 'ozone' else ['paint', 'gfx', 'angle_runtime', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services'] if layer == 'linux_ui' else ['paint', 'gfx', 'angle_runtime', 'gpu_protocol', 'x11', 'linux_buffers'] if layer == 'browser_services' else ['paint', 'gfx', 'angle_runtime', 'gpu_protocol', 'x11'] if layer == 'linux_buffers' else ['paint', 'gfx', 'angle_runtime', 'gpu_protocol'] if layer == 'x11' else ['paint', 'gfx', 'angle_runtime'] if layer == 'gpu_protocol' else ['paint', 'gfx', 'tint'] if layer == 'dawn_native' else ['paint', 'gfx'] if layer == 'tint' else ['paint'] if layer == 'gfx' else []):
            previous_sources = ROOT / ('bcr/overlay/native/' + previous + '_sources.bzl')
            if not previous_sources.is_file():
                continue
            tree = ast.parse(previous_sources.read_text())
            libraries = next(ast.literal_eval(node.value) for node in tree.body
                             if isinstance(node, ast.Assign) and node.targets[0].id == 'LIBRARIES')
            reused.update({label: ':' + library['name'] for label, library in libraries.items()})
            if layer in ('gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
                previous_actions = next((ast.literal_eval(node.value) for node in tree.body
                                         if isinstance(node, ast.Assign) and node.targets[0].id == 'ACTIONS'), [])
                existing_action_hashes.update(match.group(1) for action in previous_actions
                                              if (match := re.search(r'_([0-9a-f]{16})_0$', action['name'])))
                existing_action_names.update({match.group(1): action['name'] for action in previous_actions
                                              if (match := re.search(r'_([0-9a-f]{16})_0$', action['name']))})
        reused['//skia:skia'] = ':skia'
        reused.update({label: ':mojo_base_types' for label in [
            '//mojo/public/cpp/base:shared_typemap_traits',
            '//mojo/public/mojom/base:base', '//mojo/public/mojom/base:base_shared']})
    if layer in ('gpu_protocol', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        reused.update({
            '//mojo/public/cpp/system:system': ':mojo_cpp_system',
            '//ui/gfx:memory_buffer': ':gfx_memory_buffer',
        })
    if layer == 'gpu_protocol':
        reused['//third_party/angle:includes'] = '@chromium_angle//:headers'
    if layer in ('tint', 'dawn_native'):
        reused['//third_party/spirv-headers/src:spv_headers'] = ':spirv_headers'
    if layer in ('linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        reused.update({
            '//base:base_static': ':base_base_static',
            '//build:android_buildflags': ':all_buildflags',
            '//build:blink_buildflags': ':all_buildflags',
            '//third_party/modp_b64:modp_b64': '//third_party/modp_b64',
        })
    if layer == 'linux_ui':
        reused.update({
            '//mojo/public/cpp/base:base': ':mojo_base_types',
            '//mojo/public/interfaces/bindings:bindings': ':mojo_cpp_bindings',
            '//mojo/public/interfaces/bindings:bindings_shared': ':mojo_binding_headers',
        })
    if layer == 'ozone':
        reused.update({
            '//build/config/linux/dbus:buildflags': ':all_buildflags',
            '//build:chromecast_buildflags': ':all_buildflags',
            '//build:robolectric_buildflags': ':all_buildflags',
            '//mojo/public/cpp/base:base': ':mojo_base_types',
            '//mojo/public/interfaces/bindings:bindings': ':mojo_cpp_bindings',
            '//mojo/public/interfaces/bindings:bindings_shared': ':mojo_binding_headers',
            '//third_party/wayland:wayland_client': '@wayland//:wayland_client',
            '//third_party/wayland:wayland_util': '@wayland//:wayland_client',
            '//third_party/wayland:wayland_cursor': '@wayland//:wayland_cursor',
            '//third_party/wayland:wayland_egl': '@wayland//:wayland_egl',
            '//third_party/wayland:wayland_scanner': '@wayland//:wayland_scanner',
        })
    if layer == 'gpu_service':
        reused.update({label: ':all_buildflags' for label in [
            '//build:chromecast_buildflags', '//media:media_buildflags',
            '//skia:buildflags', '//ui/base:ozone_buildflags', '//ui/gl:buildflags']})
        reused.update({
            '//third_party:jpeg_includes': ':codec_headers',
            '//third_party/microsoft_dxheaders:dxguids': '@chromium_directx_headers//:dxguids',
            '//mojo/public/cpp/base:base': ':mojo_base_types',
            '//mojo/public/interfaces/bindings:bindings': ':mojo_cpp_bindings',
            '//mojo/public/interfaces/bindings:bindings_shared': ':mojo_binding_headers',
            '//third_party/spirv-headers/src:spv_headers': ':spirv_headers',
        })
    if layer == 'browser_v8':
        reused.update({
            '//build/win:default_exe_manifest': ':all_buildflags',
            '//third_party/dragonbox:dragonbox': '@dragonbox//:dragonbox',
            '//third_party/fast_float:fast_float': '@fast_float//:fast_float',
            '//third_party/fp16:fp16': '@fp16//:fp16',
            '//third_party/highway:libhwy': '@highway//:hwy',
            '//third_party/libaom:libaomrc': ':aom_rc_public',
            '//third_party/libvpx:libvpxrc': '@libvpx//:vpx_rc',
            '//third_party/libzip:libzip': '@libzip//:libzip',
            '//third_party/libzip:libzip_public_headers': '@libzip//:libzip',
            '//third_party/flatbuffers:flatc': '@flatbuffers//:flatc',
            '//third_party/perfetto:libperfetto': ':perfetto_runtime',
            '//third_party/rust/temporal_capi:temporal_capi': '//native/rust:temporal_capi_cpp',
        })
    if layer == 'browser_services':
        reused.update({
            '//components/variations/proto:proto': ':variations_proto',
            '//third_party/perfetto:libperfetto': ':perfetto_runtime',
            '//third_party/perfetto/include/perfetto/ext/ipc:ipc': ':perfetto_runtime',
            '//third_party/perfetto/include/perfetto/protozero:protozero': ':perfetto_proto_cpp',
            '//third_party/perfetto/protos/perfetto/trace/chrome:minimal_complete_lite': ':perfetto_proto_cpp',
            '//base/tracing/protos:chrome_track_event_zero': ':perfetto_proto_cpp',
            '//third_party/snappy:snappy': '@snappy//:snappy',
            '//third_party/protobuf:protoc_lib': '@protobuf//:protoc_lib',
            '//build:chromecast_buildflags': ':all_buildflags',
            '//build/win:default_exe_manifest': ':all_buildflags',
        })
    if layer == 'linux_buffers':
        reused['//build/config/linux/libdrm:libdrm'] = ':libdrm'
    if layer == 'gfx':
        reused.update({
            '//base:base_static': ':base_base_static',
            '//build:blink_buildflags': ':all_buildflags',
            '//build:chromecast_buildflags': ':all_buildflags',
            '//gpu/vulkan:buildflags': ':all_buildflags',
            '//device/vr/buildflags:buildflags': ':all_buildflags',
        })
    if layer == 'dawn_native':
        reused.update({
            '//third_party/spirv-tools/src:spvtools_opt': '@spirv_tools//:spirv_tools_opt',
            '//third_party/spirv-tools/src:spvtools_val': '@spirv_tools//:spirv_tools',
        })
    if layer == 'vulkan_validation':
        reused.update({
            '//third_party/spirv-tools/src:spvtools': '@spirv_tools//:spirv_tools',
            '//third_party/spirv-tools/src:spvtools_val': '@spirv_tools//:spirv_tools',
            '//third_party/spirv-tools/src:spvtools_opt': '@spirv_tools//:spirv_tools_opt',
            '//third_party/spirv-tools/src:spvtools_link': '@spirv_tools//:spirv_tools_link',
        })
    if layer in ('swiftshader', 'browser'):
        reused.update({
            '//third_party/swiftshader/third_party/SPIRV-Headers:spv_headers': ':spirv_headers',
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_headers': '@spirv_tools//:spirv_tools',
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools': '@spirv_tools//:spirv_tools',
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_val': '@spirv_tools//:spirv_tools',
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_opt': '@spirv_tools//:spirv_tools_opt',
            '//third_party/wayland:wayland_client': '@wayland//:wayland_client',
        })
    if layer == 'angle_runtime':
        reused.update({
            '//third_party/vulkan-loader/src:libvulkan': ':vulkan_loader',
            '//third_party/spirv-headers/src:spv_headers': ':spirv_headers',
            '//third_party/spirv-tools/src:spvtools_headers': '@spirv_tools//:spirv_tools',
            '//third_party/spirv-tools/src:spvtools_val': '@spirv_tools//:spirv_tools',
            '//third_party/wayland:wayland_client': '@wayland//:wayland_client',
            '//third_party/wayland:wayland_egl': '@wayland//:wayland_egl',
            '//build/config/linux/libdrm:libdrm': ':libdrm',
            '//third_party/dawn/include/dawn:headers': ':dawn_cpp_headers',
            '//third_party/dawn/src/dawn/native:native': ':dawn_native_library',
            '//third_party/dawn/src/dawn:proc': ':dawn_proc',
            '//third_party/zlib/google:compression_utils_portable': ':zlib_compression_utils_portable',
        })
    if layer in ('media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        reused.update({
            '//third_party/flac:flac': '@flac//:flac',
            '//third_party/libwebm:libwebm': '@libwebm//:libwebm',
            '//third_party/libvpx:libvpx': ':libvpx_public',
            '//third_party/libaom:libaom': ':aom_public',
            '//third_party/dav1d:dav1d': '@dav1d//:dav1d',
            '//third_party/opus:opus': '@opus//:opus',
            '//third_party/fp16:fp16': '@fp16//:fp16',
            '//third_party/crc32c:crc32c': '@crc32c//:crc32c',
            '//third_party/snappy:snappy': '@snappy//:snappy',
            '//media/filters:symphonia_glue': '//native/rust:symphonia_glue',
            '//third_party/rust/symphonia/v0_5:lib': '//native/rust:symphonia',
            '//build/rust:cxx_cppdeps': '//third_party/rust/chromium_crates_io/vendor/cxx-v1:core-lib',
            '//mojo/public/cpp/base:base': ':mojo_base_types',
            '//build:chromecast_buildflags': ':all_buildflags',
            '//components/system_media_controls/linux/buildflags:buildflags': ':all_buildflags',
            '//base/allocator:buildflags': ':all_buildflags',
        })
    if layer == 'gpu_client':
        reused.update({
            '//gpu/vulkan:buildflags': ':all_buildflags',
            '//media:media_buildflags': ':all_buildflags',
            '//mojo/public/cpp/base:base': ':mojo_base_types',
        })
    if layer in ('ffmpeg', 'browser'):
        reused['//third_party/opus:opus'] = ':ffmpeg_opus'
    if layer == 'ml':
        reused.update({
            '//third_party/pthreadpool:pthreadpool': ':pthreadpool',
            '//third_party/fp16:fp16': '@fp16//:fp16',
            '//third_party/flatbuffers:flatc': '@flatbuffers//:flatc',
        })
    font_repositories = {
        'third_party/breakpad/breakpad/': '@chromium_breakpad//:',
        'third_party/microsoft_webauthn/src/': '@chromium_microsoft_webauthn//:',
        'ui/gl/resources/angle-metal/': '@chromium_angle_metal_shaders//:',
        'third_party/google_toolbox_for_mac/src/': '@chromium_google_toolbox_for_mac//:',
        'third_party/dawn/third_party/dxc/': '@chromium_dxc//:',
        'third_party/spirv-tools/src/': '@spirv_tools//:',
        'third_party/spirv-headers/src/': '@spirv_headers//:',
        'third_party/cros_system_api/': '@chromium_cros_system_api//:',
        'third_party/devtools-frontend/src/': '@chromium_devtools_frontend//:',
        'third_party/search_engines_data/resources/': '@chromium_search_engines_data//:',
        'third_party/cld_3/src/': '@chromium_cld3//:',
        'third_party/emoji-segmenter/src/': '@chromium_emoji_segmenter//:',
        'third_party/ots/src/': '@chromium_ots//:',
        'third_party/material_color_utilities/src/': '@chromium_material_color_utilities//:',
        'third_party/smhasher/src/': '@chromium_smhasher//:',
        'third_party/libphonenumber/dist/': '@chromium_libphonenumber//:',
        'third_party/crabbyavif/src/': '@chromium_crabbyavif//:',

        'third_party/webrtc/': '@chromium_webrtc//:',
        'third_party/libsrtp/': '@chromium_libsrtp//:',
        'third_party/federated_compute/src/': '@chromium_federated_compute//:',
        'media/cdm/api/': '@chromium_cdm_api//:',
        'third_party/libgav1/src/': '@chromium_libgav1//:',
        'third_party/leveldatabase/src/': '@chromium_leveldatabase//:',
        'third_party/ffmpeg/': '@chromium_ffmpeg//:',
        **{'third_party/' + project + '/src/': '@chromium_' + project + '//:'
           for project in ['tflite', 'xnnpack', 'ruy', 'eigen3', 'gemmlowp', 'farmhash', 'neon_2_sse']},
        'third_party/pthreadpool/src/': '@chromium_pthreadpool//:',
        'v8/': '@chromium_v8//:v8/',
        'third_party/libyuv/': '@chromium_libyuv//:',
        'third_party/wayland-protocols/src/': '@chromium_wayland_protocols//:',
        'third_party/wayland-protocols/kde/': '@chromium_kde_protocols//:',
        'third_party/protobuf-javascript/src/': '@chromium_protobuf_javascript//:',
        'third_party/vulkan-tools/src/': '@chromium_vulkan_tools//:',
        'third_party/vulkan-headers/src/': '@vulkan_headers//:',
        'third_party/perfetto/include/': '@perfetto//:include/',
        'third_party/angle/': '@chromium_angle//:third_party/angle/',
        'third_party/vulkan_memory_allocator/': '@chromium_vma//:',

        'third_party/swiftshader/': '@chromium_swiftshader//:',
        'third_party/vulkan-utility-libraries/src/': '@chromium_vulkan_utility//:',
        'third_party/vulkan-validation-layers/src/': '@chromium_vulkan_validation//:',
        'third_party/vulkan-loader/src/': '@chromium_vulkan_loader//:',
        'third_party/dawn/third_party/khronos/EGL-Registry/': '@chromium_egl_registry//:',
        'third_party/dawn/third_party/khronos/OpenGL-Registry/': '@chromium_opengl_registry//:',

        'third_party/libdrm/src/': '@chromium_libdrm//:',
        'third_party/libsync/src/': '@chromium_libsync//:',
        'third_party/skia/': '@chromium_skia//:third_party/skia/',
        'third_party/libjpeg_turbo/': '@chromium_jpeg//:',
        'third_party/libwebp/src/': '@chromium_webp//:',
        'third_party/wuffs/src/': '@chromium_wuffs//:',
        'third_party/freetype/src/': '@chromium_freetype//:',
        'third_party/harfbuzz-ng/src/': '@chromium_harfbuzz//:',
        'third_party/fontconfig/src/': '@chromium_fontconfig//:',
        'third_party/catapult/': '@chromium_catapult//:',
        'third_party/openscreen/src/': '@chromium_openscreen//:',
        'third_party/pdfium/': '@chromium_pdfium//:',
        'third_party/xdg-utils/': '@chromium_xdg_utils//:',
        'third_party/libaddressinput/src/': '@chromium_libaddressinput//:',
        'third_party/ink_stroke_modeler/src/': '@chromium_ink_stroke_modeler//:',
        'third_party/ink/src/': '@chromium_ink//:',
        'third_party/dom_distiller_js/dist/': '@chromium_dom_distiller_js//:',
        'third_party/content_analysis_sdk/src/': '@chromium_content_analysis_sdk//:',
        'third_party/anonymous_tokens/src/': '@chromium_anonymous_tokens//:',
    }
    mojo_catalog = ROOT / 'native/mojo_targets.json'
    mojo_targets = json.loads(mojo_catalog.read_text()) if mojo_catalog.exists() else {}
    def name(label):
        return layer + '_' + hashlib.sha256(label.encode()).hexdigest()[:16]
    graph = json.loads(gzip.decompress(args.graph.read_bytes()))
    targets = graph['targets']
    pinned_vulkan = layer == 'browser' and graph['build_settings']['default_toolchain'].startswith('//build/toolchain/win:')
    if layer == 'browser':
        roots += browser_runtime_roots(graph)
        roots += [label for label, target in targets.items()
                  if target.get('script') == '//tools/grit/grit.py']
    interface_provider_sources = {
        BUILD + 'gen/services/service_manager/public/mojom/interface_provider.mojom.cc',
        BUILD + 'gen/services/service_manager/public/mojom/interface_provider.mojom-shared.cc',
    }
    interface_provider_suffixes = tuple(path.removeprefix(BUILD) for path in interface_provider_sources)
    if layer == 'media' and '//media/filters:symphonia_glue_cxx_generated' not in targets:
        roots.remove('//media/filters:symphonia_glue_cxx_generated')
    if layer == 'fonts' and '//third_party/fontconfig:fontconfig' not in targets:
        roots.remove('//third_party/fontconfig:fontconfig')
    for label in ['//build/config/mac:sdk_inputs', '//build/win:runtime_libs']:
        if label not in targets:
            continue
        target = targets[label]
        if target['type'] != 'group' or any(target.get(key) for key in ('deps', 'sources', 'outputs', 'data_deps', 'data', 'inputs')):
            raise ValueError('Toolchain inputs need an explicit provider: ' + label)
        extra_provided.add(label)
    flag_hashes = set(re.findall(r'name = "flags_([0-9a-f]{16})"',
                                (ROOT / 'bcr/overlay/native/buildflags.bzl').read_text()))
    for label in targets:
        if hashlib.sha256(label.encode()).hexdigest()[:16] in flag_hashes:
            reused.setdefault(label, ':all_buildflags')
    if layer in ('compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        for variant, label in MOJO_RUNTIME_TARGETS.items():
            if variant != 'unix_address':
                reused.setdefault(label, ':mojo_' + variant)
        # Existing SDK compiles this entire original Perfetto dependency closure.
        pending = ['//third_party/perfetto:libperfetto']
        seen = set()
        while pending:
            label = pending.pop()
            if label in seen or not label.startswith('//third_party/perfetto'):
                continue
            seen.add(label)
            target = targets[label]
            if target['type'] != 'executable':
                pending.extend(target.get('deps', []))
            if target['type'] in ('group', 'source_set', 'static_library'):
                reused[label] = ':perfetto_runtime'
        reused.update({
            '//third_party/jsoncpp:jsoncpp': '@jsoncpp//:jsoncpp',
            '//components/variations/proto:proto': ':variations_proto',
            '//mojo/public/cpp/base:base': ':mojo_base_types',
            '//components/cbor:cbor': ':cbor',
        })
    if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        rust_targets = set(re.findall(r'name = "(crate_[0-9a-f]{16})"',
                                     (ROOT / 'bcr/overlay/native/rust/crates.bzl').read_text()))
        for label, target in targets.items():
            rust_name = 'crate_' + hashlib.sha256(label.encode()).hexdigest()[:16]
            if target['type'] in ('rust_library', 'rust_proc_macro') and rust_name in rust_targets:
                reused[label] = '//native/rust:' + rust_name
        reused.update({
            '//third_party/blink/renderer/platform:font_format_check': '//native/rust:font_format_check',
            '//third_party/blink/common/rust_crash:rs': '//native/rust:blink_rust_crash',
            '//third_party/crabbyavif:crabbyavif': '//native/rust:crabbyavif',
            '//third_party/crabbyavif:crabbyavif_libyuv_sys': '//native/rust:crabbyavif_libyuv_sys',
            '//third_party/crabbyavif:crabbyavif_dav1d_sys': '//native/rust:crabbyavif_dav1d_sys',
            '//third_party/highway:libhwy': '@highway//:hwy',
            '//third_party/libaom:libaomrc': ':aom_rc_public',
            '//third_party/libvpx:libvpxrc': '@libvpx//:vpx_rc',
            '//third_party/libzip:libzip': '@libzip//:libzip',
            '//third_party/libzip:libzip_public_headers': '@libzip//:libzip',
            '//third_party/flatbuffers:flatc': '@flatbuffers//:flatc',
            '//third_party/icu:icudata': '//third_party/icu:icu',
            '//third_party/icu:icuuc': '//third_party/icu:icu',
            '//third_party/icu:icui18n': '//third_party/icu:icu',
            '//third_party/zstd:compress': '@zstd//:zstd',
        })
    if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        for label, target in targets.items():
            if label.partition('(')[0] == '//services/service_manager/public/mojom:mojom':
                additional = [path for path in target.get('sources', [])
                              if path.endswith('.cc') and not path.endswith(interface_provider_suffixes)]
                if additional:
                    reused.pop(label, None)
    needs_native_providers = any(
        '(' in label and re.fullmatch(r':[a-z][a-z0-9_]*_[0-9a-f]{16}',
                                     reused.get(label.partition('(')[0], ''))
        for label in targets)
    reuse_host_targets(targets, reused, extra_provided,
                       native_library_providers(args.native_overlay) if needs_native_providers else None)
    existing_actions = {label for label in targets if hashlib.sha256(label.encode()).hexdigest()[:16] in existing_action_hashes}
    reused_asset_roots = {}
    for label in browser_asset_roots:
        if label not in existing_actions:
            continue
        provider = existing_asset_providers.get(label)
        if not provider:
            provider = ':' + existing_action_names[hashlib.sha256(label.encode()).hexdigest()[:16]]
        reused_asset_roots[label] = provider
    runtime_edges = {}
    if layer in ('dawn_native', 'angle_runtime', 'linux_ui', 'browser'):
        catalog_name = {'linux_ui': 'gl', 'angle_runtime': 'angle', 'dawn_native': 'dawn', 'browser': 'browser'}[layer]
        catalog = json.loads((ROOT / ('native/' + catalog_name + '_runtime_edges.json')).read_text())
        if hashlib.sha256(args.graph.read_bytes()).hexdigest() != catalog['graph_sha256']:
            raise ValueError('runtime edges belong to another graph')
        if hashlib.sha256((args.source_root / catalog['source']).read_bytes()).hexdigest() != catalog['source_sha256']:
            raise ValueError('runtime edges belong to another source revision')
        for path, digest in catalog.get('additional_sources', {}).items():
            if hashlib.sha256((args.source_root / path).read_bytes()).hexdigest() != digest:
                raise ValueError('runtime edges belong to another source revision: ' + path)
        runtime_edges = catalog['runtime_deps']
        for label, edges in runtime_edges.items():
            if not set(edges).issubset(targets[label]['deps']):
                raise ValueError('unknown runtime dependency: ' + label)
    selected = {}
    stack = list(roots)
    boundaries = set()
    while stack:
        label = stack.pop()
        reuse_action = label in existing_actions and not (
            layer == 'browser' and targets[label].get('script') == '//tools/grit/grit.py')
        if label in selected or label in reused or label in PROVIDED or label in extra_provided or reuse_action:
            continue
        if not label.startswith(prefixes):
            boundaries.add(label)
            continue
        target = targets[label]
        selected[label] = target
        if label not in mojo_targets and (target.get('script') not in ('//third_party/rust/cxx/chromium_integration/run_cxxbridge.py', '//tools/grit/grit.py', '//build/write_buildflag_header.py') or layer == 'browser' and target.get('script') == '//tools/grit/grit.py'):
            stack.extend(dep for dep in target.get('deps', [])
                         if layer == 'browser' or dep not in runtime_edges.get(label, []))
    if boundaries:
        raise ValueError('unmapped network dependencies: ' + repr(sorted(boundaries)))
    unpack = lambda value: graph['pool'][value['pool']] if isinstance(value, dict) else value
    exports = {}
    overlay = ROOT / "bcr/overlay"
    declare_message_compiler_assets(selected, args.source_root)
    generated_paths = {path for target in targets.values() for path in target.get('outputs', [])}

    bundle_outputs = {target['bundle_data']['root_dir_output']: ':' + name(label) + '_bundle'
                      for label, target in selected.items() if target['type'] == 'create_bundle'}

    bundle_members = {output: source for target in selected.values()
                      if target['type'] == 'create_bundle'
                      for output, source in zip(target['outputs'][:-1], target['bundle_data']['source_files'])}

    @cache
    def file_label(path):
        if path in bundle_members and bundle_members[path] != path:
            return file_label(bundle_members[path])
        if path in bundle_outputs:
            return bundle_outputs[path]
        if path.startswith(BUILD):
            return ':' + path.removeprefix(BUILD)
        if not path.startswith('//'):
            raise ValueError('not a Chromium input: ' + path)
        relative = path[2:]
        if relative.startswith('build/win_toolchain/Windows Kits/10/'):
            filename = Path(relative).name.lower()
            if filename in ('d3dcompiler_47.dll', 'dxil.dll'):
                return '@chromium_windows_sdk_runtime//:' + filename.removesuffix('.dll')
        if relative.startswith('third_party/node/node_modules/'):
            return '@chromium_node_modules//:node_modules/' + relative.removeprefix('third_party/node/node_modules/')
        if relative.startswith('third_party/perfetto/protos/'):
            return '@perfetto//:' + relative.removeprefix('third_party/perfetto/')
        if relative == 'third_party/icu/common/icudtl.dat':
            return '@chromium_icu//:common/icudtl.dat'
        generated = BUILD + 'gen/' + relative
        if not (args.source_root / relative).is_file() and generated in generated_paths:
            return ':gen/' + relative
        if relative in ('gpu/webgpu/dawn_commit_hash.h', 'skia/ext/skia_commit_hash.h',
                        'gpu/config/gpu_lists_version.h'):
            return ':gen/' + relative
        if relative == 'gpu/webgpu/DAWN_VERSION':
            return ':metadata/gpu/webgpu/DAWN_VERSION'
        for prefix, repository in font_repositories.items():
            if relative.startswith(prefix):
                return repository + relative.removeprefix(prefix)
        if relative.startswith('third_party/dawn/'):
            return '@chromium_dawn//:' + relative
        if relative.startswith(QUICHE):
            return '@chromium_quiche//:' + relative
        if relative == 'third_party/protobuf/src/google/protobuf/descriptor.proto':
            return '@protobuf//:descriptor_proto_srcs'
        if not (args.source_root / relative).is_file():
            raise ValueError('missing network input: ' + relative)
        package = Path(relative).parent
        while not ((overlay / package / 'BUILD.bazel').is_file()
                   or (args.source_root / package / 'BUILD.bazel').is_file()
                   or (args.source_root / package / 'BUILD').is_file()):
            package = package.parent
        package_name = '' if str(package) == '.' else package.as_posix()
        local = Path(relative).relative_to(package).as_posix()
        exports.setdefault(package_name, set()).add(local)
        return '//' + package_name + ':' + local

    copies = {}
    for label, target in selected.items():
        if target["type"] != "copy":
            continue
        sources = target.get("sources", [])
        outputs = target.get("outputs", [])
        if len(sources) != len(outputs):
            raise ValueError("copy source/output mismatch: " + label)
        copies[label] = dict(name=name(label),
                            srcs={file_label(p): p[2:] for p in sources},
                            outputs={out.removeprefix(BUILD): src[2:] for src, out in zip(sources, outputs)})
    actions = {}
    libraries = {}
    shared_headers = set()
    scan_sources = set()
    reused_actions = set(existing_actions)
    for label, target in selected.items():
        if target['type'] == 'generated_file':
            outputs = target.get('outputs', [])
            if not outputs or any(path not in graph['generated_files'] for path in outputs):
                raise ValueError('uncaptured GN metadata: ' + label)
            reused_actions.add(label)
            existing_actions.add(label)
            continue
        if target['type'] not in ('action', 'action_foreach'):
            continue
        if target.get('script') == '//third_party/rust/cxx/chromium_integration/run_cxxbridge.py':
            for source in target.get('sources', []):
                content = (args.source_root / source[2:]).read_text()
                for header in re.findall(r'\binclude!\(\s*"([^"\n]+)"\s*\)', content):
                    if not (args.source_root / header).is_file():
                        directories = list(unpack(target.get('include_dirs', [])))
                        parent = posixpath.dirname(source)
                        while parent.startswith('//'):
                            directories.append(parent)
                            if parent == '//':
                                break
                            parent = posixpath.dirname(parent)
                        candidates = {directory[2:].rstrip('/') + '/' + header
                                      for directory in directories
                                      if directory.startswith('//')
                                      and (args.source_root / directory[2:] / header).is_file()}
                        if len(candidates) != 1:
                            raise ValueError('unresolved or ambiguous CXX include: ' + header)
                        header = candidates.pop()
                    shared_headers.add(file_label('//' + header))
                    scan_sources.add('//' + header)
            reused_actions.add(label)
            continue
        if label in mojo_targets or target['script'] in ('//build/write_buildflag_header.py', '//tools/grit/grit.py'):
            reused_actions.add(label)
            continue
        actions[label] = target

    def deps_for(label):
        result = []
        for dep in selected[label].get('deps', []):
            if dep in runtime_edges.get(label, []):
                continue
            if dep in reused:
                if reused[dep] != ":all_buildflags":
                    result.append(reused[dep])
            elif dep in PROVIDED or dep in extra_provided or dep in copies or dep in actions or dep in reused_actions or dep in mojo_targets:
                continue
            elif dep in selected:
                result.append(':' + name(dep))
            else:
                raise ValueError('unmapped dependency: ' + dep)
        return sorted(set(result))

    for label, target in sorted(selected.items()):
        if label in mojo_targets or target['type'] in ('action', 'action_foreach', 'copy', 'generated_file'):
            continue
        if target['type'] not in ('source_set', 'static_library', 'shared_library', 'group', 'executable', 'bundle_data', 'create_bundle'):
            raise ValueError('unmapped network target type: ' + label)
        public = target.get('public', [])
        paths = target.get('sources', []) + (public if isinstance(public, list) else [])
        scan_sources.update(p for p in paths if not p.startswith(BUILD) and not p[2:].startswith(QUICHE)
                            and p.endswith(('.cc', '.c', '.cpp', '.cxx', '.mm', '.m', '.h', '.hh', '.hpp', '.hxx', '.inl', '.inc', '.S', '.s', '.asm')))
        sources = [file_label(p) for p in target.get('sources', []) if p.endswith(('.cc', '.c', '.cpp', '.cxx', '.S', '.s')) or (layer in ('browser_v8', 'paint') and p.endswith('.asm')) or (layer in ('codecs', 'ffmpeg') and p.endswith('.o')) or (layer == 'paint' and p.endswith('.obj') and not p.startswith(BUILD))]
        shared_interface = any(path.endswith(interface_provider_suffixes) for path in target.get('sources', []))
        if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') and shared_interface:
            owned = {file_label(path) for path in target.get('sources', [])
                     if path.endswith(interface_provider_suffixes)}
            sources = [source for source in sources if source not in owned]
        objcxx_sources = [file_label(p) for p in target.get('sources', []) if p.endswith('.mm')]
        objc_sources = [file_label(p) for p in target.get('sources', []) if p.endswith('.m')]
        resource_sources = [file_label(p) for p in target.get('sources', []) if p.endswith('.rc')]
        # Vulkan's native BCR provider owns these public dependency headers.
        if layer == 'vulkan_validation':
            paths = [p for p in paths if not p.startswith('//third_party/vulkan-headers/src/include/')]
        headers = [file_label(p) for p in paths if p.endswith(('.h', '.hh', '.hpp', '.hxx', '.inl', '.inc'))]
        for field in ('cflags', 'cflags_cc', 'cflags_c'):
            for flag in unpack(target.get(field, [])):
                if flag.startswith('/FI'):
                    header = '//' + flag[3:].removeprefix('../../')
                    headers.append(file_label(header))
                    scan_sources.add(header)
        # GN may export a C fragment for inclusion without compiling it.
        headers.extend(file_label(p) for p in (public if isinstance(public, list) else [])
                       if p.endswith(('.c', '.cc', '.cpp', '.cxx')) and p not in target.get('sources', []))
        if label == '//third_party/libaddressinput:util':
            # localization.cc includes GRIT's generated C++ message map.
            headers.append(file_label(BUILD + 'gen/third_party/libaddressinput/en_messages.cc'))
        shared_headers.update(p for p in headers if p.startswith('//:'))
        # GN action deps can supply included C++ fragments, not translation units.
        for dep in target.get('deps', []):
            if dep in copies or dep in actions or dep in reused_actions:
                headers.extend(file_label(p) for p in targets[dep]['outputs']
                               if p.endswith(('.h', '.inc', '.cc', '.def', '.gen')) and file_label(p) not in sources)
        copts, defines = compiler_configuration(graph, dict(target, cflags=target.get("cflags", []), cflags_cc=target.get("cflags_cc", []), defines=target.get("defines", [])))
        msvc = any(flag.startswith(('/W', '/std:')) for flag in copts)
        # Protobuf 33 permits incomplete member-pointer bases in constexpr metadata.
        if layer in ('network', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            copts = [p for p in copts if p != '-fcomplete-member-pointers']
        if layer == 'geometry' and '//skia:skia' in target.get('deps', []):
            # Skia's provider owns its public configuration.
            defines = [p for p in defines if not p.startswith('SK_')]
        includes = ['..', 'gen']
        includes += [p.removeprefix(BUILD) for p in unpack(target.get('include_dirs', []))
                     if p.startswith(BUILD)]
        if layer == 'skia':
            defines = [p.replace('../../skia/config/SkUserConfig.h', 'skia/config/SkUserConfig.h') for p in defines]
        if layer in ('fonts', 'codecs', 'skia', 'paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            defines = [p.replace(chr(92)+chr(34), chr(34)).replace(chr(34), chr(92)+chr(34)) for p in defines]
            includes += ['../' + p[2:].rstrip('/') for p in unpack(target.get('include_dirs', []))
                         if p.startswith(('//third_party/freetype/include/', '//third_party/fontconfig/include/', '//third_party/libpng/', '//third_party/libxml/'))]
        # ANGLE's initializer uses optional whitespace that clang-cl response files split.
        defines = [value.replace(' ', '')
                   if value.startswith('ANGLE_PRELOADED_D3DCOMPILER_MODULE_NAMES=') else value
                   for value in defines]
        if layer in ('paint', 'gfx'):
            includes += ['../' + p[2:].rstrip('/') for p in unpack(target.get('include_dirs', []))
                         if p.startswith(('//third_party/crashpad/', '//third_party/libdrm/', '//third_party/libsync/'))]
        if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            includes += ['../' + p[2:].rstrip('/') for p in unpack(target.get('include_dirs', []))
                         if p.startswith(('//third_party/utf/', '//third_party/woff2/',
                                          '//third_party/tensorflow-text/', '//third_party/tflite_support/',
                                          '//third_party/libva/', '//third_party/puffin/src/include/',
                                          '//third_party/brotli/include/', '//third_party/s2cellid/src/',
                                          '//third_party/tensorflow_models/src/research/seq_flow_lite/',
                                          '//third_party/tensorflow_models/shims/',
                                          '//third_party/sentencepiece/'))
                         or p in ('//third_party/', '//components/')]
        if layer == 'browser':
            owner = label.split(':', 1)[0].rstrip('/') + '/'
            # Keep local include configs; external repositories export their own.
            if owner not in ('//', '//third_party/'):
                includes += ['../' + p[2:].rstrip('/')
                             for p in unpack(target.get('include_dirs', []))
                             if p != '//' and (p.startswith(owner) or owner.startswith(p))
                             and not any(p[2:].startswith(prefix) for prefix in font_repositories)]
        dependencies = deps_for(label)
        if label == '//third_party/crashpad/crashpad/util:net':
            dependencies.append('@curl//:curl')
        if label.startswith('//ui/gtk:'):
            dependencies.append('@chromium_platform_headers//:gtk_headers')
        linkopts = []
        linker_inputs = []
        system_libraries = {
            **({
                'stdc++': '@chromium_platform_headers//:qt_stdlib_shared',
                **{'Qt' + version + part: '@chromium_platform_headers//:qt' + version
                   for version in ('5', '6') for part in ('Core', 'Gui', 'Widgets')},
            } if layer == 'browser' else {}),
            **({'cups': '@chromium_platform_headers//:cups'} if layer in ('content', 'browser') else {}),
            **({'atspi': '@chromium_platform_headers//:atspi_shared'} if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') else {}),
            **({'pci': '@chromium_pciutils//:pci', 'X11': '@libx11//:libx11', 'Xi': '@libxi//:libxi', 'Xext': '@libxext//:libxext', 'xcb': '@libxcb//:libxcb'} if layer in ('angle_runtime', 'x11', 'linux_buffers', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') else {}),
            **({'gbm': '@chromium_platform_headers//:gbm', 'xkbcommon': '@xkbcommon//:xkbcommon'} if layer in ('linux_buffers', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') else {}),
            **({'dbus-1': '@chromium_platform_headers//:dbus', 'udev': '@chromium_platform_headers//:udev', 'pango-1.0': '@chromium_platform_headers//:pango', 'pangocairo-1.0': '@chromium_platform_headers//:pango', 'cairo': '@chromium_platform_headers//:cairo_shared', 'harfbuzz': ':harfbuzz', 'atk-1.0': '@chromium_platform_headers//:atk', 'atk-bridge-2.0': '@chromium_platform_headers//:atk'} if layer in ('ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') else {}),
            'xshmfence': ':platform_xshmfence_link',
            'asound': '@chromium_platform_headers//:alsa',
            'z': '//third_party/zlib',
            'ffi_pic': '@libffi//:libffi', 'ffi': '@libffi//:libffi',
            'glib-2.0': '@glib//glib', 'gmodule-2.0': '@glib//gmodule',
            'gobject-2.0': '@glib//gobject', 'gio-2.0': '@glib//gio',
            # Since GLib 2.32, thread functions live in libglib itself.
            'gthread-2.0': '@glib//glib',
        }
        if layer in ('compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            system_libraries.update({
                original: ':compositor_' + native + '_link'
                for original, native in [
                    ('Xcomposite', 'xcomposite'), ('Xdamage', 'xdamage'),
                    ('Xfixes', 'xfixes'), ('Xrandr', 'xrandr'),
                    ('Xrender', 'xrender'), ('Xtst', 'xtst'), ('drm', 'drm')]
            })
        for library in unpack(target.get('libs', [])):
            if layer == 'geometry' and '//skia:skia' in target.get('deps', []) and library in ('expat', 'uuid'):
                # Skia owns these inherited link dependencies.
                continue
            if library.startswith('$LLVM_ROOT/'):
                continue  # Native LLVM supplies its matching compiler runtime.
            if layer == 'fonts' and library == 'uuid':
                dependencies.append('@libuuid//:uuid')
            elif layer in ('skia', 'paint', 'gfx', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') and library in ('uuid', 'expat'):
                dependencies.append('@libuuid//:uuid' if library == 'uuid' else '@libexpat//:libexpat')
            elif library in system_libraries:
                dependencies.append(system_libraries[library])
            elif library in ('nspr4', 'nss3', 'nssutil3', 'plc4', 'plds4', 'smime3'):
                dependencies.append('@nss//:nss')
            else:
                if '/' in library or library.startswith('-'):
                    raise ValueError('unmapped native link input: ' + library)
                linkopts.append('-DEFAULTLIB:' + library if msvc or library.lower().endswith('.lib') else '-l' + library)
        # LLVM owns compiler/runtime paths; retain captured linker hardening.
        linker_flags = iter(unpack(target.get('ldflags', [])))
        for option in linker_flags:
            if msvc:
                if option.upper().startswith('/PDBPAGESIZE:'):
                    linkopts.append(option)
                    continue
                # Bazel owns debug outputs; LLVM supplies its matching C++ runtime.
                if option.upper().startswith(('/NATVIS:', '/PDB', '/DEBUG', '/DEFAULTLIB:LIBCPMT.LIB')) or option == '/WX':
                    continue
                if option.lower().startswith('/manifestinput:'):
                    flag, path = option.split(':', 1)
                    if path.startswith('../../'):
                        logical = '//' + path.removeprefix('../../')
                    elif path.startswith('gen/'):
                        logical = BUILD + path
                    else:
                        raise ValueError('unmapped Windows manifest input: ' + path)
                    dependency = file_label(logical)
                    linker_inputs.append(dependency)
                    linkopts.append(flag + ':$(location ' + dependency + ')')
                    continue
                if option.endswith('.lib'):
                    option = '-DEFAULTLIB:' + option
                linkopts.append(option)
                continue
            if option in ('-isysroot', '--sysroot'):
                next(linker_flags)
                continue
            if layer == 'browser' and option.startswith(('-Wl,-order_file,', '-Wl,-exported_symbols_list,')):
                flag, path = option.rsplit(',', 1)
                if not path.startswith('../../'):
                    raise ValueError('unmapped linker input: ' + path)
                dependency = file_label('//' + path.removeprefix('../../'))
                linker_inputs.append(dependency)
                linkopts.append(flag + ',$(location ' + dependency + ')')
                continue
            if layer == 'browser' and option in ('-Wl,-order_file', '-Wl,-exported_symbols_list'):
                path = next(linker_flags).removeprefix('-Wl,')
                if not path.startswith('../../'):
                    raise ValueError('unmapped linker input: ' + path)
                dependency = file_label('//' + path.removeprefix('../../'))
                linker_inputs.append(dependency)
                linkopts.extend([option, '-Wl,$(location ' + dependency + ')'])
                continue
            if layer == 'browser' and option.startswith('-Wl,--version-script='):
                path = option.partition('=')[2]
                if not path.startswith('../../'):
                    raise ValueError('unmapped linker script: ' + path)
                script_label = file_label('//' + path.removeprefix('../../'))
                linker_inputs.append(script_label)
                linkopts.append('-Wl,--version-script=$(location ' + script_label + ')')
                continue
            if option in ('-Werror', '-nostdlib++') or option.startswith(
                    ('-fuse-ld=', '--target=', '--sysroot=')):
                continue
            linkopts.append(option)
        if target.get('toolchain', '').startswith('//build/toolchain/mac:'):
            for field, option in [('frameworks', '-framework'), ('weak_frameworks', '-weak_framework')]:
                for framework in unpack(target.get(field, [])):
                    linkopts.extend([option, framework.removesuffix('.framework')])
            linkopts = [shlex.quote(option) if any(character.isspace() for character in option)
                        and '$(location ' not in option else option for option in linkopts]
        if label.split('(', 1)[0] == '//third_party/libsecret:libsecret':
            includes.append('../third_party/libsecret')
            dependencies.append('@glib//gio')
        if layer == 'compositor' and label == '//third_party/webrtc/modules/desktop_capture:desktop_capture':
            dependencies.append('@chromium_libdrm//:webrtc_headers')
        if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') and shared_interface:
            dependencies.append(':mojo_interface_provider')
        if label == '//third_party/wtl:wtl':
            includes.append('../third_party/wtl/include')
            headers.extend(file_label('//' + path.relative_to(args.source_root).as_posix())
                           for path in sorted((args.source_root / 'third_party/wtl/include').glob('*.h')))
        kind = 'group' if target['type'] in ('bundle_data', 'create_bundle') else target['type']
        libraries[label] = dict(name=name(label), kind=kind, srcs=sources,
                                hdrs=sorted(set(headers)), copts=copts, defines=defines,
                                includes=sorted(set(includes)), deps=sorted(set(protobuf_plugin_dependencies(label, dependencies))),
                                linkopts=linkopts)
        if label.startswith('//third_party/ffmpeg:'):
            configurations = {path.removeprefix('//third_party/ffmpeg/').rstrip('/')
                              for path in unpack(target.get('include_dirs', []))
                              if path.startswith('//third_party/ffmpeg/chromium/config/')}
            if len(configurations) > 1:
                raise ValueError('ambiguous FFmpeg configuration: ' + label)
            if configurations:
                libraries[label]['ffmpeg_config'] = configurations.pop()
        dxc_includes = [path.removeprefix('//third_party/dawn/third_party/dxc/').rstrip('/')
                        for path in unpack(target.get('include_dirs', []))
                        if path.startswith('//third_party/dawn/third_party/dxc/')]
        if dxc_includes:
            libraries[label]['dxc_include_dirs'] = dxc_includes
        if label.startswith('//third_party/swiftshader/'):
            libraries[label]['swiftshader_include_dirs'] = [
                path.removeprefix('//third_party/swiftshader/').rstrip('/')
                for path in unpack(target.get('include_dirs', []))
                if path.startswith('//third_party/swiftshader/')]
        definitions = [path for path in target.get('sources', []) if path.endswith('.def')]
        if msvc and definitions and target['type'] in ('executable', 'shared_library'):
            if len(definitions) != 1:
                raise ValueError('multiple Windows export definitions: ' + label)
            libraries[label]['win_def_file'] = file_label(definitions[0])
        if resource_sources:
            libraries[label]['resource_srcs'] = resource_sources
            libraries[label]['resource_defines'] = unpack(target.get('defines', []))
            generated_assets = {path for dependency in target.get('deps', [])
                                for path in targets[dependency].get('outputs', [])
                                if path.endswith(('.bin', '.ico', '.bmp', '.cur', '.manifest', '.png'))}
            for resource in target.get('sources', []):
                if resource.endswith('.rc') and not resource.startswith(BUILD):
                    text = (args.source_root / resource[2:]).read_text(errors='replace')
                    for asset in re.findall(r'"([^"\r\n]+\.tlb)"', text, re.I):
                        candidate = BUILD + 'gen/' + asset.replace('\\', '/')
                        if candidate in generated_paths:
                            generated_assets.add(candidate)
            libraries[label]['resource_assets'] = {file_label(path):
                {file_label(asset): asset[2:] for asset in sorted({asset for asset in generated_assets
                    if asset.endswith('.tlb') or posixpath.dirname(asset) == posixpath.dirname(path)} | (
                    set() if path.startswith(BUILD) else resource_asset_inputs(args.source_root, path)))}
                for path in target.get('sources', []) if path.endswith('.rc')}
            libraries[label]['resource_include_roots'] = {file_label(path): str(Path(path[2:]).parent)
                for path in target.get('sources', []) if path.endswith('.rc')}
            if not sources and not objcxx_sources and not objc_sources:
                libraries[label]['defines'] = []
        if objc_sources:
            libraries[label]['objc_srcs'] = objc_sources
            libraries[label]['objc_copts'] = compiler_configuration(graph, target, 'cflags_objc')[0]
        if objcxx_sources:
            libraries[label]['objcxx_srcs'] = objcxx_sources
            libraries[label]['objcxx_copts'] = compiler_configuration(graph, target, 'cflags_objcc')[0]
        if label.startswith('//third_party/crashpad/crashpad/'):
            libraries[label]['private_includes'] = ['third_party/crashpad/crashpad']
        if label.partition('(')[0] == '//third_party/libusb:libusb':
            libraries[label]['private_includes'] = [path[2:].rstrip('/')
                for path in unpack(target.get('include_dirs', []))
                if path.startswith('//third_party/libusb/')]
        if layer == 'browser' and '//third_party/re2/src/' in unpack(target.get('include_dirs', [])):
            libraries[label]['include_roots'] = ['@re2//:re2']
        if label.partition('(')[0] == '//third_party/vulkan-utility-libraries/src:vulkan_layer_settings' and not pinned_vulkan:
            for field in ('srcs', 'hdrs', 'copts', 'defines', 'includes', 'linkopts'):
                libraries[label][field] = []
            libraries[label]['kind'] = 'group'
            libraries[label]['deps'] = [
                '@vulkan_utility_libraries//:vulkan_layer_settings',
                '@vulkan_utility_libraries//:vulkan_safe_struct',
            ]
        if pinned_vulkan and label.startswith('//third_party/vulkan-utility-libraries/src:'):
            libraries[label]['deps'].append('@chromium_vulkan_utility//:headers')
        if label.startswith('//third_party/swiftshader/'):
            libraries[label]['deps'].extend([
                '@chromium_swiftshader//:headers',
                '@spirv_tools//:chromium_headers',
            ])
        spirv_providers = {
            '//third_party/swiftshader/third_party/SPIRV-Headers:spv_headers': [
                '@spirv_headers//:spirv_c_headers',
                '@spirv_headers//:spirv_cpp_headers',
                '@spirv_headers//:spirv_cpp11_headers',
            ],
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_headers': ['@spirv_tools//:chromium_headers'],
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools': ['@spirv_tools//:spirv_tools'],
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_val': ['@spirv_tools//:spirv_tools'],
            '//third_party/swiftshader/third_party/SPIRV-Tools:spvtools_opt': ['@spirv_tools//:spirv_tools_opt'],
        }
        if pinned_vulkan:
            spirv_providers.update({
                '//third_party/spirv-headers/src:spv_headers': [
                    '@spirv_headers//:spirv_c_headers',
                    '@spirv_headers//:spirv_cpp_headers',
                    '@spirv_headers//:spirv_cpp11_headers',
                ],
                '//third_party/spirv-tools/src:spvtools_headers': ['@spirv_tools//:chromium_headers'],
                '//third_party/spirv-tools/src:spvtools': ['@spirv_tools//:spirv_tools'],
                '//third_party/spirv-tools/src:spvtools_val': ['@spirv_tools//:spirv_tools'],
                '//third_party/spirv-tools/src:spvtools_opt': ['@spirv_tools//:spirv_tools_opt'],
                '//third_party/spirv-tools/src:spvtools_link': ['@spirv_tools//:spirv_tools_link'],
            })
        if label.partition('(')[0] in spirv_providers:
            for field in ('srcs', 'hdrs', 'copts', 'defines', 'includes', 'linkopts'):
                libraries[label][field] = []
            libraries[label]['kind'] = 'group'
            libraries[label]['deps'] = spirv_providers[label.partition('(')[0]]
        if label.startswith('//third_party/spirv-tools/src:'):
            libraries[label]['deps'].append('@spirv_tools//:chromium_headers')
        if label.partition('(')[0] == '//third_party/vulkan-tools/src:VkICD_mock_icd':
            libraries[label]['deps'].append('@chromium_vulkan_tools//:headers')
        if label.startswith('//third_party/vulkan-validation-layers/src:'):
            libraries[label]['deps'].extend([
                '@chromium_vulkan_validation//:headers',
                '@chromium_platform_headers//:graphics',
                '@vulkan_headers//:vulkan_headers',
                '@chromium_vulkan_utility//:headers' if pinned_vulkan else '@vulkan_utility_libraries//:vulkan_utility_headers',
                '@spirv_headers//:spirv_cpp_headers',
            ])
        if label.startswith('//third_party/vulkan-loader/src:'):
            libraries[label]['deps'].extend([
                '@chromium_vulkan_loader//:headers',
                '@chromium_platform_headers//:graphics',
            ])
        if label.startswith(('//third_party/angle/', '//third_party/angle:')):
            libraries[label]['deps'].extend([
                '@chromium_angle//:headers',
                '@chromium_vma//:headers',
                '@chromium_platform_headers//:graphics',
                '@chromium_pciutils//:headers',
                '@spirv_headers//:spirv_cpp_headers',
            ])
        if layer == 'browser' and label.startswith(('//net:', '//net/')):
            libraries[label]['deps'].append(':network_headers')
        if layer == 'browser' and label.startswith('//third_party/ipcz/'):
            libraries[label]['deps'].append('@ipcz//:internal_headers')
        libraries[label]['deps'] = sorted(set(libraries[label]['deps']))
        if linker_inputs:
            libraries[label]['additional_linker_inputs'] = linker_inputs
        if layer == 'browser' and target['type'] in ('executable', 'shared_library'):
            libraries[label]['outputs'] = [path.removeprefix(BUILD) for path in target.get('outputs', [])]
        if layer in ('swiftshader', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            libraries[label]['asm_copts'] = compiler_configuration(graph, dict(target, cflags=target.get('asmflags', []), cflags_cc=[], defines=target.get('defines', [])))[0]
        if layer in ('paint', 'gfx'):
            libraries[label]['asm_copts'] = compiler_configuration(graph, dict(target, cflags=target.get('cflags', []), cflags_cc=target.get('cflags_asm', []), defines=target.get('defines', [])))[0]
        if layer in ('fonts', 'codecs', 'skia', 'paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'pthreadpool', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
            libraries[label]['c_copts'] = compiler_configuration(graph, dict(target, cflags=target.get('cflags', []), cflags_cc=target.get('cflags_c', []), defines=target.get('defines', [])))[0]

    # Capture included project headers omitted from GN source lists as well.
    forwarders = {
        'third_party/re2/src/re2/re2.h': 're2/re2.h',
        'third_party/zstd/src/lib/zstd.h': 'zstd.h',
        'third_party/zstd/src/lib/zstd_errors.h': 'zstd_errors.h',
        'third_party/simdutf/simdutf.h': 'simdutf.h',
        'third_party/brotli/include/brotli/decode.h': 'brotli/decode.h',
        'third_party/brotli/include/brotli/shared_dictionary.h': 'brotli/shared_dictionary.h',
    }
    own = ('net/', 'sql/', 'ui/base/glib/', 'base/version_info/',
           'components/miracle_parameter/', 'components/network_time/',
           'components/unexportable_keys/', 'components/sqlite_proto/',
           'components/performance_manager/scenario_api/', 'third_party/apple_apsl/')
    if layer == 'media':
        forwarders = {'third_party/snappy/src/snappy.h': 'snappy.h'}
        own = ('media/', 'gpu/ipc/service/', 'third_party/ffmpeg/', 'third_party/khronos/', 'components/pref_registry/', 'components/leveldb_proto/', 'components/keyed_service/core/', 'components/services/storage/public/', 'third_party/leveldatabase/', 'third_party/libgav1/', 'third_party/widevine/cdm/', 'ui/events/')
    if layer == 'blink_rust':
        forwarders = {}
        own = ('third_party/blink/common/rust_crash/', 'third_party/blink/renderer/platform/fonts/opentype/')
    if layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        forwarders = {}
        own = ('',)
    if layer == 'compositor':
        forwarders = {}
        own = ('cc/', 'gpu/', 'device/', 'ui/', 'components/', 'services/',
               'third_party/webrtc/', 'third_party/webrtc_overrides/',
               'third_party/libsrtp/', 'third_party/federated_compute/',
               'third_party/oak/', 'third_party/libsecret/', 'third_party/blink/')
    if layer == 'gpu_client':
        forwarders = {}
        own = ('gpu/', 'components/viz/common/', 'components/viz/client/', 'third_party/khronos/')
    if layer == 'ffmpeg':
        forwarders = {}
        own = ('third_party/ffmpeg/',)
    if layer == 'ml':
        forwarders = {}
        own = tuple('third_party/' + project + '/' for project in
                    ['tflite', 'xnnpack', 'ruy', 'eigen3', 'gemmlowp', 'farmhash', 'neon_2_sse', 'fft2d', 'ml_dtypes'])
    if layer == 'pthreadpool':
        forwarders = {}
        own = ('third_party/pthreadpool/',)
    if layer == 'browser_v8':
        forwarders = {'third_party/googletest/src/googletest/include/gtest/gtest_prod.h': 'gtest/gtest_prod.h'}
        own = ('v8/', 'third_party/zlib/google/')
    if layer == 'gpu_service':
        forwarders = {}
        for header in [args.source_root / 'gpu/gpu_export.h'] + sorted(
                header for directory in ['gpu/ipc/common', 'services/viz/public/cpp/compositing']
                for header in (args.source_root / directory).glob('*_mojom_traits.h')):
            logical = '//' + header.relative_to(args.source_root).as_posix()
            shared_headers.add(file_label(logical))
            scan_sources.add(logical)
        own = ('gpu/', 'components/metal_util/', 'components/gwp_asan/', 'components/viz/common/', 'components/persistent_cache/', 'components/crash/core/common/', 'ipc/', 'third_party/dawn/', 'third_party/libyuv/', 'services/viz/public/mojom/', 'services/viz/public/cpp/', 'services/webnn/public/mojom/', 'third_party/blink/public/common/', 'url/ipc/', 'ui/base/clipboard/')
    if layer == 'ozone':
        forwarders = {'third_party/re2/src/re2/re2.h': 're2/re2.h'}
        for header in sorted(header for directory in ['ui/gl/mojom', 'services/service_manager/public/cpp'] for header in (args.source_root / directory).glob('*_mojom_traits.h')):
            logical = '//' + header.relative_to(args.source_root).as_posix()
            shared_headers.add(file_label(logical))
            scan_sources.add(logical)
        own = ('ui/', 'gpu/config/', 'components/dbus/', 'components/headless/', 'components/url_formatter/', 'components/exo/wayland/protocol/', 'dbus/', 'device/udev_linux/', 'services/tracing/public/', 'services/service_manager/public/', 'gpu/vulkan/', 'ipc/', 'third_party/khronos/')
    if layer == 'linux_ui':
        forwarders = {'third_party/re2/src/re2/re2.h': 're2/re2.h'}
        for header in sorted((args.source_root / 'ui/gl/mojom').glob('*_mojom_traits.h')):
            logical = '//' + header.relative_to(args.source_root).as_posix()
            shared_headers.add(file_label(logical))
            scan_sources.add(logical)
        own = ('ui/', 'components/device_event_log/', 'components/headless/screen_info/', 'components/stylus_handwriting/win/', 'ipc/', 'third_party/khronos/')
    if layer == 'browser_services':
        forwarders = {'third_party/snappy/src/snappy.h': 'snappy/snappy.h'}
        own = ('services/metrics/public/', 'services/tracing/public/', 'components/prefs/', 'components/variations/', 'components/system_cpu/', 'components/tracing/', 'components/version_info/', 'sandbox/policy/mojom/', 'url/mojom/', 'third_party/metrics_proto/', 'third_party/protobuf-javascript/src/')
    if layer == 'linux_buffers':
        forwarders = {}
        own = ('ui/gfx/linux/', 'ui/ozone/public/')
    if layer == 'x11':
        forwarders = {}
        own = ('ui/gfx/x/', 'ui/events/', 'third_party/x11proto/', 'third_party/libx11/', 'third_party/libxcb-keysyms/')
        for action in actions.values():
            arguments = action.get('args', [])
            if '--header' in arguments:
                header = arguments[arguments.index('--header') + 1].strip(chr(34))
                shared_headers.add(file_label('//' + header))
                scan_sources.add('//' + header)
    if layer == 'gpu_protocol':
        forwarders = {}
        own = ('gpu/command_buffer/', 'gpu/GLES2/', 'components/viz/common/resources/', 'ui/gl/')
    if layer == 'vulkan_tools':
        forwarders = {}
        own = ('third_party/vulkan-tools/src/',)
    if layer == 'angle_runtime':
        forwarders = {}
        own = ('third_party/angle/', 'third_party/vulkan_memory_allocator/')
    if layer == 'swiftshader':
        forwarders = {}
        own = ('third_party/swiftshader/src/', 'third_party/swiftshader/include/',
               'third_party/swiftshader/third_party/marl/', 'third_party/swiftshader/third_party/subzero/',
               'third_party/swiftshader/third_party/llvm-subzero/', 'third_party/swiftshader/third_party/astc-encoder/')
    if layer == 'vulkan_validation':
        forwarders = {}
        own = ('third_party/vulkan-validation-layers/', 'third_party/vulkan-utility-libraries/')
    if layer == 'vulkan_loader':
        forwarders = {}
        own = ('third_party/vulkan-loader/',)
    if layer == 'gpu_protocol':
        reused['//third_party/angle:includes'] = '@chromium_angle//:headers'
    if layer in ('tint', 'dawn_native'):
        forwarders = {}
        own = ('third_party/dawn/',)
    if layer == 'gfx':
        forwarders = {}
        own = ('ui/gfx/', 'ui/base/resource/', 'components/viz/common/', 'components/crash/core/common/', 'third_party/libdrm/',
               'third_party/libsync/', 'third_party/zlib/google/')
    if layer == 'paint':
        forwarders = {}
        own = ('cc/', 'components/crash/core/common/', 'gpu/command_buffer/common/',
               'skia/public/', 'ui/gfx/', 'ui/base/', 'ui/linux/', 'ui/display/types/',
               'third_party/crashpad/crashpad/')
        # Generated Mojo headers include these original inline typemap adapters.
        for package in ['skia/public/mojom', 'ui/gfx/mojom']:
            for header in sorted((args.source_root / package).glob('*_mojom_traits.h')):
                logical = '//' + header.relative_to(args.source_root).as_posix()
                shared_headers.add(file_label(logical))
                scan_sources.add(logical)
    if layer == 'fonts':
        forwarders = {}
        own = ('third_party/freetype/', 'third_party/fontconfig/', 'third_party/harfbuzz-ng/', 'third_party/libpng/', 'third_party/libxml/')
    if layer == 'skia':
        forwarders = {}
        own = ('skia/', 'gpu/config/', 'ui/base/', 'third_party/skia/')
        for header in ['skia/config/SkUserConfig.h', 'skia/config/sk_ref_cnt_ext_debug.h', 'skia/config/sk_ref_cnt_ext_release.h']:
            shared_headers.add(file_label('//' + header))
            scan_sources.add('//' + header)
    if layer == 'codecs':
        forwarders = {}
        own = ('third_party/libjpeg_turbo/', 'third_party/libwebp/', 'third_party/wuffs/')
    if layer == 'dawn':
        forwarders = {}
        own = ('third_party/dawn/',)
    if layer == 'geometry':
        forwarders = {}
        own = ('ui/gfx/',)
    if layer == 'blink_modules':
        # Window bindings use this header-only origin-trial mixin.
        logical = '//third_party/blink/renderer/core/testing/origin_trials_test_global.h'
        shared_headers.add(file_label(logical))
        scan_sources.add(logical)
    for target in actions.values():
        for argument in target.get('args', []):
            header = argument.partition('=')[2] if '=' in argument else argument
            header = header.strip(chr(34)).removeprefix('../../')
            if header.endswith(('.h', '.hh', '.hpp', '.hxx', '.inc')) and (args.source_root / header).is_file():
                logical = '//' + header
                shared_headers.add(file_label(logical))
                scan_sources.add(logical)
        scan_sources.update(path for path in target.get('inputs', [])
                            if not path.startswith(BUILD)
                            and Path(path).suffix in ('.tmpl', '.template', '.fragment', '.in', '.py'))
        if target['script'] == '//tools/json_to_struct/json_to_struct.py':
            schema = next(value.split('=', 1)[1] for value in target['args'] if value.startswith('--schema='))
            content = (args.source_root / schema.removeprefix('../../')).read_text()
            for headers in re.findall(r'"headers"\s*:\s*\[([^\]]*)\]', content, re.S):
                for header in re.findall(r'"([^"\n]+)"', headers):
                    shared_headers.add(file_label('//' + header))
                    scan_sources.add('//' + header)
    include_search = []
    if layer in ('fonts', 'codecs', 'skia', 'paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        include_search = sorted({p[2:] for target in selected.values()
                                 for p in unpack(target.get('include_dirs', []))
                                 if p.startswith('//') and not p.startswith(BUILD)})
    scanned = set()
    if layer in ('compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        typemap_inputs = set()
        for label in selected:
            mappings = targets.get(label.split('__')[0] + '__type_mappings', {})
            typemap_inputs.update(p for p in mappings.get('inputs', [])
                                  if p.endswith('.typemap_config'))
        for path in sorted(typemap_inputs):
            for mapping in json.loads(graph['generated_files'][path]):
                for header in (mapping.get('traits_headers', []) + mapping.get('traits_private_headers', [])
                               + mapping.get('public_headers', [])):
                    source = '//' + header
                    if not (args.source_root / header).is_file() and BUILD + 'gen/' + header in generated_paths:
                        source = BUILD + 'gen/' + header
                    shared_headers.add(file_label(source))
                    if not source.startswith(BUILD):
                        scan_sources.add(source)
    resolve_header = header_resolver(args.source_root, include_search)
    while scan_sources:
        path = scan_sources.pop()
        if path in scanned:
            continue
        scanned.add(path)
        relative = path[2:]
        if not (args.source_root / relative).is_file():
            continue
        # Preserve legacy comment bytes while scanning include directives.
        content = (args.source_root / relative).read_text(errors='surrogateescape')
        pattern = r'^\s*#\s*include\s*[<"]([^>"\n]+)[>"]' if layer in ('fonts', 'codecs', 'skia', 'paint', 'gfx', 'tint', 'dawn_native', 'vulkan_loader', 'vulkan_validation', 'swiftshader', 'angle_runtime', 'vulkan_tools', 'gpu_protocol', 'x11', 'linux_buffers', 'browser_services', 'linux_ui', 'ozone', 'gpu_service', 'browser_v8', 'ml', 'ffmpeg', 'gpu_client', 'media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') else r'^\s*#\s*include\s*"([^"\n]+)"'
        for include in re.findall(pattern, content, re.M):
            if layer in ('media', 'compositor', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
                for prefix in ['third_party/opus/src/include/', 'third_party/libvpx/source/libvpx/',
                               'third_party/libaom/source/libaom/', 'third_party/dav1d/libdav1d/include/',
                               'third_party/crc32c/src/include/', 'third_party/fp16/src/include/',
                               'third_party/re2/src/', 'third_party/jsoncpp/source/include/',
                               'third_party/libzip/src/lib/', 'third_party/flatbuffers/src/include/',
                               'third_party/highway/src/', 'third_party/libxslt/src/', 'third_party/fast_float/src/include/']:
                    if include.startswith(prefix):
                        forwarders[include] = include.removeprefix(prefix)
            if layer == 'geometry' and include.startswith('third_party/skia/'):
                forwarders[include] = include.removeprefix('third_party/skia/')
            if include.startswith('third_party/protobuf/src/'):
                forwarders[include] = include.removeprefix('third_party/protobuf/src/')
            candidate = resolve_header(relative, include)
            if candidate is not None:
                project = posixpath.normpath(candidate)
                if (project.startswith(own)
                        and not (layer == 'browser' and project.startswith('third_party/icu/'))
                        and not project.startswith((
                        QUICHE, 'third_party/protobuf/', 'third_party/perfetto/',
                        'third_party/vulkan-headers/', 'third_party/highway/', 'third_party/libxslt/', 'third_party/fast_float/', 'third_party/flac/'))):
                    shared_headers.add(file_label('//' + project))
                    scan_sources.add('//' + project)
    for old, canonical in forwarders.items():
        path = overlay / ('native/' + layer + '_forwarders') / old
        path.parent.mkdir(parents=True, exist_ok=True)
        opening, closing = ('<', '>') if '/' not in canonical else ('"', '"')
        path.write_text('#pragma once\n#include ' + opening + canonical + closing + '\n')

    # Original scripts import these Python modules; declare their complete runtime.
    python_support = sorted('//'+str(p.relative_to(args.source_root))
                            for directory in ['tools/metrics', 'build/util']
                            for p in (args.source_root / directory).rglob('*.py'))
    records = []
    metadata = {}
    revision_headers = {
        'gpu_service': ('gpu/webgpu/dawn_commit_hash.h', 'DAWN_COMMIT_HASH', 'dawn'),
        'blink_platform': ('skia/ext/skia_commit_hash.h', 'SKIA_COMMIT_HASH', 'skia'),
        'content': ('gpu/config/gpu_lists_version.h', 'GPU_LISTS_VERSION', None),
    }
    if layer in revision_headers:
        # Reproduce the DEPS revision-header hook.
        original = ast.parse((args.source_root / 'build/util/lastchange.py').read_text())
        functions = [node for node in original.body if isinstance(node, ast.FunctionDef)
                     and node.name in ('GetHeaderGuard', 'GetHeaderContents')]
        namespace = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'lastchange.py', 'exec'), namespace)
        header, macro, project = revision_headers[layer]
        revision = (graph['provenance']['chromium_revision'] if project is None
                    else json.loads((ROOT.parent / project / 'upstream.json').read_text())['revision'])
        metadata['gen/' + header] = namespace['GetHeaderContents'](
            'src/' + header, macro, revision)
        if layer == 'content':
            shared_headers.discard(':gen/' + header)
    if layer in ('dawn', 'dawn_native'):
        metadata['gpu/webgpu/DAWN_VERSION'] = json.loads((ROOT.parent / 'dawn/upstream.json').read_text())['revision']

    dawn_support = []
    if layer in ('dawn', 'dawn_native', 'gpu_service', 'browser'):
        for directory, patterns in [('third_party/dawn/generator', ['*']), ('third_party/jinja2', ['*.py']), ('third_party/markupsafe', ['*.py'])]:
            for pattern in patterns:
                dawn_support.extend('//'+str(p.relative_to(args.source_root))
                                    for p in (args.source_root / directory).rglob(pattern)
                                    if p.is_file() and '__pycache__' not in p.parts)
    def devtools_asset_deps(label):
        result = []
        for dependency in targets[label].get('deps', []):
            if not dependency.startswith('//third_party/devtools-frontend/src'):
                continue
            if dependency in existing_asset_providers:
                result.append(existing_asset_providers[dependency])
            elif dependency in actions:
                count = len(actions[dependency]['source_outputs']) if actions[dependency]['type'] == 'action_foreach' else 1
                result.extend(':' + name(dependency) + '_' + str(index) for index in range(count))
            elif dependency in copies:
                result.append(':' + copies[dependency]['name'])
            elif dependency in libraries and libraries[dependency]['kind'] == 'group':
                result.append(':' + libraries[dependency]['name'] + '_assets')
            elif targets[dependency]['type'] != 'generated_file':
                raise ValueError('unmapped DevTools asset dependency: ' + dependency)
        return sorted(set(result))

    def generated_asset_deps(label):
        # Bundlers read JS imports absent from GN inputs.
        pending = list(targets[label].get('deps', []))
        seen, result = set(), set()
        while pending:
            dependency = pending.pop()
            if dependency in seen:
                continue
            seen.add(dependency)
            target = targets[dependency]
            if target['type'] not in ('action', 'action_foreach', 'copy', 'group', 'generated_file'):
                continue
            if dependency in existing_asset_providers:
                result.add(existing_asset_providers[dependency])
            elif dependency in actions:
                count = len(actions[dependency]['source_outputs']) if target['type'] == 'action_foreach' else 1
                result.update(':' + name(dependency) + '_' + str(index) for index in range(count))
            elif dependency in copies:
                result.add(':' + copies[dependency]['name'])
            pending.extend(target.get('deps', []))
        return sorted(result)

    tools = {}
    cross_browser = layer == 'browser' and targets['//chrome:chrome'].get('toolchain', '').startswith(
        ('//build/toolchain/mac:', '//build/toolchain/win:'))
    executable_outputs = {output: label for label, target in targets.items()
                          if target['type'] == 'executable'
                          and (not cross_browser or target.get('toolchain', '').startswith('//build/toolchain/linux:'))
                          and (label in selected or reused.get(label, '').startswith((':', '@', '//')))
                          for output in target.get('outputs', [])[:1]}

    def native_tool(label, path):
        tool = dict(tool=reused.get(label, ':' + name(label)), logical_path=path[2:],
                    exec_compatible_with=['@llvm//constraints/libc:gnu.2.31'])
        if tool['tool'].startswith('@chromium//native:'):
            tool['stage_runtime'] = True
        if layer == 'browser' and '(//build/toolchain/linux:clang_x64_v8_arm64)' in label:
            host = json.loads((ROOT / 'native/platform_runtime.json').read_text())
            sonames = set(host['host_libraries']) | set(host['bazel_libraries'])
            tool['runtime_data'] = {':lib/' + soname: 'lib/' + soname for soname in sorted(sonames)}
            tool['runtime_data'].update({':lib/lib' + part + '.chk': 'lib/lib' + part + '.chk'
                                         for part in ['freebl3', 'freeblpriv3', 'nssdbm3', 'softokn3']})
            tool['runtime_data']['@chromium_icu//:common/icudtl.dat'] = 'icudtl.dat'
            if label.startswith('//tools/v8_context_snapshot:'):
                tool['runtime_data'][':snapshot_blob.bin'] = 'snapshot_blob.bin'
        if path.rsplit('/', 1)[-1] == 'top_domain_generator':
            tool['runtime_data'] = {'@chromium_icu//:common/icudtl.dat': 'icudtl.dat'}
        if label.partition('(')[0] == '//third_party/blink/renderer/platform:character_data_generator':
            tool['stage_runtime'] = True
            tool['runtime_data'] = {'@chromium_icu//:common/icudtl.dat': 'icudtl.dat'}
        return tool

    for label, target in sorted(actions.items()):
        instances = [(None, target.get('outputs', []))]
        if target['type'] == 'action_foreach':
            instances = [(source, [BUILD + p for p in outputs])
                         for source, outputs in target['source_outputs'].items()]
        mig = target['script'] == '//third_party/crashpad/crashpad/util/mach/mig.py'
        if mig:
            sources = {Path(path).name: path for path in target['sources']}
            if len(sources) != len(target['sources']):
                raise ValueError('ambiguous MIG source names: ' + label)
            instances = [(sources[Path(source).name].replace('$MACOS_SDK_ROOT/', '//third_party/macos_sdk/'), outputs)
                         for source, outputs in instances]
        for index, (source, outputs) in enumerate(instances):
            inputs = set(target.get('inputs', []) + target.get('sources', []) + [target['script']])
            if target['script'] == '//ui/webui/resources/tools/bundle_js.py':
                arguments = target.get('args', [])
                directory = arguments[arguments.index('--input') + 1]
                if '--external_paths' in arguments:
                    for mapping in arguments[arguments.index('--external_paths') + 1:]:
                        if mapping.startswith('--'):
                            break
                        external = Path(os.path.abspath(args.source_root / 'out/bazel-import' / mapping.split('|', 1)[1]))
                        if external.is_relative_to(args.source_root / 'out/bazel-import'):
                            continue
                        if not external.is_relative_to(args.source_root) or not external.is_dir():
                            raise ValueError('invalid WebUI external source directory: ' + str(external))
                        inputs.update('//' + path.relative_to(args.source_root).as_posix()
                                      for path in external.rglob('*') if path.is_file())
                if directory.startswith('../../'):
                    # Source bundles resolve entry names relative to --input.
                    inputs.update('//' + path.relative_to(args.source_root).as_posix()
                                  for path in (args.source_root / directory[6:]).rglob('*')
                                  if path.is_file() and '__pycache__' not in path.parts)
            for argument in target.get('args', []):
                value = argument.partition('=')[2] if '=' in argument else argument
                value = value.strip(chr(34))
                value = re.sub(r'^-[A-Za-z](?=\.\./\.\./)', '', value)
                if value.startswith('../../') and (args.source_root / value[6:]).is_file():
                    inputs.add('//' + value[6:])
            for dependency in target.get('deps', []):
                if dependency in actions or dependency in existing_actions:
                    inputs.update(targets[dependency].get('outputs', []))
            if target['script'].startswith('//tools/metrics/'):
                inputs.update(python_support)
            if target['script'] == '//chrome/tools/build/sha256_file.py':
                inputs.update(['//build/action_helpers.py', '//build/gn_helpers.py'])
            if target['script'] == '//build/toolchain/win/midl.py':
                generated = args.source_root / target['args'][1].removeprefix('../../')
                inputs.update('//' + path.relative_to(args.source_root).as_posix()
                              for path in generated.rglob('*') if path.is_file())
            if target['script'] == '//build/win/message_compiler.py':
                arguments = target['args']
                directory = re.sub(r'^(?:[^/]+/)?gen/', 'mc/', arguments[arguments.index('-h') + 1])
                generated = args.source_root / 'third_party/win_build_output' / directory
                inputs.update('//' + path.relative_to(args.source_root).as_posix()
                              for path in generated.rglob('*') if path.is_file())
            if target['script'] == '//build/win/reorder-imports.py':
                inputs.update('//' + path.relative_to(args.source_root).as_posix()
                              for path in (args.source_root / 'third_party/pefile_py3').rglob('*.py'))
            if '//build/util/version.py' in inputs:
                inputs.add('//build/util/android_chrome_version.py')
            if target['script'] == '//build/apple/tweak_info_plist.py' and '--scm=0' not in target.get('args', []):
                inputs.add('//build/util/LASTCHANGE')
                revision = overlay / 'build/util/LASTCHANGE'
                revision.parent.mkdir(parents=True, exist_ok=True)
                revision.write_bytes((args.source_root / 'build/util/LASTCHANGE').read_bytes())
            if (target['script'].startswith('//tools/grit/')
                    or target['script'].endswith('/generate_permission_element_grd.py')
                    or target['script'] == '//base/win/embedded_i18n/create_string_rc.py'):
                directories = ['tools/grit']
                if target['script'] == '//base/win/embedded_i18n/create_string_rc.py':
                    directories.append('tools/python')
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in directories
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
            if target['script'].endswith('/generate_permission_element_grd.py'):
                arguments = target['args']
                directory = arguments[arguments.index('--input_base_dir') + 1]
                if not directory.startswith('../../'):
                    raise ValueError('unmapped permission strings directory: ' + directory)
                base = args.source_root / directory[6:]
                inputs.add('//' + (base / 'permission_element_strings.grd').relative_to(args.source_root).as_posix())
                inputs.update('//' + path.relative_to(args.source_root).as_posix()
                              for path in base.glob('translations/permission_element_strings_*') if path.is_file())
            if target['script'].startswith('//tools/flags/'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['tools/flags', 'third_party/pyjson5/src']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
                inputs.update(['//chrome/VERSION', '//chrome/browser/flag-metadata.json'])
            if target['script'].startswith('//tools/json_schema_compiler/'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['tools/json_schema_compiler', 'tools/json_comment_eater',
                                                'tools/idl_parser', 'third_party/ply']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
                schema_directories = {posixpath.dirname(path[2:]) for path in inputs
                                      if path.startswith('//') and not path.startswith(BUILD)
                                      and path.endswith(('.json', '.idl', '.webidl'))}
                for argument in target.get('args', []):
                    if argument.startswith('--include-rules='):
                        schema_directories.update(rule.split(':', 1)[0]
                                                  for rule in shlex.split(argument.split('=', 1)[1]))
                    if argument.startswith('--impl-dir='):
                        inputs.update('//' + str(path.relative_to(args.source_root))
                                      for path in (args.source_root / argument.split('=', 1)[1]).rglob('*.h'))
                # NamespaceResolver discovers referenced schemas by filename.
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in schema_directories
                              for path in (args.source_root / directory).iterdir()
                              if path.is_file() and path.suffix in ('.json', '.idl', '.webidl'))
                for schema in list(inputs):
                    if schema.startswith('//') and not schema.startswith(BUILD) and schema.endswith(('.json', '.idl')):
                        content = (args.source_root / schema[2:]).read_text()
                        for header in re.findall(r'"?implemented_in"?\s*[:=]\s*"([^"\n]+)"', content):
                            inputs.add('//' + header)
            if target['script'] == '//chrome/browser/resources/accessibility/tools/generate_manifest.py':
                inputs.add('//build/util/LASTCHANGE.dummy')
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['third_party/jinja2', 'third_party/markupsafe',
                                                'tools/json_comment_eater', 'build/util']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
            if target['script'].endswith('/ulp_serialized_to_static_c.py'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['third_party/jinja2', 'third_party/markupsafe']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
            if target['script'] in (
                    '//components/safe_browsing/content/resources/gen_file_type_proto.py',
                    '//components/safe_browsing/content/resources/real_time_url_checks_allowlist/gen_real_time_url_allowlist_proto.py',
                    '//components/resources/ssl/ssl_error_assistant/gen_ssl_error_assistant_proto.py'):
                inputs.add('//components/resources/protobufs/binary_proto_generator.py')
            if set(target.get('deps', [])) & {'//third_party/protobuf:py_proto',
                                             '//third_party/protobuf:py_proto_runtime'}:
                pending = list(target.get('deps', []))
                seen = set()
                while pending:
                    dependency = pending.pop()
                    if dependency in seen:
                        continue
                    seen.add(dependency)
                    provider = targets[dependency]
                    inputs.update(path for path in provider.get('outputs', [])
                                  if path.startswith(BUILD + 'pyproto/')
                                  and not path.startswith(BUILD + 'pyproto/google/protobuf/'))
                    if provider['type'] in ('group', 'static_library', 'source_set'):
                        pending.extend(provider.get('deps', []))
            if target['script'].startswith('//components/policy/'):
                inputs.update('//' + path.relative_to(args.source_root).as_posix()
                              for path in (args.source_root / 'components/policy/tools').rglob('*.py')
                              if '__pycache__' not in path.parts)
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'third_party/pyyaml').glob('*.py'))
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'components/policy/resources/templates').rglob('*')
                              if path.is_file() and '__pycache__' not in path.parts)
            if target['script'].startswith('//third_party/catapult/'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'third_party/catapult').rglob('*.py')
                              if '__pycache__' not in path.parts)
                for directory in ['third_party/polymer', 'tracing/third_party', 'tracing/tracing']:
                    inputs.update('//' + str(path.relative_to(args.source_root))
                                  for path in (args.source_root / 'third_party/catapult' / directory).rglob('*')
                                  if path.is_file() and '__pycache__' not in path.parts)
            if any(argument.endswith('/front_end/core/i18n/collect-ui-strings.js')
                   for argument in target.get('args', [])):
                frontend = args.source_root / 'third_party/devtools-frontend/src'
                for directory in ['front_end', 'third_party/i18n', 'scripts']:
                    inputs.update('//' + str(path.relative_to(args.source_root))
                                  for path in (frontend / directory).rglob('*')
                                  if path.is_file() and '__pycache__' not in path.parts)
                inputs.add('//third_party/devtools-frontend/src/package.json')
            if target['script'] == '//components/vector_icons/aggregate_vector_icons.py':
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'components/vector_icons').glob('*.template'))
            if target['script'].endswith('/check_generated_file_list.py'):
                inputs.add('//third_party/blink/renderer/bindings/union_name_map.conf')
            if layer in ('blink_core', 'blink_modules', 'content', 'browser') and target['script'].startswith('//third_party/blink/renderer/'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['third_party/blink/renderer/bindings/scripts',
                                                'third_party/blink/renderer/build/scripts',
                                                'third_party/jinja2', 'third_party/markupsafe',
                                                'third_party/pyjson5/src', 'third_party/ply',
                                                'tools/idl_parser']
                              for pattern in ['*.py', '*.tmpl']
                              for path in (args.source_root / directory).rglob(pattern)
                              if '__pycache__' not in path.parts)
            if target['script'] == '//third_party/inspector_protocol/check_protocol_compatibility.py':
                for argument in target.get('args', []):
                    if argument.startswith('../../') and argument.endswith(('.pdl', '.json')):
                        protocol = args.source_root / argument.removeprefix('../../')
                        inputs.update('//' + str(path.relative_to(args.source_root))
                                      for path in protocol.parent.glob(protocol.stem + '-*.json'))
            if target['script'] in ('//tools/variations/fieldtrial_to_struct.py', '//tools/json_to_struct/json_to_struct.py'):
                for directory in ['tools/json_comment_eater', 'tools/json_to_struct']:
                    inputs.update('//' + str(p.relative_to(args.source_root))
                                  for p in (args.source_root / directory).glob('*.py')
                                  if not p.name.endswith('_test.py'))
                if target['script'] == '//tools/variations/fieldtrial_to_struct.py':
                    inputs.add('//components/variations/service/generate_ui_string_overrider.py')
            if layer in ('dawn', 'dawn_native', 'gpu_service') or target['script'].startswith('//third_party/dawn/'):
                inputs.update(dawn_support)
                arguments = target.get('args', [])
                if '--expected-outputs-file' in arguments:
                    expected = arguments[arguments.index('--expected-outputs-file')+1]
                    captured = graph['generated_files'].get(BUILD + expected)
                    metadata[expected] = captured if captured is not None else (args.source_root / BUILD[2:] / expected).read_text()
                    inputs.add(BUILD + expected)
                if '--version-file' in arguments:
                    inputs.add('//' + arguments[arguments.index('--version-file')+1].removeprefix('../../'))
                for argument in arguments:
                    if argument.startswith('../../third_party/dawn/') and (args.source_root / argument[6:]).is_file():
                        inputs.add('//' + argument[6:])
            if layer == 'browser_v8' and target['script'].startswith('//v8/third_party/inspector_protocol/'):
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'v8/third_party/inspector_protocol').glob('*.py'))
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'v8/third_party/inspector_protocol').rglob('*.template'))
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['third_party/jinja2', 'third_party/markupsafe']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
            if target['script'].startswith('//third_party/inspector_protocol/'):
                inputs.update(protocol_inputs(args.source_root,
                              [item for item in inputs if item.startswith('//') and item.endswith('.pdl')]))
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for directory in ['third_party/inspector_protocol', 'third_party/jinja2', 'third_party/markupsafe']
                              for path in (args.source_root / directory).rglob('*.py')
                              if '__pycache__' not in path.parts)
                inputs.update('//' + str(path.relative_to(args.source_root))
                              for path in (args.source_root / 'third_party/inspector_protocol').rglob('*.template'))
            files = {}
            deps = []
            for output, executable in executable_outputs.items():
                if executable in target.get('deps', []):
                    tool_name = name(executable) + '_tool'
                    tools[tool_name] = native_tool(executable, output)
                    deps.append(':' + tool_name)
                    inputs.discard(output)
            if (target['script'] == '//third_party/node/node.py'
                    or any(path.startswith('//third_party/node/') for path in target.get('inputs', []))
                    or target['script'].startswith(('//tools/typescript/', '//tools/polymer/', '//third_party/lottie/'))):
                deps += [':node_npm_sources', ':webui_node_inputs', ':webui_python_inputs']
            if set(target.get('deps', [])) & {'//third_party/protobuf:py_proto',
                                             '//third_party/protobuf:py_proto_runtime'}:
                deps.append(':protobuf_python_runtime')
            if target['script'] in ('//ui/webui/resources/tools/eslint_ts.py', '//tools/typescript/ts_library.py'):
                deps.extend(existing_asset_providers.get(dependency,
                                ':' + existing_action_names.get(hashlib.sha256(dependency.encode()).hexdigest()[:16], name(dependency) + '_0'))
                            for dependency in target.get('deps', [])
                            if targets[dependency].get('script') == '//tools/typescript/ts_library.py')
            for dependency in target.get('deps', []):
                if dependency.partition('(')[0] != '//third_party/protobuf:protoc':
                    continue
                protoc_outputs = targets[dependency].get('outputs', [])
                executables = [path for path in protoc_outputs if Path(path).name in ('protoc', 'protoc.exe')]
                if len(executables) != 1:
                    raise ValueError('expected one captured protoc executable: ' + dependency)
                output = executables[0]
                if output == BUILD + 'protoc':
                    deps.append(':protoc_tool')
                else:
                    tool_name = name(dependency) + '_tool'
                    tools[tool_name] = dict(tool=':protobuf_compiler', logical_path=output[2:])
                    deps.append(':' + tool_name)
            plugin = '//third_party/dom_distiller_js/protoc_plugins/json_values_converter.py'
            if target['script'] == '//tools/protoc_wrapper/protoc_wrapper.py' and plugin in inputs:
                tools['browser_dom_distiller_plugin'] = dict(
                    tool=':browser_dom_distiller_cli', logical_path=plugin[2:])
                deps.append(':browser_dom_distiller_plugin')
                file_label(plugin)  # Export script for its py_binary target.
                inputs.discard(plugin)
            if label.startswith('//third_party/devtools-frontend/src'):
                inputs.discard('//third_party/devtools-frontend/src/third_party/esbuild/esbuild')
                deps += [':devtools_inspector_runtime', ':devtools_inspector_npm',
                         ':webui_node_inputs', ':webui_python_inputs',
                         ':devtools_inspector_esbuild_inputs']
            if target['script'] == '//build/gn_run_binary.py' and target['args'][0] == 'character_data_generator':
                inputs.add(BUILD + 'icudtl.dat')
            needs_gperf = layer in ('blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') and 'gperf' in target.get('args', [])
            if needs_gperf:
                tools[layer + '_gperf_tool'] = dict(tool='@gperf//:gperf', logical_path=BUILD[2:] + 'gperf')
                deps.append(':' + layer + '_gperf_tool')
            if layer == 'browser_v8' and target['script'] == '//v8/tools/run.py':
                inputs.add(BUILD + target['args'][0].removeprefix('./'))
            if target['script'] == '//build/gn_run_binary.py':
                binary = BUILD + target['args'][0].removeprefix('./')
                if binary in executable_outputs:
                    tool_name = name(executable_outputs[binary]) + '_tool'
                    tools[tool_name] = native_tool(executable_outputs[binary], binary)
                    deps.append(':' + tool_name)
                    inputs.discard(binary)
            if layer in ('ml', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser') and target['script'] == '//build/gn_run_binary.py' and Path(target['args'][0]).name == 'flatc':
                if target['args'][0] == 'flatc':
                    tools[layer + '_flatc_tool'] = dict(tool='@flatbuffers//:flatc', logical_path=BUILD[2:]+'flatc')
                    deps.append(':' + layer + '_flatc_tool')
                    inputs.discard(BUILD + 'flatc')
                pending_schemas = [p for p in inputs if p.endswith('.fbs')]
                schema_roots = [args.source_root / target['args'][i+1].removeprefix('../../')
                                for i, value in enumerate(target['args']) if value == '-I']
                while pending_schemas:
                    schema = args.source_root / pending_schemas.pop()[2:]
                    for include in re.findall(r'^\s*include\s+"([^"\n]+)"\s*;', schema.read_text(), re.M):
                        dependency = next((root / include for root in schema_roots + [schema.parent]
                                           if (root / include).is_file()), None)
                        if dependency is None:
                            raise ValueError('missing FlatBuffers include: ' + include)
                        path = '//' + posixpath.normpath(dependency.relative_to(args.source_root).as_posix())
                        if path not in inputs:
                            inputs.add(path)
                            pending_schemas.append(path)
            if layer in ('codecs', 'ffmpeg') and target['script'] == '//build/gn_run_binary.py' and target['args'][0] == 'nasm':
                tool_name = 'nasm_tool' if layer == 'codecs' else layer + '_nasm_tool'
                tools[tool_name] = dict(tool='@nasm//:nasm', logical_path=BUILD[2:]+'nasm')
                deps.append(':' + tool_name)
            if mig:
                deps.append(':mac_mig_inputs')
            for path in sorted(inputs):
                if mig and path.startswith('$MACOS_SDK_ROOT/'):
                    continue
                if path == '//third_party/node/linux/node-linux-x64/bin/node':
                    deps.append(':webui_node_inputs')
                    continue
                if layer == 'ozone' and path == BUILD + 'wayland_scanner':
                    tools['ozone_wayland_scanner_tool'] = dict(tool='@wayland//:wayland_scanner', logical_path=path[2:])
                    deps.append(':ozone_wayland_scanner_tool')
                    continue
                if path.startswith(BUILD) and posixpath.basename(path) == 'protoc':
                    deps.append(':protoc_tool')
                    continue
                if path in executable_outputs:
                    host_label = executable_outputs[path]
                    tool_name = name(host_label) + '_tool'
                    tools[tool_name] = native_tool(host_label, path)
                    deps.append(':' + tool_name)
                    continue
                files[file_label(path)] = path[2:]
            arguments = [p.replace('$SOURCE_ROOT/out/bazel-import/', '') for p in target.get('args', [])]
            if mig:
                arguments = [argument.replace('$LLVM_ROOT', '../../third_party/llvm-build/Release+Asserts')
                             .replace('$MACOS_SDK_ROOT', '../../third_party/macos_sdk') for argument in arguments]
            if layer in ('blink_core', 'blink_modules', 'content', 'browser') and target['script'].endswith('/run_with_pythonpath.py'):
                for directory in ['../../third_party/blink/renderer/build/scripts',
                                  '../../third_party', '../../third_party/pyjson5/src', '../../tools']:
                    if directory not in arguments:
                        arguments = ['-I', directory] + arguments
            if needs_gperf:
                arguments = ['./gperf' if p == 'gperf' else p for p in arguments]
            if any('$SOURCE_ROOT' in p for p in arguments):
                raise ValueError('unmapped source-root argument: ' + label)
            if source:
                arguments = foreach_arguments(arguments, source, outputs)
            if 'response_file_contents' in target:
                response = target['response_file_contents']
            else:
                response = []
            if target['script'] == '//third_party/dawn/third_party/gn/dxc/build/run_built_binary.py' and arguments and not arguments[0]:
                arguments = arguments[1:]
            record = dict(response_file_contents=response, name=name(label)+'_'+str(index), srcs=files,
                                outs={p.removeprefix(BUILD): p.removeprefix(BUILD) for p in outputs},
                                script=target['script'][2:], args=arguments, deps=sorted(set(deps)))
            if target['script'].startswith('//third_party/dawn/third_party/dxc/utils/hct/'):
                for path in json.loads((Path(__file__).parent / 'dxc_generator_files.json').read_text())['hct']:
                    logical = 'third_party/dawn/third_party/dxc/' + path
                    record['srcs'][file_label('//' + logical)] = logical
            if target['script'] == '//third_party/dawn/third_party/gn/dxc/build/run_built_binary.py':
                for path in json.loads((Path(__file__).parent / 'dxc_generator_files.json').read_text())['tablegen']:
                    logical = 'third_party/dawn/third_party/dxc/' + path
                    record['srcs'][file_label('//' + logical)] = logical
            if target['script'] == '//third_party/dawn/third_party/gn/dxc/build/message_compiler.py':
                directory = args.source_root / 'third_party/dawn/third_party/gn/dxc/win_build_output'
                for artifact in sorted(directory.rglob('*')):
                    if artifact.is_file():
                        logical = artifact.relative_to(args.source_root).as_posix()
                        record['srcs'][file_label('//' + logical)] = logical
            if target['script'] == '//ui/webui/resources/tools/bundle_js.py':
                record['generated_deps'] = generated_asset_deps(label)
            if layer == 'browser' and label.startswith('//third_party/devtools-frontend/src'):
                record['output_deps'] = devtools_asset_deps(label)
                if target['script'] == '//third_party/node/node.py' and target.get('args') and (Path(target['args'][0]).name in ('esbuild.js', 'rollup.js') or target['args'][0].endswith('/node_modules/@rollup/wasm-node/dist/bin/rollup')):
                    record['generated_deps'] = record['output_deps']
            records.append(record)
    if layer == 'browser':
        deduplicate_source_sets(libraries)
    if layer == 'browser' and any(label.endswith('(//build/toolchain/linux:clang_x64_v8_arm64)')
                                  for label in libraries):
        reference = json.loads(gzip.decompress((ROOT / 'native/linux_x64.json.gz').read_bytes()))
        print('Reused', reuse_host_graphics(graph, reference, libraries,
                                          native_graphics_providers(args.native_overlay)),
              'matching native graphics libraries')

    overlay = ROOT / 'bcr/overlay'
    data = {'LIBRARIES': libraries, 'SHARED_HEADERS': sorted(shared_headers),
            'ACTIONS': records, 'TOOLS': tools}
    if copies or layer == 'x11':
        if layer == 'browser':
            for label, copy in copies.items():
                if label.startswith('//third_party/devtools-frontend/src'):
                    copy['output_deps'] = devtools_asset_deps(label)
        data['COPIES'] = list(copies.values())
    if layer in ('angle_runtime', 'linux_ui', 'browser'):
        data['RUNTIME_DEPS'] = runtime_edges
    if layer == 'browser':
        bundles = []
        for label, target in sorted(selected.items()):
            if target['type'] != 'create_bundle':
                continue
            bundle = target['bundle_data']
            paths = bundle['source_files']
            outputs = target['outputs']
            if len(outputs) != len(paths) + 1 or outputs[-1] != bundle['root_dir_output']:
                raise ValueError('bundle source/output mismatch: ' + label)
            root = bundle['root_dir']
            if any(not output.startswith(root) for output in outputs[:-1]):
                raise ValueError('bundle output escapes root: ' + label)
            bundles.append(dict(name=name(label) + '_bundle', root=root.removeprefix(BUILD).rstrip('/'),
                                srcs=[file_label(path) for path in paths],
                                destinations=[output.removeprefix(root) for output in outputs[:-1]]))
        data['BUNDLES'] = bundles
        data['ASSET_GROUPS'] = [dict(name=library['name'] + '_assets', srcs={}, deps=devtools_asset_deps(label))
                                for label, library in libraries.items()
                                if label.startswith('//third_party/devtools-frontend/src') and library['kind'] == 'group']
        if reused_asset_roots:
            data['ASSET_GROUPS'].append(dict(name='browser_reused_asset_roots', srcs={},
                                            deps=sorted(set(reused_asset_roots.values()))))
        data['RUNTIME_FILES'] = [path.removeprefix(BUILD) for path in graph['runtime_files']['//chrome:chrome']]
    if layer == 'dawn_native':
        data['RUNTIME_DEPS'] = runtime_edges
        data['PUBLIC_DEFINES'] = [
            p for p in libraries['//third_party/dawn/src/dawn/native:headers']['defines']
            if p.startswith(('DAWN_', 'TINT_', 'DCHECK_ALWAYS_ON', 'NDEBUG'))
        ]
    if layer == 'ml':
        data['PUBLIC_DEFINES'] = [p for p in unpack(targets['//third_party/tflite:tflite']['defines'])
                                  if p.startswith(('TFL_STATIC_LIBRARY_BUILD', 'TF_MAJOR_VERSION=',
                                                   'TF_MINOR_VERSION=', 'TF_PATCH_VERSION=', 'TF_VERSION_SUFFIX'))]
    if layer == 'browser_v8':
        data['PUBLIC_DEFINES'] = [p for p in unpack(targets['//v8:v8_headers']['defines'])
                                  if p.startswith(('V8_', 'CPPGC_', 'TEMPORAL_', 'DCHECK_ALWAYS_ON', 'NDEBUG', 'DEBUG'))]
    if layer == 'tint':
        data['PUBLIC_DEFINES'] = [p for p in libraries['//third_party/dawn/src/tint/api:api']['defines']
                                  if p.startswith(('TINT_', 'DCHECK_ALWAYS_ON', 'NDEBUG'))]
    if layer in ('media', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        data['LIBGAV1_DEFINES'] = [p for p in unpack(targets['//third_party/libgav1:libgav1_parser']['defines']) if p.startswith('LIBGAV1_')]
        data['BRIDGES'] = [dict(name=name(label)+'_0', src=file_label(targets[label]['sources'][0]), logical_source=targets[label]['sources'][0][2:])
                           for label in sorted(reused_actions) if targets[label].get('script') == '//third_party/rust/cxx/chromium_integration/run_cxxbridge.py']
    if layer == 'blink_rust':
        data['BRIDGES'] = [dict(name=name(label)+'_0', src=file_label(targets[label]['sources'][0]), logical_source=targets[label]['sources'][0][2:])
                           for label in sorted(reused_actions) if targets[label].get('script') == '//third_party/rust/cxx/chromium_integration/run_cxxbridge.py']
    if layer == 'skia':
        # This consumer receives exactly Skia's public GN configuration.
        public = unpack(targets['//ui/gfx/geometry:geometry_skia']['defines'])
        data['PUBLIC_DEFINES'] = [
            p.replace('../../skia/config/SkUserConfig.h', 'skia/config/SkUserConfig.h').replace('"', '\\"')
            for p in public
            if p.startswith(('SK_', 'VK_USE_PLATFORM_', 'DCHECK_ALWAYS_ON', 'NDEBUG'))
        ]
        data['BRIDGES'] = [dict(name=name(label)+'_0', src=file_label(targets[label]['sources'][0]), logical_source=targets[label]['sources'][0][2:])
                           for label in sorted(reused_actions) if targets[label].get('script') == '//third_party/rust/cxx/chromium_integration/run_cxxbridge.py']
    if layer in ('dawn', 'dawn_native', 'gpu_service', 'blink_platform', 'blink_core', 'blink_modules', 'content', 'browser'):
        data['METADATA'] = metadata
    if layer == 'browser' and any(label.endswith('(//build/toolchain/linux:clang_x64_v8_arm64)') for label in libraries):
        copy = host_webui_resource_copy(graph, reference)
        if copy:
            data.setdefault('COPIES', []).append(copy)
    (overlay / ('native/' + layer + '_sources.bzl')).write_text(
        ('"""Generated by tools/import_network.py; complete original network closure."""\n\n' if layer == 'network' else '"""Generated by tools/import_cpp_layer.py; native '+layer+' closure."""\n\n')+
        '\n\n'.join(k+' = '+starlark_literal(v) for k,v in data.items())+'\n')
    if layer == 'browser':
        catalog = {label: name(label) + '_0_outputs' for label in actions if targets[label]['type'] == 'action'}
        catalog.update({label: copy['name'] + '_outputs' for label, copy in copies.items()})
        catalog.update({label: provider.removeprefix('//native:').removeprefix(':')
                        for label, provider in reused_asset_roots.items()})
        (overlay / 'native/browser_targets.json').write_text(json.dumps(catalog, indent=2) + '\n')
    elif layer in ('blink_core', 'blink_modules', 'content'):
        catalog = {label: name(label) + '_0' for label in actions if targets[label]['type'] == 'action'}
        catalog.update({label: copy['name'] for label, copy in copies.items()})
        (overlay / ('native/' + layer + '_targets.json')).write_text(json.dumps(catalog, indent=2) + '\n')
    begin, end = '# BEGIN ' + layer.upper() + ' INPUTS', '# END ' + layer.upper() + ' INPUTS'
    for build_file in overlay.rglob('BUILD.bazel'):
        package = build_file.parent.relative_to(overlay).as_posix()
        package = '' if package == '.' else package
        if package not in exports:
            content = build_file.read_text()
            if begin in content:
                build_file.write_text(re.sub(re.escape(begin) + r'.*?' + re.escape(end) + r'\n?', '', content, flags=re.S))
    for package, paths in exports.items():
        build_file = overlay / package / 'BUILD.bazel'
        if not build_file.exists():
            build_file.parent.mkdir(parents=True, exist_ok=True)
            build_file.write_text('package(default_visibility = ["//visibility:public"])\n')
        replace_block(overlay / package / 'BUILD.bazel', '# BEGIN ' + layer.upper() + ' INPUTS', '# END ' + layer.upper() + ' INPUTS',
                      'exports_files('+json.dumps(sorted(paths), indent=4)+')')
    module = ROOT / 'MODULE.bazel'
    text = module.read_text()
    for filename in [layer + '.bzl', layer + '_sources.bzl'] + (['browser_targets.json'] if layer == 'browser' else []):
        line = f'        "native/{filename}": "//bcr/overlay/native:{filename}",\n'
        if line not in text:
            marker = text.index('        "native/BUILD.bazel":')
            text = text[:marker]+line+text[marker:]
    for package in exports:
        filename = str(Path(package) / 'BUILD.bazel')
        overlay_package = '//bcr/overlay' + ('/' + package if package else '')
        line = f'        "{filename}": "{overlay_package}:BUILD.bazel",\n'
        if line not in text:
            marker = text.index('        "native/BUILD.bazel":')
            text = text[:marker]+line+text[marker:]
    if (overlay / 'build/util/LASTCHANGE').is_file():
        line = '        "build/util/LASTCHANGE": "//bcr/overlay/build:util/LASTCHANGE",\n'
        if line not in text:
            marker = text.index('        "native/BUILD.bazel":')
            text = text[:marker] + line + text[marker:]
    module.write_text(sort_archive_files(text))
    print(len(libraries), 'native libraries/tools;', len(records), 'generator actions;',
          sum(sum(p.endswith(('.c', '.cc', '.cpp', '.cxx')) for p in v['srcs']) for v in libraries.values()), 'C/C++ units')
    if layer == 'paint':
        print(sum(sum(p.endswith(('.S', '.s', '.asm')) for p in v['srcs']) for v in libraries.values()), 'assembler sources')
    if layer == 'codecs':
        print(sum(sum(p.endswith('.o') for p in v['srcs']) for v in libraries.values()), 'assembler objects')


if __name__ == '__main__':
    main()
