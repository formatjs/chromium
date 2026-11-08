"""Manual shared Bind.h cohorts with original compiler and archive contexts."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":base_bind_consumer_data.bzl", "BASE_BIND_CONSUMERS")
load(":project_pch.bzl", "chromium_pch_compile")

def base_bind_partition(name, sources, groups, pchs):
    combined = dict(groups)
    for source in BASE_BIND_CONSUMERS[name]:
        if source not in sources or combined[source]:
            fail("Bind.h cohort missing source or overlaps another PCH: " + source)
        combined[source] = "bind"
    producers = dict(pchs)
    producers[":base_bind_default_pch"] = "bind"
    return (
        select({
            "//native/tool_configuration:base_bind_pch": combined,
            "//conditions:default": groups,
        }),
        select({
            "//native/tool_configuration:base_bind_pch": producers,
            "//conditions:default": pchs,
        }),
    )

def base_bind_cohort(common):
    name = common["name"]
    eligible = {source: True for source in BASE_BIND_CONSUMERS[name]}
    sources = common["srcs"]
    if any([source not in sources for source in eligible]):
        fail("Pinned Bind.h source outside owner: " + name)
    if any([not source.endswith((".cc", ".cpp")) for source in sources]):
        fail("Bind.h cohort requires C++ sources: " + name)
    context = name + "_bind_context"
    attributes = dict(common)
    attributes.pop("name")
    attributes.pop("srcs")
    cc_library(name = context, tags = ["manual"], **attributes)
    complete = False
    for option in common["copts"]:
        if option == "-fcomplete-member-pointers":
            complete = True
        elif option == "-fno-complete-member-pointers":
            complete = False
    variant = "complete" if complete else "default"
    chromium_pch_compile(
        name = name + "_bind_pch",
        sources = {source: "bind" if source in eligible else "" for source in sources},
        pchs = {":base_bind_" + variant + "_pch": "bind"},
        object_order = [source.split("/")[-1].rsplit(".", 1)[0] + ".pic.o" for source in sources],
        alwayslink = common.get("alwayslink", False),
        context = ":" + context,
        copts = common["copts"],
        local_defines = common.get("local_defines", []),
        extra_inputs = common.get("additional_compiler_inputs", []),
        features = common.get("features", []),
        target_compatible_with = [
            "@platforms//os:linux",
            "@platforms//cpu:x86_64",
            "@llvm//constraints/libc:gnu.2.31",
        ],
        tags = ["manual"],
    )
    return ":" + name + "_bind_pch"
