"""Full captured Linux ui/gfx closure with native codecs, DRM and sync."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":gfx_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS")
load(":python_action.bzl", "chromium_python_action")

def native_gfx():
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "gfx_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_libdrm//:headers", "@chromium_libsync//:headers"],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":gfx_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = captured_copts(library, "c_copts"),
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in c_sources],
            copts = captured_copts(library),
            **common
        )
    for name, original in {
        "gfx": "//ui/gfx:gfx",
        "gfx_codec": "//ui/gfx/codec:codec",
        "gfx_memory_buffer": "//ui/gfx:memory_buffer_sources",
        "ui_data_pack": "//ui/base:ui_data_pack",
        "libdrm": "//third_party/libdrm:libdrm",
        "libsync": "//third_party/libsync:libsync",
        "zlib_compression_utils": "//third_party/zlib/google:compression_utils",
        "zlib_compression_utils_portable": "//third_party/zlib/google:compression_utils_portable",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
