"""Captured Ozone platforms, GL initialization and desktop integration."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":ozone_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":python_action.bzl", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_ozone():
    chromium_resource_copy(
        name = "ozone_host_icu_data",
        srcs = {"@chromium_icu//:common/icudtl.dat": "third_party/icu/common/icudtl.dat"},
        outputs = {"icudtl.dat": "third_party/icu/common/icudtl.dat"},
    )
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "ozone_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["ozone_forwarders/**/*.h"]),
        includes = ["..", "gen", "../gpu", "ozone_forwarders"],
        deps = [
            "//build:build_config",
            "@chromium_angle//:headers",
            "@chromium_libdrm//:headers",
            "@chromium_platform_headers//:graphics",
            "@vulkan_headers//:vulkan_headers",
            "@wayland//:wayland_client",
            "@xkbcommon//:xkbcommon_headers",
        ],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":ozone_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = library["c_copts"],
                alwayslink = library["kind"] == "source_set",
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        if library["kind"] == "executable":
            cc_binary(
                name = library["name"],
                srcs = library["srcs"] + library["hdrs"],
                data = [":ozone_host_icu_data"],
                copts = library["copts"],
                local_defines = library["defines"],
                linkopts = library["linkopts"],
                linkstatic = True,
                deps = [":ozone_headers"] + library["deps"],
            )
        else:
            cc_library(
                name = library["name"],
                srcs = [p for p in library["srcs"] if p not in c_sources],
                copts = library["copts"],
                alwayslink = library["kind"] == "source_set",
                **common
            )
    for name, original in {
        "ozone": "//ui/ozone:ozone",
        "gl_init": "//ui/gl/init:init",
        "chromium_dbus": "//dbus:dbus",
        "url_formatter": "//components/url_formatter:url_formatter",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
