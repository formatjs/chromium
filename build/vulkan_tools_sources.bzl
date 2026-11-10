"""Pinned Vulkan tools runtime data used by ANGLE."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_vulkan_tools_sources():
    git_repository(
        name = "chromium_vulkan_tools",
        remote = "https://chromium.googlesource.com/external/github.com/KhronosGroup/Vulkan-Tools",
        commit = "d643b80d6ba8c191bc289fdda52867c3bb3c190b",
        build_file = Label("//build:vulkan_tools.BUILD.bazel"),
    )
