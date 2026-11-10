"""Chromium's pinned Wayland protocol XML inputs."""

load("@bazel_tools//tools/build_defs/repo:git.bzl", "git_repository")

def chromium_wayland_protocol_sources():
    for name, remote, commit in [
        ("chromium_wayland_protocols", "external/anongit.freedesktop.org/git/wayland/wayland-protocols.git", "efbc060534be948b63e1f395d69b583eebba3235"),
        ("chromium_kde_protocols", "external/github.com/KDE/plasma-wayland-protocols.git", "0b07950714b3a36c9b9f71fc025fc7783e82926e"),
    ]:
        git_repository(
            name = name,
            remote = "https://chromium.googlesource.com/" + remote,
            commit = commit,
            build_file = Label("//build:wayland_protocols.BUILD.bazel"),
        )
