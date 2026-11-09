"""Run declared upstream Python generators in their logical Chromium layout."""

NATIVE_LINUX_TOOLCHAIN = Label("//native/tool_configuration:native_linux_type")

def native_linux_exec_group():
    # Unused native sharing must not require a Linux executor.
    return exec_group(toolchains = [config_common.toolchain_type(NATIVE_LINUX_TOOLCHAIN, mandatory = False)])

def require_native_linux(ctx):
    if ctx.exec_groups["native_linux"].toolchains[NATIVE_LINUX_TOOLCHAIN] == None:
        fail("Native tool sharing requires the Linux AMD64 GNU 2.31 execution toolchain")

ChromiumFilesInfo = provider(
    "Files staged at their declared Chromium-relative paths.",
    fields = {
        "mappings": "Depset of (file, Chromium-relative path) pairs.",
        "executables": "Optional list of (files_to_run, logical path) pairs.",
        "executable_names": "Optional logical executable path to stable argv[0] mapping.",
        "native_linux": "Optional requirement to execute shared native tools on Linux AMD64 GNU 2.31.",
        "node_symlinks": "Optional requirement to preserve logical Node module paths.",
    },
)

ChromiumGeneratedFilesInfo = provider(
    "Generated outputs available to downstream generators.",
    fields = {"mappings": "Depset of generated file and logical-path pairs."},
)

def _generated(deps):
    return [dep[ChromiumGeneratedFilesInfo].mappings for dep in deps if ChromiumGeneratedFilesInfo in dep]

def _executables(deps):
    tools = {}
    for dep in deps:
        for runner, logical in getattr(dep[ChromiumFilesInfo], "executables", []):
            if logical in tools and tools[logical].executable != runner.executable:
                fail("conflicting logical executable: %s" % logical)
            tools[logical] = runner
    return [(tools[path], path) for path in sorted(tools)]

def _executable_names(deps):
    names = {}
    for dep in deps:
        for logical, name in getattr(dep[ChromiumFilesInfo], "executable_names", {}).items():
            if logical in names and names[logical] != name:
                fail("conflicting executable invocation name: %s" % logical)
            names[logical] = name
    return names

def requires_native_linux(deps):
    return any([getattr(dep[ChromiumFilesInfo], "native_linux", False) for dep in deps])

def requires_node_symlinks(deps):
    return any([getattr(dep[ChromiumFilesInfo], "node_symlinks", False) for dep in deps])

def _direct_mappings(srcs):
    mappings = []
    for target, logical in srcs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("each logical input must identify one file: %s" % target.label)
        mappings.append((files[0], logical))
    return mappings

def _logical_group_impl(ctx):
    mappings = depset(
        _direct_mappings(ctx.attr.srcs),
        transitive = [dep[ChromiumFilesInfo].mappings for dep in ctx.attr.deps],
    )
    return [
        DefaultInfo(files = depset([file for file, _ in mappings.to_list()])),
        ChromiumFilesInfo(
            mappings = mappings,
            executables = _executables(ctx.attr.deps),
            executable_names = _executable_names(ctx.attr.deps),
            native_linux = requires_native_linux(ctx.attr.deps),
            node_symlinks = requires_node_symlinks(ctx.attr.deps),
        ),
        ChromiumGeneratedFilesInfo(mappings = depset(
            [pair for pair in _direct_mappings(ctx.attr.srcs) if pair[1].startswith("out/bazel-import/")],
            transitive = _generated(ctx.attr.deps),
        )),
    ]

chromium_filegroup = rule(
    implementation = _logical_group_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True),
        "deps": attr.label_list(providers = [ChromiumFilesInfo]),
    },
)

def _binding_resources_two(_os, _inputs):
    return {"cpu": 2, "memory": 1024}

def _binding_resources_four(_os, _inputs):
    return {"cpu": 4, "memory": 2048}

