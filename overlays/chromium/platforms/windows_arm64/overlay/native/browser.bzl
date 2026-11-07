"""Native Chromium executable, host generators and browser assets."""

load("@chromium//native:python_action.bzl", NativeChromiumFilesInfo = "ChromiumFilesInfo")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", _cc_library = "cc_library")
load("@rules_python//python:defs.bzl", "py_binary")
load(":browser_sources.bzl", "ACTIONS", "ASSET_GROUPS", "BRIDGES", "COPIES", "LIBRARIES", "RUNTIME_FILES", "SHARED_HEADERS", "TOOLS")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":grit_resource_inputs.bzl", "RESOURCE_INPUTS")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":public_dependency.bzl", "chromium_header_dependency", "chromium_snapshot_dependencies")
load(":python_action.bzl", "ChromiumFilesInfo", "chromium_filegroup", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":runtime_bundle.bzl", "chromium_runtime_bundle")
load(":tool_inputs.bzl", "chromium_tool_inputs")
load(":windows_resources.bzl", "chromium_windows_resource")

def _host_runtime_impl(ctx):
    runtime = ctx.attr.runtime[NativeChromiumFilesInfo]
    return [
        DefaultInfo(files = ctx.attr.runtime[DefaultInfo].files),
        ChromiumFilesInfo(mappings = runtime.mappings, executables = runtime.executables),
    ]

_host_runtime = rule(
    implementation = _host_runtime_impl,
    attrs = {"runtime": attr.label(
        default = Label("@chromium//native:browser_host_platform_runtime"),
        cfg = "exec",
        providers = [NativeChromiumFilesInfo],
    )},
)

