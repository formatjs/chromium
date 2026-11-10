"""Build canonical ipcz with standalone support or the caller's Chromium base."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":sources.bzl", "CHROMIUM_DEFINES", "COPTS", "CORE_SOURCES")

_COPTS = COPTS
_DRIVER_SOURCES = [
    "third_party/ipcz/src/reference_drivers/object.cc",
    "third_party/ipcz/src/reference_drivers/random.cc",
    "third_party/ipcz/src/reference_drivers/single_process_reference_driver_base.cc",
    "third_party/ipcz/src/reference_drivers/sync_reference_driver.cc",
]
_DRIVER_HEADERS = [path[:-3] + ".h" for path in _DRIVER_SOURCES]

def ipcz_library(name, chromium_base = None, library_rule = cc_library, **kwargs):
    """Build original core using the selected upstream support implementation.

    Args:
        name: Library target.
        chromium_base: Chromium base target; None selects upstream standalone support.
        library_rule: Caller-owned library constructor.
        **kwargs: Common cc_library attributes.
    """
    library_rule(
        name = name,
        srcs = [Label("//:" + path) for path in CORE_SOURCES],
        copts = _COPTS,
        defines = [] if chromium_base else ["IPCZ_STANDALONE"],
        local_defines = CHROMIUM_DEFINES if chromium_base else [],
        linkstatic = True,
        deps = [Label("//:internal_headers")] + ([chromium_base] if chromium_base else [Label("//:standalone_support")]),
        **kwargs
    )

def ipcz_reference_drivers(name, ipcz, chromium = False, **kwargs):
    """Build original synchronous reference driver for integration tests.

    Args:
        name: Driver target.
        ipcz: Matching ipcz core library.
        chromium: Match Chromium core configuration.
        **kwargs: Common cc_library attributes.
    """
    cc_library(
        name = name,
        testonly = True,
        srcs = [Label("//:" + path) for path in _DRIVER_SOURCES],
        hdrs = [Label("//:" + path) for path in _DRIVER_HEADERS],
        copts = _COPTS,
        local_defines = CHROMIUM_DEFINES if chromium else [],
        linkstatic = True,
        deps = [ipcz],
        **kwargs
    )
