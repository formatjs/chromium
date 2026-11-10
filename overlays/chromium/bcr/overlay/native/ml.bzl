"""Captured TFLite, XNNPACK and matrix kernels."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":ml_sources.bzl", "ACTIONS", "COPIES", "LIBRARIES", "PUBLIC_DEFINES", "SHARED_HEADERS", "TOOLS")
load(":python_action.bzl", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_ml():
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    for copy in COPIES:
        chromium_resource_copy(**copy)
    cc_library(
        name = "ml_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + [":" + copy["name"] for copy in COPIES],
        includes = ["..", "gen", "gen/third_party/tflite/src", "../third_party/tflite/shims", "../third_party/ml_dtypes/src", "../third_party/ml_dtypes/src/ml_dtypes"],
        deps = ["@chromium_" + project + "//:chromium_headers" for project in [
            "tflite",
            "xnnpack",
            "ruy",
            "eigen3",
            "gemmlowp",
            "farmhash",
            "neon_2_sse",
        ]] + ["@flatbuffers//:runtime_cc", "@cpuinfo//:cpuinfo", "@fp16//:fp16", "@fxdiv//:FXdiv", "@chromium_pthreadpool//:headers"],
    )
    for original, library in LIBRARIES.items():
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        asm_sources = [p for p in library["srcs"] if p.endswith((".s", ".S"))]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":ml_headers"] + library["deps"],
        )
        if original == "//third_party/tflite:tflite_op_shim":
            common["deps"] = common["deps"] + ["@abseil-cpp//absl/log:check", "@abseil-cpp//absl/log:log"]
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
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in c_sources and p not in asm_sources],
            copts = library["copts"],
            **common
        )
    for name, original in {
        "tflite": "//third_party/tflite:tflite",
        "tflite_builtin_op_resolver": "//third_party/tflite:tflite_builtin_op_resolver",
        "xnnpack": "//third_party/xnnpack:xnnpack",
        "ruy": "//third_party/ruy:ruy",
    }.items():
        if name in ["tflite", "tflite_builtin_op_resolver"]:
            cc_library(
                name = name,
                defines = PUBLIC_DEFINES,
                deps = [":" + LIBRARIES[original]["name"]],
            )
        else:
            native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
