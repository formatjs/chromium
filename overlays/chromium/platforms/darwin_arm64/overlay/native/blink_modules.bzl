"""Blink modules and their original code generators."""

load(":blink_modules_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":objcxx.bzl", "chromium_objc_libraries")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_blink_modules():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "blink_modules_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["blink_modules_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "blink_modules_forwarders"],
        deps = [":blink_core_headers", ":libxslt"],
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
            deps = [":blink_modules_headers"] + library["deps"],
        )
        if original.startswith("//third_party/blink/renderer/modules") or original.startswith("//third_party/blink/renderer/bindings"):
            common.update(
                features = ["cc_include_scanning"],
                # Skia uses macro includes that the scanner cannot resolve.
                additional_compiler_inputs = [
                    "//:base/component_export.h",
                    "//:skia/config/SkUserConfig.h",
                    "//:skia/config/sk_ref_cnt_ext_debug.h",
                    "//:skia/config/sk_ref_cnt_ext_release.h",
                    "//:skia/ext/skia_histogram.h",
                    ":gen/gpu/config/gpu_driver_bug_workaround_autogen.h",
                    ":blink_modules_forwarders/third_party/re2/src/re2/re2.h",
                ],
            )
        common["deps"] = common["deps"] + chromium_objc_libraries(library, common["deps"])
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
            srcs = [p for p in library["srcs"] if p not in c_sources],
            copts = library["copts"],
            **common
        )
    native.alias(
        name = "blink_modules",
        actual = ":" + LIBRARIES["//third_party/blink/renderer/modules:modules"]["name"],
    )
    native.filegroup(
        name = "blink_modules_assets",
        srcs = [":" + action["name"] for action in ACTIONS],
    )
