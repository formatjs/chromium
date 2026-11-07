"""Captured ANGLE EGL/GLES libraries and native backend dependencies."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":angle_runtime_sources.bzl", "ACTIONS", "LIBRARIES", "RUNTIME_DEPS", "SHARED_HEADERS")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":python_action.bzl", "chromium_python_action")

def native_angle_runtime():
    for action in ACTIONS:
        chromium_python_action(**action)
    write_file(
        name = "angle_runtime_requirements",
        out = "angle_runtime_requirements.json",
        content = [json.encode_indent(RUNTIME_DEPS, indent = "  ")],
    )
    cc_library(
        name = "angle_runtime_headers",
        hdrs = SHARED_HEADERS,
        includes = ["../third_party/zlib/google"],
        deps = [
            "@chromium_angle//:headers",
            "@chromium_vma//:headers",
            "@chromium_platform_headers//:graphics",
            "@chromium_pciutils//:headers",
            "@spirv_headers//:spirv_cpp_headers",
            ":spirv_headers",
        ],
    )
    for original, library in LIBRARIES.items():
        common = dict(
            copts = captured_copts(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":angle_runtime_headers"] + library["deps"],
        )
        if library["kind"] == "shared_library":
            filename = original.split(":")[-1] + ".so"
            cc_binary(
                name = filename,
                srcs = library["srcs"],
                linkshared = True,
                **dict(common, linkopts = common["linkopts"] + ["-Wl,-soname," + filename])
            )
            cc_import(name = library["name"], shared_library = ":" + filename)
        else:
            c_sources = [p for p in library["srcs"] if p.endswith(".c")]
            common.update(hdrs = library["hdrs"], includes = captured_includes(library))
            if c_sources:
                cc_library(name = library["name"] + "_c", srcs = c_sources, **dict(common, copts = captured_copts(library, "c_copts")))
                common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
            cc_library(
                name = library["name"],
                srcs = [p for p in library["srcs"] if p not in c_sources],
                alwayslink = library["kind"] == "source_set",
                **common
            )
    native.filegroup(
        name = "angle_runtime",
        srcs = [":libEGL.so", ":libGLESv2.so", ":dawn_native_runtime", ":vulkan_mock_runtime"],
    )
