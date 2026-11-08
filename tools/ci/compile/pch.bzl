"""Experimental upstream PCH with declared hermetic compiler inputs."""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(":batch_sources.bzl", BATCH_SOURCES = "SOURCES")
load(":project_pch_headers.bzl", "ELIGIBLE_SOURCES", "HEADER", "PROJECT_HEADER_PATHS")

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

def _project_path(path):
    if path.startswith("bazel-out/"):
        parts = path.split("/", 3)
        if len(parts) != 4 or parts[2] != "bin":
            fail("Unsupported generated PCH header: " + path)
        path = parts[3]
    if path.startswith("external/"):
        path = path[len("external/"):]
    return path

def _project_inputs_impl(ctx):
    expected = {path: True for path in PROJECT_HEADER_PATHS}
    found = {}
    for file in ctx.attr.library[CcInfo].compilation_context.headers.to_list() + ctx.files.extras:
        path = _project_path(file.path)
        if path in expected:
            if path in found and found[path] != file:
                fail("Ambiguous PCH header: " + path)
            found[path] = file
    missing = [path for path in expected if path not in found]
    if missing:
        fail("Missing PCH headers: " + str(missing))
    return [DefaultInfo(files = depset(found.values()))]

_project_inputs = rule(
    implementation = _project_inputs_impl,
    attrs = {
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "extras": attr.label_list(allow_files = True),
    },
)

def _project_pch_impl(ctx):
    toolchain = find_cpp_toolchain(ctx)
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    context = ctx.attr.library[CcInfo].compilation_context
    defines = []
    for value in ctx.attr.local_defines:
        tokens = ctx.tokenize(ctx.expand_make_variables("local_defines", value, {}))
        if len(tokens) != 1:
            fail("define must expand to one token: " + value)
        defines.append(tokens[0])
    raw = ctx.actions.declare_file(ctx.label.name + ".raw.pch")
    dependency = ctx.actions.declare_file(ctx.label.name + ".d")
    pch = ctx.actions.declare_file(ctx.label.name + ".pch")
    manifest = ctx.actions.declare_file(ctx.label.name + ".headers.json")
    ctx.actions.write(manifest, json.encode(PROJECT_HEADER_PATHS))
    variables = cc_common.create_compile_variables(
        cc_toolchain = toolchain,
        feature_configuration = features,
        source_file = ctx.file.header.path,
        output_file = raw.path,
        variables_extension = {"dependency_file": dependency.path},
        user_compile_flags = ctx.attr.copts + ["-x", "c++-header", "--relocatable-pch"],
        preprocessor_defines = depset(defines, transitive = [context.defines]),
        include_directories = context.includes,
        quote_include_directories = context.quote_includes,
        system_include_directories = context.system_includes,
        framework_include_directories = context.framework_includes,
        use_pic = True,
    )
    ctx.actions.run(
        executable = cc_common.get_tool_for_action(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile),
        arguments = cc_common.get_memory_inefficient_command_line(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
        env = cc_common.get_environment_variables(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
        inputs = depset([ctx.file.header] + ctx.files.extras, transitive = [toolchain.all_files, context.headers]),
        outputs = [raw, dependency],
        mnemonic = "ChromiumProjectPch",
    )
    runtime = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._validator.path, dependency.path, manifest.path, raw.path, pch.path],
        inputs = depset([ctx.file._validator, dependency, manifest, raw], transitive = [runtime.files]),
        outputs = [pch],
        mnemonic = "ChromiumPchClosure",
    )
    return [DefaultInfo(files = depset([pch]))]

