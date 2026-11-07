"""Content browser, renderer and service dependencies."""

load("@bazel_skylib//rules:write_file.bzl", "write_file")
load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_python//python:py_info.bzl", "PyInfo")
load(":captured_includes.bzl", "captured_copts", "captured_includes")
load(":content_sources.bzl", "ACTIONS", "COPIES", "LIBRARIES", "METADATA", "SHARED_HEADERS", "TOOLS")
load(":generated_files.bzl", "CAPTURED_FILES")
load(":python_action.bzl", "ChromiumFilesInfo", "ChromiumGeneratedFilesInfo", "chromium_python_action")
load(":resource_copy.bzl", "chromium_resource_copy")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def _protobuf_python_inputs_impl(ctx):
    mappings = []
    for file in ctx.attr.runtime[PyInfo].transitive_sources.to_list():
        relative = file.short_path.partition("/google/protobuf/")[2]
        if not relative:
            fail("unexpected Protobuf Python input: " + file.short_path)
        for root in ["third_party/protobuf/python/", "out/bazel-import/pyproto/"]:
            mappings.append((file, root + "google/protobuf/" + relative))
    return [
        DefaultInfo(files = depset([file for file, _ in mappings])),
        ChromiumFilesInfo(mappings = depset(mappings), executables = []),
        ChromiumGeneratedFilesInfo(mappings = depset([pair for pair in mappings if pair[1].startswith("out/")])),
    ]

_protobuf_python_inputs = rule(
    implementation = _protobuf_python_inputs_impl,
    attrs = {"runtime": attr.label(providers = [PyInfo], mandatory = True)},
)

def native_content():
    for path, content in METADATA.items():
        if path in CAPTURED_FILES:
            continue
        write_file(
            name = "content_metadata_" + path.replace("/", "_"),
            out = path,
            content = [content],
        )
    cc_library(
        name = "content_revision_headers",
        hdrs = [":" + path for path in METADATA],
    )
    _protobuf_python_inputs(name = "protobuf_python_runtime", runtime = "@protobuf//:protobuf_python")
    for name, tool in TOOLS.items():
        chromium_tool_inputs(name = name, **tool)
    for action in ACTIONS:
        chromium_python_action(**action)
    for copy in COPIES:
        chromium_resource_copy(**copy)
    cc_library(
        name = "content_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["content_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "content_forwarders"],
        deps = [":blink_modules_headers", ":libxslt", "@chromium_openscreen//:chromium_headers", "@chromium_pdfium//:chromium_headers"],
    )
    for original, library in LIBRARIES.items():
        library = dict(library)
        include_options = ["-I" + Label(":all_buildflags").workspace_root + "/" + path for path in library.get("private_includes", [])]
        for field in ["copts", "c_copts", "asm_copts", "objc_copts", "objcxx_copts"]:
            if field in library:
                library[field] = library[field] + include_options
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = captured_includes(library),
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":content_headers"] + library["deps"],
        )
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = captured_copts(library, "c_copts"),
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cpp_sources = [p for p in library["srcs"] if p not in c_sources]
        gpu_internals = "//:content/browser/gpu/gpu_internals_ui.cc"
        if gpu_internals in cpp_sources:
            cc_library(
                name = "content_gpu_internals",
                srcs = [gpu_internals],
                copts = captured_copts(library),
                implementation_deps = [":content_revision_headers"],
                **common
            )
            cpp_sources.remove(gpu_internals)
            common["deps"] = common["deps"] + [":content_gpu_internals"]
        cc_library(
            name = library["name"],
            srcs = cpp_sources,
            copts = captured_copts(library),
            **common
        )
    native.alias(
        name = "content",
        actual = ":" + LIBRARIES["//content:content"]["name"],
    )

    native.filegroup(
        name = "content_assets",
        srcs = [":" + record["name"] for record in ACTIONS + COPIES],
    )