def native_browser():
    _host_runtime(name = "browser_host_platform_runtime")
    if "browser_dom_distiller_plugin" in TOOLS:
        py_binary(
            name = "browser_dom_distiller_cli",
            srcs = ["//:third_party/dom_distiller_js/protoc_plugins/" + path for path in [
                "json_values_converter.py",
                "util/__init__.py",
                "util/plugin_protos.py",
                "util/types.py",
                "util/writer.py",
            ]],
            main = "//:third_party/dom_distiller_js/protoc_plugins/json_values_converter.py",
            imports = ["../third_party/dom_distiller_js/protoc_plugins"],
            deps = ["@protobuf//:protobuf_python"],
        )
    native_tools = {":" + library["name"]: True for library in LIBRARIES.values() if library["kind"] == "executable"}
    for name, tool in TOOLS.items():
        tool = dict(tool)
        if tool["tool"] in native_tools:
            tool["stage_runtime"] = True
            tool["runtime_deps"] = [":browser_host_platform_runtime"]
        chromium_tool_inputs(name = name, **tool)
    for bridge in BRIDGES:
        chromium_cxx_bridge(**bridge)
    for group in ASSET_GROUPS:
        chromium_filegroup(**group)
    for action in ACTIONS:
        if any([argument.endswith("/front_end/core/i18n/collect-ui-strings.js") for argument in action.get("args", [])]):
            action = dict(action)
            action["deps"] = [":devtools_i18n_npm" if dependency == ":devtools_inspector_npm" else dependency for dependency in action["deps"] if dependency != ":node_npm_sources"]
        standalone = action["script"].startswith("third_party/catapult/") or action["script"].endswith("/generate_devtools_grd.py")
        devtools = action["script"].startswith("third_party/devtools-frontend/") or any(["third_party/devtools-frontend/" in value for value in action["args"]])
        chromium_python_action(
            propagate_inputs = not standalone and (not devtools or action["script"].endswith("/ts_library.py")),
            **action
        )
        chromium_filegroup(
            name = action["name"] + "_outputs",
            srcs = {":" + path: "out/bazel-import/" + logical for path, logical in action["outs"].items()},
        )
    for copy in COPIES:
        chromium_resource_copy(**copy)
        chromium_filegroup(
            name = copy["name"] + "_outputs",
            srcs = {":" + path: "out/bazel-import/" + path for path in copy["outputs"]},
        )
    cc_library(
        name = "browser_headers_with_links",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["browser_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "browser_forwarders"],
        deps = [":content_headers", "@fast_float//:fast_float"] + ["@chromium_" + project + "//:chromium_headers" for project in [
            "anonymous_tokens",
            "breakpad",
            "microsoft_webauthn",
            "content_analysis_sdk",
            "dom_distiller_js",
            "ink",
            "ink_stroke_modeler",
            "libaddressinput",
            "openscreen",
            "pdfium",
            "xdg_utils",
        ]],
    )
    cc_library(
        name = "browser_tool_headers",
        hdrs = native.glob(["browser_forwarders/**/*.h"], allow_empty = True),
        includes = ["browser_forwarders"],
    )
    chromium_header_dependency(name = "browser_headers", dependency = ":browser_headers_with_links")
    for original, library in LIBRARIES.items():
        library = dict(library)
        host = "(//build/toolchain/linux:" in original
        include_options = ["-I" + Label(root).workspace_root for root in library.get("include_roots", [])] + [("/clang:-iquote" if original.startswith("//third_party/crashpad/crashpad/") else "-I") + Label(":all_buildflags").workspace_root + "/" + path for path in library.get("private_includes", [])]
        include_options = [("-iquote" if host else "/clang:-iquote") + Label("@chromium_swiftshader//:headers").workspace_root + "/" + path for path in library.get("swiftshader_include_dirs", [])] + include_options
        for field in ["copts", "c_copts", "asm_copts", "objc_copts", "objcxx_copts"]:
            if field in library:
                library[field] = library[field] + include_options
        declare_library = _cc_library if host else cc_library
        deps = library["deps"]
        if original.startswith("//third_party/swiftshader/"):
            deps = deps + [":spirv_headers", "@spirv_headers//:spirv_cpp_headers"]

        # Standalone libraries must not inherit Chromium defines or SDK headers.
        standalone = any([original.startswith(prefix) for prefix in [
            "//third_party/spirv-headers/",
            "//third_party/spirv-tools/",
            "//third_party/swiftshader/",
            "//third_party/vulkan-validation-layers/",
            "//third_party/vulkan-utility-libraries/",
        ]])
        if not standalone and (library["srcs"] or library["hdrs"] or library.get("resource_srcs")):
            deps = (["@chromium//native:base_headers", ":browser_tool_headers"] if host else [":browser_headers"]) + deps
        common = dict(
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = deps,
        )
        if library.get("additional_linker_inputs"):
            common["additional_linker_inputs"] = library["additional_linker_inputs"]
        resources = []
        for index, resource in enumerate(library.get("resource_srcs", [])):
            target = library["name"] + "_resource_" + str(index)
            assets = dict(RESOURCE_INPUTS.get(resource[1:] if resource.startswith(":") else resource, {}))
            assets.update(library.get("resource_assets", {}).get(resource, {}))
            chromium_windows_resource(
                name = target,
                src = resource,
                hdrs = library["hdrs"],
                assets = assets,
                include_root = library.get("resource_include_roots", {}).get(resource, ""),
                defines = library["resource_defines"],
                includes = library["includes"],
                deps = common["deps"],
            )
            resources.append(":" + target)
        common["deps"] = common["deps"] + resources
        if "(//build/toolchain/linux:" not in original and library["kind"] not in ["executable", "shared_library"] and any([original.startswith(prefix) for prefix in ["//chrome/", "//chrome:", "//extensions/", "//extensions:", "//components/", "//components:"]]):
            common.update(
                features = ["cc_include_scanning"],
                # Skia selects these headers through macro includes.
                additional_compiler_inputs = [
                    "//:base/component_export.h",
                    "//:skia/config/SkUserConfig.h",
                    "//:skia/config/sk_ref_cnt_ext_debug.h",
                    "//:skia/config/sk_ref_cnt_ext_release.h",
                    "//:skia/ext/skia_histogram.h",
                    ":gen/gpu/config/gpu_driver_bug_workaround_autogen.h",
                    ":browser_forwarders/third_party/re2/src/re2/re2.h",
                ],
            )

        c_sources = [path for path in library["srcs"] if path.endswith(".c")]
        asm_sources = [path for path in library["srcs"] if path.endswith((".s", ".S"))]
        for suffix, sources, options in [
            ("_c", c_sources, library.get("c_copts", [])),
            ("_asm", asm_sources, library.get("asm_copts", [])),
        ]:
            if sources:
                declare_library(
                    name = library["name"] + suffix,
                    srcs = sources,
                    hdrs = library["hdrs"],
                    includes = library["includes"],
                    copts = options,
                    alwayslink = True,
                    **common
                )
                common["deps"] = common["deps"] + [":" + library["name"] + suffix]
        sources = [path for path in library["srcs"] if path not in c_sources and path not in asm_sources]
        if library["kind"] in ["executable", "shared_library"]:
            if original.split("(")[0] == "//tools/v8_context_snapshot:v8_context_snapshot_generator":
                chromium_snapshot_dependencies(
                    name = library["name"] + "_snapshot_dependencies",
                    deps = common["deps"],
                )
                common["deps"] = [":" + library["name"] + "_snapshot_dependencies"]
            if not host:
                common["deps"] = common["deps"] + ["@chromium_msvc_atl_libraries//:atls"]
            if host:
                common["linkopts"] = common["linkopts"] + ["-Wl,--disable-new-dtags,-rpath,$$ORIGIN/lib"]
            primary = library["outputs"][0]
            shared = library["kind"] == "shared_library"
            cc_binary(
                name = primary,
                srcs = sources + library["hdrs"],
                includes = library["includes"],
                copts = library["copts"],
                data = [":icudtl.dat"] + ([":browser_host_platform_runtime"] if host else []),
                linkshared = shared,
                features = ["generate_pdb_file"] if not host else [],
                win_def_file = library.get("win_def_file"),
                **common
            )
            if not host:
                native.filegroup(name = primary + ".pdb", srcs = [":" + primary], output_group = "pdb_file")
            if shared:
                native.filegroup(name = primary + ".lib", srcs = [":" + primary], output_group = "interface_library")
                cc_import(name = library["name"], shared_library = ":" + primary, interface_library = ":" + primary + ".lib", hdrs = library["hdrs"], includes = library["includes"])
            else:
                native.alias(name = library["name"], actual = ":" + primary)
        else:
            declare_library(
                name = library["name"],
                srcs = sources,
                hdrs = library["hdrs"],
                includes = library["includes"],
                copts = library["copts"],
                alwayslink = library["kind"] == "source_set",
                **common
            )
    native.filegroup(
        name = "browser_assets",
        srcs = [":blink_core_assets", ":blink_modules_assets", ":content_assets", ":devtools_inspector_assets"] + [":" + action["name"] for action in ACTIONS if action["script"] != "build/win/reorder-imports.py"] + [":" + copy["name"] for copy in COPIES] + [":" + group["name"] for group in ASSET_GROUPS],
    )
    for dll in ["dbghelp", "dbgcore"]:
        native.alias(name = dll + ".dll", actual = "@chromium_windows_debuggers//:" + dll)
    native.alias(name = "browser", actual = ":chrome.exe")
    chromium_runtime_bundle(name = "browser_bundle", srcs = {":" + path: path for path in RUNTIME_FILES})
