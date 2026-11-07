"""Exact browser dependency sources absent from BCR."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "new_git_repository")

def chromium_browser_sources(ctx):
    for name, remote, commit, prefix in [
        ("catapult", "https://chromium.googlesource.com/catapult.git", "04c85a1d0e324464c6be4b3d193b47cb6177d03a", "third_party/catapult"),
        ("openscreen", "https://chromium.googlesource.com/openscreen", "4654d7968ac1a1e825a84bd4d85acadd7993c49a", "third_party/openscreen/src"),
        ("pdfium", "https://pdfium.googlesource.com/pdfium.git", "e95c6ead2f97716c98526ec42d5fd9ebb50e6e23", "third_party/pdfium"),
        ("anonymous_tokens", "https://chromium.googlesource.com/external/github.com/google/anonymous-tokens.git", "50e04fb27eacd49a5e2bfde5977ac689e13ebeeb", "third_party/anonymous_tokens/src"),
        ("content_analysis_sdk", "https://chromium.googlesource.com/external/github.com/chromium/content_analysis_sdk.git", "9a408736204513e0e95dd2ab3c08de0d95963efc", "third_party/content_analysis_sdk/src"),
        ("dom_distiller_js", "https://chromium.googlesource.com/chromium/dom-distiller/dist.git", "199de96b345ada7c6e7e6ba3d2fa7a6911b8767d", "third_party/dom_distiller_js/dist"),
        ("readability", "https://chromium.googlesource.com/external/github.com/mozilla/readability.git", "1f0ec42686c89a4a1c71789849f7ffde349ab197", "third_party/readability/src"),
        ("ink", "https://chromium.googlesource.com/external/github.com/google/ink.git", "4e6081ad7052f97df7d77e1d87cea2d70c18a47b", "third_party/ink/src"),
        ("ink_stroke_modeler", "https://chromium.googlesource.com/external/github.com/google/ink-stroke-modeler.git", "fe79520c9ad7d2d445d26d3c59fda6fc54eb4d5c", "third_party/ink_stroke_modeler/src"),
        ("libaddressinput", "https://chromium.googlesource.com/external/libaddressinput.git", "2610f7b1043d6784ada41392fc9392d1ea09ea07", "third_party/libaddressinput/src"),
        ("xdg_utils", "https://chromium.googlesource.com/chromium/deps/xdg-utils.git", "cb54d9db2e535ee4ef13cc91b65a1e2741a94a44", "third_party/xdg-utils"),
    ]:
        new_git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            patch_cmds = ["find . -mindepth 2 -type f \\( -name BUILD -o -name BUILD.bazel \\) -delete"] + (["rm -rf third_party/protobuf"] if name == "openscreen" else []),
            build_file_content = ctx.read(Label("//build:browser_sources.BUILD.bazel")).replace("@@PREFIX@@", prefix).replace("@@HEADER_EXCLUDES@@", str(["third_party/protobuf/**"] if name == "openscreen" else [])),
        )
