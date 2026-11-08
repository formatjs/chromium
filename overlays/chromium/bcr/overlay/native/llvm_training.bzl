"""Capture declared C++ inputs for compiler training without linking Chromium."""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

TRAINING_PLATFORM = [
    "@platforms//os:linux",
    "@platforms//cpu:x86_64",
    "@llvm//constraints/libc:gnu.2.31",
]

def _preprocessed_source_impl(ctx):
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
    source = ctx.actions.declare_file(ctx.label.name + ".ii")
    dependency = ctx.actions.declare_file(ctx.label.name + ".d")
    manifest = ctx.actions.declare_file(ctx.label.name + ".json")
    variables = cc_common.create_compile_variables(
        cc_toolchain = toolchain,
        feature_configuration = features,
        source_file = ctx.file.src.path,
        output_file = source.path,
        variables_extension = {"dependency_file": dependency.path},
        user_compile_flags = ctx.attr.copts + ["-E"],
        preprocessor_defines = depset(defines, transitive = [context.defines]),
        include_directories = context.includes,
        quote_include_directories = context.quote_includes,
        system_include_directories = context.system_includes,
        framework_include_directories = context.framework_includes,
        use_pic = True,
    )
    compiler = cc_common.get_tool_for_action(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile)
    arguments = cc_common.get_memory_inefficient_command_line(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables)
    environment = cc_common.get_environment_variables(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables)
    ctx.actions.run(
        executable = compiler,
        arguments = arguments,
        env = environment,
        inputs = depset([ctx.file.src] + ctx.files.extras, transitive = [toolchain.all_files, context.headers]),
        outputs = [source, dependency],
        mnemonic = "ChromiumTrainingPreprocess",
    )
    ctx.actions.write(manifest, json.encode({
        "source": ctx.file.src.path,
        "preprocessed": source.path,
        "compiler": compiler,
        "arguments": arguments,
        "environment": environment,
    }))
    return [DefaultInfo(files = depset([source, dependency, manifest]))]

chromium_training_source = rule(
    implementation = _preprocessed_source_impl,
    attrs = {
        "src": attr.label(mandatory = True, allow_single_file = [".cc"]),
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
        "extras": attr.label_list(allow_files = True),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type"],
)
