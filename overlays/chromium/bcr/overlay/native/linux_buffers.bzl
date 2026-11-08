"""Captured Linux DRM/GBM wrappers with the original system GBM interface."""

load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":linux_buffers_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_linux_buffers():
    cc_library(
        name = "linux_buffers_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_platform_headers//:gbm", "@chromium_libdrm//:headers"],
    )
    for original, library in LIBRARIES.items():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            hdrs = library["hdrs"],
            includes = library["includes"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":linux_buffers_headers"] + library["deps"],
        )
    for name, original in {
        "linux_gbm": "//ui/gfx/linux:gbm",
        "linux_drm": "//ui/gfx/linux:drm",
        "x11_gpu_memory_buffer_support": "//ui/gfx/linux:gpu_memory_buffer_support_x11",
        "native_pixmap_usage": "//ui/ozone:native_pixmap_usage",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
