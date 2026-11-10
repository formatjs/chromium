"""Chromium's FFmpeg fork, including its captured codec configuration."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_ffmpeg_sources():
    git_repository(
        name = "chromium_ffmpeg",
        remote = "https://chromium.googlesource.com/chromium/third_party/ffmpeg.git",
        commit = "9e751092c9498b84bbb77e2e0689ef9f50fe608f",
        build_file = Label("//build:ffmpeg.BUILD.bazel"),
    )
