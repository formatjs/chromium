"""Original URL parser, canonicalizer, origins and Mojo traits."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":url_sources.bzl", "COPTS", "DEFINES", "GENERATED_HEADERS", "HEADERS", "SOURCES")

def native_url():
    """Compile Linux URL sources and original generated wire representations."""
    cc_library(
        name = "url_headers",
        hdrs = ["//:" + path for path in HEADERS] + [":" + path for path in GENERATED_HEADERS] + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = [":base", ":mojo_binding_headers"],
    )
    dependencies = {
        "url": [":base_i18n", "//third_party/icu:icu"],
        "gurl_shared": [":mojo_cpp_bindings"],
        "origin_shared": [":mojo_cpp_bindings", ":mojo_base_shared"],
        "scheme_host_port_shared": [":mojo_cpp_bindings"],
        "traits": [":url", ":url_gurl_shared", ":url_origin_shared", ":url_scheme_host_port_shared", ":mojo_base_traits_shared"],
        "gurl": [":url", ":url_traits", ":url_gurl_shared", ":mojo_cpp_bindings"],
        "origin": [":url", ":url_traits", ":url_gurl", ":url_origin_shared", ":mojo_base_types", ":mojo_cpp_bindings"],
        "scheme_host_port": [":url", ":url_traits", ":url_scheme_host_port_shared", ":mojo_cpp_bindings"],
    }
    for name, deps in dependencies.items():
        cc_library(
            name = "url" if name == "url" else "url_" + name,
            srcs = [(":" if path.startswith("gen/") else "//:") + path for path in SOURCES[name]],
            copts = COPTS[name],
            local_defines = DEFINES[name],
            linkstatic = True,
            deps = [":url_headers"] + deps,
        )
