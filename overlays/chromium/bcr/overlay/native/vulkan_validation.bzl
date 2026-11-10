"""Captured Vulkan validation shared library and original runtime JSON."""

load(":shared_prefix_consumers.bzl", cc_binary = "shared_prefix_binary")
load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":python_action.bzl", "chromium_python_action")
load(":vulkan_validation_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS")

def native_vulkan_validation():
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "vulkan_validation_headers",
        hdrs = SHARED_HEADERS,
        deps = [
            ":spirv_headers",
            "@spirv_headers//:spirv_cpp_headers",
            "@chromium_vulkan_validation//:headers",
            "@chromium_platform_headers//:graphics",
            "@vulkan_headers//:vulkan_headers",
            "@chromium_vulkan_utility//:headers",
        ],
    )
    for original, library in LIBRARIES.items():
        common = dict(
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":vulkan_validation_headers"] + library["deps"],
        )
        if library["kind"] == "group":
            native.filegroup(name = library["name"], srcs = library["deps"])
        elif library["kind"] == "shared_library":
            common["linkopts"] = common["linkopts"] + ["-Wl,-soname,libVkLayer_khronos_validation.so"]
            cc_binary(
                name = "libVkLayer_khronos_validation.so",
                linkshared = True,
                **common
            )
            native.alias(name = library["name"], actual = ":libVkLayer_khronos_validation.so")
        else:
            cc_library(
                name = library["name"],
                hdrs = library["hdrs"],
                **common
            )
    native.filegroup(
        name = "vulkan_validation_runtime",
        srcs = [":libVkLayer_khronos_validation.so", ":angledata/VkLayer_khronos_validation.json"],
    )