_project_pch = rule(
    implementation = _project_pch_impl,
    attrs = {
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "header": attr.label(mandatory = True, allow_single_file = True),
        "extras": attr.label_list(allow_files = True),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
        "_validator": attr.label(default = "//tools/ci/compile:validate_pch.py", allow_single_file = True),
        "_python": attr.label(default = "@rules_python//python:current_py_toolchain", cfg = "exec"),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
)

def _source_aware_compile_impl(ctx):
    toolchain = find_cpp_toolchain(ctx)
    features = cc_common.configure_features(
        ctx = ctx,
        cc_toolchain = toolchain,
        requested_features = ctx.features,
        unsupported_features = ctx.disabled_features,
    )
    defines = []
    for value in ctx.attr.local_defines:
        tokens = ctx.tokenize(ctx.expand_make_variables("local_defines", value, {}))
        if len(tokens) != 1:
            fail("define must expand to one token: " + value)
        defines.append(tokens[0])
    objects = {}
    for suffix, sources, options, inputs in [
        ("_pch", ctx.files.pch_sources, ctx.attr.copts + ["-isysroot", ".", "-ffile-prefix-map=./=", "-include-pch", ctx.file.pch.path], ctx.files.extra_inputs + [ctx.file.pch] + ctx.files.pch_headers),
        ("_plain", ctx.files.plain_sources, ctx.attr.copts, ctx.files.extra_inputs),
    ]:
        _, outputs = cc_common.compile(
            actions = ctx.actions,
            feature_configuration = features,
            cc_toolchain = toolchain,
            name = ctx.label.name + suffix,
            srcs = sources,
            compilation_contexts = [ctx.attr.library[CcInfo].compilation_context],
            user_compile_flags = options,
            local_defines = defines,
            additional_inputs = inputs,
            disallow_nopic_outputs = True,
        )
        for file in outputs.pic_objects:
            if file.basename in objects:
                fail("Duplicate cohort object: " + file.basename)
            objects[file.basename] = file
    if sorted(objects.keys()) != sorted(ctx.attr.object_order):
        fail("Unexpected cohort object inventory")
    outputs = cc_common.create_compilation_outputs(pic_objects = depset([objects[name] for name in ctx.attr.object_order]))
    linking_context, linking_outputs = cc_common.create_linking_context_from_compilation_outputs(
        actions = ctx.actions,
        name = ctx.label.name,
        feature_configuration = features,
        cc_toolchain = toolchain,
        compilation_outputs = outputs,
        disallow_dynamic_library = True,
    )
    library = linking_outputs.library_to_link
    return [
        CcInfo(compilation_context = ctx.attr.library[CcInfo].compilation_context, linking_context = linking_context),
        DefaultInfo(files = depset([file for file in [library.static_library, library.pic_static_library] if file])),
    ]

_source_aware_compile = rule(
    implementation = _source_aware_compile_impl,
    attrs = {
        "pch_sources": attr.label_list(allow_files = [".cc"]),
        "plain_sources": attr.label_list(allow_files = [".cc"]),
        "object_order": attr.string_list(),
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "pch": attr.label(mandatory = True, allow_single_file = True),
        "pch_headers": attr.label_list(allow_files = True),
        "extra_inputs": attr.label_list(allow_files = True),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
)

def blink_project_pch_probe(name, libraries, target_compatible_with):
    """Keep experimental PCH imports on their original consumers."""
    library = libraries["//third_party/blink/renderer/core:core"]
    copts = library["copts"] + ["-isysroot", ".", "-ffile-prefix-map=./="]
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
    _project_inputs(name = name + "_inputs", library = ":" + headers, extras = inputs + ["@chromium//:" + HEADER])
    _project_pch(
        name = pch,
        library = ":" + headers,
        header = "@chromium//:" + HEADER,
        extras = inputs,
        copts = copts,
        local_defines = library["defines"],
        target_compatible_with = target_compatible_with,
    )
    _source_aware_compile(
        name = name,
        pch_sources = ["@chromium//:" + source for source in BATCH_SOURCES[:256] if source in ELIGIBLE_SOURCES],
        plain_sources = ["@chromium//:" + source for source in BATCH_SOURCES[:256] if source not in ELIGIBLE_SOURCES],
        object_order = [source.split("/")[-1][:-3] + ".pic.o" for source in BATCH_SOURCES[:256]],
        library = ":" + headers,
        pch = ":" + pch,
        pch_headers = [":" + name + "_inputs"],
        extra_inputs = inputs,
        copts = library["copts"],
        local_defines = library["defines"],
        features = ["cc_include_scanning"],
        tags = ["manual"],
        target_compatible_with = target_compatible_with,
    )
