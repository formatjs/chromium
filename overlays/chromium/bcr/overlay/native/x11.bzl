"""Captured Chromium X11 protocol and platform-event libraries."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":python_action.bzl", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":x11_sources.bzl", "ACTIONS", "COPIES", "LIBRARIES", "SHARED_HEADERS")

def native_x11():
    for copy in COPIES:
        chromium_resource_copy(**copy)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "x11_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_platform_headers//:graphics"],
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
            deps = [":x11_headers"] + library["deps"],
        )
    for name, original in {
        "gfx_x11": "//ui/gfx/x:x",
        "platform_event": "//ui/events:platform_event",
        "platform_event_source": "//ui/events/platform:platform",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
