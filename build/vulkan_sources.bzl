"""Pinned Vulkan runtime sources required by Chromium's browser bundle."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_vulkan_sources():
    git_repository(
        name = "chromium_vulkan_loader",
        remote = "https://chromium.googlesource.com/external/github.com/KhronosGroup/Vulkan-Loader",
        commit = "f703f919c30c5b67958d35d40a4297cb3823ed78",
        build_file = Label("//build:vulkan_loader.BUILD.bazel"),
    )

    git_repository(
        name = "chromium_vulkan_validation",
        remote = "https://chromium.googlesource.com/external/github.com/KhronosGroup/Vulkan-ValidationLayers",
        commit = "83d96b88de7b85c3f29545170857e54e348421b2",
        build_file = Label("//build:vulkan_validation.BUILD.bazel"),
    )

    git_repository(
        name = "chromium_vulkan_utility",
        remote = "https://chromium.googlesource.com/external/github.com/KhronosGroup/Vulkan-Utility-Libraries",
        commit = "4322db5906e67b57ec9c327e6afe3d98ed893df7",
        build_file = Label("//build:vulkan_utility.BUILD.bazel"),
    )
