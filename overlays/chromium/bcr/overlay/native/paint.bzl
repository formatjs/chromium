"""Complete captured compositor paint closure, using Chromium's native providers."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":paint_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_paint():
    cc_library(
        name = "paint_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
    )
    for original, library in LIBRARIES.items():
        assembly = [p for p in library["srcs"] if p.endswith((".S", ".s"))]
        if assembly:
            cc_library(
                name = library["name"] + "_asm",
                srcs = assembly,
                hdrs = library["hdrs"],
                includes = captured_includes(library),
                copts = captured_copts(library, "asm_copts"),
                local_defines = library["defines"],
                deps = [":paint_headers"] + library["deps"],
            )
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in assembly],
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            copts = captured_copts(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":paint_headers"] + library["deps"] + ([":" + library["name"] + "_asm"] if assembly else []),
        )
    for name, original in {
        "paint": "//cc/paint:paint",
        "cc_base": "//cc/base:base",
        "cc_debug": "//cc/debug:debug",
        "gfx_color_space": "//ui/gfx:color_space",
        "gfx_skia": "//ui/gfx:gfx_skia",
        "gfx_animation": "//ui/gfx/animation:animation",
        "crash_keys": "//components/crash/core/common:crash_key",
        "crashpad_client": "//third_party/crashpad/crashpad/client:client",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
