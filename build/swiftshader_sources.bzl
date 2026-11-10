"""Pinned SwiftShader source for Chromium's native Vulkan runtime."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_swiftshader_sources():
    git_repository(
        name = "chromium_swiftshader",
        remote = "https://swiftshader.googlesource.com/SwiftShader.git",
        commit = "5f1c459a11bb4899301e89609cbf7547f9f31e20",
        build_file = Label("//build:swiftshader.BUILD.bazel"),
        patch_cmds = ["rm -f third_party/marl/BUILD.bazel third_party/marl/examples/BUILD.bazel third_party/SPIRV-Tools/BUILD.bazel third_party/SPIRV-Headers/BUILD.bazel"],
    )
