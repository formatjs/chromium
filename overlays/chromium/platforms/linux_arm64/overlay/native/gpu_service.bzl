"""Captured GPU service, command decoders, Dawn wire and libyuv."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":gpu_service_sources.bzl", "ACTIONS", "LIBRARIES", "METADATA", "SHARED_HEADERS")
load(":python_action.bzl", "chromium_python_action")

def native_gpu_service():
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
            "@chromium_platform_headers_cross//:graphics",
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
