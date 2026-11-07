"""Captured GPU clients, raster command producers and Viz common types."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":gpu_client_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_gpu_client():
    cc_library(
        name = "gpu_client_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = [":gpu_service_headers", ":gpu_protocol_headers", ":paint_headers", ":gfx_headers"],
    )
    for original, library in LIBRARIES.items():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            hdrs = library["hdrs"],
            copts = captured_copts(library),
            includes = captured_includes(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":gpu_client_headers"] + library["deps"],
        )
    for name, original in {
        "gpu_ipc_client": "//gpu/ipc/client:client",
        "gles2_implementation": "//gpu/command_buffer/client:gles2_implementation",
        "gles2_cmd_helper": "//gpu/command_buffer/client:gles2_cmd_helper",
        "raster_implementation": "//gpu/command_buffer/client:raster",
        "raster_interface": "//gpu/command_buffer/client:raster_interface",
        "viz_common": "//components/viz/common:common",
        "viz_client": "//components/viz/client:client",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
    cc_library(
        name = "gpu_client_test_support",
        deps = [":gpu_client_headers", ":gpu_service", ":gles2_cmd_helper"],
        testonly = True,
    )
