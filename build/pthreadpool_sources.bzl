"""Chromium's pinned Google pthreadpool fork."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_pthreadpool_sources():
    git_repository(
        name = "chromium_pthreadpool",
        remote = "https://chromium.googlesource.com/external/github.com/google/pthreadpool.git",
        commit = "f5a07eddbf4be8f23e29e60a2ccf66b78b71f119",
        build_file = Label("//build:pthreadpool.BUILD.bazel"),
    )
