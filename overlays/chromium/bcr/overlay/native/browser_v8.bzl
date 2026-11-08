"""Chromium's captured V8 profile, host generators and external snapshot."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load(":browser_v8_sources.bzl", "ACTIONS", "LIBRARIES", "PUBLIC_DEFINES", "SHARED_HEADERS", "TOOLS")
load(":llvm_training.bzl", "TRAINING_PLATFORM", "chromium_training_source")
load(":masm.bzl", "chromium_masm")
load(":public_dependency.bzl", "chromium_snapshot_dependencies")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")
load(":v8_pch.bzl", "v8_base_pch")

def native_browser_v8():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "browser_v8_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["browser_v8_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "gen/v8", "browser_v8_forwarders"],
        deps = ["@chromium_v8//:headers", "//native/rust:temporal_capi_headers", "@googletest//:gtest_prod"],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        asm_sources = [p for p in library["srcs"] if (p.endswith(".s") or p.endswith(".S"))]
        masm_sources = [p for p in library["srcs"] if p.endswith(".asm")]
        masm_objects = []
        for index, source in enumerate(masm_sources):
            target = library["name"] + "_masm_" + str(index)
            chromium_masm(name = target, src = source)
            masm_objects.append(":" + target)
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            defines = PUBLIC_DEFINES if original == "//v8:v8_headers" else [],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":browser_v8_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = library["c_copts"],
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        if asm_sources:
            cc_library(
                name = library["name"] + "_asm",
                srcs = asm_sources,
                copts = library["asm_copts"],
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_asm"]
        if original == "//v8:v8_base_without_compiler":
            v8_base_pch(library, common, library["srcs"])
            chromium_training_source(
                name = "llvm_training_v8",
                src = "@chromium_v8//:v8/src/maglev/maglev-graph-builder.cc",
                library = ":" + library["name"],
                copts = library["copts"],
                local_defines = library["defines"],
                extras = ["//testing/gtest:include/gtest/gtest_prod.h"],
                target_compatible_with = TRAINING_PLATFORM,
                tags = ["manual"],
            )
        if library["kind"] == "executable":
            if original.split("(")[0] == "//v8:mksnapshot":
                chromium_snapshot_dependencies(
                    name = library["name"] + "_snapshot_dependencies",
                    deps = common["deps"],
                )
                common["deps"] = [":" + library["name"] + "_snapshot_dependencies"]
            cc_binary(
                name = library["name"],
                srcs = library["srcs"] + library["hdrs"],
                copts = library["copts"],
                local_defines = library["defines"],
                linkopts = library["linkopts"],
                linkstatic = True,
                data = [":icudtl.dat"],
                deps = common["deps"],
            )
        else:
            cc_library(
                name = library["name"],
                srcs = [p for p in library["srcs"] if p not in c_sources and p not in asm_sources and p not in masm_sources] + masm_objects,
                copts = library["copts"],
                **common
            )
    native.alias(name = "browser_v8", actual = ":" + LIBRARIES["//v8:v8"]["name"])
    native.alias(name = "browser_v8_platform", actual = ":" + LIBRARIES["//v8:v8_libplatform"]["name"])
    native.filegroup(name = "browser_v8_runtime", srcs = [":icudtl.dat", ":snapshot_blob.bin"])
