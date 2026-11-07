"""Complete captured Chromium Skia graph with its original configuration."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":python_action.bzl", "chromium_python_action")
load(":skia_sources.bzl", "ACTIONS", "BRIDGES", "LIBRARIES", "PUBLIC_DEFINES", "SHARED_HEADERS")

def native_skia():
    for bridge in BRIDGES:
        chromium_cxx_bridge(**bridge)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "skia_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen", "gen/third_party/skia"],
        defines = PUBLIC_DEFINES,
        deps = [
            ":base_headers",
            ":dawn_cpp_headers",
            "@chromium_skia//:headers",
            "@chromium_platform_headers//:graphics",
            "@vulkan_headers//:vulkan_headers",
        ],
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
            deps = [":skia_headers"] + library["deps"],
        )
    native.alias(name = "skia", actual = ":" + LIBRARIES["//skia:skia"]["name"])
