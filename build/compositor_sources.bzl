"""Exact Chromium compositor dependencies absent from BCR."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def chromium_compositor_sources(ctx):
    for name, remote, commit, prefix in [
        ("webrtc", "https://webrtc.googlesource.com/src.git", "29d6eabaf0b5c1a62af6e7fd03adebf5e1a446e8", "third_party/webrtc"),
        ("libsrtp", "https://chromium.googlesource.com/chromium/deps/libsrtp.git", "a52756acb1c5e133089c798736dd171567df11f5", "third_party/libsrtp"),
        ("federated_compute", "https://chromium.googlesource.com/external/github.com/google-parfait/federated-compute.git", "e51058dfe7888094ecc09cda38bfceffd4d4664b", "third_party/federated_compute/src"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            patches = [Label("//build:libsrtp-private-config.patch")] if name == "libsrtp" else [],
            patch_args = ["-p1"],
            patch_cmds = ["find . -mindepth 2 -type f \\( -name BUILD -o -name BUILD.bazel \\) -delete"],
            build_file_content = ctx.read(Label("//build:compositor_sources.BUILD.bazel")).replace("@@PREFIX@@", prefix),
        )

    for name, archive, digest, template in [
        ("xcomposite", "libXcomposite-0.4.5", "b3218a2c15bab8035d16810df5b8251ffc7132ff3aa70651a1fba0bfe9634e8f", "xcomposite"),
        ("xtst", "libXtst-1.2.3", "4655498a1b8e844e3d6f21f3b2c4e2b571effb5fd83199d428a6ba7ea4bf5204", "xtst"),
    ]:
        http_archive(
            name = "chromium_" + name,
            urls = ["https://www.x.org/releases/individual/lib/" + archive + ".tar.bz2"],
            sha256 = digest,
            strip_prefix = archive,
            build_file = Label("//build:" + template + ".BUILD.bazel"),
        )
