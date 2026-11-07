"""Chromium FFmpeg profile and native SIMD assembly."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":ffmpeg_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":public_dependency.bzl", "chromium_public_dependency")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_ffmpeg():
    chromium_public_dependency(name = "ffmpeg_opus", dependency = "@opus//:opus")
    source_root = Label("@chromium_ffmpeg//:chromium/config/Chromium/linux/x64/config.h").workspace_root
    config_options = select({
        "@platforms//cpu:aarch64": ["-iquote" + source_root + "/chromium/config/Chromium/linux/arm64"],
        "//conditions:default": ["-iquote" + source_root + "/chromium/config/Chromium/linux/x64"],
    })
    cc_library(
        name = "ffmpeg_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_ffmpeg//:chromium_headers"],
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
            deps = [":ffmpeg_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = config_options + captured_copts(library, "c_copts"),
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = other_sources,
            copts = config_options + captured_copts(library),
            **common
        )
    native.alias(name = "ffmpeg", actual = ":" + LIBRARIES["//third_party/ffmpeg:ffmpeg"]["name"])
