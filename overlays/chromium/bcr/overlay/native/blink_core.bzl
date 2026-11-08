"""Blink core and its original code generators."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":blink_core_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":blink_pch.bzl", "blink_bindings_pch", "blink_core_pch")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_blink_core():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "blink_core_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["blink_core_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "blink_core_forwarders"],
        deps = [":blink_platform_headers", ":libxslt"],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            features = ["cc_include_scanning"],
            # Skia selects these through macro includes.
            additional_compiler_inputs = [
                "//:base/component_export.h",
                "//:skia/config/SkUserConfig.h",
                "//:skia/config/sk_ref_cnt_ext_debug.h",
                "//:skia/config/sk_ref_cnt_ext_release.h",
                "//:skia/ext/skia_histogram.h",
                # Keep the directory used by ../../skia/config includes.
                ":blink_core_forwarders/third_party/re2/src/re2/re2.h",
            ],
            deps = [":blink_core_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = library["c_copts"],
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        sources = [p for p in library["srcs"] if p not in c_sources]
        replacement = None
        if original == "//third_party/blink/renderer/core:core":
            replacement = blink_core_pch(library["name"], library, common)
        elif original == "//third_party/blink/renderer/bindings/core/v8:v8":
            replacement = blink_bindings_pch(library, common)
        if replacement:
            sources = select({
                "//native/tool_configuration:blink_pch": [],
                "//conditions:default": sources,
            })
            common["deps"] = select({
                "//native/tool_configuration:blink_pch": [replacement] + common["deps"],
                "//conditions:default": common["deps"],
            })
        cc_library(
            name = library["name"],
            srcs = sources,
            copts = library["copts"],
            **common
        )
    native.alias(
        name = "blink_core",
        actual = ":" + LIBRARIES["//third_party/blink/renderer/core:core"]["name"],
    )
