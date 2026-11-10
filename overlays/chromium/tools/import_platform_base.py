#!/usr/bin/env python3
"""Regenerate platform base and support metadata in an isolated overlay."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from import_cpp_layer import native_library_providers

ROOT = Path(__file__).resolve().parents[1]
CXX = 'third_party/rust/chromium_crates_io/vendor/cxx-v1'


def atomic_copy(source, target):
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def copy_package_inputs(overlay, destination, layers):
    """Merge generated exports while preserving platform rule adapters."""
    packages = {path.relative_to(root) for root in [overlay, destination]
                for path in root.rglob('BUILD.bazel')}
    for package in sorted(packages):
        if package.as_posix() in ('BUILD.bazel', 'native/BUILD.bazel'):
            continue
        source, target = overlay / package, destination / package
        captured = source.read_text() if source.exists() else ''
        original = target.read_text() if target.exists() else captured
        text = original
        for layer in layers:
            begin, end = '# BEGIN ' + layer.upper() + ' INPUTS', '# END ' + layer.upper() + ' INPUTS'
            pattern = re.escape(begin) + r'.*?' + re.escape(end) + r'\n?'
            block = re.search(pattern, captured, re.S)
            if re.search(pattern, text, re.S):
                text = re.sub(pattern, lambda _: block[0] if block else '', text, flags=re.S)
            elif block:
                text += '\n' + block[0]
        if text == original and (target.exists() or not any(
                '# BEGIN ' + layer.upper() + ' INPUTS' in text for layer in layers)):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as output:
            output.write(text)
        Path(output.name).replace(target)



def write_host_support(destination, variant):
    """Resolve Linux host providers by GN identity across layer boundaries."""
    native = native_library_providers(ROOT / 'bcr/overlay')
    cross = native_library_providers(destination)
    aliases = {name.removeprefix(':'): native[label].removeprefix(':')
               for label, name in cross.items() if label in native and native[label] != name}
    suffix, system = ('mac', 'macos') if variant == 'darwin_arm64' else ('windows', 'windows')
    text = '\n'.join([
        '"""Keep Linux host tools on their native library configuration."""',
        '',
        'load("@rules_cc//cc:cc_library.bzl", _cc_library = "cc_library")',
        '',
        '_HOST_TARGETS = ' + json.dumps(dict(sorted(aliases.items())), indent=4),
        '',
        'def platform_cc_library(name, **kwargs):',
        '    _cc_library(name = name + "_' + suffix + '", **kwargs)',
        '    native.alias(name = name, actual = select({',
        '        "@platforms//os:' + system + '": ":" + name + "_' + suffix + '",',
        '        "//conditions:default": "@chromium//" + native.package_name() + ":" + _HOST_TARGETS.get(name, name),',
        '    }))',
        '',
    ])
    (destination / 'native/host_support.bzl').write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', required=True, choices=['windows_amd64', 'windows_arm64', 'darwin_arm64'])
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', type=Path, help='Write metadata to this directory instead of the maintained profile')
    parser.add_argument('--ipc', action='store_true', help='Also import Mojo runtime, bindings and URL traits')
    parser.add_argument('--network', action='store_true', help='Also import the network closure and its support libraries')
    parser.add_argument('--v8', action='store_true', help='Also import V8, Temporal and its platform prerequisites')
    parser.add_argument('--graphics', action='store_true', help='Also import geometry, fonts, codecs, Dawn and Skia')
    parser.add_argument('--desktop', action='store_true', help='Also import paint, Crashpad and gfx')
    parser.add_argument('--gn', type=Path, help='GN executable for capturing GPU runtime edges')
    parser.add_argument('--gpu', action='store_true', help='Also import Tint, Dawn native and GPU command protocol')
    parser.add_argument('--angle', action='store_true', help='Also import the ANGLE EGL/GLES backends')
    parser.add_argument('--gl', action='store_true', help='Also import browser tracing/metrics and OpenGL integration')
    parser.add_argument('--gpu-service', action='store_true', help='Also import the GPU command service closure')
    parser.add_argument('--media', action='store_true', help='Also import GPU clients and media decoding')
    parser.add_argument('--bootstrap-webui', action='store_true', help='Import WebUI producers before discovering generated GRIT inputs')
    parser.add_argument('--generated-root', type=Path, help='Built platform native output directory for GRIT input discovery')
    parser.add_argument('--compositor', action='store_true', help='Also import the compositor closure')
    parser.add_argument('--blink-platform', action='store_true', help='Also import Blink platform and its Rust bridges')
    parser.add_argument('--blink-core', action='store_true', help='Also import Blink DOM, layout and paint')
    parser.add_argument('--blink-modules', action='store_true', help='Also import Blink web API modules')
    parser.add_argument('--content', action='store_true', help='Also import content browser and renderer services')
    parser.add_argument('--browser', action='store_true', help='Import the complete browser and its runtime assets')
    parser.add_argument('--gpu-client', action='store_true', help='Also import GPU command producers and Viz types')
    args = parser.parse_args()
    args.content = args.content or args.browser
    args.blink_modules = args.blink_modules or args.content
    args.blink_core = args.blink_core or args.blink_modules
    args.blink_platform = args.blink_platform or args.blink_core
    args.compositor = args.compositor or args.blink_platform
    args.media = args.media or args.compositor
    args.gpu_client = args.gpu_client or args.media
    args.gpu_service = args.gpu_service or args.gpu_client
    args.gl = args.gl or args.gpu_service or args.bootstrap_webui
    args.angle = args.angle or args.gl
    args.gpu = args.gpu or args.angle
    if args.gpu and not args.gn:
        parser.error('--gpu requires --gn')
    args.desktop = args.desktop or args.gpu
    args.graphics = args.graphics or args.desktop
    args.v8 = args.v8 or args.graphics
    args.network = args.network or args.v8
    args.ipc = args.ipc or args.network
    source = args.source_root.resolve()
    graph = ROOT / 'native' / (args.variant + '.json.gz')
    destination = args.output or ROOT / 'platforms' / args.variant / 'overlay'
    with tempfile.TemporaryDirectory(prefix='chromium-platform-import-') as temporary:
        stage = Path(temporary) / 'chromium'
        overlay = stage / 'bcr/overlay'
        shutil.copytree(ROOT / 'tools', stage / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT / 'MODULE.bazel', stage / 'MODULE.bazel')
        if args.graphics:
            for project in ['dawn', 'skia']:
                sibling = stage.parent / project
                sibling.mkdir()
                shutil.copy2(ROOT.parent / project / 'upstream.json', sibling / 'upstream.json')
        (stage / 'native').mkdir()
        for path in (ROOT / 'bcr/overlay').rglob('BUILD.bazel'):
            target = overlay / path.relative_to(ROOT / 'bcr/overlay')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        maintained = ROOT / 'platforms' / args.variant / 'overlay'
        for path in maintained.rglob('BUILD.bazel'):
            target = overlay / path.relative_to(maintained)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        commands = [
            ['import_base.py', str(graph), '--source-root', str(source)],
            ['import_generated_files.py', str(graph)],
            ['import_buildflags.py', str(graph)],
            ['import_perfetto_proto.py', str(graph)],
            ['import_perfetto_runtime.py', str(graph), str(source / 'third_party/perfetto'), '--select-platform-sources'],
            ['import_rust_crates.py', str(graph), '--source-root', str(source),
             '--root', 'rust_logger', '--root', 'serde_json_wrapper', '--root', 'cxxbridge'],
        ]
        if args.v8:
            commands[-1].extend(['--root', 'temporal_capi'])
        if args.graphics:
            for crate in ['font_types', 'read_fonts', 'skrifa', 'png', 'skia_fontations', 'skia_png']:
                commands[-1].extend(['--root', crate])
        if args.media and '//media/filters:symphonia_glue' in json.loads(gzip.decompress(graph.read_bytes()))['targets']:
            commands[-1].extend(['--root', 'symphonia_glue'])
        if args.blink_platform:
            for crate in ['font_format_check', 'blink_rust_crash', 'crabbyavif',
                          'crabbyavif_libyuv_sys', 'crabbyavif_dav1d_sys']:
                commands[-1].extend(['--root', crate])
        if args.content:
            commands[-1].extend(['--root', 'llguidance'])
        if args.browser:
            for crate in ['qr_code_generator', 'user_data_importer_zip']:
                commands[-1].extend(['--root', crate])
        if args.variant == 'darwin_arm64' or args.network:
            commands.append(['import_crypto.py', str(graph), '--source-root', str(source)])
        if args.ipc:
            commands.extend([
                ['import_mojo_runtime.py', str(graph), '--source-root', str(source)],
                ['import_mojo_actions.py', str(graph), str(source)],
                ['import_url.py', str(graph), '--source-root', str(source)],
            ])
        if args.network:
            commands.extend([
                ['import_sqlite.py', str(graph)],
                ['import_quiche.py', str(graph), '--source-root', str(source)],
                ['import_grit_actions.py', str(graph), '--source-root', str(source), '--root', '//net:net_resources_grit'],
                ['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'network'],
            ])
        if args.graphics:
            for layer in ['geometry', 'fonts', 'codecs', 'dawn', 'skia']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
        if args.v8:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'browser_v8'])
        if args.desktop:
            for layer in ['paint', 'gfx']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
        if args.gpu:
            commands.append(['capture_dawn_runtime_edges.py', '--source-root', str(source),
                             '--gn', str(args.gn.resolve()), '--graph', str(graph),
                             '--output', str(stage / 'native/dawn_runtime_edges.json')])
            for layer in ['tint', 'dawn_native', 'gpu_protocol']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
        if args.angle:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source),
                             '--layer', 'vulkan_loader'])
            commands.append(['capture_angle_runtime_edges.py', '--source-root', str(source),
                             '--gn', str(args.gn.resolve()), '--graph', str(graph),
                             '--output', str(stage / 'native/angle_runtime_edges.json')])
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source),
                             '--layer', 'angle_runtime'])
        if args.gl:
            commands.append(['capture_runtime_edges.py', '--source-root', str(source),
                             '--gn', str(args.gn.resolve()), '--graph', str(graph),
                             '--target', '//ui/gl:gl', '--output', str(stage / 'native/gl_runtime_edges.json')])
            for layer in ['browser_services', 'linux_ui']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
            for root in ['//ui/base:base', '//ui/events:events', '//ui/gfx/ipc:ipc',
                         '//ui/gl/init:init', '//ui/gl/mojom:mojom', '//ui/gfx/ipc/buffer_types:buffer_types',
                         '//ui/gfx/ipc/color:color', '//ui/gfx/ipc/skia:skia']:
                commands[-1].extend(['--root', root])
        if args.gpu_service:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'gpu_service'])
        if args.media:
            for layer in ['pthreadpool', 'ml', 'ffmpeg']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
        if args.gpu_client:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'gpu_client'])
        if args.media:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'media'])
        if args.compositor:
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'compositor'])
        if args.blink_platform:
            for layer in ['blink_rust', 'blink_platform']:
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
            commands.append(['import_devtools_inspector.py', str(graph), '--source-root', str(source)])
        if args.gl:
            commands.append(['import_webui_actions.py', str(graph), '--source-root', str(source),
                             '--root', '//ui/webui/resources:build_grd'])
        if args.blink_core:
            commands.append(['import_xslt.py', str(graph), '--source-root', str(source)])
        for layer in ['blink_core', 'blink_modules', 'content']:
            if getattr(args, layer):
                commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', layer])
        if args.browser:
            targets = json.loads(gzip.decompress(graph.read_bytes()))['targets']
            assets = json.loads((ROOT / 'native/browser_asset_roots.json').read_text())
            assets['roots'] = [label for label in assets['roots'] if label in targets]
            assets['graph_sha256'] = hashlib.sha256(graph.read_bytes()).hexdigest()
            (stage / 'native/browser_asset_roots.json').write_text(json.dumps(assets, indent=2) + '\n')
            commands.append(['capture_runtime_edges.py', '--source-root', str(source),
                             '--gn', str(args.gn.resolve()), '--graph', str(graph),
                             '--target', '//chrome:chrome', '--output', str(stage / 'native/browser_runtime_edges.json')])
            commands.append(['import_cpp_layer.py', str(graph), '--source-root', str(source), '--layer', 'browser'])
        if args.gl:
            grit = ['import_grit_actions.py', str(graph), '--source-root', str(source)]
            for root in ['//net:net_resources_grit', '//ui/resources:ui_resources_grd_grit',
                         '//ui/resources:ui_unscaled_resources_grd_grit',
                         '//ui/strings:ui_strings_grit', '//ui/strings:app_locale_settings_grit',
                         '//ui/strings:ax_strings_grit', '//ui/strings:auto_image_annotation_strings_grit',
                         '//ui/webui/resources:resources_grit']:
                if args.bootstrap_webui and root == '//ui/webui/resources:resources_grit':
                    continue
                grit.extend(['--root', root])
            if args.generated_root:
                grit.extend(['--generated-root', str(args.generated_root.resolve())])
            if args.compositor:
                grit.extend(['--root', '//components/metrics:server_urls_grd_grit'])
            if args.blink_platform:
                for root in ['//third_party/blink/public/strings:strings_grit',
                             '//third_party/blink/public:image_resources_grit',
                             '//third_party/blink/public:resources_grit',
                             '//third_party/blink/public:devtools_inspector_resources_grit',
                             '//ui/resources:ui_lottie_resources_grd_grit',
                             '//device/bluetooth/strings:strings_grit',
                             '//device/fido/strings:strings_grit']:
                    if args.bootstrap_webui and root == '//third_party/blink/public:devtools_inspector_resources_grit':
                        continue
                    grit.extend(['--root', root])
            if args.blink_core:
                for root in ['//third_party/blink/public/strings:permission_element_strings_grit',
                             '//third_party/blink/public/strings:permission_element_generated_strings_grit',
                             '//third_party/blink/renderer/modules/media_controls:media_controls_resources_grit']:
                    if args.bootstrap_webui and root.endswith(':permission_element_generated_strings_grit'):
                        continue
                    grit.extend(['--root', root])
            if args.browser:
                grit = ['import_grit_actions.py', str(graph), '--source-root', str(source)]
                if args.generated_root:
                    grit.extend(['--generated-root', str(args.generated_root.resolve())])
            commands.append(grit)
        for command in commands:
            if command[0] == 'import_cpp_layer.py':
                command.extend(['--native-overlay', str(ROOT / 'bcr/overlay')])
            subprocess.run([sys.executable, str(stage / 'tools' / command[0]), *command[1:]], check=True)
        files = [
            'BUILD.bazel', 'build/BUILD.bazel', 'native/base_sources.bzl',
            'native/generated_files.bzl', 'native/buildflags.bzl',
            'native/perfetto_proto.bzl', 'native/perfetto_proto_targets.json',
            'native/perfetto_runtime.bzl', 'native/rust/crates.bzl', CXX + '/BUILD.bazel',
        ]
        if args.variant == 'darwin_arm64' or args.network:
            files.append('native/crypto_sources.bzl')
        if args.ipc:
            files.append('native/url_sources.bzl')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native').glob('mojo_*.bzl')))
        if args.network:
            files.extend(['native/' + name + '_sources.bzl' for name in ['sqlite', 'quiche', 'network']])
            files.extend(['native/grit_actions.bzl', 'native/grit_sources.bzl', 'native/grit_targets.json', 'native/grit_resource_inputs.bzl'])
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/network_forwarders').rglob('*')) if path.is_file())
        if args.graphics:
            for layer in ['geometry', 'fonts', 'codecs', 'dawn', 'skia']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.desktop:
            for layer in ['paint', 'gfx']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.gpu:
            for layer in ['tint', 'dawn_native', 'gpu_protocol']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.angle:
            files.extend(['native/angle_runtime_sources.bzl', 'native/vulkan_loader_sources.bzl'])
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/angle_runtime_forwarders').rglob('*')) if path.is_file())
        if args.gl:
            files.extend(['native/webui_actions.bzl', 'native/webui_targets.json'])
            for layer in ['browser_services', 'linux_ui']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.gpu_service:
            files.append('native/gpu_service_sources.bzl')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/gpu_service_forwarders').rglob('*')) if path.is_file())
        if args.media:
            for layer in ['pthreadpool', 'ml', 'ffmpeg', 'gpu_client', 'media']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.gpu_client and not args.media:
            files.append('native/gpu_client_sources.bzl')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/gpu_client_forwarders').rglob('*')) if path.is_file())
        if args.compositor:
            files.append('native/compositor_sources.bzl')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/compositor_forwarders').rglob('*')) if path.is_file())
        if args.blink_platform:
            files.extend(['native/devtools_inspector_sources.bzl', 'native/devtools_inspector_targets.json'])
            for layer in ['blink_rust', 'blink_platform']:
                files.append('native/' + layer + '_sources.bzl')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.v8:
            files.append('native/browser_v8_sources.bzl')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/browser_v8_forwarders').rglob('*')) if path.is_file())
        for layer in ['blink_core', 'blink_modules', 'content']:
            if getattr(args, layer):
                files.append('native/' + layer + '_sources.bzl')
                files.append('native/' + layer + '_targets.json')
                files.extend(str(path.relative_to(overlay)) for path in
                             sorted((overlay / ('native/' + layer + '_forwarders')).rglob('*')) if path.is_file())
        if args.blink_core:
            files.append('native/xslt.bzl')
        if args.browser:
            files.extend(['native/browser_sources.bzl', 'native/browser_targets.json'])
            if (overlay / 'build/util/LASTCHANGE').is_file():
                files.append('build/util/LASTCHANGE')
            files.extend(str(path.relative_to(overlay)) for path in
                         sorted((overlay / 'native/browser_forwarders').rglob('*')) if path.is_file())
        if args.variant.startswith('windows_'):
            build = overlay / 'build/BUILD.bazel'
            build.write_text(build.read_text() + '\nexports_files(["precompile.h"])\n')
        for name in files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_copy(overlay / name, target)
        layers = [command[command.index('--layer') + 1] for command in commands
                  if command[0] == 'import_cpp_layer.py']
        copy_package_inputs(overlay, destination, layers)
        write_host_support(destination, args.variant)
    print('Regenerated ' + args.variant + '; platform rule adapters preserved')


if __name__ == '__main__':
    main()
