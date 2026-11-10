"""Exact Blink dependency sources absent from BCR."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")
load("@bazel_tools//tools/build_defs/repo:http.bzl", "http_archive")

def chromium_blink_sources(ctx):
    http_archive(
        name = "chromium_devtools_esbuild",
        urls = ["https://chrome-infra-packages.appspot.com/dl/infra/3pp/tools/esbuild/linux-amd64/+/version:3@0.25.1.chromium.2"],
        sha256 = "520554b1c0ad045201310582a01ef7a0ba9b5d033d8f03a709c369c52f81d9c9",
        type = "zip",
        build_file_content = "exports_files([\"esbuild\"])\n",
    )
    for name, remote, commit, prefix in [
        ("cros_system_api", "https://chromium.googlesource.com/chromiumos/platform2/system_api.git", "c33ff08e2b27ddaed22c8799fefd3a4b7d3c49a9", "third_party/cros_system_api"),
        ("devtools_frontend", "https://chromium.googlesource.com/devtools/devtools-frontend", "38cfe98a56a034da33ee62a5f1ea235fe47f58a7", "third_party/devtools-frontend/src"),
        ("search_engines_data", "https://chromium.googlesource.com/external/search_engines_data.git", "94eb2a9a225078cb5f40e82fd890bce387c8121a", "third_party/search_engines_data/resources"),
        ("cld3", "https://chromium.googlesource.com/external/github.com/google/cld_3.git", "b48dc46512566f5a2d41118c8c1116c4f96dc661", "third_party/cld_3/src"),
        ("emoji_segmenter", "https://chromium.googlesource.com/external/github.com/google/emoji-segmenter.git", "955936be8b391e00835257059607d7c5b72ce744", "third_party/emoji-segmenter/src"),
        ("ots", "https://chromium.googlesource.com/external/github.com/khaledhosny/ots.git", "46bea9879127d0ff1c6601b078e2ce98e83fcd33", "third_party/ots/src"),
        ("material_color_utilities", "https://chromium.googlesource.com/external/github.com/material-foundation/material-color-utilities.git", "13434b50dcb64a482cc91191f8cf6151d90f5465", "third_party/material_color_utilities/src"),
        ("smhasher", "https://chromium.googlesource.com/external/smhasher.git", "0ff96f7835817a27d0487325b6c16033e2992eb5", "third_party/smhasher/src"),
        ("libphonenumber", "https://chromium.googlesource.com/external/libphonenumber.git", "140dfeb81b753388e8a672900fb7a971e9a0d362", "third_party/libphonenumber/dist"),
        ("crabbyavif", "https://chromium.googlesource.com/external/github.com/webmproject/CrabbyAvif.git", "3ba05863e84fd3acb4f4af2b4545221b317a2e55", "third_party/crabbyavif/src"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = remote,
            commit = commit,
            patch_cmds = ["find . -mindepth 2 -type f \\( -name BUILD -o -name BUILD.bazel \\) -delete"],
            build_file_content = """package(default_visibility = ["//visibility:public"])
exports_files(glob(["**"]))
filegroup(name = "npm_files", srcs = glob(["node_modules/**"], allow_empty = True))
""" if name in ["search_engines_data", "devtools_frontend"] else ctx.read(Label("//build:blink_sources.BUILD.bazel")).replace("@@PREFIX@@", prefix),
        )
