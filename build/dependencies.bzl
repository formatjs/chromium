"""One dependency setup for the combined Chromium workspace."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")
load(":angle_repository.bzl", "chromium_angle_repository", "chromium_angle_support")
load(":blink_sources.bzl", "chromium_blink_sources")
load(":browser_sources.bzl", "chromium_browser_sources")
load(":codecs.bzl", "chromium_codec_sources")
load(":compositor_sources.bzl", "chromium_compositor_sources")
load(":ffmpeg_sources.bzl", "chromium_ffmpeg_sources")
load(":fonts.bzl", "chromium_font_sources")
load(":graphics_sources.bzl", "chromium_graphics_sources")
load(":khronos_sources.bzl", "chromium_khronos_sources")
load(":libyuv_sources.bzl", "chromium_libyuv_sources")
load(":media_sources.bzl", "chromium_media_sources")
load(":ml_sources.bzl", "chromium_ml_sources")
load(":msvc_atl.bzl", "chromium_msvc_atl", "chromium_msvc_atl_libraries")
load(":msvc_dia.bzl", "chromium_msvc_dia")
load(":platform_runtime.bzl", "chromium_platform_headers_dispatch", "chromium_platform_runtime_repository")
load(":protobuf_javascript_sources.bzl", "chromium_protobuf_javascript_sources")
load(":pthreadpool_sources.bzl", "chromium_pthreadpool_sources")
load(":repositories.bzl", "chromium_dawn_repository", "chromium_overlay_archive", "chromium_overlay_repository", "chromium_quiche_repository")
load(":skia_repository.bzl", "chromium_skia_repository")
load(":swiftshader_sources.bzl", "chromium_swiftshader_sources")
load(":v8_repository.bzl", "chromium_v8_repository")
load(":vulkan_sources.bzl", "chromium_vulkan_sources")
load(":vulkan_tools_sources.bzl", "chromium_vulkan_tools_sources")
load(":wayland_protocol_sources.bzl", "chromium_wayland_protocol_sources")

_OVERLAYS = [
    "angle",
    "chromium",
    "chromium_icu",
    "compact_enc_det",
    "dragonbox",
    "fp16",
    "ipcz",
    "linux-syscall-support",
    "nspr",
    "nss",
    "perfetto",
    "skia",
    "v8",
]

def _dependencies_impl(ctx):
    chromium_msvc_atl(name = "chromium_msvc_atl")
    chromium_msvc_atl_libraries(name = "chromium_msvc_atl_libraries")
    chromium_msvc_dia(name = "chromium_msvc_dia")
    chromium_platform_runtime_repository(
        name = "chromium_platform_runtime",
        manifest = Label("//overlays/chromium:native/platform_runtime.json"),
    )
    chromium_platform_runtime_repository(
        name = "chromium_platform_runtime_arm64",
        manifest = Label("//overlays/chromium:platforms/linux_arm64/platform_runtime.json"),
    )
    chromium_platform_headers_dispatch(
        name = "chromium_platform_headers_cross",
        template = Label("//build:platform_headers.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_windows_debuggers",
        urls = ["https://api.nuget.org/v3-flatcontainer/microsoft.debugging.platform.dbgeng/20260319.1511.0/microsoft.debugging.platform.dbgeng.20260319.1511.0.nupkg"],
        sha256 = "875678516f9ceed4a1c8b9b106d165106fcaa38723ad7c584c47b95b231600de",
        type = "zip",
        build_file = Label("//build:windows_debuggers.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_windows_sdk_runtime",
        urls = ["https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.cpp/10.0.26100.7705/microsoft.windows.sdk.cpp.10.0.26100.7705.nupkg"],
        sha256 = "ff455660bee071a744715a9665666fa29c07681579d3d815959a9eec5a556424",
        type = "zip",
        strip_prefix = "c",
        build_file = Label("//build:windows_sdk_runtime.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_mig",
        urls = ["https://chrome-infra-packages.appspot.com/dl/chromium/third_party/mig/linux-amd64/+/4wxov_ILjFdgBumBqgUgOgIcr4kcMh7i4b4oJi_cLjcC"],
        sha256 = "e30c68bff20b8c576006e981aa05203a021caf891c321ee2e1be28262fdc2e37",
        type = "zip",
        build_file_content = "exports_files([\"migcom\"])\n",
    )
    chromium_ffmpeg_sources()
    chromium_media_sources(ctx)
    chromium_compositor_sources(ctx)
    chromium_blink_sources(ctx)
    chromium_browser_sources(ctx)
    chromium_ml_sources(ctx)
    chromium_pthreadpool_sources()
    chromium_libyuv_sources()
    chromium_wayland_protocol_sources()
    chromium_angle_support()
    chromium_protobuf_javascript_sources()
    chromium_font_sources()
    chromium_graphics_sources()
    chromium_khronos_sources()
    chromium_vulkan_sources()
    chromium_vulkan_tools_sources()
    chromium_swiftshader_sources()
    chromium_codec_sources()
    archives = {}
    root = ctx.path(Label("//:overlays.json")).dirname
    for name in _OVERLAYS:
        base = root.get_child("overlays/" + name + "/bcr")
        source = json.decode(ctx.read(base.get_child("source.json")))

        # Shared pins need one extraction; patched archives retain their own copy.
        key = name if base.get_child("patches").exists else json.encode(source)
        archive_name = archives.get(key)
        if not archive_name:
            archive_name = name + "_sources"
            chromium_overlay_archive(name = archive_name, overlay = name, catalog = Label("//:overlays.json"))
            archives[key] = archive_name
        chromium_overlay_repository(
            name = name,
            overlay = name,
            archive = "@" + archive_name + "//__source__:anchor",
            catalog = Label("//:overlays.json"),
            exclude_paths = ["third_party/protobuf/src"] if name in ["chromium", "ipcz"] else [],
        )
    chromium_overlay_repository(
        name = "chromium_linux_arm64",
        overlay = "chromium",
        variant = "linux_arm64",
        archive = "@chromium_sources//__source__:anchor",
        catalog = Label("//:overlays.json"),
        exclude_paths = ["third_party/protobuf/src"],
    )
    for variant in ["windows_amd64", "windows_arm64", "darwin_arm64"]:
        chromium_overlay_repository(
            name = "chromium_" + variant,
            overlay = "chromium",
            variant = variant,
            patches = [Label("//build:chromium-macos-headless-quit.patch")] if variant == "darwin_arm64" else [],
            archive = "@chromium_sources//__source__:anchor",
            catalog = Label("//:overlays.json"),
            exclude_paths = ["third_party/protobuf/src"],
        )
    chromium_v8_repository(name = "chromium_v8", archive = "@v8_sources//__source__:anchor", catalog = Label("//:overlays.json"))
    chromium_angle_repository(name = "chromium_angle", archive = "@angle_sources//__source__:anchor", catalog = Label("//:overlays.json"))
    chromium_skia_repository(name = "chromium_skia", archive = "@skia_sources//__source__:anchor", catalog = Label("//:overlays.json"))
    chromium_dawn_repository(name = "chromium_dawn", catalog = Label("//:overlays.json"))
    http_archive(
        name = "chromium_dxc",
        urls = ["https://github.com/microsoft/DirectXShaderCompiler/archive/2b58d6d865832f7146d6e22e2106e562458bbd0a.tar.gz"],
        sha256 = "6c6aad0787bc460f62be016660f3a6991c4b6f436a7d39b09132fcb5d1cf2c0c",
        strip_prefix = "DirectXShaderCompiler-2b58d6d865832f7146d6e22e2106e562458bbd0a",
        build_file = Label("//build:dxc.BUILD.bazel"),
        patches = [Label("//build:dxc-stdlib.patch")],
        patch_args = ["-p1"],
    )
    http_archive(
        name = "chromium_directx_headers",
        urls = ["https://github.com/microsoft/DirectX-Headers/archive/8287305d36a2f717260dbbba7b6f5fae36f0f88a.tar.gz"],
        sha256 = "84dce590cd2d99ef446cd5b52275be6029f118a6c29b9d70d3a21b5f1cfe6393",
        strip_prefix = "DirectX-Headers-8287305d36a2f717260dbbba7b6f5fae36f0f88a",
        build_file = Label("//build:directx_headers.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_breakpad",
        urls = ["https://github.com/google/breakpad/archive/a1220f673dc44632e821bd1a217089e5a159a203.tar.gz"],
        sha256 = "a4c96db27987d6ca4039d5d4210b5e00f5fb9ccbd6a8ed72e48303f8a8980e89",
        strip_prefix = "breakpad-a1220f673dc44632e821bd1a217089e5a159a203",
        build_file_content = ctx.read(Label("//build:browser_sources.BUILD.bazel")).replace("@@PREFIX@@", "third_party/breakpad/breakpad").replace("@@HEADER_EXCLUDES@@", "[]"),
    )
    http_archive(
        name = "chromium_microsoft_webauthn",
        urls = ["https://github.com/microsoft/webauthn/archive/c3ed95fd7603441a0253c55c14e79239cb556a9f.tar.gz"],
        sha256 = "b44f5f81eadb96b2f3a0736bb5a7bff0aa3dd1b3774cac50d2dc17d61ad7a654",
        strip_prefix = "webauthn-c3ed95fd7603441a0253c55c14e79239cb556a9f",
        build_file_content = ctx.read(Label("//build:browser_sources.BUILD.bazel")).replace("@@PREFIX@@", "third_party/microsoft_webauthn/src").replace("@@HEADER_EXCLUDES@@", "[]"),
    )
    http_archive(
        name = "chromium_google_toolbox_for_mac",
        urls = ["https://github.com/google/google-toolbox-for-mac/archive/42b12f10cd8342f5cb41a1e3e3a2f13fd9943b0d.tar.gz"],
        sha256 = "e475d96e91d843ec993bb27dedfe18296f9d3ef4bac94707e6190bd483925354",
        strip_prefix = "google-toolbox-for-mac-42b12f10cd8342f5cb41a1e3e3a2f13fd9943b0d",
        build_file_content = ctx.read(Label("//build:browser_sources.BUILD.bazel")).replace("@@PREFIX@@", "third_party/google_toolbox_for_mac/src").replace("@@HEADER_EXCLUDES@@", "[]"),
    )
    http_archive(
        name = "chromium_angle_metal_shaders",
        urls = ["https://chrome-infra-packages.appspot.com/dl/chromium/gpu/angle-metal-shader-libraries/+/S0FPOVKrgaiqyuR20SSHiPorLgYez29bfwEdKBobUMMC"],
        sha256 = "4b414f3952ab81a8aacae476d1248788fa2b2e061ecf6f5b7f011d281a1b50c3",
        type = "zip",
        build_file_content = 'exports_files(["gpu_shader_cache.bin"])',
    )
    chromium_quiche_repository(name = "chromium_quiche", catalog = Label("//:overlays.json"))
    new_git_repository(
        name = "chromium_sqlite",
        remote = "https://chromium.googlesource.com/chromium/deps/sqlite",
        commit = "7d348fc79216a09b864ff881d8561a6222301666",
        build_file = Label("//build:sqlite.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_platform_headers",
        type = "tar.xz",
        urls = ["https://commondatastorage.googleapis.com/chrome-linux-sysroot/36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50"],
        sha256 = "36a164623d03f525e3dfb783a5e9b8a00e98e1ddd2b5cff4e449bd016dd27e50",
        build_file = Label("//build:platform_headers.BUILD.bazel"),
    )
    http_archive(
        name = "chromium_platform_headers_arm64",
        type = "tar.xz",
        urls = ["https://commondatastorage.googleapis.com/chrome-linux-sysroot/2f915d821eec27515c0c6d21b69898e23762908d8d7ccc1aa2a8f5f25e8b7e18"],
        sha256 = "2f915d821eec27515c0c6d21b69898e23762908d8d7ccc1aa2a8f5f25e8b7e18",
        build_file_content = ctx.read(Label("//build:platform_headers.BUILD.bazel")).replace("x86_64-linux-gnu", "aarch64-linux-gnu"),
    )
    return ctx.extension_metadata(
        reproducible = True,
        root_module_direct_deps = _OVERLAYS + ["chromium_darwin_arm64", "chromium_windows_amd64", "chromium_windows_arm64", "chromium_windows_debuggers", "chromium_windows_sdk_runtime", "chromium_mig", "chromium_dxc", "chromium_directx_headers", "chromium_breakpad", "chromium_microsoft_webauthn", "chromium_google_toolbox_for_mac", "chromium_angle_metal_shaders", "chromium_msvc_dia", "chromium_msvc_atl_libraries", "chromium_linux_arm64", "chromium_platform_headers_arm64", "chromium_platform_headers_cross", "chromium_platform_runtime_arm64"] + ["chromium_platform_runtime", "chromium_catapult"] + ["chromium_openscreen", "chromium_pdfium", "chromium_readability"] + ["chromium_anonymous_tokens", "chromium_content_analysis_sdk", "chromium_dom_distiller_js", "chromium_ink", "chromium_ink_stroke_modeler", "chromium_libaddressinput", "chromium_xdg_utils"] + ["chromium_search_engines_data", "chromium_cld3", "chromium_emoji_segmenter", "chromium_ots", "chromium_material_color_utilities", "chromium_smhasher", "chromium_libphonenumber", "chromium_crabbyavif", "chromium_cros_system_api", "chromium_devtools_frontend", "chromium_devtools_esbuild", "chromium_xcomposite", "chromium_xtst", "chromium_webrtc", "chromium_libsrtp", "chromium_federated_compute", "chromium_cdm_api", "chromium_libgav1", "chromium_leveldatabase", "chromium_ffmpeg", "chromium_ruy", "chromium_eigen3", "chromium_gemmlowp", "chromium_farmhash", "chromium_neon_2_sse", "chromium_tflite", "chromium_xnnpack", "chromium_pthreadpool", "chromium_libyuv", "chromium_v8", "chromium_wayland_protocols", "chromium_kde_protocols", "chromium_protobuf_javascript", "chromium_vulkan_tools", "chromium_pciutils", "chromium_angle", "chromium_vma", "chromium_swiftshader", "chromium_vulkan_utility", "chromium_vulkan_validation", "chromium_vulkan_loader", "chromium_egl_registry", "chromium_opengl_registry", "chromium_libdrm", "chromium_libsync", "chromium_skia", "chromium_jpeg", "chromium_webp", "chromium_wuffs", "chromium_freetype", "chromium_harfbuzz", "chromium_fontconfig", "chromium_dawn", "chromium_quiche", "chromium_sqlite", "chromium_platform_headers"],
        root_module_direct_dev_deps = [],
    )

chromium_dependencies = module_extension(implementation = _dependencies_impl)
