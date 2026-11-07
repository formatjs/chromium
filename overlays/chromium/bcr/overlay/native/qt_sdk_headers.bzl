"""Keep Qt on the captured SDK's GNU C++ headers and runtime."""

load("@rules_cc//cc:find_cc_toolchain.bzl", "find_cpp_toolchain", "use_cc_toolchain")
load("@rules_cc//cc/common:cc_common.bzl", "cc_common")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")

def _qt_sdk_headers_impl(ctx):
    toolchain = find_cpp_toolchain(ctx)
    resources = {}
    for file in toolchain.all_files.to_list():
        if "/lib/clang/" in file.path:
            prefix, suffix = file.path.split("/lib/clang/", 1)
            resources[prefix + "/lib/clang/" + suffix.split("/", 1)[0]] = True
    if len(resources) != 1:
        fail("Qt SDK profile needs one Clang resource directory from the selected toolchain")
    headers = ctx.attr.sdk[CcInfo].compilation_context.headers
    configs = [file for file in headers.to_list() if file.path.endswith("/c++/10/bits/c++config.h")]
    if len(configs) != 1:
        fail("Qt SDK profile needs one architecture-specific GNU C++ configuration header")
    multiarch = configs[0].path.removesuffix("/c++/10/bits/c++config.h")
    root = multiarch.split("/usr/include/", 1)[0]
    return [CcInfo(
        compilation_context = cc_common.create_compilation_context(
            headers = headers,
            includes = depset([
                root + "/usr/include/c++/10",
                multiarch + "/c++/10",
                resources.keys()[0] + "/include",
                multiarch,
                root + "/usr/include",
            ], order = "preorder"),
        ),
        linking_context = ctx.attr.sdk[CcInfo].linking_context,
    )]

chromium_qt_sdk_headers = rule(
    implementation = _qt_sdk_headers_impl,
    attrs = {"sdk": attr.label(mandatory = True, providers = [CcInfo])},
    fragments = ["cpp"],
    toolchains = use_cc_toolchain(),
)
