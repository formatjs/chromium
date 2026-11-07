"""Native Chromium executable, host generators and browser assets."""

load("@chromium//native:python_action.bzl", NativeChromiumFilesInfo = "ChromiumFilesInfo")
load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", _cc_library = "cc_library")
load("@rules_python//python:defs.bzl", "py_binary")
load(":browser_sources.bzl", "ACTIONS", "ASSET_GROUPS", "BRIDGES", "BUNDLES", "COPIES", "LIBRARIES", "RUNTIME_FILES", "SHARED_HEADERS", "TOOLS")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":host_support.bzl", cc_library = "platform_cc_library")
load(":objcxx.bzl", "chromium_objc_libraries")
load(":public_dependency.bzl", "chromium_header_dependency", "chromium_snapshot_dependencies")
load(":python_action.bzl", "ChromiumFilesInfo", "chromium_filegroup", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":runtime_bundle.bzl", "chromium_runtime_bundle")
load(":tool_inputs.bzl", "chromium_tool_inputs")

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

def _verification_tools_impl(ctx):
    files = [ctx.file.nm, ctx.file.objdump]
    return [
        DefaultInfo(files = depset(files)),
        ChromiumFilesInfo(mappings = depset([(file, "third_party/llvm-build/Release+Asserts/bin/" + name) for file, name in [(ctx.file.nm, "llvm-nm"), (ctx.file.objdump, "llvm-objdump")]])),
    ]

_verification_tools = rule(
    implementation = _verification_tools_impl,
    attrs = {
        "nm": attr.label(default = Label("@llvm//tools:llvm-nm"), allow_single_file = True, cfg = "exec"),
        "objdump": attr.label(default = Label("@llvm//tools:llvm-objdump"), allow_single_file = True, cfg = "exec"),
    },
)

def native_browser():
    _verification_tools(name = "browser_verification_tools")
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
        if action["script"] == "build/config/mac/package_framework.py":
            continue
        if any([argument.endswith("/front_end/core/i18n/collect-ui-strings.js") for argument in action.get("args", [])]):
            action = dict(action)
            action["deps"] = [":devtools_i18n_npm" if dependency == ":devtools_inspector_npm" else dependency for dependency in action["deps"] if dependency != ":node_npm_sources"]
        if action["script"] in ["chrome/tools/build/mac/verify_order.py", "chrome/tools/build/mac/verify_dynamic_libraries.py"]:
            action = dict(action)
            action["args"] = [argument.replace("$LLVM_ROOT", "../../third_party/llvm-build/Release+Asserts") for argument in action["args"]]
            action["deps"] = action["deps"] + [":browser_verification_tools"]

            # LLVM uses the pinned macOS SDK libc++ runtime.
            if action["script"].endswith("/verify_dynamic_libraries.py"):
                action["args"] = action["args"] + ["--allow", "/usr/lib/libc++.1.dylib"]
            if action["script"].endswith("/verify_order.py"):
                framework = [bundle for bundle in BUNDLES if bundle["root"].endswith(".framework")][0]
                action["srcs"] = dict(action["srcs"])
                action["srcs"][":" + framework["name"]] = "out/bazel-import/" + framework["root"]
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
            "google_toolbox_for_mac",
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
        include_options = ["-I" + Label(root).workspace_root for root in library.get("include_roots", [])]
        for field in ["copts", "c_copts", "asm_copts", "objc_copts", "objcxx_copts"]:
            if field in library:
                library[field] = library[field] + include_options
        host = "(//build/toolchain/linux:" in original
        declare_library = _cc_library if host else cc_library
        deps = library["deps"]
        if original.startswith("//third_party/swiftshader/"):
            deps = deps + [":spirv_headers", "@spirv_headers//:spirv_cpp_headers"]
        if library["srcs"] or library["hdrs"]:
            deps = (["@chromium//native:base_headers", ":browser_tool_headers"] if host else [":browser_headers"]) + deps
        common = dict(
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = deps,
        )
        common["deps"] = common["deps"] + chromium_objc_libraries(library, deps)
        if library.get("additional_linker_inputs"):
            common["additional_linker_inputs"] = library["additional_linker_inputs"]
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
            if host:
                common["linkopts"] = common["linkopts"] + ["-Wl,--disable-new-dtags,-rpath,$$ORIGIN/lib"]
            if "//:chrome/app/chrome_exe_main_mac.cc" in sources:
                common["linkopts"] = common["linkopts"] + ["-Wl,-dead_strip_dylibs"]
            primary = library["outputs"][0]
            shared = library["kind"] == "shared_library"
            binary = primary + ".dylib" if shared and not primary.endswith(".dylib") else primary
            cc_binary(
                name = binary,
                srcs = sources + library["hdrs"],
                includes = library["includes"],
                copts = library["copts"],
                data = [":icudtl.dat"] + ([":browser_host_platform_runtime"] if host else []),
                linkshared = shared,
                **common
            )
            if primary != binary:
                chromium_resource_copy(
                    name = library["name"] + "_copy",
                    srcs = {":" + binary: primary},
                    outputs = {primary: primary},
                )
            if shared:
                cc_import(name = library["name"], shared_library = ":" + binary)
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
    for bundle in BUNDLES:
        symlinks = {}
        if bundle["root"].endswith(".framework"):
            versions = {path.split("/")[1]: True for path in bundle["destinations"] if path.startswith("Versions/")}
            if len(versions) != 1:
                fail("expected one framework version: " + bundle["root"])
            version = versions.keys()[0]
            symlinks["Versions/Current"] = version
            for path in bundle["destinations"]:
                component = path.split("/")[2]
                symlinks[component] = "Versions/Current/" + component
        if len(bundle["srcs"]) != len({source: True for source in bundle["srcs"]}):
            fail("duplicate bundle source: " + bundle["root"])
        chromium_runtime_bundle(
            name = bundle["name"],
            directory = bundle["root"],
            srcs = dict(zip(bundle["srcs"], bundle["destinations"])),
            symlinks = symlinks,
        )
    native.filegroup(
        name = "browser_assets",
        srcs = [":blink_core_assets", ":blink_modules_assets", ":content_assets", ":devtools_inspector_assets"] + [":" + record["name"] for record in ACTIONS if record["script"] not in ["build/config/mac/package_framework.py", "chrome/tools/build/mac/verify_order.py", "chrome/tools/build/mac/verify_dynamic_libraries.py"]] + [":" + record["name"] for record in COPIES] + [":" + group["name"] for group in ASSET_GROUPS],
    )
    if "//chrome:chrome_app_executable" in LIBRARIES:
        native.alias(name = "browser", actual = ":" + LIBRARIES["//chrome:chrome_app_executable"]["name"])
        app = [bundle for bundle in BUNDLES if bundle["root"] == "Chromium.app"][0]
        chromium_runtime_bundle(name = "browser_bundle", srcs = {":" + app["name"]: app["root"]}, validations = [":" + record["name"] for record in ACTIONS if record["script"] in ["chrome/tools/build/mac/verify_order.py", "chrome/tools/build/mac/verify_dynamic_libraries.py"]])
