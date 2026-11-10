"""Pinned Linux graphics dependencies missing from BCR."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_graphics_sources():
    for name, remote, commit in [
        ("libdrm", "https://chromium.googlesource.com/chromiumos/third_party/libdrm.git", "ad78bb591d02162d3b90890aa4d0a238b2a37cde"),
        ("libsync", "https://chromium.googlesource.com/aosp/platform/system/core/libsync.git", "f4f4387b6bf2387efbcfd1453af4892e8982faf6"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            build_file = Label("//build:" + name + ".BUILD.bazel"),
        )
