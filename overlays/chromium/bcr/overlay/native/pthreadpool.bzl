"""Captured pthreadpool profile using Chromium's base::PostJob adapter."""

load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":pthreadpool_sources.bzl", "LIBRARIES", "SHARED_HEADERS")

def native_pthreadpool():
    cc_library(
        name = "pthreadpool_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"],
        includes = ["..", "gen"],
        deps = ["@chromium_pthreadpool//:headers"],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":pthreadpool_headers"] + library["deps"],
        )
        cc_library(
            name = library["name"] + "_c",
            srcs = c_sources,
            copts = library["c_copts"],
            **common
        )
        common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in c_sources],
            copts = library["copts"],
            **common
        )
    native.alias(name = "pthreadpool", actual = ":" + LIBRARIES["//third_party/pthreadpool:pthreadpool"]["name"])
