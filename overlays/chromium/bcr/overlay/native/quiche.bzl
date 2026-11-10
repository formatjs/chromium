"""Complete Chromium QUICHE with original platform overrides and URL library."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":quiche_sources.bzl", "COPTS", "DEFINES", "HEADERS", "SOURCES")

_PREFIX = "net/third_party/quiche/src/"
_PROTOS = [
    "quiche/quic/core/proto/" + name
    for name in ["cached_network_parameters", "crypto_server_config", "source_address_token"]
]

def native_quiche():
    native.genrule(
        name = "quic_proto_gen",
        srcs = ["@chromium_quiche//:" + _PREFIX + path + ".proto" for path in _PROTOS],
        outs = ["gen/" + _PREFIX + path + suffix for path in _PROTOS for suffix in [".pb.cc", ".pb.h"]],
        tools = [":protobuf_compiler"],
        cmd = "$(execpath :protobuf_compiler) --proto_path=$$(dirname $(location @chromium_quiche//:" + _PREFIX + _PROTOS[0] + ".proto))/../../../.. --cpp_out=$(RULEDIR)/gen/" + _PREFIX + " " + " ".join([path + ".proto" for path in _PROTOS]),
    )
    for name, dependencies in {
        "uri_template": [":base"],
        "quic_proto": [":base", ":protobuf_lite_runtime"],
        "quiche": [":base", ":url", ":uri_template", ":quic_proto", "//third_party/abseil-cpp:absl", "//third_party/boringssl", "//third_party/zlib"],
    }.items():
        cc_library(
            name = name,
            srcs = SOURCES[name],
            hdrs = HEADERS[name] + [":all_buildflags"],
            includes = ["..", "../net/third_party/quiche/overrides", "gen", "gen/" + _PREFIX],
            copts = COPTS[name],
            local_defines = DEFINES[name],
            linkstatic = True,
            deps = dependencies + (["@chromium_quiche//:headers"] if name == "quiche" else []),
        )
