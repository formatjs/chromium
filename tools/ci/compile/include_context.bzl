"""Experimental GN-owned include context with unchanged declared headers."""

load("@bazel_skylib//lib:paths.bzl", "paths")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(":batch_sources.bzl", BATCH_SOURCES = "SOURCES")
load(":include_context_roots.bzl", "INCLUDE_ROOTS")

def _logical_path(path):
    path = paths.normalize(path)
    if path.startswith("bazel-out/"):
        parts = path.split("/", 3)
        if len(parts) == 4 and parts[2] == "bin":
            path = parts[3]
    return path

def _keep(path, repository, own):
    logical = _logical_path(path)
    if logical != repository and not logical.startswith(repository + "/"):
        return True
    if logical in own:
        return True

    # Forwarders adapt removed vendored trees to declared registry headers.
    return any([part.endswith("_forwarders") for part in logical.split("/")])

def _headers_impl(ctx):
    context = ctx.attr.library[CcInfo].compilation_context
    if not ctx.attr.projected:
        return [DefaultInfo(files = depset()), CcInfo(compilation_context = context)]
    owner = ctx.attr.library.label
    own = {paths.normalize(paths.join(owner.workspace_root, owner.package, path)): True for path in ctx.attr.includes}
    selected = {}
    for name in ["includes", "quote_includes", "system_includes", "framework_includes"]:
        selected[name] = depset([path for path in getattr(context, name).to_list() if _keep(path, owner.workspace_root, own)])
    return [
        DefaultInfo(files = depset()),
        CcInfo(compilation_context = cc_common.create_compilation_context(
            headers = context.headers,
            defines = context.defines,
            local_defines = context.local_defines,
            includes = selected["includes"],
            quote_includes = selected["quote_includes"],
            system_includes = selected["system_includes"],
            framework_includes = selected["framework_includes"],
        )),
    ]

_headers = rule(
    implementation = _headers_impl,
    attrs = {
        "library": attr.label(mandatory = True, providers = [CcInfo]),
        "includes": attr.string_list(),
        "projected": attr.bool(default = True),
    },
)

def blink_include_context_probe(name, libraries):
    """Measure a smaller search list before considering production changes."""
    library = libraries["//third_party/blink/renderer/core:core"]
    for variant, projected in [(name, True), (name + "_baseline", False)]:
        _headers(
            name = variant + "_headers",
            projected = projected,
            library = "@chromium//native:" + library["name"],
            includes = INCLUDE_ROOTS,
        )
        cc_library(
            name = variant,
            srcs = ["@chromium//:" + source for source in BATCH_SOURCES[:256]],
            copts = library["copts"],
            local_defines = library["defines"],
            deps = [":" + variant + "_headers"],
            additional_compiler_inputs = [
                "@chromium//:base/component_export.h",
                "@chromium//:skia/config/SkUserConfig.h",
                "@chromium//:skia/config/sk_ref_cnt_ext_debug.h",
                "@chromium//:skia/config/sk_ref_cnt_ext_release.h",
                "@chromium//:skia/ext/skia_histogram.h",
                "@chromium//native:blink_core_forwarders/third_party/re2/src/re2/re2.h",
            ],
            features = ["cc_include_scanning"],
            linkstatic = True,
            tags = ["manual"],
            target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:x86_64"],
        )
