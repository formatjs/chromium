"""Shared project and SDK prefixes with frozen header closures."""

load("@rules_cc//cc:cc_library.bzl", original_cc_library = "cc_library")
load(":project_pch.bzl", "chromium_project_pch")
load(":shared_prefix_data.bzl", "BASE_HEADERS", "COMPONENT_HEADERS", "COMPONENT_INCLUDES", "FULL_INCLUDES", "GLOBAL_HEADERS", "ORIGINAL_PRODUCERS", "SAFE_INCLUDES", "SDK_DEFINES", "SDK_OWNERS", "STD_INCLUDES", "V8_HEADERS")

_QUALIFIED_REPOSITORY = Label("@chromium//native:BUILD.bazel").repo_name

_LINUX = ["@platforms//os:linux", "@platforms//cpu:x86_64", "@llvm//constraints/libc:gnu.2.31"]
_SDK_INCLUDES = "".join(["#include <" + header + ">\n" for header in [
    "algorithm", "array", "chrono", "deque", "functional", "limits", "map", "memory",
    "optional", "ranges", "set", "span", "string", "tuple", "type_traits", "unordered_map",
    "unordered_set", "utility", "variant", "vector",
]])

def _header_impl(ctx):
    text = ctx.attr.includes
    if ctx.file.original:
        path = ctx.file.original.path
        if path.startswith("bazel-out/"):
            path = path.split("/", 3)[3]
        if not path.startswith("external/"):
            fail("Expected an external Chromium prefix header")
        text = '#include "' + path.split("/", 2)[2] + '"\n' + text
    output = ctx.actions.declare_file(ctx.label.name + ".h")
    ctx.actions.write(output, text)
    return [DefaultInfo(files = depset([output]))]

_prefix_header = rule(
    implementation = _header_impl,
    attrs = {"original": attr.label(allow_single_file = True), "includes": attr.string()},
)

def _attributes(original):
    return {key: original[key] for key in ["copts", "local_defines", "features"] if key in original}

def shared_prefixes(scoped = True):
    """Declare candidates after original producers; callers choose qualified imports."""
    if native.package_relative_label(":BUILD.bazel").repo_name != _QUALIFIED_REPOSITORY:
        return
    for group, original_name in ORIGINAL_PRODUCERS.items():
        original = native.existing_rule(original_name)
        if not original:
            fail("Missing original prefix producer: " + original_name)
        context = "shared_prefix_context_" + group
        dependencies = [original["library"]] if "v8" in group else [original["library"], ":serialization_prefix_context"]
        original_cc_library(name = context, deps = {Label(value): True for value in dependencies}.keys(), tags = ["manual"])
        includes = STD_INCLUDES if "v8" in group else (FULL_INCLUDES if any([path.endswith("/base/metrics/field_trial_params.h") for path in original["paths"]]) else SAFE_INCLUDES)
        paths = (V8_HEADERS if "v8" in group else BASE_HEADERS) + GLOBAL_HEADERS[group]
        for kind in (["global", "component"] if group in COMPONENT_HEADERS else ["global"]):
            header = "shared_" + kind + "_" + group + "_header"
            additions = "".join(['#include "' + path + '"\n' for path in COMPONENT_INCLUDES[group]]) if kind == "component" else ""
            _prefix_header(name = header, original = original["header"], includes = includes + additions)
            closure = paths + (COMPONENT_HEADERS[group] if kind == "component" else []) + ["+chromium_dependencies+chromium/native/" + header + ".h"]
            attributes = _attributes(original)
            for mode in ["normal", "eager"]:
                options = [option for option in attributes["copts"] if option != "-fpch-instantiate-templates"] + (["-fpch-instantiate-templates"] if mode == "eager" else [])
                chromium_project_pch(
                    name = "shared_" + kind + "_" + group + "_" + mode + "_pch",
                    library = ":" + context,
                    header = ":" + header,
                    extras = list(original.get("extras", [])) + [original["header"]],
                    paths = sorted(closure),
                    closure_inputs = scoped,
                    target_compatible_with = _LINUX,
                    tags = ["manual"],
                    **dict(attributes, copts = options)
                )
    for family, owner in SDK_OWNERS.items():
        original = native.existing_rule(owner)
        if not original or original.get("nocopts"):
            fail("Unsupported SDK source context: " + owner)
        context = "shared_sdk_" + family + "_context"
        original_cc_library(
            name = context,
            defines = SDK_DEFINES[family],
            target_compatible_with = _LINUX,
            tags = ["manual"],
        )
        header = "shared_sdk_" + family + "_header"
        _prefix_header(name = header, includes = _SDK_INCLUDES)
        attributes = _attributes(original)
        for mode in ["normal", "eager"]:
            options = list(attributes["copts"]) + ["-isysroot", ".", "-ffile-prefix-map=./="] + (["-fpch-instantiate-templates"] if mode == "eager" else [])
            chromium_project_pch(
                name = "shared_sdk_" + family + "_" + mode + "_pch",
                library = ":" + context,
                header = ":" + header,
                paths = ["+chromium_dependencies+chromium/native/" + header + ".h"],
                closure_inputs = scoped,
                target_compatible_with = _LINUX,
                tags = ["manual"],
                **dict(attributes, copts = options)
            )
