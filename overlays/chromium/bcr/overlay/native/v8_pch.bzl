"""Manual V8 isolate PCH candidate with original source set linking semantics."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")
load(":v8_pch_data.bzl", "ISOLATE_HEADER", "ISOLATE_HEADER_PATHS", "ISOLATE_SOURCES")

def v8_base_pch(library, common, sources):
    name = library["name"]
    context = name + "_pch_context"
    eligible = {source: True for source in ISOLATE_SOURCES}
    if any([source not in sources for source in eligible]):
        fail("Pinned PCH source outside V8 base")
    compatibility = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
        "@llvm//constraints/libc:gnu.2.31",
    ]
    extras = common.get("additional_compiler_inputs", []) + ["//testing/gtest:include/gtest/gtest_prod.h"]
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    producer = name + "_isolate_pch"
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = ISOLATE_HEADER,
        extras = extras,
        paths = ISOLATE_HEADER_PATHS,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = {source: "isolate" if source in eligible else "" for source in sources},
        pchs = {":" + producer: "isolate"},
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in sources],
        alwayslink = common["alwayslink"],
        context = ":" + context,
        copts = library["copts"],
        local_defines = library["defines"],
        extra_inputs = extras,
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
