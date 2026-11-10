"""Chromium media/storage dependencies absent from BCR."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_media_sources(ctx):
    for name, remote, commit in [
        ("libgav1", "https://chromium.googlesource.com/codecs/libgav1.git", "c05bf9be660cf170d7c26bd06bb42b3322180e58"),
        ("leveldatabase", "https://chromium.googlesource.com/external/leveldb.git", "4ee78d7ea98330f7d7599c42576ca99e3c6ff9c5"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            patch_cmds = ["find . -mindepth 2 -type f \\( -name BUILD -o -name BUILD.bazel \\) -delete"],
            build_file_content = ctx.read(Label("//build:media_sources.BUILD.bazel")).replace("@@PROJECT@@", name),
        )
    git_repository(
        name = "chromium_cdm_api",
        remote = "https://chromium.googlesource.com/chromium/cdm.git",
        commit = "a4cbc4325e6de42ead733f2af43c08292d0e65a8",
        build_file_content = ctx.read(Label("//build:media_sources.BUILD.bazel")).replace("third_party/@@PROJECT@@/src", "media/cdm/api"),
    )
