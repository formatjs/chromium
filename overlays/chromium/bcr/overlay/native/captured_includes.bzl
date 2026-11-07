"""Keep captured GN include lists local to their compilation units."""

load("@bazel_skylib//lib:paths.bzl", "paths")

_SETTING = Label("//native:local_captured_includes")

def captured_include_options(library, owner = None):
    """Return opt-in source/generated search paths without exporting them."""
    if not library.get("srcs", []):
        return []
    owner = owner or Label("//native:BUILD.bazel")
    options = []
    for directory in library["includes"]:
        source = paths.normalize(paths.join(owner.workspace_root, owner.package, directory))
        options.extend(["-isystem", source, "-isystem", "$(GENDIR)/" + source])
    return select({_SETTING: options, "//conditions:default": []})

def captured_copts(library, field = "copts"):
    return library.get(field, []) + captured_include_options(library)

def captured_includes(library):
    # Header-only providers still publish their include interface.
    if not library.get("srcs", []):
        return library["includes"]
    return select({_SETTING: [], "//conditions:default": library["includes"]})
