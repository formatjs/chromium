"""Compile source partitions with validated project PCH imports."""

load("@rules_cc//cc:action_names.bzl", "ACTION_NAMES")
load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cpp_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(":eager_template_pch_data.bzl", "EAGER_TEMPLATE_SOURCES")
load(":pch_flags.bzl", "PCH_CONSUMER_FLAGS", "PCH_PRODUCER_FLAGS")

ChromiumPchInfo = provider(fields = ["pch", "headers", "eager_pch", "eager_sources"])

_NATIVE_LINUX = Label("//native/tool_configuration:native_linux_type")

def _project_path(path):
    if path.startswith("bazel-out/"):
        parts = path.split("/", 3)
        if len(parts) != 4 or parts[2] != "bin":
            fail("Unsupported generated PCH header: " + path)
        path = parts[3]
    return path[len("external/"):] if path.startswith("external/") else path

def _imported_headers(ctx):
    expected = {path: True for path in ctx.attr.paths}
    found = {}
    files = ctx.attr.library[CcInfo].compilation_context.headers.to_list() + ctx.files.extras + [ctx.file.header]
    for file in files:
        path = _project_path(file.path)
        if path in expected:
            if path in found and found[path] != file:
                fail("Ambiguous PCH header: " + path)
            found[path] = file
    missing = [path for path in expected if path not in found]
    if missing:
        fail("Missing PCH headers: " + str(missing))
    return found.values()

def _pch_impl(ctx):
    headers = _imported_headers(ctx)
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
    eager_sources = {}
    if ctx.var.get("CHROMIUM_BASE_BIND_PCH") == "1" and ctx.var.get("COMPILATION_MODE") == "fastbuild":
        eager_sources = EAGER_TEMPLATE_SOURCES.get(ctx.label.name, {})
    variants = {}
    for suffix in (["", "_templates"] if eager_sources else [""]):
        raw = ctx.actions.declare_file(ctx.label.name + suffix + ".raw.pch")
        dependency = ctx.actions.declare_file(ctx.label.name + suffix + ".d")
        pch = ctx.actions.declare_file(ctx.label.name + suffix + ".pch")
        manifest = ctx.actions.declare_file(ctx.label.name + suffix + ".headers.json")
        ctx.actions.write(manifest, json.encode(ctx.attr.paths))
        variables = cc_common.create_compile_variables(
            cc_toolchain = toolchain,
            feature_configuration = features,
            source_file = ctx.file.header.path,
            output_file = raw.path,
            variables_extension = {"dependency_file": dependency.path},
            user_compile_flags = ctx.attr.copts + (["-fpch-instantiate-templates"] if suffix else []) + PCH_PRODUCER_FLAGS,
            preprocessor_defines = depset(defines, transitive = [context.defines]),
            include_directories = context.includes,
            quote_include_directories = context.quote_includes,
            system_include_directories = context.system_includes,
            framework_include_directories = context.framework_includes,
            use_pic = True,
        )
        inputs = depset([ctx.file.header] + ctx.files.extras, transitive = [toolchain.all_files, context.headers])
        if ctx.attr.closure_inputs:
            inputs = depset(headers + ctx.files.extras, transitive = [toolchain.all_files])
        ctx.actions.run(
            executable = cc_common.get_tool_for_action(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile),
            arguments = cc_common.get_memory_inefficient_command_line(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
            env = cc_common.get_environment_variables(feature_configuration = features, action_name = ACTION_NAMES.cpp_compile, variables = variables),
            inputs = inputs,
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
        variants[suffix] = pch

    # Preserve producer directory anchors used by Clang's recorded header paths.
    return [
        DefaultInfo(files = depset([variants[""]])),
        ChromiumPchInfo(
            pch = variants[""],
            headers = depset(headers + ctx.files.extras),
            eager_pch = variants.get("_templates"),
            eager_sources = eager_sources,
        ),
    ]

chromium_project_pch = rule(
    implementation = _pch_impl,
    attrs = {
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "header": attr.label(mandatory = True, allow_single_file = True),
        "extras": attr.label_list(allow_files = True),
        "paths": attr.string_list(mandatory = True),
        "closure_inputs": attr.bool(default = False, doc = "Use only pinned headers after validating their sandbox directory layout."),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
        "_validator": attr.label(default = Label("//native:pch_validate.py"), allow_single_file = True),
        "_python": attr.label(default = "@rules_python//python:current_py_toolchain", cfg = "exec"),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type", _NATIVE_LINUX],
)

def _groups(ctx):
    producers = {name: target[ChromiumPchInfo] for target, name in ctx.attr.pchs.items()}
    if "" in producers or len(producers) != len(ctx.attr.pchs):
        fail("PCH group names must be unique and nonempty")
    sources = {name: [] for name in [""] + producers.keys()}
    for target, name in ctx.attr.sources.items():
        if name not in sources:
            fail("Unknown PCH group: " + name)
        files = target.files.to_list()
        if len(files) != 1 or files[0].extension not in ["cc", "cpp"]:
            fail("Each PCH source must identify one C++ file: " + str(target.label))
        sources[name].append(files[0])
    groups = []
    for name, files in sources.items():
        if not files:
            continue
        if not name:
            groups.append(("_plain", files, ctx.attr.copts, ctx.files.extra_inputs))
            continue
        producer = producers[name]
        qualified = {path: True for path in producer.eager_sources.get(ctx.label.name, [])}
        eager = []
        original = []
        for file in files:
            (eager if _project_path(file.path) in qualified else original).append(file)
        for pch, selected in [(producer.pch, original), (producer.eager_pch, eager)]:
            if not selected:
                continue
            options = ctx.attr.copts + ["-isysroot", ".", "-ffile-prefix-map=./="] + PCH_CONSUMER_FLAGS + ["-include-pch", pch.path]
            inputs = ctx.files.extra_inputs + [pch] + producer.headers.to_list()

            # Keep original object paths and archive order across both imports.
            groups.append(("_" + name, selected, options, inputs))

    return groups

def _compile_impl(ctx):
    groups = _groups(ctx)
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
    for suffix, sources, options, inputs in groups:
        _, outputs = cc_common.compile(
            actions = ctx.actions,
            feature_configuration = features,
            cc_toolchain = toolchain,
            name = ctx.label.name + suffix,
            srcs = sources,
            compilation_contexts = [ctx.attr.context[CcInfo].compilation_context],
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
        alwayslink = ctx.attr.alwayslink,
        disallow_dynamic_library = True,
    )
    library = linking_outputs.library_to_link
    archives = depset([file for file in [library.static_library, library.pic_static_library] if file])
    return [
        CcInfo(compilation_context = ctx.attr.context[CcInfo].compilation_context, linking_context = linking_context),
        DefaultInfo(files = archives),
        OutputGroupInfo(archive = archives),
    ]

chromium_pch_compile = rule(
    implementation = _compile_impl,
    attrs = {
        "sources": attr.label_keyed_string_dict(allow_files = [".cc", ".cpp"]),
        "pchs": attr.label_keyed_string_dict(providers = [ChromiumPchInfo]),
        "object_order": attr.string_list(mandatory = True),
        "alwayslink": attr.bool(default = False),
        "context": attr.label(mandatory = True, providers = [CcInfo]),
        "extra_inputs": attr.label_list(allow_files = True),
        "copts": attr.string_list(),
        "local_defines": attr.string_list(),
    },
    fragments = ["cpp"],
    toolchains = ["@bazel_tools//tools/cpp:toolchain_type", _NATIVE_LINUX],
)
