"""Expose native host tools and private runtimes to Chromium generators."""

load(":python_action.bzl", "ChromiumFilesInfo", "native_linux_exec_group", "require_native_linux")

def _stage_runtime(ctx, tool, executable, runtime_data, runtime_deps, native_linux):
    sources = {executable.basename: executable}
    for file in tool[DefaultInfo].default_runfiles.files.to_list():
        if file == executable:
            continue
        path = file.short_path
        runfile = path[3:] if path.startswith("../") else ctx.workspace_name + "/" + path
        sources[executable.basename + ".runfiles/" + runfile] = file
        if ctx.attr.stage_runtime:
            relative = None
            if file.basename in ["icudtl.dat", "snapshot_blob.bin", "v8_context_snapshot.bin"]:
                relative = file.basename
            elif file.path.startswith(executable.dirname + "/"):
                relative = file.path[len(executable.dirname) + 1:]
            if relative and relative not in runtime_data.values():
                if relative in sources and sources[relative] != file:
                    fail("conflicting host runtime data: %s" % relative)
                sources[relative] = file
    for dependency in runtime_deps:
        for file, logical in dependency[ChromiumFilesInfo].mappings.to_list():
            prefix = "out/bazel-import/"
            if not logical.startswith(prefix):
                fail("host runtime needs a build-relative path: %s" % logical)
            relative = logical[len(prefix):]
            if relative.startswith("/") or ".." in relative.split("/") or not relative:
                fail("invalid host runtime path: %s" % relative)
            if relative in runtime_data.values():
                continue
            if relative in sources and sources[relative] != file:
                fail("conflicting host runtime data: %s" % relative)
            sources[relative] = file
    for target, relative in runtime_data.items():
        if relative.startswith("/") or ".." in relative.split("/") or not relative:
            fail("invalid runtime data path: %s" % relative)
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("runtime data must identify one file: %s" % target.label)
        if relative in sources and sources[relative] != files[0]:
            fail("conflicting runtime data: %s" % relative)
        sources[relative] = files[0]
    outputs = {relative: ctx.actions.declare_file(ctx.label.name + ".runtime/" + relative) for relative in sorted(sources)}
    manifest = ctx.actions.declare_file(ctx.label.name + ".runtime.json")
    ctx.actions.write(manifest, json.encode([[sources[path].path, outputs[path].path] for path in sorted(sources)]))
    runtime = ctx.attr._native_python if native_linux else ctx.attr._python
    python = runtime[platform_common.ToolchainInfo].py3_runtime
    ctx.actions.run(
        executable = python.interpreter,
        arguments = ["-I", "-B", ctx.file._stage_script.path, manifest.path],
        inputs = depset(sources.values() + [manifest, ctx.file._stage_script], transitive = [python.files]),
        outputs = outputs.values(),
        mnemonic = "ChromiumToolRuntime",
        exec_group = "native_linux" if native_linux else None,
    )
    return outputs[executable.basename], outputs.values()

def _tool_inputs_impl(ctx):
    if (ctx.attr.tool == None) == (ctx.attr.native_tool == None):
        fail("Exactly one execution or native target tool is required")
    native_linux = ctx.attr.native_tool != None
    if native_linux:
        require_native_linux(ctx)
    tool = ctx.attr.native_tool if native_linux else ctx.attr.tool
    runtime_data = ctx.attr.native_runtime_data if native_linux else ctx.attr.runtime_data
    runtime_deps = ctx.attr.native_runtime_deps if native_linux else ctx.attr.runtime_deps
    runner = tool[DefaultInfo].files_to_run
    executable = runner.executable
    files = [executable]
    if ctx.attr.stage_runtime or runtime_data or runtime_deps:
        # Keep host runtime data beside its executable, outside target GN inputs.
        executable, files = _stage_runtime(ctx, tool, executable, runtime_data, runtime_deps, native_linux)
    logical_paths = [ctx.attr.logical_path] + ctx.attr.additional_logical_paths
    return [
        DefaultInfo(files = depset(files)),
        ChromiumFilesInfo(
            mappings = depset([(executable, path) for path in logical_paths]),
            executables = [(runner, path) for path in logical_paths],
            native_linux = native_linux,
        ),
    ]

_tool_inputs = rule(
    implementation = _tool_inputs_impl,
    attrs = {
        "tool": attr.label(executable = True, cfg = "exec"),
        "native_tool": attr.label(executable = True, cfg = "target"),
        "logical_path": attr.string(mandatory = True),
        "additional_logical_paths": attr.string_list(),
        "runtime_data": attr.label_keyed_string_dict(allow_files = True, cfg = "exec"),
        "stage_runtime": attr.bool(default = False),
        "runtime_deps": attr.label_list(providers = [ChromiumFilesInfo], cfg = "exec"),
        "native_runtime_data": attr.label_keyed_string_dict(allow_files = True),
        "native_runtime_deps": attr.label_list(providers = [ChromiumFilesInfo]),
        "_stage_script": attr.label(default = Label("//native:stage_tool.py"), allow_single_file = True),
        "_python": attr.label(default = Label("@rules_python//python:current_py_toolchain"), cfg = "exec"),
        "_native_python": attr.label(default = Label("@rules_python//python:current_py_toolchain"), cfg = config.exec("native_linux")),
    },
    exec_groups = {"native_linux": native_linux_exec_group()},
)

def chromium_tool_inputs(name, tool, runtime_data = {}, runtime_deps = [], allow_native_sharing = True, **kwargs):
    """Optionally share captured native Linux tools with target libraries."""

    # Configurable and external tools retain their execution transition.
    if not allow_native_sharing or type(tool) != "string" or not tool.startswith(":") or type(runtime_data) != "dict" or type(runtime_deps) not in ["list", "tuple"]:
        _tool_inputs(name = name, tool = tool, runtime_data = runtime_data, runtime_deps = runtime_deps, **kwargs)
        return
    shared = Label("//native/tool_configuration:share_native")
    _tool_inputs(
        name = name,
        tool = select({shared: None, "//conditions:default": tool}),
        native_tool = select({shared: tool, "//conditions:default": None}),
        runtime_data = select({shared: {}, "//conditions:default": runtime_data}),
        native_runtime_data = select({shared: runtime_data, "//conditions:default": {}}),
        runtime_deps = select({shared: [], "//conditions:default": runtime_deps}),
        native_runtime_deps = select({shared: runtime_deps, "//conditions:default": []}),
        **kwargs
    )