def _python_action_impl(ctx):
    native_linux = requires_native_linux(ctx.attr.deps)
    if native_linux:
        require_native_linux(ctx)
    python = ctx.attr._native_python if native_linux else ctx.attr._python
    runtime = python[platform_common.ToolchainInfo].py3_runtime
    outputs = ctx.outputs.out_files
    mappings = depset(
        _direct_mappings(ctx.attr.srcs),
        transitive = [dep[ChromiumFilesInfo].mappings for dep in ctx.attr.deps] + _generated(ctx.attr.generated_deps),
    )
    staged = {}
    for file, logical in mappings.to_list():
        if logical in staged and staged[logical] != file:
            fail("conflicting logical input: %s" % logical)
        staged[logical] = file
    inputs = staged.values()
    manifest = ctx.actions.declare_file(ctx.label.name + ".action.json")
    generator_args = list(ctx.attr.args)
    resources = None
    if ctx.attr.script == "third_party/blink/renderer/bindings/scripts/generate_bindings.py":
        workers = ctx.var.get("CHROMIUM_BINDINGS_WORKERS", "1")
        if workers not in ["1", "2", "4"]:
            fail("CHROMIUM_BINDINGS_WORKERS must be 1, 2 or 4")
        if workers == "1":
            if "--single_process" not in generator_args:
                generator_args = ["--single_process"] + generator_args
        else:
            if "--single_process" in generator_args or any([arg.startswith("--worker_processes") for arg in generator_args]):
                fail("Binding worker count must come from CHROMIUM_BINDINGS_WORKERS")
            generator_args = ["--worker_processes=" + workers] + generator_args
            resources = _binding_resources_two if workers == "2" else _binding_resources_four
    description = {
        "inputs": [[staged[logical].path, logical] for logical in sorted(staged)],
        "outputs": [[out.path, logical] for out, logical in zip(outputs, ctx.attr.logical_outputs)],
        "script": ctx.attr.script,
        "args": generator_args,
        "response_file_contents": ctx.attr.response_file_contents,
        "build_dir": "out/bazel-import",
    }
    if requires_node_symlinks(ctx.attr.deps):
        description["preserve_node_symlinks"] = True
    executables = _executables(ctx.attr.deps)
    if executables:
        description["executable_inputs"] = [logical for _, logical in executables]
    names = _executable_names(ctx.attr.deps)
    if names:
        description["executable_names"] = names
    ctx.actions.write(manifest, json.encode(description))
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, manifest.path],
        inputs = depset(inputs + [manifest, ctx.file._script], transitive = [runtime.files] + [dep[DefaultInfo].files for dep in ctx.attr.deps]),
        outputs = outputs,
        tools = [runner for runner, _ in executables],
        resource_set = resources,
        mnemonic = "ChromiumPython",
        progress_message = "Generating %s" % ctx.label,
        exec_group = "native_linux" if native_linux else None,
    )
    return [
        DefaultInfo(files = depset(outputs)),
        ChromiumGeneratedFilesInfo(mappings = depset(
            [(out, "out/bazel-import/" + logical) for out, logical in zip(outputs, ctx.attr.logical_outputs)],
            transitive = _generated(ctx.attr.deps + ctx.attr.output_deps + ctx.attr.generated_deps),
        )),
        ChromiumFilesInfo(
            mappings = depset([
                (out, "out/bazel-import/" + logical)
                for out, logical in zip(outputs, ctx.attr.logical_outputs)
            ], transitive = [mappings] if ctx.attr.propagate_inputs else []),
            executables = executables if ctx.attr.propagate_inputs else [],
            executable_names = names if ctx.attr.propagate_inputs else {},
            native_linux = native_linux and ctx.attr.propagate_inputs,
            node_symlinks = ctx.attr.propagate_inputs and requires_node_symlinks(ctx.attr.deps),
        ),
    ]

_python_action = rule(
    implementation = _python_action_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True),
        "propagate_inputs": attr.bool(default = False),
        "deps": attr.label_list(providers = [ChromiumFilesInfo]),
        "output_deps": attr.label_list(providers = [ChromiumGeneratedFilesInfo]),
        "generated_deps": attr.label_list(providers = [ChromiumGeneratedFilesInfo]),
        "out_files": attr.output_list(mandatory = True),
        "logical_outputs": attr.string_list(mandatory = True),
        "script": attr.string(mandatory = True),
        "args": attr.string_list(),
        "response_file_contents": attr.string_list(),
        "_script": attr.label(default = Label("//native:python_action.py"), allow_single_file = True),
        "_python": attr.label(default = Label("@rules_python//python:current_py_toolchain"), cfg = "exec"),
        "_native_python": attr.label(default = Label("@rules_python//python:current_py_toolchain"), cfg = config.exec("native_linux")),
    },
    exec_groups = {"native_linux": native_linux_exec_group()},
)

def chromium_python_action(name, srcs, outs, script, args = None, response_file_contents = None, deps = None, **kwargs):
    """Declare upstream Python generator and individually addressable outputs.

    Args:
        name: Action target name.
        srcs: File labels mapped to Chromium-relative input paths.
        outs: Bazel output paths mapped to paths relative to logical build directory.
        script: Chromium-relative path of upstream script.
        args: Upstream generator arguments.
        response_file_contents: Arguments substituted for GN response-file placeholder.
        deps: Generator prerequisites, including validation actions.
        **kwargs: Common rule attributes.
    """
    paths = sorted(outs)
    _python_action(
        name = name,
        srcs = srcs,
        out_files = paths,
        logical_outputs = [outs[path] for path in paths],
        script = script,
        args = args or [],
        response_file_contents = response_file_contents or [],
        deps = deps or [],
        **kwargs
    )
