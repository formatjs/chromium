"""Share generated V8 opening includes after checking their order."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":project_pch.bzl", "chromium_pch_compile", "chromium_project_pch")
load(":v8_generated_pch_data.bzl", "GENERATED_HEADER_PATHS", "GENERATED_SOURCES")

def _prefix_impl(ctx):
    manifest = ctx.actions.declare_file(ctx.label.name + ".sources.json")
    stamp = ctx.actions.declare_file(ctx.label.name + ".validated")
    ctx.actions.write(manifest, json.encode([file.path for file in ctx.files.srcs]))
    runtime = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._validator.path, manifest.path, ctx.file.prefix.path, stamp.path],
        inputs = depset([manifest, ctx.file.prefix, ctx.file._validator] + ctx.files.srcs, transitive = [runtime.files]),
        outputs = [stamp],
        mnemonic = "ChromiumPchPrefix",
    )
    return [DefaultInfo(files = depset([stamp]))]

_prefix_guard = rule(
    implementation = _prefix_impl,
    attrs = {
        "srcs": attr.label_list(allow_files = True),
        "prefix": attr.label(allow_single_file = True, mandatory = True),
        "_validator": attr.label(default = Label("//native:pch_prefix_validate.py"), allow_single_file = True),
        "_python": attr.label(default = "@rules_python//python:current_py_toolchain", cfg = "exec"),
    },
)

def v8_generated_pch(library, common, sources):
    if "V8_TARGET_ARCH_X64" not in library["defines"]:
        return
    name = library["name"]
    context = name + "_pch_context"
    eligible = {source: True for source in GENERATED_SOURCES}
    if any([source not in sources for source in eligible]):
        fail("Pinned PCH source outside V8 generated initializers")
    compatibility = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
        "@llvm//constraints/libc:gnu.2.31",
    ]
    header = ":v8_generated_prefix.h"
    guard = name + "_prefix_guard"
    _prefix_guard(
        name = guard,
        srcs = GENERATED_SOURCES,
        prefix = header,
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    extras = common.get("additional_compiler_inputs", []) + [":" + guard, "//testing/gtest:include/gtest/gtest_prod.h"]
    cc_library(name = context, copts = library["copts"], tags = ["manual"], **common)
    producer = name + "_generated_pch"
    chromium_project_pch(
        name = producer,
        library = ":" + context,
        header = header,
        extras = extras,
        paths = GENERATED_HEADER_PATHS,
        closure_inputs = True,
        copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="],
        local_defines = library["defines"],
        target_compatible_with = compatibility,
        tags = ["manual"],
    )
    chromium_pch_compile(
        name = name + "_pch",
        sources = {source: "generated" if source in eligible else "" for source in sources},
        pchs = {":" + producer: "generated"},
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
