"""Native copies preserving Chromium's generated asset paths."""

load(":python_action.bzl", "ChromiumFilesInfo", "ChromiumGeneratedFilesInfo", "requires_native_linux", "requires_node_symlinks")

def _copy_impl(ctx):
    sources = {}
    for target, logical in ctx.attr.srcs.items():
        files = target[DefaultInfo].files.to_list()
        if len(files) != 1:
            fail("copy source must identify one file: %s" % target.label)
        sources[logical] = files[0]
    mappings = []
    for output, logical, source in zip(ctx.outputs.out_files, ctx.attr.logical_outputs, ctx.attr.logical_sources):
        ctx.actions.symlink(output = output, target_file = sources[source])
        mappings.append((output, "out/bazel-import/" + logical))
    return [
        DefaultInfo(files = depset(ctx.outputs.out_files)),
        ChromiumGeneratedFilesInfo(mappings = depset(
            mappings,
            transitive = [dep[ChromiumGeneratedFilesInfo].mappings for dep in ctx.attr.deps + ctx.attr.output_deps if ChromiumGeneratedFilesInfo in dep],
        )),
        ChromiumFilesInfo(mappings = depset(
            mappings + [(file, logical) for logical, file in sources.items()],
            transitive = [dep[ChromiumFilesInfo].mappings for dep in ctx.attr.deps],
        ), native_linux = requires_native_linux(ctx.attr.deps), node_symlinks = requires_node_symlinks(ctx.attr.deps)),
    ]

_copy = rule(
    implementation = _copy_impl,
    attrs = {
        "srcs": attr.label_keyed_string_dict(allow_files = True),
        "deps": attr.label_list(providers = [ChromiumFilesInfo]),
        "output_deps": attr.label_list(providers = [ChromiumGeneratedFilesInfo]),
        "out_files": attr.output_list(mandatory = True),
        "logical_outputs": attr.string_list(mandatory = True),
        "logical_sources": attr.string_list(mandatory = True),
    },
)

def chromium_resource_copy(name, srcs, outputs, deps = [], output_deps = []):
    """Copy declared sources to original generated paths.

    Args:
        name: Copy action target.
        srcs: Source labels mapped to Chromium-relative paths.
        outputs: Generated paths mapped to source logical paths.
        deps: Original generated-source prerequisites.
        output_deps: Generated dependency outputs carried to consumers.
    """
    _copy(
        name = name,
        srcs = srcs,
        deps = deps,
        output_deps = output_deps,
        out_files = outputs.keys(),
        logical_outputs = outputs.keys(),
        logical_sources = outputs.values(),
    )
