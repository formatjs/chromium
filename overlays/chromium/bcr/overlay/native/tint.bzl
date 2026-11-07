"""Chromium's full captured Tint API and shader backends."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":tint_sources.bzl", "LIBRARIES", "PUBLIC_DEFINES", "SHARED_HEADERS")

def native_tint():
    cc_library(
        name = "spirv_headers",
        deps = [
            "@spirv_headers//:spirv_c_headers",
            "@spirv_headers//:spirv_cpp11_headers",
            "@spirv_headers//:spirv_common_headers",
        ],
    )
    cc_library(
        name = "tint_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        defines = PUBLIC_DEFINES,
        deps = ["@chromium_dawn//:source_headers", ":spirv_headers"],
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
            deps = [":tint_headers"] + library["deps"],
        )
    for name, original in {
        "tint": "//third_party/dawn/src/tint/api:api",
        "tint_wgsl_reader": "//third_party/dawn/src/tint/lang/wgsl/reader:reader",
        "tint_wgsl_writer": "//third_party/dawn/src/tint/lang/wgsl/writer:writer",
        "tint_spirv_writer": "//third_party/dawn/src/tint/lang/spirv/writer:writer",
        "tint_glsl_writer": "//third_party/dawn/src/tint/lang/glsl/writer:writer",
        "tint_hlsl_writer": "//third_party/dawn/src/tint/lang/hlsl/writer:writer",
        "tint_msl_writer": "//third_party/dawn/src/tint/lang/msl/writer:writer",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
