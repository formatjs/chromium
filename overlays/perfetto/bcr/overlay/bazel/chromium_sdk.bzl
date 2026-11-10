"""Compile Chromium's Perfetto SDK graph against caller-owned generated protocols."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":sdk_sources.bzl", "SDK_COPTS", "SDK_DEFINES", "SDK_SOURCES")

def chromium_sdk(name, protocol_library, generated_sources, generated_headers, library_rule = cc_library, source_list = None, **kwargs):
    """Build real browser tracing, service, IPC and minimal storage code.

    Args:
        name: SDK library target.
        protocol_library: Matching generated C++ protocol library.
        generated_sources: Generated IPC implementation files.
        generated_headers: Table and descriptor headers.
        library_rule: Caller-owned library constructor.
        source_list: Optional static sources; compiler configuration stays selected.
        **kwargs: Common rule attributes.
    """
    library_rule(
        name = name,
        srcs = (SDK_SOURCES if source_list == None else source_list) + generated_sources,
        hdrs = generated_headers,
        includes = ["gen/third_party/perfetto"],
        copts = SDK_COPTS,
        local_defines = SDK_DEFINES,
        linkstatic = True,
        deps = [
            Label("//:chromium_include_aliases"),
            Label("//:chromium_jsoncpp"),
            Label("@zlib//:zlib"),
            protocol_library,
        ],
        **kwargs
    )
