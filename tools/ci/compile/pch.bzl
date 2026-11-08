"""Experimental upstream PCH with declared hermetic compiler inputs."""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(":batch_sources.bzl", BATCH_SOURCES = "SOURCES")

def _headers_impl(ctx):
    return [
        DefaultInfo(files = depset()),
        CcInfo(compilation_context = ctx.attr.library[CcInfo].compilation_context),
    ]

_headers = rule(
    implementation = _headers_impl,
    attrs = {"library": attr.label(mandatory = True, providers = [CcInfo])},
)

def _pch_impl(ctx):
    toolchain = find_cpp_toolchain(ctx)
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    context = ctx.attr.library[CcInfo].compilation_context
    for option in ctx.attr.copts:
        if option.startswith(("-I", "-iquote", "-isystem", "-include", "-imacros", "-iframework", "-F", "-ivfsoverlay", "-idirafter")):
            fail("Standard PCH requires toolchain include paths: " + option)
    defines = []
    for value in ctx.attr.local_defines:
        tokens = ctx.tokenize(ctx.expand_make_variables("local_defines", value, {}))
        if len(tokens) != 1:
            fail("define must expand to one token: " + value)
        defines.append(tokens[0])
    pch = ctx.actions.declare_file(ctx.label.name + ".pch")
    dependency = ctx.actions.declare_file(ctx.label.name + ".d")
    variables = cc_common.create_compile_variables(
        cc_toolchain = toolchain,
        feature_configuration = features,
        source_file = ctx.file._header.path,
        output_file = pch.path,
        variables_extension = {"dependency_file": dependency.path},
        user_compile_flags = ctx.attr.copts + ["-x", "c++-header", "--relocatable-pch"],
        preprocessor_defines = depset(defines, transitive = [context.defines]),
        use_pic = True,
    )
    ctx.actions.run(
        executable = cc_common.get_tool_for_action(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile),
        arguments = cc_common.get_memory_inefficient_command_line(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
        env = cc_common.get_environment_variables(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
        inputs = depset([ctx.file._header], transitive = [toolchain.all_files]),
        outputs = [pch, dependency],
        mnemonic = "ChromiumPch",
        progress_message = "Precompiling upstream Chromium header",
    )
    return [DefaultInfo(files = depset([pch]))]

chromium_standard_pch = rule(
    implementation = _pch_impl,
    attrs = {
        "_header": attr.label(default = "@chromium//build:precompile.h", allow_single_file = [".h"]),
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
)

def blink_pch_probe(name, libraries, target_compatible_with):
    """Keep the fixed Blink cohort and upstream compiler options."""
    library = libraries["//third_party/blink/renderer/core:core"]
    copts = library["copts"] + ["-isysroot", "."]
    headers = name + "_headers"
    pch = name + "_pch"
    inputs = [
        "@chromium//:base/component_export.h",
        "@chromium//:skia/config/SkUserConfig.h",
        "@chromium//:skia/config/sk_ref_cnt_ext_debug.h",
        "@chromium//:skia/config/sk_ref_cnt_ext_release.h",
        "@chromium//:skia/ext/skia_histogram.h",
        "@chromium//native:blink_core_forwarders/third_party/re2/src/re2/re2.h",
    ]
    _headers(name = headers, library = "@chromium//native:" + library["name"])
    chromium_standard_pch(
        name = pch,
        library = ":" + headers,
        copts = copts,
        local_defines = library["defines"],
        target_compatible_with = target_compatible_with,
    )
    for suffix, pch_inputs, pch_options in [
        ("_baseline", [], []),
        ("", [":" + pch, "@chromium//build:precompile.h"], ["-include-pch", "$(location :" + pch + ")"]),
    ]:
        cc_library(
            name = name + suffix,
            srcs = ["@chromium//:" + source for source in BATCH_SOURCES[:256]],
            copts = copts + pch_options,
            local_defines = library["defines"],
            additional_compiler_inputs = inputs + pch_inputs,
            features = ["cc_include_scanning"],
            linkstatic = True,
            deps = [":" + headers],
            tags = ["manual"],
            target_compatible_with = target_compatible_with,
        )
