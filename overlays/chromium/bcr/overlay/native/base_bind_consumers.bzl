"""Manual shared Bind.h cohorts with original compiler and archive contexts."""

load("@rules_cc//cc:cc_library.bzl", original_cc_library = "cc_library")
load(":base_bind_consumer_data.bzl", "BASE_BIND_CONSUMERS")
load(":project_pch.bzl", "chromium_pch_compile")

def base_bind_library(**common):
    name = common["name"]
    sources = common.get("srcs", [])
    supported = (
        name in BASE_BIND_CONSUMERS and
        name not in ["browser_9541da8b21719506", "browser_d48195c21c933c30", "content_b640bd1dddd3ce1d"] and
        type(sources) == "list" and
        type(common.get("copts", [])) == "list" and
        not common.get("implementation_deps") and
        not common.get("nocopts")
    )
    if supported:
        objects = [source.split("/")[-1].rsplit(".", 1)[0] for source in sources]
        supported = (
            all([source.endswith((".cc", ".cpp")) for source in sources]) and
            all([source in sources for source in BASE_BIND_CONSUMERS[name]]) and
            len(objects) == len({name: True for name in objects})
        )
    if supported:
        replacement = base_bind_cohort(common)
        common["srcs"] = select({
            "//native/tool_configuration:base_bind_pch": [],
            "//conditions:default": sources,
        })
        common["deps"] = select({
            "//native/tool_configuration:base_bind_pch": [replacement] + common.get("deps", []),
            "//conditions:default": common.get("deps", []),
        })
    original_cc_library(**common)

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
    tags = attributes.pop("tags", [])
    original_cc_library(name = context, tags = tags + ["manual"], **attributes)
    complete = False
    for option in common.get("copts", []):
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
        copts = common.get("copts", []),
        local_defines = common.get("local_defines", []),
        extra_inputs = common.get("additional_compiler_inputs", []),
        features = common.get("features", []),
        testonly = common.get("testonly", False),
        target_compatible_with = common.get("target_compatible_with", []) + [
            "@platforms//os:linux",
            "@platforms//cpu:x86_64",
            "@llvm//constraints/libc:gnu.2.31",
        ],
        tags = ["manual"],
    )
    return ":" + name + "_bind_pch"
