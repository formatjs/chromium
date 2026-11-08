"""Opt-in Blink core PCH with the original native compilation context."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":blink_idl_pch_data.bzl", "IDL_HEADER", "IDL_HEADER_PATHS")
load(":blink_pch_data.bzl", "DOCUMENT_HEADER", "DOCUMENT_HEADER_PATHS", "DOCUMENT_SOURCES", "STRING_HEADER", "STRING_HEADER_PATHS", "STRING_SOURCES")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")

_LINUX = [
    "@platforms//os:linux",
    "@platforms//cpu:x86_64",
    "@llvm//constraints/libc:gnu.2.31",
]

def blink_core_pch(name, library, common):
    """Return replacement objects without depending on the original owner."""
    context = name + "_pch_context"
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    document = {source: True for source in DOCUMENT_SOURCES}
    string = {source: True for source in STRING_SOURCES}
    sources = [source[3:] if source.startswith("//:") else source for source in library["srcs"]]
    if any([source not in sources for source in document.keys() + string.keys()]):
        fail("Pinned PCH source outside Blink core")
    if any([source in string for source in document]):
        fail("Overlapping PCH source partitions")
    pchs = {}
    for group, header, paths in [
        ("document", DOCUMENT_HEADER, DOCUMENT_HEADER_PATHS),
        ("string", STRING_HEADER, STRING_HEADER_PATHS),
    ]:
        producer = name + "_" + group + "_pch"
        chromium_project_pch(
            name = producer,
            library = ":" + context,
            header = "//:" + header,
            extras = common["additional_compiler_inputs"],
            paths = paths,
            copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
            local_defines = library["defines"],
            target_compatible_with = _LINUX,
            tags = ["manual"],
        )
        pchs[":" + producer] = group
    chromium_pch_compile(
        name = name + "_pch",
        sources = {original: "document" if source in document else "string" if source in string else "" for original, source in zip(library["srcs"], sources)},
        pchs = pchs,
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in sources],
        context = ":" + context,
        copts = library["copts"],
        local_defines = library["defines"],
        extra_inputs = common["additional_compiler_inputs"],
        features = ["cc_include_scanning"],
        target_compatible_with = _LINUX,
        tags = ["manual"],
    )
    return ":" + name + "_pch"

def blink_bindings_pch(library, common):
    """Return validated IDL PCH objects without an owner dependency."""
    name = library["name"]
    context = name + "_pch_context"
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    producer = name + "_idl_pch"
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = "//:" + IDL_HEADER,
        extras = common["additional_compiler_inputs"],
        paths = IDL_HEADER_PATHS,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = _LINUX,
        tags = ["manual"],
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = {source: "idl" for source in library["srcs"]},
        pchs = {":" + producer: "idl"},
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in library["srcs"]],
        context = ":" + context,
        copts = library["copts"],
        local_defines = library["defines"],
        extra_inputs = common["additional_compiler_inputs"],
        features = ["cc_include_scanning"],
        target_compatible_with = _LINUX,
        tags = ["manual"],
    )
    return ":" + name + "_pch"
