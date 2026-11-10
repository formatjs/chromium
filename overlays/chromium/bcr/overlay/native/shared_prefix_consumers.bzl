"""Keep ordinary C++ interfaces while importing qualified shared prefixes."""

load("@rules_cc//cc:cc_binary.bzl", original_cc_binary = "cc_binary")
load("@rules_cc//cc:cc_library.bzl", original_cc_library = "cc_library")
load(":project_pch.bzl", "chromium_pch_compile")
load(":shared_prefix_imports.bzl", "SHARED_PREFIX_ENABLED", "qualified_shared_imports", "shared_import_attributes")

_ENABLED = SHARED_PREFIX_ENABLED
_LINUX = ["@platforms//os:linux", "@platforms//cpu:x86_64", "@llvm//constraints/libc:gnu.2.31"]

# Header checks retain the owner's compiler options and private definitions.
_CONTEXT_ATTRIBUTES = ["copts", "defines", "features", "includes", "local_defines", "testonly", "target_compatible_with"]

def _filename(source):
    return str(source).rsplit(":", 1)[-1].rsplit("/", 1)[-1]

def _object_order(sources):
    names = [_filename(source).rsplit(".", 1)[0] + ".pic.o" for source in sources]
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    seen = {}
    result = []
    for name in names:
        if counts[name] > 1:
            result.append(str(seen.get(name, 0)) + "/" + name)
            seen[name] = seen.get(name, 0) + 1
        else:
            result.append(name)
    return result

def _replacement(name, imports, binary, common):
    if not binary and common.get("linkstatic") != True:
        return None
    sources = common.get("srcs", [])
    if type(sources) != "list" or common.get("nocopts"):
        return None
    cpp = [source for source in sources if _filename(source).endswith((".cc", ".cpp", ".cxx"))]
    headers = [source for source in sources if _filename(source).endswith((".h", ".hh", ".hpp", ".inc"))]
    if not cpp or len(cpp) + len(headers) != len(sources):
        return None
    context = name + "_shared_context"
    attributes = {key: common[key] for key in _CONTEXT_ATTRIBUTES if key in common}
    original_cc_library(
        name = context,
        hdrs = common.get("hdrs", []) + headers,
        deps = common.get("deps", []) + common.get("implementation_deps", []),
        linkstatic = True,
        tags = ["manual"],
        **attributes
    )
    shared = shared_import_attributes(imports)
    replacement = name + "_shared_pch"
    chromium_pch_compile(
        name = replacement,
        sources = {source: "" for source in cpp},
        object_suffixes = {"": ""},
        object_order = _object_order(cpp),
        shared_sources = shared["shared_sources"],
        shared_pchs = shared["shared_pchs"],
        context = ":" + context,
        expose_context = False,
        alwayslink = True if binary else common.get("alwayslink", False),
        copts = common.get("copts", []),
        local_defines = common.get("local_defines", []),
        extra_inputs = common.get("additional_compiler_inputs", []),
        features = common.get("features", []),
        testonly = common.get("testonly", False),
        target_compatible_with = common.get("target_compatible_with", []) + _LINUX,
        tags = ["manual"],
    )
    return replacement, headers

def _consume(name, imports, binary, common):
    original = original_cc_binary if binary else original_cc_library
    if imports == None:
        imports = qualified_shared_imports(name)
    if not imports:
        original(name = name, **common)
        return
    result = _replacement(name, imports, binary, common)
    if result:
        replacement, headers = result
        common["srcs"] = select({_ENABLED: headers, "//conditions:default": common["srcs"]})
        common["deps"] = select({_ENABLED: [":" + replacement], "//conditions:default": []}) + common.get("deps", [])
    original(name = name, **common)

def shared_prefix_library(name, imports = None, **kwargs):
    """Import qualified PCHs into static libraries without exposing private dependencies."""
    _consume(name, imports, False, kwargs)

def shared_prefix_binary(name, imports = None, **kwargs):
    """Keep every original binary object when linking replacement source groups."""
    _consume(name, imports, True, kwargs)
