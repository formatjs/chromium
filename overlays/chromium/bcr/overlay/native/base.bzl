"""Compile Chromium's complete Linux base library with native actions."""

load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":base_bind_pch.bzl", "base_bind_pchs")
load(":base_sources.bzl", "COPTS", "DEFINES", "HEADERS", "SOURCES")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":python_action.bzl", "chromium_python_action")

def native_base(name):
    """Build base and its original support libraries.

    Args:
        name: Base C++ library target.
    """
    chromium_python_action(
        name = "base_build_date",
        srcs = {"//:base/write_build_date_header.py": "base/write_build_date_header.py"},
        script = "base/write_build_date_header.py",
        args = ["gen/base/generated_build_date.h", "1759640400"],
        outs = {"gen/base/generated_build_date.h": "gen/base/generated_build_date.h"},
    )
    chromium_python_action(
        name = "base_check_version",
        srcs = {
            "//:base/check_version_internal.h.in": "base/check_version_internal.h.in",
            "//:chrome/VERSION": "chrome/VERSION",
            "//build:util/version.py": "build/util/version.py",
            "//build:util/android_chrome_version.py": "build/util/android_chrome_version.py",
            "//build:util/LASTCHANGE.dummy": "build/util/LASTCHANGE.dummy",
        },
        script = "build/util/version.py",
        args = ["-f", "../../chrome/VERSION", "-e", "VERSION_MAJOR=\"%s\" % (MAJOR)", "-e", "NEXT_VERSION_MAJOR=\"%d\" % (int(MAJOR) + 1)", "-o", "gen/base/check_version_internal.h", "../../base/check_version_internal.h.in"],
        outs = {"gen/base/check_version_internal.h": "gen/base/check_version_internal.h"},
    )
    cc_library(
        name = "base_headers",
        hdrs = ["//:" + path for path in HEADERS] + [
            ":all_buildflags",
            ":gen/base/generated_build_date.h",
            ":gen/base/check_version_internal.h",
        ],
        defines = [value for value in DEFINES["base"] if value not in ["BASE_IMPLEMENTATION", "IS_RAW_PTR_IMPL"]],
        includes = ["..", "gen"],
        deps = [
            ":perfetto_proto_cpp",
            "//base/allocator/partition_allocator/src/partition_alloc:raw_ptr",
            "//base/third_party/cityhash",
            "//base/third_party/double_conversion",
            "//base/third_party/icu:icu_utf",
            "//base/third_party/superfasthash",
            "//build:build_config",
            "//:cxx_wrapper_headers",
            "//third_party/abseil-cpp:absl",
            "//third_party/boringssl:boringssl",
            "//third_party/icu:icu",
            "//third_party/modp_b64",
            "//third_party/perfetto:libperfetto",
            "//third_party/zlib:zlib",
            "//third_party/lss:lss",
            "//testing/gtest:gtest_prod",
            "@glib//glib",
        ],
    )
    for support in ["base_static", "cityhash_v103", "symbolize", "xdg_user_dirs", "dwarf_helpers"]:
        cc_library(
            name = "base_" + support,
            srcs = ["//:" + path for path in SOURCES[support]],
            copts = COPTS[support],
            local_defines = DEFINES[support],
            linkstatic = True,
            deps = [":base_headers"],
        )
    chromium_cxx_bridge(
        name = "rust_logger_generated",
        src = "//:base/logging/rust_logger.rs",
        logical_source = "base/logging/rust_logger.rs",
    )
    cc_library(
        name = "rust_logger_cpp",
        linkstatic = True,
        srcs = [":gen/base/logging/rust_logger.rs.cc"],
        hdrs = [":gen/base/logging/rust_logger.rs.h"],
        copts = COPTS["base"],
        local_defines = ["BASE_IMPLEMENTATION"],
        includes = ["gen"],
        deps = [":base_headers"],
    )
    base_dependencies = [
        ":base_headers",
        ":base_base_static",
        ":base_cityhash_v103",
        ":base_symbolize",
        ":base_xdg_user_dirs",
        ":base_dwarf_helpers",
        "//native/rust:rust_logger",
        "//native/rust:serde_json_wrapper",
        "@glib//gmodule",
        "@glib//gobject",
    ]
    base_bind_pchs(COPTS["base"], ["BASE_IMPLEMENTATION", "IS_RAW_PTR_IMPL"], base_dependencies)
    cc_library(
        name = name,
        linkstatic = True,
        srcs = ["//:" + path for path in SOURCES["base"]],
        copts = COPTS["base"],
        local_defines = ["BASE_IMPLEMENTATION", "IS_RAW_PTR_IMPL"],
        linkopts = ["-pthread", "-ldl", "-lrt"],
        deps = base_dependencies,
    )
    cc_library(
        name = name + "_i18n",
        linkstatic = True,
        srcs = ["//:" + path for path in SOURCES["base_i18n"]],
        copts = COPTS["base_i18n"],
        local_defines = DEFINES["base_i18n"],
        deps = [":" + name, "//third_party/ced:ced", "//third_party/icu:icu"],
    )
