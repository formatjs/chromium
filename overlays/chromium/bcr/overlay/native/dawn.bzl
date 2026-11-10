"""Chromium's Dawn API generators, common support and dispatch library."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":dawn_sources.bzl", "ACTIONS", "LIBRARIES", "METADATA", "SHARED_HEADERS")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":python_action.bzl", "chromium_python_action")

def native_dawn():
    for path, content in METADATA.items():
        if path in CAPTURED_FILES:
            continue
        write_file(
            name = "dawn_metadata_" + path.replace("/", "_"),
            out = path if path.startswith("gen/") else "metadata/" + path,
            content = [content],
        )
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "dawn_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen", "gen/third_party/dawn/include", "gen/third_party/dawn/src"],
        deps = ["@chromium_dawn//:source_headers"],
    )
    for original, library in LIBRARIES.items():
        cc_library(
            name = library["name"],
            srcs = library["srcs"],
            hdrs = library["hdrs"],
            includes = library["includes"],
            copts = library["copts"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = [":dawn_headers"] + library["deps"],
        )
    for name, original in {
        "dawn_cpp_headers": "//third_party/dawn/include/dawn:cpp_headers",
        "dawn_proc": "//third_party/dawn/src/dawn:proc",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
