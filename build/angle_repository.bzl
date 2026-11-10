"""Expose cached ANGLE sources at Chromium paths."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def _impl(ctx):
    root = ctx.path(ctx.attr.catalog).dirname
    source = ctx.path(ctx.attr.archive).dirname.dirname
    for path in source.readdir():
        if path.basename not in ["BUILD", "BUILD.bazel", "__source__"]:
            ctx.symlink(path, "third_party/angle/" + path.basename)
    ctx.symlink(root.get_child("build/angle.BUILD.bazel"), "BUILD.bazel")

chromium_angle_repository = repository_rule(
    implementation = _impl,
    attrs = {
        "archive": attr.label(mandatory = True),
        "catalog": attr.label(mandatory = True),
    },
)

def chromium_angle_support():
    http_archive(
        name = "chromium_pciutils",
        urls = ["https://www.kernel.org/pub/software/utils/pciutils/pciutils-3.7.0.tar.xz"],
        sha256 = "9d40b97be8b6a2cdf96aead5a61881d1f7e4e0da9544a9bac4fba1ae9dcd40eb",
        strip_prefix = "pciutils-3.7.0",
        build_file = Label("//build:pciutils.BUILD.bazel"),
    )
    git_repository(
        name = "chromium_vma",
        remote = "https://chromium.googlesource.com/external/github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator.git",
        commit = "cb0597213b0fcb999caa9ed08c2f88dc45eb7d50",
        build_file = Label("//build:vma.BUILD.bazel"),
    )
