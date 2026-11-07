"""Stable source fetch and overlay projection rules."""

def _archive_impl(ctx):
    root = ctx.path(ctx.attr.catalog).dirname
    base = root.get_child("overlays/" + ctx.attr.overlay + "/bcr")
    source = json.decode(ctx.read(base.get_child("source.json")))
    ctx.download_and_extract(
        url = source["url"],
        integrity = source["integrity"],
        stripPrefix = source.get("strip_prefix", ""),
    )
    patches = base.get_child("patches")
    if patches.exists:
        ctx.watch_tree(patches)
        for patch in sorted(patches.readdir(), key = str):
            if not patch.is_dir:
                ctx.patch(patch, strip = source.get("patch_strip", 1))
    ctx.file("__source__/BUILD.bazel", 'exports_files(["anchor"])\n')
    ctx.file("__source__/anchor", ctx.attr.overlay)

_archive = repository_rule(
    implementation = _archive_impl,
    attrs = {
        "catalog": attr.label(mandatory = True),
        "overlay": attr.string(mandatory = True),
    },
)

def _sources_impl(ctx):
    root = ctx.path(ctx.attr.catalog).dirname
    overlay = root.get_child("overlays/" + ctx.attr.overlay + "/bcr/overlay")
    files = {}
    directories = {"": True}
    excluded = {relative: True for relative in ctx.attr.exclude_paths}
    for relative in excluded:
        parts = relative.split("/")
        if not relative or relative.startswith("/") or ".." in parts:
            fail("Invalid excluded source path: " + relative)
        for depth in range(1, len(parts)):
            directories["/".join(parts[:depth])] = True
    layers = [overlay]
    if ctx.attr.variant:
        layers.append(root.get_child("overlays/" + ctx.attr.overlay + "/platforms/" + ctx.attr.variant + "/overlay"))
    for layer in layers:
        ctx.watch_tree(layer)
        pending = [(layer, "")]
        for _ in range(32):
            next_level = []
            for directory, prefix in pending:
                for path in sorted(directory.readdir(), key = str):
                    relative = prefix + path.basename
                    if path.is_dir:
                        directories[relative] = True
                        next_level.append((path, relative + "/"))
                    else:
                        files[relative] = path
            pending = next_level
            if not pending:
                break
        if pending:
            fail("Overlay exceeds supported directory depth: " + str(layer))

    # Split only directories containing overrides; symlink unchanged source trees.
    # Rule edits then avoid extracting Chromium's archive again.
    source = ctx.path(ctx.attr.archive).dirname.dirname
    patched_files = {}
    for patch in ctx.attr.patches:
        lines = ctx.read(patch).splitlines()
        before = [line[6:].split("\t")[0] for line in lines if line.startswith("--- a/")]
        after = [line[6:].split("\t")[0] for line in lines if line.startswith("+++ b/")]
        if not after or before != after:
            fail("Source patches must modify existing a/ and b/ paths: " + str(patch))
        for relative in after:
            parts = relative.split("/")
            if not relative or relative.startswith("/") or ".." in parts:
                fail("Invalid patched source path: " + relative)
            patched_files[relative] = True
            if relative not in files:
                files[relative] = source.get_child(relative)
            for depth in range(1, len(parts)):
                directories["/".join(parts[:depth])] = True
    pending = [(source, "")]
    for _ in range(32):
        next_level = []
        for directory, prefix in pending:
            for path in sorted(directory.readdir(), key = str):
                relative = prefix + path.basename
                if relative in excluded:
                    continue
                if path.is_dir and relative in directories:
                    next_level.append((path, relative + "/"))
                elif relative not in files:
                    ctx.symlink(path, relative)
        pending = next_level
        if not pending:
            break
    if pending:
        fail("Source exceeds supported directory depth: " + ctx.attr.overlay)
    for relative, path in files.items():
        if relative in patched_files:
            ctx.file(relative, ctx.read(path), executable = False)
        else:
            ctx.symlink(path, relative)
    for patch in ctx.attr.patches:
        ctx.patch(ctx.path(patch), strip = 1)

_sources = repository_rule(
    implementation = _sources_impl,
    attrs = {
        "archive": attr.label(mandatory = True),
        "catalog": attr.label(mandatory = True),
        "overlay": attr.string(mandatory = True),
        "patches": attr.label_list(allow_files = [".patch"]),
        "variant": attr.string(),
        "exclude_paths": attr.string_list(),
    },
)

def _quiche_impl(ctx):
    prefix = "net/third_party/quiche/src"
    ctx.download_and_extract(
        url = "https://github.com/google/quiche/archive/c0df0d316bd7e4ddf44e5ba094b5c5b061d94b0c.tar.gz",
        sha256 = "23e9c360d3a42e8d9cd006e0fcafebe9387e9f72bd722d5a0d0ba92ca349b110",
        stripPrefix = "quiche-c0df0d316bd7e4ddf44e5ba094b5c5b061d94b0c",
        output = prefix,
    )
    for path in ["BUILD.bazel", "build/BUILD.bazel", "quiche/BUILD.bazel"]:
        ctx.delete(prefix + "/" + path)
    root = ctx.path(ctx.attr.catalog).dirname
    ctx.symlink(root.get_child("overlays/chromium/bcr/overlay/native/quiche_repository.BUILD.bazel"), "BUILD.bazel")

_quiche = repository_rule(
    implementation = _quiche_impl,
    attrs = {"catalog": attr.label(mandatory = True)},
)

chromium_overlay_archive = _archive
chromium_overlay_repository = _sources
chromium_quiche_repository = _quiche

def _dawn_impl(ctx):
    prefix = "third_party/dawn"
    ctx.download_and_extract(
        url = "https://github.com/google/dawn/archive/cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920.tar.gz",
        sha256 = "604b16af14b41e2485df4d9e65f749d649e5c25729a1de43569b41e63249a16e",
        stripPrefix = "dawn-cee9cb0d67e749bf42f5e90cb3b8a6f525dbb920",
        output = prefix,
    )
    root = ctx.path(ctx.attr.catalog).dirname
    ctx.patch(root.get_child("build/dawn-dxc-version-include.patch"), strip = 1)
    for package in json.decode(ctx.read(root.get_child("build/dawn_packages.json"))):
        ctx.delete(prefix + "/" + package)
    ctx.symlink(root.get_child("build/dawn.BUILD.bazel"), "BUILD.bazel")

chromium_dawn_repository = repository_rule(
    implementation = _dawn_impl,
    attrs = {"catalog": attr.label(mandatory = True)},
)
