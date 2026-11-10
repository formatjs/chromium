"""Cache deterministic browser archives alongside their declared bundle inputs."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")

def _compression_resources(os, inputs):
    return {"cpu": 16, "memory": 256}

def _archive_impl(ctx):
    bundle = ctx.attr.bundle[DefaultInfo].files.to_list()
    if len(bundle) != 1 or not bundle[0].is_directory:
        fail("expected one browser bundle directory")
    revision = ctx.attr._revision[BuildSettingInfo].value
    if len(revision) != 40 or any([character not in "0123456789abcdef" for character in revision.elems()]):
        fail("set --//tools/ci:revision to the full source commit SHA")
    archive = ctx.actions.declare_file(ctx.label.name + "/chromium-" + ctx.attr.platform + ".tar.gz")
    checksum = ctx.actions.declare_file(archive.basename + ".sha256", sibling = archive)
    payload = ctx.actions.declare_file(ctx.label.name + "/bundle.tar.gz")
    runtime = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    compression_arguments = []
    compression_tools = []
    compression_options = {}
    if ctx.attr.compressor:
        compression_arguments = ["--compressor", ctx.executable.compressor.path]
        compression_tools = [ctx.attr.compressor[DefaultInfo].files_to_run]
        compression_options["resource_set"] = _compression_resources
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = [
            "-I",
            "-B",
            ctx.file._script.path,
            "package-payload",
            "--bundle",
            bundle[0].path,
            "--payload",
            payload.path,
            "--platform",
            ctx.attr.platform,
        ] + compression_arguments,
        inputs = depset(bundle + [ctx.file._script, ctx.file._configuration], transitive = [runtime.files]),
        tools = compression_tools,
        outputs = [payload],
        mnemonic = "ChromiumPayloadArchive",
        progress_message = "Compressing Chromium %s" % ctx.attr.platform,
        **compression_options
    )
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = [
            "-I",
            "-B",
            ctx.file._script.path,
            "stamp-payload",
            "--payload",
            payload.path,
            "--directory",
            archive.dirname,
            "--platform",
            ctx.attr.platform,
            "--revision",
            revision,
        ],
        inputs = depset([payload, ctx.file._script, ctx.file._configuration], transitive = [runtime.files]),
        outputs = [archive, checksum],
        mnemonic = "ChromiumArchive",
        progress_message = "Packaging Chromium %s" % ctx.attr.platform,
    )
    return [DefaultInfo(files = depset([archive, checksum]))]

chromium_archive = rule(
    implementation = _archive_impl,
    attrs = {
        "bundle": attr.label(mandatory = True),
        "platform": attr.string(mandatory = True),
        "compressor": attr.label(executable = True, cfg = "exec"),
        "_revision": attr.label(default = Label("//tools/ci:revision")),
        "_python": attr.label(default = Label("@rules_python//python:current_py_toolchain"), cfg = "exec"),
        "_script": attr.label(default = Label("//tools/ci:chromium.py"), allow_single_file = True),
        "_configuration": attr.label(default = Label("//tools/ci:platforms.json"), allow_single_file = True),
    },
)
