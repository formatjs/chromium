"""Original geometry/range implementations and complete native Mojo bindings."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":geometry_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_geometry():
    cc_library(
        name = "geometry_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["geometry_forwarders/**/*.h"]),
        includes = ["..", "gen", "geometry_forwarders"],
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
            deps = [":geometry_headers"] + library["deps"],
        )
    for name, original in {
        "gfx_geometry_skia": "//ui/gfx/geometry:geometry_skia",
        "gfx_geometry": "//ui/gfx/geometry:geometry",
        "gfx_range": "//ui/gfx/range:range",
        "gfx_geometry_mojom": "//ui/gfx/geometry/mojom:mojom",
        "gfx_range_mojom": "//ui/gfx/range/mojom:mojom",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
