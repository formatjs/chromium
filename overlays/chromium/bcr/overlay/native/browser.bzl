"""Native Chromium executable, host generators and browser assets."""

load("@rules_cc//cc:cc_binary.bzl", "cc_binary")
load("@rules_cc//cc:cc_import.bzl", "cc_import")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_python//python:defs.bzl", "py_binary")
load(":browser_pch.bzl", "browser_project_pch")
load(":browser_sources.bzl", "ACTIONS", "ASSET_GROUPS", "BRIDGES", "COPIES", "LIBRARIES", "RUNTIME_FILES", "SHARED_HEADERS", "TOOLS")
load(":cxx_bridge.bzl", "chromium_cxx_bridge")
load(":public_dependency.bzl", "chromium_snapshot_dependencies")
load(":python_action.bzl", "chromium_filegroup", "chromium_python_action")
load(":qt_sdk_headers.bzl", "chromium_qt_sdk_headers")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":runtime_bundle.bzl", "chromium_runtime_bundle")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_browser():
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
        name = "browser_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["browser_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "browser_forwarders"],
        deps = [":content_headers", "@fast_float//:fast_float"] + ["@chromium_" + project + "//:chromium_headers" for project in [
            "anonymous_tokens",
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
    if any([label.startswith("//third_party/ffmpeg:") for label in LIBRARIES]):
        cc_library(
            name = "browser_ffmpeg_headers",
            hdrs = [":all_buildflags"],
            deps = ["@chromium_ffmpeg//:chromium_headers"],
        )
    qt_libraries = ["//ui/qt:qt_interface", "//ui/qt:qt5_shim", "//ui/qt:qt6_shim"]
    if any([label in LIBRARIES for label in qt_libraries]):
        chromium_qt_sdk_headers(name = "browser_qt_sdk_headers", sdk = "@chromium_platform_headers//:qt_stdlib")
    runtime_binaries = []
    for original, library in LIBRARIES.items():
        if library["kind"] == "shared_library_import":
            primary = [path for path in library["outputs"] if path.endswith(".so") or (".so." in path and not path.endswith(".TOC"))][0]
            chromium_resource_copy(
                name = library["name"] + "_copy",
                srcs = {library["shared_library"]: primary},
                outputs = {primary: primary},
            )
            cc_import(name = library["name"] + "_import", shared_library = ":" + primary)
            cc_library(
                name = library["name"],
                deps = [":" + library["name"] + "_import"],
                data = [library["shared_library"]],
            )
            if primary in RUNTIME_FILES:
                runtime_binaries.append(":" + primary)
            continue
        angle = original.startswith("//third_party/angle/") or original.startswith("//third_party/angle:")
        v8 = original.startswith("//v8:") or original.startswith("//v8/")
        ffmpeg = original.startswith("//third_party/ffmpeg:")
        common = dict(
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            deps = ([":browser_tool_headers"] if angle or v8 or ffmpeg else ([":browser_headers"] if library["srcs"] or library["hdrs"] else [])) + library["deps"],
        )
        qt = original in qt_libraries
        include_options = ["-I" + Label(root).workspace_root for root in library.get("include_roots", [])]
        if angle:
            include_options.append("-I" + Label("@chromium_angle//:headers").workspace_root + "/third_party/angle/include")
        if v8:
            include_options.insert(0, "-I" + Label("@chromium_v8//:headers").workspace_root + "/v8")
            common["deps"] = common["deps"] + ["@chromium_v8//:headers"]
        if ffmpeg:
            common["deps"] = common["deps"] + [":browser_ffmpeg_headers"]
        if library.get("ffmpeg_config"):
            include_options.insert(0, "-iquote" + Label("@chromium_ffmpeg//:headers").workspace_root + "/" + library["ffmpeg_config"])
        cpp_options = library["copts"] + include_options
        if qt:
            common["deps"] = library["deps"]
            if original == "//ui/qt:qt_interface":
                common["implementation_deps"] = [":browser_qt_sdk_headers"]
            else:
                common["deps"] = [":browser_qt_sdk_headers"] + common["deps"]
            cpp_options = cpp_options + ["-nostdinc++", "-nobuiltininc"]
        if library.get("additional_linker_inputs"):
            common["additional_linker_inputs"] = library["additional_linker_inputs"]
        if library["kind"] in ["executable", "shared_library"]:
            common["linkopts"] = common["linkopts"] + ["-Wl,--disable-new-dtags,-rpath,$$ORIGIN/lib"]
            outputs = library["outputs"]
            shared = library["kind"] == "shared_library"
            primary = [path for path in outputs if path.endswith(".so") or (".so." in path and not path.endswith(".TOC"))][0] if shared else outputs[0]
            main = original == "//chrome:chrome_initial"
            if not main and not shared:
                common["deps"] = [":base_headers", ":browser_tool_headers"] + library["deps"]
            if qt:
                common["features"] = ["-static_link_cpp_runtimes"]
            binary_data = [":browser_platform_runtime"] if qt else [":icudtl.dat", ":browser_v8_runtime", ":browser_host_platform_runtime"]
            if original == "//tools/code_cache_generator:code_cache_generator" and "v8_context_snapshot.bin" in RUNTIME_FILES:
                binary_data.append(":v8_context_snapshot.bin")
            c_sources = [path for path in library["srcs"] if path.endswith(".c")]
            asm_sources = [path for path in library["srcs"] if path.endswith((".s", ".S"))]
            for suffix, sources, options in [
                ("_c", c_sources, library.get("c_copts", [])),
                ("_asm", asm_sources, library.get("asm_copts", [])),
            ]:
                if sources:
                    cc_library(
                        name = library["name"] + suffix,
                        srcs = sources,
                        hdrs = library["hdrs"],
                        includes = library["includes"],
                        copts = options + include_options,
                        local_defines = library["defines"],
                        deps = common["deps"],
                        linkstatic = True,
                        alwayslink = True,
                    )
                    common["deps"] = common["deps"] + [":" + library["name"] + suffix]
            if original.split("(")[0] == "//tools/v8_context_snapshot:v8_context_snapshot_generator":
                chromium_snapshot_dependencies(
                    name = library["name"] + "_snapshot_dependencies",
                    deps = common["deps"],
                )
                common["deps"] = [":" + library["name"] + "_snapshot_dependencies"]
            cc_binary(
                name = primary,
                srcs = [path for path in library["srcs"] if path not in c_sources and path not in asm_sources] + library["hdrs"],
                includes = library["includes"],
                copts = cpp_options,
                linkshared = shared,
                data = [":icudtl.dat", ":browser_assets", ":browser_v8_runtime", ":angle_runtime"] if main else binary_data,
                **common
            )
            native.alias(name = library["name"], actual = ":" + primary)
            if not main and [path for path in outputs if path in RUNTIME_FILES]:
                runtime_binaries.append(":" + library["name"])
            continue
        common.update(
            hdrs = library["hdrs"],
            includes = library["includes"],
            alwayslink = library["kind"] == "source_set",
        )
        if any([original.startswith(prefix) for prefix in ["//chrome/", "//chrome:", "//extensions/", "//extensions:", "//components/", "//components:"]]):
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
                cc_library(name = library["name"] + suffix, srcs = sources, copts = options + include_options, **common)
                common["deps"] = common["deps"] + [":" + library["name"] + suffix]
        sources = [path for path in library["srcs"] if path not in c_sources and path not in asm_sources]
        if original in ["//chrome/browser/ui:ui", "//chrome/browser:browser"]:
            replacement = browser_project_pch(library, common, sources, cpp_options)
            sources = select({
                "//native/tool_configuration:project_pch": [],
                "//conditions:default": sources,
            })
            common["deps"] = select({
                "//native/tool_configuration:project_pch": [replacement] + common["deps"],
                "//conditions:default": common["deps"],
            })
        cc_library(
            name = library["name"],
            srcs = sources,
            copts = cpp_options,
            **common
        )
    native.filegroup(
        name = "browser_assets",
        srcs = [":" + record["name"] for record in ACTIONS + COPIES] + [":" + group["name"] for group in ASSET_GROUPS] + runtime_binaries + [":browser_platform_runtime"],
    )
    if "//chrome:chrome_initial" in LIBRARIES:
        native.alias(name = "browser", actual = ":chrome")
        chromium_resource_copy(
            name = "browser_curl_copy",
            srcs = {"@curl//:curl_shared": "curl/libcurl.so"},
            outputs = {"lib/libcurl.so": "curl/libcurl.so"},
        )
        chromium_filegroup(
            name = "browser_curl_runtime",
            srcs = {":lib/libcurl.so": "out/bazel-import/lib/libcurl.so"},
        )
        chromium_runtime_bundle(
            name = "browser_bundle",
            srcs = {":" + path: path for path in RUNTIME_FILES},
            deps = [":browser_platform_runtime", ":browser_curl_runtime"],
        )
