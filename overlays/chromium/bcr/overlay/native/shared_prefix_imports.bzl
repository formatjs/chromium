"""Resolve shared imports only for Chromium's native compile owners."""

load(":qualified_shared_prefixes.bzl", "SHARED_PREFIX_IMPORTS")

SHARED_PREFIX_ENABLED = Label("//native/tool_configuration:shared_pch")
_REPOSITORY = Label("//native:BUILD.bazel").repo_name

def qualified_shared_imports(name):
    owner = native.package_relative_label(":" + name)
    if owner.repo_name != _REPOSITORY or owner.package != "native":
        return {}
    return SHARED_PREFIX_IMPORTS.get(name, {})

def shared_import_attributes(imports):
    labels = sorted({label: True for label in imports.values()})
    producers = {label: "shared_" + str(index) for index, label in enumerate(labels)}
    return {
        "shared_sources": {source: producers[label] for source, label in imports.items()},
        "shared_pchs": producers,
    }
