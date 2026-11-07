"""Captured GPU command protocol, shared-image formats and GLES2 interfaces."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":gpu_protocol_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_gpu_protocol():
    cc_library(
        name = "gpu_protocol_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen", "../gpu"],
        deps = ["@chromium_angle//:headers"],
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
            alwayslink = library["kind"] == "source_set",
            deps = [":gpu_protocol_headers"] + library["deps"],
        )
    for name, original in {
        "gpu_command_common": "//gpu/command_buffer/common:common",
        "gpu_gles2_commands": "//gpu/command_buffer/common:gles2",
        "gpu_gles2_utils": "//gpu/command_buffer/common:gles2_utils",
        "gpu_gles2_interface": "//gpu/command_buffer/client:gles2_interface",
        "viz_shared_image_format": "//components/viz/common:shared_image_format",
        "gl_enums": "//ui/gl:gl_enums",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
