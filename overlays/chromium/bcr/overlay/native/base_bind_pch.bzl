"""Manual Bind.h PCH producers with original consumer language modes."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":base_bind_pch_data.bzl", "BASE_BIND_HEADER_PATHS")
load(":project_pch.bzl", "chromium_project_pch")
load(":serialization_pch_data.bzl", "SERIALIZATION_HEADER_PATHS", "SERIALIZATION_SOURCES")

def base_bind_pchs(copts, defines, deps):
    context = "base_bind_pch_context"
    cc_library(
        name = context,
        copts = copts,
        local_defines = defines,
        linkstatic = True,
        deps = deps,
        tags = ["manual"],
    )
    if "-fcomplete-member-pointers" not in copts:
        fail("Pinned Base member-pointer language option changed")
    default_options = [value for value in copts if value != "-fcomplete-member-pointers"]
    compatibility = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
        "@llvm//constraints/libc:gnu.2.31",
    ]
    cc_library(
        name = "serialization_prefix_context",
        deps = [":" + context, ":mojo_binding_headers"],
        tags = ["manual"],
    )
    chromium_project_pch(
        name = "serialization_eager_pch",
        library = ":serialization_prefix_context",
        header = ":serialization_prefix.h",
        paths = SERIALIZATION_HEADER_PATHS,
        closure_inputs = True,
        copts = default_options + ["-isysroot", ".", "-ffile-prefix-map=./=", "-fpch-instantiate-templates"],
        local_defines = defines,
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    for variant, options in [
        ("complete", copts),
        ("default", default_options),
    ]:
        chromium_project_pch(
            name = "base_bind_" + variant + "_pch",
            library = ":" + context,
            header = "//:base/functional/bind.h",
            paths = BASE_BIND_HEADER_PATHS,
            closure_inputs = True,
            copts = options + ["-isysroot", ".", "-ffile-prefix-map=./="],
            local_defines = defines,
            alternate = ":serialization_eager_pch" if variant == "default" and SERIALIZATION_SOURCES else None,
            alternate_sources = SERIALIZATION_SOURCES if variant == "default" else {},
            target_compatible_with = compatibility,
            tags = ["manual"],
        )
