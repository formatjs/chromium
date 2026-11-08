"""Complete Linux network closure, native generators, DNS and SQL support."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":base_bind_consumers.bzl", "base_bind_cohort")
load(":network_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":protobuf_config.bzl", "chromium_protobuf_library")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_network():
    chromium_protobuf_library(name = "protobuf_full_runtime", dep = "@protobuf//:protobuf")
    cc_library(
        name = "network_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["network_forwarders/**/*.h"]),
        includes = ["..", "gen", "network_forwarders"],
    )
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    for original, library in LIBRARIES.items():
        rule = cc_binary if library["kind"] == "executable" else cc_library
        common = dict(
            name = library["name"],
            srcs = library["srcs"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":network_headers", "@chromium_platform_headers//:gssapi"] + library["deps"],
        )
        if library["kind"] == "executable":
            common["srcs"] = library["srcs"] + library["hdrs"]
        else:
            common["hdrs"] = library["hdrs"]
            common["includes"] = library["includes"]
        if library["name"] == "network_211be4e8e759f7c4":
            replacement = base_bind_cohort(common)
            common["srcs"] = select({
                "//native/tool_configuration:base_bind_pch": [],
                "//conditions:default": common["srcs"],
            })
            common["deps"] = select({
                "//native/tool_configuration:base_bind_pch": [replacement] + common["deps"],
                "//conditions:default": common["deps"],
            })
        rule(**common)
    for name, original in {
        "net": "//net:net",
        "sql": "//sql:sql",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
