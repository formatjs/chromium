"""Use the pinned C++-trained compiler as an explicit, verified dependency input."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from tools.ci.buildbuddy_artifacts import api_request


REVISION = '366173ffc47d1a12a92c32d542c39c24b80fea28'
SHA256 = 'adbc348d20518481b44be46c21440c8aec541572014a86614248c3db2b46cc5c'
BINARY_SHA256 = 'd94fff11dc9347aa4d1c8d1a2b51e35935bab730a187e6d2280c979a7d103e38'
BASELINE_SHA256 = '2808ea0503af3656373fc141ddc7d082b53c7f858efd5245aed0241734257348'
NAME = 'llvm-23.1.2-linux-amd64-cxx.tar.zst'
SIZE = 39193174
URI = ('bytestream://remote.buildbuddy.io/bb-snapshot/'
       '02243316ca41f110bb13a141260f7622b9bf21b294f56e1c6fb4b0e2fbaf52b9/'
       'blobs/' + SHA256 + '/' + str(SIZE))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_archive(path):
    path = path.resolve(strict=True)
    if not path.name.endswith('.tar.zst') or path.stat().st_size != SIZE or digest(path) != SHA256:
        raise ValueError('Compiler archive SHA256/size mismatch')
    return path


def ensure_archive(destination):
    cached = destination.exists()
    if not cached:
        key = os.environ.get('BUILDBUDDY_API_KEY', '')
        if not key:
            raise ValueError('Managed BuildBuddy workflow API auth is not available')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            archive = Path(temporary) / NAME
            size, checksum = 0, hashlib.sha256()
            with api_request('GetFile', {'uri': URI}, key) as response, archive.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > SIZE:
                        raise ValueError('Compiler archive exceeds pinned size')
                    checksum.update(chunk)
                    output.write(chunk)
            if size != SIZE or checksum.hexdigest() != SHA256:
                raise ValueError('Compiler archive SHA256/size mismatch')
            shutil.move(archive, destination)
    verify_archive(destination)
    return {'archive_sha256': SHA256, 'archive_bytes': SIZE, 'archive_already_fetched': cached,
            'transport': 'Exact prior compiler-preparation artifact; fetched dependency archive only'}


def configure_compiler(source, archive):
    archive = verify_archive(archive)
    template = source / 'build/llvm-compiler-base-index.json'
    index = json.loads(template.read_text())
    original = index['latest_by_llvm_version']['23.1.2']
    if index['releases'][original]['linux-amd64-musl']['sha256'] != BASELINE_SHA256:
        raise ValueError('Unexpected baseline compiler index')
    module, build = source / 'MODULE.bazel', source / 'BUILD.bazel'
    module_text = module.read_text()
    if 'llvm_toolchain_minimal.bzl' in module_text:
        raise ValueError('Source already selects an explicit LLVM index')
    selected = 'llvm-23.1.2-cxx-training-1'
    index['releases'][selected] = copy.deepcopy(index['releases'][original])
    index['releases'][selected]['linux-amd64-musl'] = {'url': archive.as_uri(), 'sha256': SHA256}
    index['latest_by_llvm_version']['23.1.2'] = selected
    generated = source / '_cold_compiler_index.json'
    if generated.exists():
        raise FileExistsError(generated)
    generated.write_text(json.dumps(index, indent=2) + '\n')
    module.write_text(module_text + '''

cold_llvm_prebuilt = use_extension("@llvm//extensions:llvm_toolchain_minimal.bzl", "llvm_toolchain_minimal")
cold_llvm_prebuilt.index(file = "//:_cold_compiler_index.json")
use_repo(
    cold_llvm_prebuilt,
    "llvm-toolchain-minimal-darwin-amd64",
    "llvm-toolchain-minimal-darwin-arm64",
    "llvm-toolchain-minimal-linux-amd64",
    "llvm-toolchain-minimal-linux-arm64",
    "llvm-toolchain-minimal-windows-amd64",
    "llvm-toolchain-minimal-windows-arm64",
)
''')
    with build.open('a') as output:
        output.write('\nexports_files(["_cold_compiler_index.json"])\n')
    return {'archive_sha256': SHA256, 'archive_uri': archive.as_uri(),
            'expected_binary_sha256': BINARY_SHA256,
            'base_index_sha256': digest(template), 'generated_index_sha256': digest(generated),
            'configured_module_sha256': digest(module),
            'configuration': 'Fresh git archive plus explicit verified compiler dependency via LLVM root index API'}


def verify_compiler(output_base):
    driver = output_base / ('external/llvm++llvm_toolchain_minimal+'
                            'llvm-toolchain-minimal-linux-amd64/bin/clang++')
    actual = digest(driver)
    if actual != BINARY_SHA256:
        raise ValueError('Build did not select the pinned trained compiler binary')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=[REVISION], required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(ensure_archive(args.destination)), flush=True)


if __name__ == '__main__':
    main()
