"""Original Linux font stack, PNG support and Chromium XML configuration."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":fonts_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_fonts():
    cc_library(
        name = "fonts_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = [
            "..",
            "gen",
            "../third_party/fontconfig/include",
            "../third_party/fontconfig/include/src",
            "../third_party/fontconfig/include/fc-lang",
            "../third_party/freetype/include",
            "../third_party/freetype/include/freetype-custom",
            "../third_party/libpng",
            "../third_party/libxml/linux",
            "../third_party/libxml/linux/include",
            "../third_party/libxml/src/include",
        ],
        deps = [
            "@chromium_fontconfig//:headers",
            "@chromium_freetype//:headers",
            "@chromium_harfbuzz//:headers",
            "//third_party/icu:icu",
            "//third_party/zlib",
        ],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        cpp_sources = [p for p in library["srcs"] if not p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":fonts_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = captured_copts(library, "c_copts"),
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = cpp_sources,
            copts = captured_copts(library),
            **common
        )
    for name, original in {
        "freetype": "//third_party/freetype:freetype",
        "harfbuzz": "//third_party/harfbuzz-ng:harfbuzz-ng",
        "fontconfig": "//third_party/fontconfig:fontconfig",
        "libpng": "//third_party/libpng:libpng",
        "libxml": "//third_party/libxml:libxml",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
