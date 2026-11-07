"""Original JPEG, WebP and GIF codec implementations and native SIMD assembly."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":codecs_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_codecs():
    cc_library(
        name = "codec_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_jpeg//:headers", "@chromium_webp//:headers", "@chromium_wuffs//:headers"],
    )
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        other_sources = [p for p in library["srcs"] if not p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":codec_headers"] + library["deps"],
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
            srcs = other_sources,
            copts = captured_copts(library),
            **common
        )
    for name, original in {
        "jpeg": "//third_party:jpeg",
        "webp": "//third_party/libwebp:libwebp",
        "wuffs": "//third_party/wuffs:wuffs",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
