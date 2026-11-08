"""Use LLVM's archive override for Stage 3 relocations and its BOLT runtime."""

import ast
import hashlib
import json
from pathlib import Path
import shutil

from tools.ci.chromium import ROOT


RUNTIME_TARGET = '@llvm-project//bolt/runtime:bolt_rt_instr'


def source_patches(workspace):
    module = ast.parse((workspace / 'extensions/llvm.bzl').read_text())
    values = {node.targets[0].id: node.value for node in module.body if isinstance(node, ast.Assign)}

    def evaluate(node):
        if isinstance(node, ast.Name):
            return evaluate(values[node.id])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return evaluate(node.left) + evaluate(node.right)
        return ast.literal_eval(node)

    patches = evaluate(values['_LLVM_23_SOURCE_PATCHES'])
    if not 20 < len(patches) < 100 or any(not (workspace / name[2:].replace(':', '/')).is_file() for name in patches):
        raise ValueError('Unexpected pinned LLVM source patches')
    return patches


def source_excludes(workspace):
    module = ast.parse((workspace / 'private/llvm_project_archive.bzl').read_text())
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == '_default_excludes')
    values = {node.targets[0].id: ast.literal_eval(node.value)
              for node in function.body if isinstance(node, ast.Assign)}
    excludes = list(values['excludes'])
    for project in values['test_docs_subprojects']:
        if project != 'mlir':
            excludes.append(project + '/test/*')
        excludes.append(project + '/docs/*')
    return excludes


def install_relocations(workspace):
    module = workspace / 'MODULE.bazel'
    text = module.read_text()
    marker = 'llvm.version(llvm_version = LLVM_VERSION)'
    if text.count(marker) != 1 or 'llvm.from_archive(' in text:
        raise ValueError('Unexpected LLVM source version declaration')
    index = json.loads((workspace / 'llvm_versions.json').read_text())
    spec = index['23.1.2']
    patches = source_patches(workspace)
    excludes = source_excludes(workspace)
    patch = workspace / 'llvm-bolt-input.patch'
    shutil.copyfile(ROOT / 'build/llvm-bolt-relocations.patch', patch)
    runtime = workspace / 'llvm-bolt-runtime.BUILD.bazel'
    shutil.copyfile(ROOT / 'build/llvm-bolt-runtime.BUILD.bazel', runtime)
    build = workspace / 'BUILD.bazel'
    build.write_text(build.read_text() + '\nexports_files(["llvm-bolt-input.patch", "llvm-bolt-runtime.BUILD.bazel"])\n')
    declaration = '\nllvm.from_archive(\n'
    for key, value in [('url', spec['url']), ('sha256', spec['sha256']),
                       ('strip_prefix', spec.get('strip_prefix', 'llvm-project-23.1.2.src')),
                       ('patch_args', ['-p1']), ('patches', patches + ['//:llvm-bolt-input.patch']),
                       ('excludes', excludes),
                       ('files', {'bolt/runtime/BUILD.bazel': '//:llvm-bolt-runtime.BUILD.bazel'})]:
        declaration += '    ' + key + ' = ' + json.dumps(value) + ',\n'
    declaration += ')\n'
    module.write_text(text.replace(marker, marker + declaration))
    return {'llvm_archive_sha256': spec['sha256'], 'llvm_archive_url': spec['url'],
            'original_patches_retained': len(patches), 'original_excludes_retained': len(excludes),
            'bolt_input_patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
            'bolt_runtime_build_sha256': hashlib.sha256(runtime.read_bytes()).hexdigest()}
