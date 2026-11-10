"""Native Linux Mojo core, bindings and system libraries."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":mojo_runtime_sources.bzl", "COPTS", "DEFINES", "GENERATED_HEADERS", "HEADERS", "SOURCES")

def native_mojo_runtime():
    """Build unchanged Linux sources with original per-target configuration."""
    cc_library(
        name = "mojo_runtime_headers",
        hdrs = ["//:" + path for path in HEADERS] + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["//build:build_config"],
    )
    cc_library(
        name = "mojo_binding_headers",
        hdrs = [":" + path for path in GENERATED_HEADERS],
        includes = ["gen"],
        deps = [":mojo_runtime_headers"],
    )
    dependencies = {
        "unix_address": [],
        "features": [],
        "platform": [":mojo_features", ":mojo_unix_address"],
        "c_system": [],
        "core": [":mojo_features", ":mojo_platform", "//third_party/ipcz:ipcz"],
        "embedder": [":mojo_core", ":mojo_c_system", ":mojo_features", ":mojo_platform"],
        "cpp_system": [":mojo_embedder", ":mojo_c_system", ":mojo_platform"],
        "ipc_messages": [":mojo_cpp_system"],
        "bindings_base": [":mojo_cpp_system", ":mojo_binding_headers"],
        "bindings_shared": [":mojo_bindings_base", ":mojo_binding_headers"],
        "bindings_control": [":mojo_bindings_base", ":mojo_bindings_shared", ":mojo_binding_headers"],
        "cpp_bindings": [":mojo_ipc_messages", ":mojo_bindings_base", ":mojo_bindings_control", ":mojo_cpp_system", ":mojo_binding_headers"],
        "interface_provider": [":mojo_cpp_bindings", ":mojo_binding_headers"],
        "base_values": [":mojo_cpp_bindings", ":mojo_cpp_system"],
        "base_shared": [":mojo_cpp_bindings", ":mojo_binding_headers"],
        "base_traits_shared": [":mojo_base_values", ":mojo_base_shared", ":base_i18n", ":mojo_binding_headers"],
        "base_traits": [":mojo_base_values", ":mojo_base_shared", ":mojo_base_traits_shared", ":mojo_binding_headers"],
        "base_types": [":mojo_base_values", ":mojo_base_shared", ":mojo_base_traits_shared", ":mojo_base_traits", ":base_i18n", ":mojo_binding_headers"],
    }
    for name, deps in dependencies.items():
        cc_library(
            name = "mojo_" + name,
            srcs = [(":" if path.startswith("gen/") else "//:") + path for path in SOURCES[name]],
            copts = COPTS[name],
            local_defines = DEFINES[name],
            linkstatic = True,
            deps = [":base", ":mojo_runtime_headers"] + deps,
        )
