"""Import declared Chromium preprocessing outputs into LLVM's training workspace."""

import hashlib
import json
from pathlib import Path
import shutil


def compile_flags(arguments, source):
    """Keep code generation flags; preprocessing inputs are already embedded."""
    result = ['-x', 'c++-cpp-output']
    pairs = {'-o', '-MF', '-MT', '-MQ', '-I', '-iquote', '-isystem', '-iframework',
             '-D', '-U', '-isysroot', '--sysroot', '-resource-dir', '-x'}
    switches = {'-c', '-E', '-MD', '-MMD', '-MP', '-nostdlibinc', '-nostdinc', '-nostdinc++'}
    index = 0
    found = 0
    while index < len(arguments):
        value = arguments[index]
        if value == source:
            found += 1
        elif value in pairs:
            if index + 1 == len(arguments):
                raise ValueError('Missing compile option value: ' + value)
            index += 1
        elif arguments[index:index + 3] == ['-Xclang', '-internal-isystem', '-Xclang']:
            if index + 3 == len(arguments):
                raise ValueError('Missing compiler include path')
            index += 3
        elif value not in switches and not value.startswith(('-I', '-D', '-U', '--sysroot=', '-resource-dir=')):
            if ('external/' in value or 'bazel-out/' in value) and not value.startswith('-frandom-seed='):
                raise ValueError('Unexpected compiler input path: ' + value)
            result.append(value)
        index += 1
    if found != 1:
        raise ValueError('Expected one original source argument')
    result += ['-Xclang', '-main-file-name', '-Xclang', Path(source).name]
    return result


def install_inputs(directory, workspace):
    directory = Path(directory).resolve()
    destination = workspace / 'toolchain/bootstrap/stage3/chromium_training'
    destination.mkdir(exist_ok=False)
    workloads, provenance = [], []
    for name in ['v8', 'content']:
        stem = 'llvm_training_' + name
        manifest_path, source = directory / (stem + '.json'), directory / (stem + '.ii')
        if any(path.is_symlink() or not path.is_file() for path in [manifest_path, source]):
            raise ValueError('Expected regular Bazel preprocessing outputs: ' + stem)
        manifest = json.loads(manifest_path.read_text())
        if Path(manifest['preprocessed']).name != source.name:
            raise ValueError('Preprocessed output does not match manifest')
        flags = compile_flags(manifest['arguments'], manifest['source'])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        copied = destination / source.name
        shutil.copyfile(source, copied)
        if hashlib.sha256(copied.read_bytes()).hexdigest() != digest:
            raise ValueError('Training input changed while copying')
        workloads.append({'name': name, 'source': 'chromium_training/' + source.name, 'flags': flags})
        provenance.append({'name': name, 'source': manifest['source'],
                           'preprocessed_sha256': digest, 'preprocessed_bytes': copied.stat().st_size,
                           'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                           'compiler': manifest['compiler'], 'flags': flags})
    lines = ['WORKLOADS = [']
    for workload in workloads:
        lines += ['    {', '        \"name\": ' + json.dumps(workload['name']) + ',',
                  '        \"source\": ' + json.dumps(workload['source']) + ',',
                  '        \"flags\": [']
        lines += ['            ' + json.dumps(flag) + ',' for flag in workload['flags']]
        lines += ['        ],', '    },']
    (destination / 'inputs.bzl').write_text('\n'.join(lines + [']', '']))
    (destination / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance
