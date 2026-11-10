"""Manual V8 isolate PCH candidate with original source set linking semantics."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")
load(":v8_compiler_pch_data.bzl", "COMPILER_SOURCES")
load(":v8_objects_pch_data.bzl", "V8_OBJECTS_EAGER_SOURCES", "V8_OBJECTS_HEADER_PATHS", "V8_OBJECTS_PARENT", "V8_OBJECTS_SOURCES")
load(":v8_pch_data.bzl", "ISOLATE_HEADER", "ISOLATE_HEADER_PATHS", "ISOLATE_SOURCES")

def v8_base_pch(library, common, sources):
    if "V8_TARGET_ARCH_X64" not in library["defines"]:
        return
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
    alternate = {}
    if producer == V8_OBJECTS_PARENT:
        for mode in ["eager", "normal"]:
            chromium_project_pch(
                name = "v8_objects_" + mode + "_pch",
                library = ":" + context,
                header = ":v8_objects_prefix.h",
                extras = extras,
                paths = V8_OBJECTS_HEADER_PATHS,
                closure_inputs = True,
                copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="] + (["-fpch-instantiate-templates"] if mode == "eager" else []),
                local_defines = library["defines"],
                target_compatible_with = compatibility,
                tags = ["manual"],
                **({"eager_variant": ":v8_objects_eager_pch", "eager_sources": V8_OBJECTS_EAGER_SOURCES} if mode == "normal" else {})
            )
        alternate = {"alternate": ":v8_objects_normal_pch", "alternate_sources": V8_OBJECTS_SOURCES}
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = ISOLATE_HEADER,
        extras = extras,
        paths = ISOLATE_HEADER_PATHS,
        closure_inputs = True,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
        **alternate
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
    return ":" + name + "_pch"

def v8_compiler_pch(library, common, sources, producer):
    """Keep compiler context; reuse its existing base dependency's isolate PCH."""
    if "V8_TARGET_ARCH_X64" not in library["defines"]:
        return
    eligible = {source: True for source in COMPILER_SOURCES}
    if any([source not in sources for source in eligible]):
        fail("Pinned PCH source outside V8 compiler")
    name = library["name"]
    context = name + "_pch_context"
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    chromium_pch_compile(
        name = name + "_pch",
        sources = {source: "isolate" if source in eligible else "" for source in sources},
        pchs = {producer: "isolate"},
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in sources],
        alwayslink = common["alwayslink"],
        context = ":" + context,
        copts = library["copts"],
        local_defines = library["defines"],
        extra_inputs = common.get("additional_compiler_inputs", []) + ["//testing/gtest:include/gtest/gtest_prod.h"],
        target_compatible_with = [
            "@platforms//os:linux",
            "@platforms//cpu:x86_64",
            "@llvm//constraints/libc:gnu.2.31",
        ],
        tags = ["manual"],
    )
    return ":" + name + "_pch"
