"""Manual Content PCH candidate with original source set linking semantics."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":content_pch_data.bzl", "FRAME_HOST_HEADER", "FRAME_HOST_HEADER_PATHS", "FRAME_HOST_SOURCES")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")

def content_browser_pch(library, common, sources):
    name = library["name"]
    context = name + "_pch_context"
    eligible = {source: True for source in FRAME_HOST_SOURCES}
    if any([source not in sources for source in eligible]):
        fail("Pinned PCH source outside Content browser")
    compatibility = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
        "@llvm//constraints/libc:gnu.2.31",
    ]
    extras = common.get("additional_compiler_inputs", [])
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    producer = name + "_frame_host_pch"
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = "//:" + FRAME_HOST_HEADER,
        extras = extras,
        paths = FRAME_HOST_HEADER_PATHS,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = {source: "frame_host" if source in eligible else "" for source in sources},
        pchs = {":" + producer: "frame_host"},
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in sources],
        alwayslink = common["alwayslink"],
        context = ":" + context,
        copts = library["copts"],
        local_defines = library["defines"],
        extra_inputs = extras,
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
