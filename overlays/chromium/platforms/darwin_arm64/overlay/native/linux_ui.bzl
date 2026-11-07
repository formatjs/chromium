"""Captured macOS Chromium GL integration."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":linux_ui_sources.bzl", "ACTIONS", "LIBRARIES", "RUNTIME_DEPS", "SHARED_HEADERS")
load(":objcxx.bzl", "objcxx_library")
load(":python_action.bzl", "chromium_python_action")

def native_linux_ui():
    for action in ACTIONS:
        chromium_python_action(**action)
    write_file(
        name = "gl_runtime_requirements",
        out = "gl_runtime_requirements.json",
        content = [json.encode_indent(RUNTIME_DEPS, indent = "  ")],
    )
    cc_library(
        name = "linux_ui_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["linux_ui_forwarders/**/*.h"]),
        includes = ["..", "gen", "../gpu", "linux_ui_forwarders"],
        deps = [
            "//build:build_config",
            "@chromium_angle//:headers",
        ],
    )
    for original, library in LIBRARIES.items():
        c_sources = [source for source in library["srcs"] if source.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":linux_ui_headers"] + library["deps"],
        )
        if library.get("objcxx_srcs"):
            cc_library(
                name = library["name"] + "_headers",
                hdrs = library["hdrs"],
                includes = library["includes"],
                deps = common["deps"],
            )
            objcxx_library(
                name = library["name"] + "_objcxx",
                srcs = library["objcxx_srcs"],
                copts = library["objcxx_copts"],
                local_defines = library["defines"],
                deps = [":" + library["name"] + "_headers"],
                alwayslink = True,
                target_compatible_with = ["@platforms//os:macos"],
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_objcxx"]
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = library["c_copts"],
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = [source for source in library["srcs"] if source not in c_sources],
            copts = library["copts"],
            **common
        )
    for name, original in {
        "chromium_gl": "//ui/gl:gl",
        "ui_base": "//ui/base:base",
        "ui_events": "//ui/events:events",
        "ui_x11": "//ui/base/x:x",
        "gfx_mojom": "//ui/gfx/mojom:mojom",
    }.items():
        if original in LIBRARIES:
            native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
    native.filegroup(name = "gl_runtime", srcs = [":angle_runtime"])
