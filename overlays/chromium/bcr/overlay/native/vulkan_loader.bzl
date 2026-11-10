"""Captured Vulkan loader shared library and its native link interface."""

load(":shared_prefix_consumers.bzl", cc_binary = "shared_prefix_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":vulkan_loader_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_vulkan_loader():
    library = LIBRARIES["//third_party/vulkan-loader/src:libvulkan"]
    cc_library(
        name = "vulkan_loader_headers",
        hdrs = sorted({p: True for p in SHARED_HEADERS + library["hdrs"]}),
        deps = ["@chromium_vulkan_loader//:headers", "@chromium_platform_headers//:graphics", "@vulkan_headers//:vulkan_headers"],
    )
    cc_binary(
        name = "libvulkan.so.1",
        srcs = library["srcs"],
        copts = library["c_copts"],
        local_defines = library["defines"],
        linkopts = library["linkopts"] + ["-Wl,-soname,libvulkan.so.1"],
        linkshared = True,
        linkstatic = True,
        deps = [":vulkan_loader_headers"],
    )
    cc_import(
        name = "vulkan_loader_shared_import",
        shared_library = ":libvulkan.so.1",
    )
    cc_library(
        name = "vulkan_loader",
        deps = [":vulkan_loader_shared_import", "@vulkan_headers//:vulkan_headers"],
    )
