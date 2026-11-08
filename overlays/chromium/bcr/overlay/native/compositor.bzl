"""Captured compositor and its network, metrics and WebRTC dependencies."""

load(":base_bind_consumers.bzl", cc_library = "base_bind_library")
load(":compositor_sources.bzl", "ACTIONS", "LIBRARIES", "SHARED_HEADERS")
load(":public_dependency.bzl", "chromium_link_dependency", "chromium_public_dependency")
load(":python_action.bzl", "chromium_python_action")

def native_compositor():
    for name, dependency in {
        "xcomposite": "@chromium_xcomposite//:xcomposite",
        "xdamage": "@libxdamage//:libxdamage",
        "xfixes": "@libxfixes//:libxfixes",
        "xrandr": "@libxrandr//:libxrandr",
        "xrender": "@libxrender//:libxrender",
        "xtst": "@chromium_xtst//:xtst",
        "drm": "@chromium_platform_headers//:drm_shared",
    }.items():
        chromium_link_dependency(name = "compositor_" + name + "_link", dependency = dependency)
    chromium_public_dependency(
        name = "webrtc_public_headers",
        dependency = "@chromium_webrtc//:chromium_headers",
    )
    cc_library(
        name = "webrtc_override_headers",
        hdrs = [p for p in SHARED_HEADERS if p.startswith("//:third_party/webrtc_overrides/")],
        strip_include_prefix = "/third_party/webrtc_overrides",
    )
    for action in ACTIONS:
        chromium_python_action(**action)
    cc_library(
        name = "compositor_headers",
        hdrs = SHARED_HEADERS + [":all_buildflags"] + native.glob(["compositor_forwarders/**/*.h"], allow_empty = True),
        includes = ["..", "gen", "compositor_forwarders"],
        deps = [
            ":media_headers",
            ":browser_services_headers",
            ":webrtc_override_headers",
            ":webrtc_public_headers",
            "@chromium_libsrtp//:chromium_headers",
            "@chromium_federated_compute//:chromium_headers",
            "@chromium_libyuv//:chromium_headers",
            "@jsoncpp//:jsoncpp",
            "@chromium_platform_headers//:pipewire_headers",
        ],
    )
    chromium_public_dependency(
        name = "libsrtp_public_headers",
        dependency = ":compositor_headers",
    )
    for original, library in LIBRARIES.items():
        private_copts = []
        if original == "//third_party/libsrtp:libsrtp":
            private_copts = ["-iquote" + Label("@chromium_libsrtp//:config/config.h").workspace_root + "/config"]
        c_sources = [p for p in library["srcs"] if p.endswith(".c")]
        common = dict(
            hdrs = library["hdrs"],
            includes = library["includes"],
            local_defines = library["defines"],
            linkopts = library["linkopts"],
            linkstatic = True,
            alwayslink = library["kind"] == "source_set",
            deps = [":compositor_headers"] + library["deps"],
        )
        if original == "//third_party/libsrtp:libsrtp":
            common["deps"] = [":libsrtp_public_headers"] + library["deps"]
        if c_sources:
            cc_library(
                name = library["name"] + "_c",
                srcs = c_sources,
                copts = private_copts + library["c_copts"],
                **common
            )
            common["deps"] = common["deps"] + [":" + library["name"] + "_c"]
        cc_library(
            name = library["name"],
            srcs = [p for p in library["srcs"] if p not in c_sources],
            copts = private_copts + library["copts"],
            **common
        )
    for name, original in {
        "compositor": "//cc:cc",
        "network_public_cpp": "//services/network/public/cpp:cpp",
        "private_metrics": "//components/metrics/private_metrics:private_metrics",
        "libsrtp": "//third_party/libsrtp:libsrtp",
        "confidential_compute": "//third_party/federated_compute:confidential_compute",
    }.items():
        native.alias(name = name, actual = ":" + LIBRARIES[original]["name"])
    cc_library(
        name = "webrtc_task_queue_factory",
        deps = [
            ":" + LIBRARIES["//third_party/webrtc/api/task_queue:default_task_queue_factory"]["name"],
            ":" + LIBRARIES["//third_party/webrtc_overrides:system_time"]["name"],
        ],
    )
