"""Pinned native protoc JavaScript plugin used by Chromium generators."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_protobuf_javascript_sources():
    git_repository(
        name = "chromium_protobuf_javascript",
        remote = "https://chromium.googlesource.com/external/github.com/protocolbuffers/protobuf-javascript",
        commit = "e6d763860001ba1a76a63adcff5efb12b1c96024",
        build_file = Label("//build:protobuf_javascript.BUILD.bazel"),
        patch_cmds = ["rm -f generator/BUILD.bazel"],
    )
