"""Pinned nested Dawn sources for native OpenGL loader generation."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_khronos_sources():
    for name, project, commit in [
        ("egl_registry", "EGL-Registry", "7dea2ed79187cd13f76183c4b9100159b9e3e071"),
        ("opengl_registry", "OpenGL-Registry", "5bae8738b23d06968e7c3a41308568120943ae77"),
    ]:
        git_repository(
            name = "chromium_" + name,
            remote = "https://chromium.googlesource.com/external/github.com/KhronosGroup/" + project,
            commit = commit,
            build_file = Label("//build:" + name + ".BUILD.bazel"),
        )
