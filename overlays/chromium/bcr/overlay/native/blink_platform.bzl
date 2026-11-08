"""Blink platform and its captured native dependency closure."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":blink_platform_sources.bzl", "ACTIONS", "LIBRARIES", "METADATA", "SHARED_HEADERS", "TOOLS")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":public_dependency.bzl", "chromium_public_dependency")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_blink_platform():
    for path, content in METADATA.items():
        if path in CAPTURED_FILES:
            continue
        write_file(
            name = "blink_platform_metadata_" + path.replace("/", "_"),
            out = path,
            content = [content],
        )
    chromium_public_dependency(name = "blink_libvpx_rc", dependency = "@libvpx//:vpx_rc")
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "blink_platform_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + [":" + path for path in METADATA] + native.glob(["blink_platform_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "blink_platform_forwarders"],
        deps = ["@chromium_" + project + "//:chromium_headers" for project in [
            "cld3",
            "emoji_segmenter",
            "ots",
            "material_color_utilities",
            "smhasher",
            "libphonenumber",
            "crabbyavif",
            "cros_system_api",
        ]] + [
            ":blink_font_format_cpp",
            ":blink_rust_crash_cpp",
            "@libzip//:libzip",
            "@chromium_platform_headers//:va_headers",
            ":compositor_headers",
            ":ml_headers",
        ],
    )
    for original, library in LIBRARIES.items():
        deps = [":blink_libvpx_rc" if p == "@libvpx//:vpx_rc" else p for p in library["deps"]]
        common = dict(
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = ([":blink_platform_headers"] if library["srcs"] or library["hdrs"] else []) + deps,
        )
        if library["kind"] == "executable":
            common["deps"] = [":base_headers"] + deps
            cc_binary(
                name = library["name"],
                srcs = library["srcs"] + library["hdrs"],
                data = [":icudtl.dat"],
                copts = library["copts"],
                **common
            )
            continue
        common.update(
            hdrs = library["hdrs"],
            includes = library["includes"],
            alwayslink = library["kind"] == "source_set",
        )
        if original.startswith("//third_party/blink/renderer/platform"):
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
                    ":blink_platform_forwarders/third_party/re2/src/re2/re2.h",
                ],
            )
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
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
        name = "blink_platform",
        actual = ":" + LIBRARIES["//third_party/blink/renderer/platform:platform"]["name"],
    )
