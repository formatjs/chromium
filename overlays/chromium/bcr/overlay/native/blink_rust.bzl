"""Blink's original Rust font-format and crash CXX bridges."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":blink_rust_sources.bzl", "BRIDGES", "LIBRARIES", "SHARED_HEADERS")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")

def native_blink_rust():
    for bridge in BRIDGES:
        chromium_cxx_bridge(**bridge)
    for original, library in LIBRARIES.items():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            hdrs = library["hdrs"] + SHARED_HEADERS,
            copts = library["copts"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = library["deps"],
        )
    for name, original in {
        "blink_font_format_cpp": "//third_party/blink/renderer/platform:font_format_check_cxx_generated",
        "blink_rust_crash_cpp": "//third_party/blink/common/rust_crash:rs_cxx_generated",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
