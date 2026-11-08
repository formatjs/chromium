"""Captured Chromium media pipeline, parsers, storage and Symphonia bridge."""

load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":media_sources.bzl", "ACTIONS", "BRIDGES", "LIBGAV1_DEFINES", "LIBRARIES", "SHARED_HEADERS")
load(":public_dependency.bzl", "chromium_public_dependency")
load(":python_action.bzl", "chromium_python_action")

def native_media():
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
            "@chromium_platform_headers//:alsa",
            "@chromium_platform_headers//:pulse_headers",
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
