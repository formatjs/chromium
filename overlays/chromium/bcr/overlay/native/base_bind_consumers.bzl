"""Manual shared project PCH cohorts with original compiler and archive contexts."""

load(":shared_prefix_consumers.bzl", original_cc_library = "shared_prefix_library")
load(":base_bind_consumer_data.bzl", "BASE_BIND_CONSUMERS")
load(":project_pch.bzl", "chromium_pch_compile")
load(":shared_project_pch_data.bzl", "SHARED_PROJECT_PCH_CONSUMERS")

_SHARED_PCHS = {
    "document": ":blink_core_83e906bc2e906865_document_pch",
    "string": ":blink_core_83e906bc2e906865_string_pch",
    "public_frame_host": ":content_b640bd1dddd3ce1d_public_frame_host_pch",
}

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
            all([source in sources for source in SHARED_PROJECT_PCH_CONSUMERS.get(name, {})]) and
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

def _shared_partitions(name, sources, groups, pchs):
    combined = dict(groups)
    for source, group in SHARED_PROJECT_PCH_CONSUMERS.get(name, {}).items():
        if source not in sources or combined[source] not in ["", "bind"]:
            fail("Shared PCH source missing or overlaps an existing cohort: " + source)
        if group not in _SHARED_PCHS:
            fail("Unknown shared PCH group: " + group)
        combined[source] = group
    used = combined.values()
    producers = {producer: group for producer, group in pchs.items() if group in used}
    for group, producer in _SHARED_PCHS.items():
        if group in used:
            if any([existing == group and target != producer for target, existing in producers.items()]):
                fail("Conflicting shared PCH producer: " + group)
            producers[producer] = group
    return combined, producers

def base_bind_partition(name, sources, groups, pchs):
    combined = dict(groups)
    for source in BASE_BIND_CONSUMERS[name]:
        if source not in sources or combined[source]:
            fail("Bind.h cohort missing source or overlaps another PCH: " + source)
        combined[source] = "bind"
    producers = dict(pchs)
    producers[":base_bind_default_pch"] = "bind"
    combined, producers = _shared_partitions(name, sources, combined, producers)
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
    groups = {source: "bind" if source in eligible else "" for source in sources}
    producers = {":base_bind_" + variant + "_pch": "bind"} if "bind" in groups.values() else {}
    groups, producers = _shared_partitions(name, sources, groups, producers)
    chromium_pch_compile(
        name = name + "_bind_pch",
        sources = groups,
        pchs = producers,
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
