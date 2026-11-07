"""Captured GPU service, command decoders, Dawn wire and libyuv."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":gpu_service_sources.bzl", "ACTIONS", "LIBRARIES", "METADATA", "SHARED_HEADERS", "TOOLS")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":objcxx.bzl", "objcxx_library")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_gpu_service():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for path, content in METADATA.items():
        if path in CAPTURED_FILES:
            continue
        write_file(
            name = "gpu_service_metadata_" + path.replace("/", "_"),
            out = path,
            content = [content],
        )
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "gpu_service_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["gpu_service_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "../gpu", "gen/third_party/dawn/include", "gen/third_party/dawn/src", "gpu_service_forwarders"],
        deps = [
            ":dawn_headers",
            ":dawn_native_headers",
            ":skia_headers",
            ":tint_headers",
            "@chromium_angle//:headers",
            "@chromium_libyuv//:chromium_headers",
            "@vulkan_headers//:vulkan_headers",
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
            alwayslink = library["kind"] == "source_set",
            deps = [":gpu_service_headers"] + library["deps"],
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
            srcs = [p for p in library["srcs"] if p not in c_sources],
            copts = library["copts"],
            **common
        )
    for name, original in {
        "gpu_service": "//gpu/command_buffer/service:gles2",
        "gpu_config": "//gpu/config:config",
        "dawn_wire": "//third_party/dawn/src/dawn/wire:wire",
        "persistent_cache": "//components/persistent_cache:persistent_cache",
        "libyuv": "//third_party/libyuv:libyuv",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
