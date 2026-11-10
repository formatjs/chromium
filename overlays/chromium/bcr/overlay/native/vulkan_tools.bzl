"""Captured optional mock ICD artifact bundled with ANGLE."""

load(":shared_prefix_consumers.bzl", cc_binary = "shared_prefix_binary")
load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":python_action.bzl", "chromium_python_action")
load(":vulkan_tools_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS")

def native_vulkan_tools():
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "vulkan_tools_headers",
        hdrs = SHARED_HEADERS,
        deps = ["@chromium_vulkan_tools//:headers", "@chromium_platform_headers//:graphics", "@vulkan_headers//:vulkan_headers"],
    )
    library = LIBRARIES["//third_party/vulkan-tools/src:VkICD_mock_icd"]
    cc_binary(
        name = "libVkICD_mock_icd.so",
        srcs = library["srcs"],
        copts = library["copts"],
        local_defines = library["defines"],
        linkopts = library["linkopts"] + ["-Wl,-soname,libVkICD_mock_icd.so"],
        linkshared = True,
        linkstatic = True,
        deps = [":vulkan_tools_headers"] + library["deps"],
    )
    native.filegroup(
        name = "vulkan_mock_runtime",
        srcs = [":libVkICD_mock_icd.so", ":angledata/VkICD_mock_icd.json"],
    )
