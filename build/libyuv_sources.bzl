"""Chromium's pinned libyuv sources."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_libyuv_sources():
    git_repository(
        name = "chromium_libyuv",
        remote = "https://chromium.googlesource.com/libyuv/libyuv.git",
        commit = "94417b9d213364905ce849c25719b819b8dbbaaa",
        build_file = Label("//build:libyuv.BUILD.bazel"),
    )
