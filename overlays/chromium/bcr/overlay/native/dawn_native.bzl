"""Captured Dawn native library; runtime shared libraries remain separate."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":dawn_native_sources.bzl", "ACTIONS", "LIBRARIES", "METADATA", "PUBLIC_DEFINES", "RUNTIME_DEPS", "SHARED_HEADERS")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":python_action.bzl", "chromium_python_action")

def native_dawn_backend():
    native.filegroup(
        name = "dawn_native_runtime",
        srcs = [":libvulkan.so.1", ":swiftshader_runtime", ":vulkan_validation_runtime"],
    )
    write_file(
        name = "dawn_native_runtime_requirements",
        out = "dawn_native_runtime_requirements.json",
        content = [json.encode_indent(RUNTIME_DEPS, indent = "  ")],
    )
    for path, content in METADATA.items():
        if path in CAPTURED_FILES:
            continue
        if path == "gpu/webgpu/DAWN_VERSION":
            continue
        write_file(
            name = "dawn_native_metadata_" + path.replace("/", "_"),
            out = path if path.startswith("gen/") else "metadata/" + path,
            content = [content],
        )
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "dawn_native_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen", "gen/third_party/dawn/include", "gen/third_party/dawn/src"],
        defines = PUBLIC_DEFINES,
        deps = [
            ":dawn_cpp_headers",
            ":tint_headers",
            "@chromium_dawn//:source_headers",
            "@chromium_dawn//:khronos_headers",
            "@chromium_platform_headers//:graphics",
            "@vulkan_utility_libraries//:vulkan_utility_headers",
        ],
    )
    for original, library in LIBRARIES.items():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            copts = captured_copts(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":dawn_native_headers"] + library["deps"],
        )
    native.alias(
        name = "dawn_native_library",
        actual = ":" + LIBRARIES["//third_party/dawn/src/dawn/native:static"]["name"],
    )
