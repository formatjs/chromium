"""Manual Content PCH candidate with original source set linking semantics."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":base_bind_consumers.bzl", "base_bind_partition")
load(":content_pch_data.bzl", "FRAME_HOST_HEADER", "FRAME_HOST_HEADER_PATHS", "FRAME_HOST_SOURCES")
load(":content_public_pch_data.bzl", "PUBLIC_FRAME_HOST_HEADER", "PUBLIC_FRAME_HOST_HEADER_PATHS", "PUBLIC_FRAME_HOST_SOURCES")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")

def content_browser_pch(library, common, sources):
    name = library["name"]
    context = name + "_pch_context"
    eligible = {source: "frame_host" for source in FRAME_HOST_SOURCES}
    for source in PUBLIC_FRAME_HOST_SOURCES:
        if source in eligible:
            fail("Content PCH cohorts overlap")
        eligible[source] = "public_frame_host"
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
        # Relative Skia includes traverse this existing forwarder directory.
        extras = extras + [":content_forwarders/third_party/re2/src/re2/re2.h"],
        paths = FRAME_HOST_HEADER_PATHS,
        closure_inputs = True,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    public_producer = name + "_public_frame_host_pch"
    chromium_project_pch(
        name = public_producer,
        library = ":" + context,
        header = "//:" + PUBLIC_FRAME_HOST_HEADER,
        extras = extras + [":content_forwarders/third_party/re2/src/re2/re2.h"],
        paths = PUBLIC_FRAME_HOST_HEADER_PATHS,
        closure_inputs = True,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    partitions, producers = base_bind_partition(
        name,
        sources,
        {source: eligible.get(source, "") for source in sources},
        {":" + producer: "frame_host", ":" + public_producer: "public_frame_host"},
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = partitions,
        pchs = producers,
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
