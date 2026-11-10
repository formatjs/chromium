"""Captured SwiftShader Vulkan driver with its original Subzero JIT."""

load(":shared_prefix_consumers.bzl", cc_binary = "shared_prefix_binary")
load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":python_action.bzl", "chromium_python_action")
load(":swiftshader_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS")

def native_swiftshader():
    for action in ACTIONS:
        chromium_python_action(**action)
    native.filegroup(
        name = "swiftshader_runtime",
        srcs = [":libvk_swiftshader.so", ":vk_swiftshader_icd.json"],
    )
    cc_library(
        name = "swiftshader_headers",
        hdrs = SHARED_HEADERS,
        deps = [
            ":spirv_headers",
            "@spirv_headers//:spirv_cpp_headers",
            "@chromium_swiftshader//:headers",
            "@chromium_platform_headers//:graphics",
        ],
    )
    for original, library in LIBRARIES.items():
        dependencies = [":swiftshader_headers"] + library["deps"]
        if library["kind"] == "shared_library":
            script = "@chromium_swiftshader//:src/Vulkan/vk_swiftshader.lds"
            cc_binary(
                name = "libvk_swiftshader.so",
                srcs = library["srcs"],
                copts = library["copts"],
                local_defines = library["defines"],
                additional_linker_inputs = [script],
                linkopts = [p.replace("../../third_party/swiftshader/src/Vulkan/vk_swiftshader.lds", "$(location " + script + ")") for p in library["linkopts"]] + ["-Wl,-soname,libvk_swiftshader.so"],
                linkshared = True,
                linkstatic = True,
                deps = dependencies,
            )
            continue
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        assembly = [p for p in library["srcs"] if p.endswith((".S", ".s"))]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = dependencies,
        )
        if c_sources:
            cc_library(name = library["name"] + "_c", srcs = c_sources, copts = library["c_copts"], **common)
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        if assembly:
            cc_library(name = library["name"] + "_asm", srcs = assembly, copts = library["asm_copts"], **common)
            common["deps"] = common["deps"] + [":" + library["name"] + "_asm"]
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in c_sources and p not in assembly],
            copts = library["copts"],
            **common
        )
