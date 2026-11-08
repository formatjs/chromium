"""Compile representative Blink sources with their real compiler inputs."""

load("@rules_cc//cc:cc_library.bzl", "cc_library")
load("@rules_cc//cc/common:cc_info.bzl", "CcInfo")
load(":batch_sources.bzl", BATCH_SOURCES = "SOURCES")
load(":browser_probe_sources.bzl", "PLATFORM_SOURCE_OVERRIDES", "SOURCE_GROUPS")

def _headers_impl(ctx):
    return [
        DefaultInfo(files = depset()),
        CcInfo(compilation_context = ctx.attr.library[CcInfo].compilation_context),
    ]

_compilation_headers = rule(
    implementation = _headers_impl,
    attrs = {"library": attr.label(mandatory = True, providers = [CcInfo])},
)

def _blink_library_probe(name, library, repository, sources, forwarders = "blink_core_forwarders", gpu_header = None):
    _compilation_headers(
        name = name + "_headers",
        library = repository + "//native:" + library["name"],
    )
    cc_library(
        name = name,
        srcs = [repository + ("//native" if source.startswith(":") else "//:") + source for source in sources],
        copts = library["copts"],
        local_defines = library["defines"],
        linkstatic = True,
        deps = [":" + name + "_headers"],
        features = select({
            "//tools/ci/compile:scan_disabled": [],
            "//conditions:default": ["cc_include_scanning"],
        }),
        # Skia selects these headers through macro includes.
        additional_compiler_inputs = [
            repository + "//:base/component_export.h",
            repository + "//:skia/config/SkUserConfig.h",
            repository + "//:skia/config/sk_ref_cnt_ext_debug.h",
            repository + "//:skia/config/sk_ref_cnt_ext_release.h",
            repository + "//:skia/ext/skia_histogram.h",
            # Preserve the directory used by ../../skia/config includes.
            repository + "//native:" + forwarders + "/third_party/re2/src/re2/re2.h",
        ] + ([gpu_header] if gpu_header else []),
        tags = ["manual"],
    )

def native_compile_probe(name, library, sources):
    """Compare scanning with the owner's unchanged compilation context."""
    if any([source not in library["srcs"] for source in sources]):
        fail("Probe source is not compiled by " + library["name"])
    _compilation_headers(
        name = name + "_headers",
        library = "@chromium//native:" + library["name"],
    )
    cc_library(
        name = name,
        srcs = ["@chromium//native" + p if p.startswith(":") else "@chromium" + p if p.startswith("//") else p for p in sources],
        copts = library["copts"],
        local_defines = library["defines"],
        linkstatic = True,
        deps = [":" + name + "_headers"],
        features = select({
            "//tools/ci/compile:scan_disabled": [],
            "//conditions:default": ["cc_include_scanning"],
        }),
        additional_compiler_inputs = ["@chromium//:base/component_export.h"],
        tags = ["manual"],
    )

def blink_compile_probe(name, libraries, repository = "@chromium", batch = False, batch_limit = None):
    """Reuse each source's real context without requesting its owner's objects."""
    sources = BATCH_SOURCES if batch else [
        "third_party/blink/renderer/core/layout/layout_box.cc",
        "third_party/blink/renderer/core/layout/layout_view.cc",
        "third_party/blink/renderer/core/paint/svg_object_painter.cc",
        "third_party/blink/renderer/core/css/css_palette_mix_value.cc",
        "third_party/blink/renderer/core/css/css_relative_color_value.cc",
    ]
    if batch_limit != None:
        if not batch or batch_limit < 1 or batch_limit > len(sources):
            fail("batch_limit requires a nonempty subset of the fixed batch")
        sources = sources[:batch_limit]
    _blink_library_probe(name, libraries["//third_party/blink/renderer/core:core"], repository, sources)
    _blink_library_probe(name + "_canvas", libraries["//third_party/blink/renderer/core/probe:probe"], repository, [
        "third_party/blink/renderer/core/probe/core_probes.cc",
    ])

