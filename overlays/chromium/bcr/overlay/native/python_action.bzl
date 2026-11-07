"""Run declared upstream Python generators in their logical Chromium layout."""

ChromiumFilesInfo = provider(
    "Files staged at their declared Chromium-relative paths.",
    fields = {
        "mappings": "Depset of (file, Chromium-relative path) pairs.",
        "executables": "Optional list of (files_to_run, logical path) pairs.",
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
        ChromiumFilesInfo(mappings = mappings, executables = _executables(ctx.attr.deps)),
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

def _python_action_impl(ctx):
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
    description = {
        "inputs": [[staged[logical].path, logical] for logical in sorted(staged)],
        "outputs": [[out.path, logical] for out, logical in zip(outputs, ctx.attr.logical_outputs)],
        "script": ctx.attr.script,
        "args": ctx.attr.args,
        "response_file_contents": ctx.attr.response_file_contents,
        "build_dir": "out/bazel-import",
    }
    executables = _executables(ctx.attr.deps)
    if executables:
        description["executable_inputs"] = [logical for _, logical in executables]
    if ctx.var.get("CHROMIUM_GENERATOR_SCRATCH") == "execroot":
        description["scratch_in_execroot"] = True
    ctx.actions.write(manifest, json.encode(description))
    ctx.actions.run(
        executable = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._script.path, manifest.path],
        inputs = depset(inputs + [manifest, ctx.file._script], transitive = [ctx.attr._python[platform_common.ToolchainInfo].py3_runtime.files] + [dep[DefaultInfo].files for dep in ctx.attr.deps]),
        outputs = outputs,
        tools = [runner for runner, _ in executables],
        mnemonic = "ChromiumPython",
        progress_message = "Generating %s" % ctx.label,
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
    },
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
    generator_args = list(args or [])
    if script == "third_party/blink/renderer/bindings/scripts/generate_bindings.py" and "--single_process" not in generator_args:
        # Keep the upstream pool from growing with the executor's host CPU count.
        generator_args = ["--single_process"] + generator_args
    _python_action(
        name = name,
        srcs = srcs,
        out_files = paths,
        logical_outputs = [outs[path] for path in paths],
        script = script,
        args = generator_args,
        response_file_contents = response_file_contents or [],
        deps = deps or [],
        **kwargs
    )
