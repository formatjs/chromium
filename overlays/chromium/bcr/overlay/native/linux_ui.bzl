"""Captured Linux UI and Chromium GL wrapper closure."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":linux_ui_sources.bzl", "ACTIONS", "LIBRARIES", "RUNTIME_DEPS", "SHARED_HEADERS")
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
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen", "../gpu"],
        deps = [
            "//build:build_config",
            "@xkbcommon//:xkbcommon_headers",
            "@chromium_angle//:headers",
            "@chromium_platform_headers//:graphics",
            "@chromium_libdrm//:headers",
        ],
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
            deps = [":linux_ui_headers"] + library["deps"],
        )
    for name, original in {
        "chromium_gl": "//ui/gl:gl",
        "ui_base": "//ui/base:base",
        "ui_events": "//ui/events:events",
        "ui_x11": "//ui/base/x:x",
        "gfx_mojom": "//ui/gfx/mojom:mojom",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
    native.filegroup(name = "gl_runtime", srcs = [":angle_runtime"])