def host_blink_compile_probe(name, libraries, repository, wide = False, captured_host = True):
    """Compile Blink contexts independently, including the captured ARM64 host."""
    toolchain = "(//build/toolchain/linux:clang_x64_v8_arm64)" if captured_host else ""
    generated = ":clang_x64_v8_arm64/gen/" if captured_host else ":gen/"
    owners = [
        ("", "//third_party/blink/renderer/core:core", [
            "third_party/blink/renderer/core/layout/layout_box.cc",
            "third_party/blink/renderer/core/layout/layout_view.cc",
            "third_party/blink/renderer/core/paint/svg_object_painter.cc",
            "third_party/blink/renderer/core/css/css_palette_mix_value.cc",
            "third_party/blink/renderer/core/css/css_relative_color_value.cc",
        ] + ([generated + "third_party/blink/renderer/core/html/html_permission_element_strings_map.cc"] if wide else [])),
        ("_canvas", "//third_party/blink/renderer/core/probe:probe", [
            "third_party/blink/renderer/core/probe/core_probes.cc",
        ]),
    ]
    if wide:
        owners += [
            ("_accessibility", "//third_party/blink/renderer/modules/accessibility:accessibility", [
                "third_party/blink/renderer/modules/accessibility/ax_object.cc",
                "third_party/blink/renderer/modules/accessibility/ax_node_object.cc",
            ]),
            ("_canvas2d", "//third_party/blink/renderer/modules/canvas:canvas", [
                "third_party/blink/renderer/modules/canvas/canvas2d/canvas_rendering_context_2d.cc",
            ]),
            ("_platform", "//third_party/blink/renderer/platform/wtf:wtf", [
                "third_party/blink/renderer/platform/wtf/date_math.cc",
            ]),
            ("_bindings", "//third_party/blink/renderer/bindings/modules/v8:v8", [
                generated + "third_party/blink/renderer/bindings/modules/v8/v8_video_frame.cc",
                generated + "third_party/blink/renderer/bindings/modules/v8/v8_webgl2_rendering_context_webgpu.cc",
            ]),
            ("_graphics", "//third_party/blink/renderer/platform:platform", [
                "third_party/blink/renderer/platform/graphics/accelerated_static_bitmap_image.cc",
                "third_party/blink/renderer/platform/graphics/mailbox_texture_backing.cc",
                "third_party/blink/renderer/platform/graphics/video_frame_image_util.cc",
                "third_party/blink/renderer/platform/webrtc/convert_to_webrtc_video_frame_buffer.cc",
            ]),
            ("_mediastream", "//third_party/blink/renderer/modules/mediastream:mediastream", [
                "third_party/blink/renderer/modules/mediastream/web_media_player_ms_compositor.cc",
            ]),
            ("_webcodecs", "//third_party/blink/renderer/modules/webcodecs:webcodecs", [
                "third_party/blink/renderer/modules/webcodecs/video_frame.cc",
            ]),
        ]
    for suffix, owner, sources in owners:
        library = dict(libraries[owner + toolchain])
        library["copts"] = library["copts"] + ["-I" + Label(root).workspace_root for root in library.get("include_roots", [])]
        forwarders = "browser_forwarders"
        if not captured_host:
            if owner.startswith("//third_party/blink/renderer/core"):
                forwarders = "blink_core_forwarders"
            elif owner.startswith("//third_party/blink/renderer/platform"):
                forwarders = "blink_platform_forwarders"
            else:
                forwarders = "blink_modules_forwarders"
        _blink_library_probe(
            name + suffix,
            library,
            repository,
            sources,
            forwarders = forwarders,
            gpu_header = ("@chromium" if captured_host else repository) + "//native:gen/gpu/config/gpu_driver_bug_workaround_autogen.h",
        )

def browser_compile_probe(name, libraries, repository = "@chromium", platform = "linux-amd64"):
    """Compile measured browser hotspots with each source's owning context."""
    overrides = PLATFORM_SOURCE_OVERRIDES.get(platform, {})
    for index, (owner, sources) in enumerate(SOURCE_GROUPS.items()):
        library = dict(libraries[owner])
        sources = [overrides.get(source, source) for source in sources]
        for source in sources:
            if source not in library["srcs"] and "//:" + source not in library["srcs"]:
                fail("Probe source is not compiled by " + owner + ": " + source)
        library["copts"] = library["copts"] + ["-I" + Label(root).workspace_root for root in library.get("include_roots", [])]
        _blink_library_probe(
            name + "_" + str(index),
            library,
            repository,
            sources,
            forwarders = "browser_forwarders",
            gpu_header = repository + "//native:gen/gpu/config/gpu_driver_bug_workaround_autogen.h",
        )
