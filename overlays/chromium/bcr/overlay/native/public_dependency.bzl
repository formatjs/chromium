"""Public C++ headers and linking without private repository quote paths."""

load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _codec_dependency_impl(ctx):
    dependency = ctx.attr.dependency[CcInfo]
    headers = dependency.compilation_context

    # Keep repository quote paths private; retain public headers and linking.
    return [CcInfo(
        compilation_context = cc_common.create_compilation_context(
            headers = headers.headers,
            includes = headers.includes,
            system_includes = headers.system_includes,
            framework_includes = headers.framework_includes,
            defines = headers.defines,
            local_defines = headers.local_defines,
        ),
        linking_context = dependency.linking_context,
    )]

chromium_public_dependency = rule(
    implementation = _codec_dependency_impl,
    attrs = {"dependency": attr.label(providers = [CcInfo])},
)

def _link_dependency_impl(ctx):
    return [CcInfo(
        compilation_context = cc_common.create_compilation_context(),
        linking_context = ctx.attr.dependency[CcInfo].linking_context,
    )]

chromium_link_dependency = rule(
    implementation = _link_dependency_impl,
    attrs = {"dependency": attr.label(providers = [CcInfo])},
)

def _header_dependency_impl(ctx):
    return [CcInfo(compilation_context = ctx.attr.dependency[CcInfo].compilation_context)]

chromium_header_dependency = rule(
    implementation = _header_dependency_impl,
    attrs = {"dependency": attr.label(providers = [CcInfo])},
)

def _public_source_header_file_impl(ctx):
    headers = [
        header
        for header in ctx.attr.dependency[CcInfo].compilation_context.direct_public_headers
        if header.is_source and header.basename == ctx.attr.header
    ]
    if len(headers) != 1:
        fail("Expected one public source header %s, got %d" % (ctx.attr.header, len(headers)))
    return [DefaultInfo(files = depset(headers))]

chromium_public_source_header_file = rule(
    implementation = _public_source_header_file_impl,
    attrs = {
        "dependency": attr.label(mandatory = True, providers = [CcInfo]),
        "header": attr.string(mandatory = True),
    },
)

def _snapshot_dependencies_impl(ctx):
    merged = cc_common.merge_cc_infos(cc_infos = [dep[CcInfo] for dep in ctx.attr.deps])
    inputs = []
    for linker_input in merged.linking_context.linker_inputs.to_list():
        # Snapshot executables own ICF policy; inherited flags can override it.
        flags = linker_input.user_link_flags
        if type(flags) == "depset":
            flags = flags.to_list()
        flags = [flag for flag in flags if not flag.startswith("-Wl,--icf=") and flag.upper() not in ["/OPT:ICF", "/OPT:NOICF"] and flag != "-Wl,-no_deduplicate"]
        inputs.append(cc_common.create_linker_input(
            owner = linker_input.owner,
            libraries = depset(linker_input.libraries),
            user_link_flags = depset(flags),
            additional_inputs = depset(linker_input.additional_inputs),
        ))
    return [
        CcInfo(
            compilation_context = merged.compilation_context,
            # Preserve archive extraction order when rebuilding linker inputs.
            linking_context = cc_common.create_linking_context(linker_inputs = depset(inputs, order = "topological")),
        ),
        DefaultInfo(runfiles = ctx.runfiles().merge_all([
            dep[DefaultInfo].default_runfiles
            for dep in ctx.attr.deps
            if dep[DefaultInfo].default_runfiles
        ])),
    ]

chromium_snapshot_dependencies = rule(
    implementation = _snapshot_dependencies_impl,
    attrs = {"deps": attr.label_list(providers = [CcInfo])},
)
