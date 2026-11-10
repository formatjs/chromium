"""Pinned image codec sources used by Chromium and Skia."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_codec_sources():
    for name, remote, commit in [
        ("jpeg", "https://chromium.googlesource.com/chromium/deps/libjpeg_turbo.git", "e14cbfaa85529d47f9f55b0f104a579c1061f9ad"),
        ("webp", "https://chromium.googlesource.com/webm/libwebp.git", "b0e8039062eedbcb20ebb1bad62bfeaee2b94ec6"),
        ("wuffs", "https://skia.googlesource.com/external/github.com/google/wuffs-mirror-release-c.git", "e3f919ccfe3ef542cfc983a82146070258fb57f8"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            build_file = Label("//build:" + name + ".BUILD.bazel"),
        )
