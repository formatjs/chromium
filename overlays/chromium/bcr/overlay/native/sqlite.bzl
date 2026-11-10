"""Chromium SQLite amalgamation with original symbol names and safety flags."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":sqlite_sources.bzl", "COPTS", "DEFINES")

# Consumers include the same public SQLite configuration as original GN graph.
SQLITE_DEFINES = [value for value in DEFINES if value.startswith("SQLITE_")]

def native_sqlite():
    cc_library(
        name = "chromium_sqlite",
        srcs = ["//:third_party/sqlite/sqlite3_shim.c"],
        hdrs = ["//:third_party/sqlite/sqlite3.h", "//:third_party/sqlite/sqlite3_shim_fixups.h"],
        includes = [".."],
        copts = COPTS,
        local_defines = DEFINES,
        defines = SQLITE_DEFINES,
        linkstatic = True,
        deps = ["@chromium_sqlite//:headers", "//third_party/icu:icu"],
    )
