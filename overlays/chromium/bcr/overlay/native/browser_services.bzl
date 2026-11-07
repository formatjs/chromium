"""Captured browser metrics, tracing, variations and preference services."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":browser_services_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_browser_services():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "browser_services_snappy_headers",
        hdrs = ["@snappy//:snappy.h"],
        include_prefix = "snappy",
        strip_include_prefix = "/",
        deps = ["@snappy//:snappy"],
    )
    cc_library(
        name = "browser_services_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["browser_services_forwarders/**/*.h"]),
        includes = ["..", "gen", "browser_services_forwarders"],
        deps = ["@chromium_protobuf_javascript//:headers", ":browser_services_snappy_headers"],
    )
    for original, library in LIBRARIES.items():
        common = dict(
            name = library["name"],
            srcs = library["srcs"],
            copts = captured_copts(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":browser_services_headers"] + library["deps"],
        )
        if library["kind"] == "executable":
            cc_binary(**dict(common, srcs = library["srcs"] + library["hdrs"]))
        else:
            cc_library(
                hdrs = library["hdrs"],
                includes = captured_includes(library),
                alwayslink = library["kind"] == "source_set",
                **common
            )
    for name, original in {
        "browser_metrics": "//services/metrics/public/cpp:metrics_cpp",
        "browser_tracing": "//services/tracing/public/cpp:cpp",
        "prefs": "//components/prefs:prefs",
        "variations": "//components/variations:variations",
        "metrics_proto": "//third_party/metrics_proto:metrics_proto",
        "version_info": "//components/version_info:version_info",
        "url_mojom_traits": "//url/mojom:mojom_traits",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
