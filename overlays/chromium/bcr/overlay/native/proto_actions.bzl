"""Native Variations protocol generation; run tools/import_proto_actions.py."""

load(":shared_prefix_consumers.bzl", cc_library = "shared_prefix_library")
load(":protobuf_config.bzl", "chromium_protobuf_library", "chromium_protoc")
load(":python_action.bzl", "chromium_python_action")
load(":tool_inputs.bzl", "chromium_tool_inputs")

def native_variations_proto(name):
    """Generate and compile original Chromium Variations schemas.

    Args:
        name: C++ protocol library target.
    """
    chromium_protoc(
        name = "protobuf_compiler",
        tool = "@protobuf//:protoc",
    )
    chromium_protobuf_library(
        name = "protobuf_lite_runtime",
        dep = "@protobuf//:protobuf_lite",
    )
    chromium_tool_inputs(
        name = "protoc_tool",
        tool = ":protobuf_compiler",
        allow_native_sharing = False,
        logical_path = "out/bazel-import/protoc",
    )
    chromium_python_action(
        name = "variations_proto_gen",
        srcs = {"//:components/variations/proto/layer.proto": "components/variations/proto/layer.proto", "//:components/variations/proto/stored_seed_info.proto": "components/variations/proto/stored_seed_info.proto", "//:components/variations/proto/study.proto": "components/variations/proto/study.proto", "//:components/variations/proto/variations_seed.proto": "components/variations/proto/variations_seed.proto", ":protoc_tool": "out/bazel-import/protoc", "@protobuf//:descriptor_proto_srcs": "third_party/protobuf/src/google/protobuf/descriptor.proto", "//:tools/protoc_wrapper/protoc_wrapper.py": "tools/protoc_wrapper/protoc_wrapper.py"},
        outs = {"gen/components/variations/proto/layer.pb.h": "gen/components/variations/proto/layer.pb.h", "gen/components/variations/proto/layer.pb.cc": "gen/components/variations/proto/layer.pb.cc", "gen/components/variations/proto/stored_seed_info.pb.h": "gen/components/variations/proto/stored_seed_info.pb.h", "gen/components/variations/proto/stored_seed_info.pb.cc": "gen/components/variations/proto/stored_seed_info.pb.cc", "gen/components/variations/proto/study.pb.h": "gen/components/variations/proto/study.pb.h", "gen/components/variations/proto/study.pb.cc": "gen/components/variations/proto/study.pb.cc", "gen/components/variations/proto/variations_seed.pb.h": "gen/components/variations/proto/variations_seed.pb.h", "gen/components/variations/proto/variations_seed.pb.cc": "gen/components/variations/proto/variations_seed.pb.cc", "pyproto/components/variations/proto/layer_pb2.py": "pyproto/components/variations/proto/layer_pb2.py", "pyproto/components/variations/proto/stored_seed_info_pb2.py": "pyproto/components/variations/proto/stored_seed_info_pb2.py", "pyproto/components/variations/proto/study_pb2.py": "pyproto/components/variations/proto/study_pb2.py", "pyproto/components/variations/proto/variations_seed_pb2.py": "pyproto/components/variations/proto/variations_seed_pb2.py"},
        script = "tools/protoc_wrapper/protoc_wrapper.py",
        args = ["layer.proto", "stored_seed_info.proto", "study.proto", "variations_seed.proto", "--protoc", "./protoc", "--proto-in-dir", "../../components/variations/proto", "--fatal_warnings", "--cc-out-dir", "gen/components/variations/proto", "--py-out-dir", "pyproto/components/variations/proto", "--import-dir=../../third_party/protobuf/src"],
        deps = [":protoc_tool"],
    )
    cc_library(
        name = name,
        srcs = [":gen/components/variations/proto/layer.pb.cc", ":gen/components/variations/proto/stored_seed_info.pb.cc", ":gen/components/variations/proto/study.pb.cc", ":gen/components/variations/proto/variations_seed.pb.cc"],
        hdrs = [":gen/components/variations/proto/layer.pb.h", ":gen/components/variations/proto/stored_seed_info.pb.h", ":gen/components/variations/proto/study.pb.h", ":gen/components/variations/proto/variations_seed.pb.h"],
        includes = ["gen/components/variations/proto", "gen"],
        copts = ["-std=c++20"],
        deps = [":protobuf_lite_runtime"],
    )
