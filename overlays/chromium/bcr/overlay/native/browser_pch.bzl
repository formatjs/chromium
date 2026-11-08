"""Opt-in Chrome PCHs with original compiler contexts and source-set linking."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":base_bind_consumers.bzl", "base_bind_partition")
load(":browser_pch_data.bzl", "BROWSER_HEADER", "BROWSER_HEADER_PATHS", "BROWSER_SOURCES", "PROFILE_HEADER", "PROFILE_HEADER_PATHS", "PROFILE_SOURCES")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")

def browser_project_pch(library, common, sources, copts):
    name = library["name"]
    context = name + "_pch_context"
    if name == "browser_9541da8b21719506":
        header, paths, qualified, group = BROWSER_HEADER, BROWSER_HEADER_PATHS, BROWSER_SOURCES, "browser"
    elif name == "browser_d48195c21c933c30":
        header, paths, qualified, group = PROFILE_HEADER, PROFILE_HEADER_PATHS, PROFILE_SOURCES, "profile"
    else:
        fail("Unknown Chrome PCH owner: " + name)
    eligible = {source: True for source in qualified}
    if any([source not in sources for source in eligible]):
        fail("Pinned PCH source outside Chrome owner")
    compatibility = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
        "@llvm//constraints/libc:gnu.2.31",
    ]
    extras = common.get("additional_compiler_inputs", [])
    cc_library(name = context, copts = copts, tags = ["manual"], **common)
    producer = name + "_" + group + "_pch"
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = "//:" + header,
        extras = extras,
        paths = paths,
        closure_inputs = True,
        copts = copts + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    partitions, producers = base_bind_partition(
        name,
        sources,
        {source: group if source in eligible else "" for source in sources},
        {":" + producer: group},
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = partitions,
        pchs = producers,
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in sources],
        alwayslink = common["alwayslink"],
        context = ":" + context,
        copts = copts,
        local_defines = library["defines"],
        extra_inputs = extras,
        features = common.get("features", []),
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    return ":" + name + "_pch"
