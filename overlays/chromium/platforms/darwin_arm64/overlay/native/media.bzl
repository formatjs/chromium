"""Captured Chromium media pipeline, parsers, storage and Symphonia bridge."""

load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":media_sources.bzl", "ACTIONS", "BRIDGES", "LIBGAV1_DEFINES", "LIBRARIES", "SHARED_HEADERS", "TOOLS")
load(":objcxx.bzl", "objcxx_library")
load(":public_dependency.bzl", "chromium_public_dependency")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_media():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    chromium_public_dependency(name = "libvpx_public", dependency = "@libvpx//:libvpx")
    chromium_public_dependency(name = "aom_public", dependency = "@aom//:aom")
    chromium_public_dependency(name = "aom_rc_public", dependency = "@aom//:aom_rc")
    for bridge in BRIDGES:
        chromium_cxx_bridge(**bridge)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "media_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["media_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "media_forwarders", "../third_party/leveldatabase", "../third_party/leveldatabase/include"],
        deps = [
            ":gpu_client_headers",
            ":gpu_service_headers",
            ":linux_ui_headers",
            ":paint_headers",
            ":gfx_headers",
            ":codec_headers",
            ":skia_headers",
            "@chromium_leveldatabase//:chromium_headers",
            "@chromium_libgav1//:chromium_headers",
            "@chromium_cdm_api//:chromium_headers",
            "@chromium_ffmpeg//:chromium_headers",
            "@flac//:chromium_headers",
            "@libwebm//:chromium_headers",
            "@opus//:opus",
            ":libvpx_public",
            ":aom_public",
            "@dav1d//:dav1d",
            "@re2//:re2",
            "@fp16//:fp16",
            "@crc32c//:crc32c",
            "//third_party/rust/chromium_crates_io/vendor/cxx-v1:core-lib",
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
            deps = [":media_headers"] + library["deps"],
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
        "media": "//media:media",
        "media_base": "//media/base:base",
        "media_filters": "//media/filters:filters",
        "leveldb": "//third_party/leveldatabase:leveldatabase",
        "leveldb_proto": "//components/leveldb_proto:leveldb_proto",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
    cc_library(
        name = "libgav1_parser",
        defines = LIBGAV1_DEFINES,
        deps = [":" + LIBRARIES["//third_party/libgav1:libgav1_parser"]["name"]],
    )
