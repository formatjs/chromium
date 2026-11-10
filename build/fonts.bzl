"""Pinned font sources for Chromium's native renderer graph."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_font_sources():
    for name, remote, commit in [
        ("freetype", "https://chromium.googlesource.com/chromium/src/third_party/freetype2.git", "d3668e00da732654b50e4e81f982544ed6e26390"),
        ("harfbuzz", "https://chromium.googlesource.com/external/github.com/harfbuzz/harfbuzz.git", "7d936359a27abb2d7cb14ecc102463bb15c11843"),
        ("fontconfig", "https://chromium.googlesource.com/external/fontconfig.git", "f0ed9c3f43161d3555f6f7a5234b22fe7ca60727"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            build_file = Label("//build:" + name + ".BUILD.bazel"),
        )
