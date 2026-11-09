"""Expose locked npm runtime files at their original Chromium paths."""

load(":python_action.bzl", "ChromiumFilesInfo", "chromium_filegroup")

def _package_inputs_impl(ctx):
    suffix = "typescript/package.json"
    if not ctx.file.manifest.path.endswith(suffix):
        fail("invalid Node source archive anchor")
    root = ctx.file.manifest.path[:-len(suffix)]
    mappings = []
    packages = {package: True for package in ctx.attr.packages}
    for file in ctx.attr.src[DefaultInfo].files.to_list():
        if not file.path.startswith(root):
            fail("npm file outside package root: %s" % file.path)
        relative = file.path[len(root):]
        if packages:
            directory = ""
            selected = False
            for part in relative.split("/")[:-1]:
                directory = directory + "/" + part if directory else part
                if directory in packages:
                    selected = True
                    break
            if not selected:
                continue
        mappings.append((file, ctx.attr.logical_root + "/" + relative))
    tree = ctx.actions.declare_directory(ctx.label.name + ".node_modules")
    manifest = ctx.actions.declare_file(ctx.label.name + ".files.json")
    ctx.actions.write(manifest, json.encode([
        [file.path, logical[len(ctx.attr.logical_root) + 1:]]
        for file, logical in mappings
    ]))
    runtime = ctx.attr._python[platform_common.ToolchainInfo].py3_runtime
    ctx.actions.run(
        executable = runtime.interpreter,
        arguments = ["-I", "-B", ctx.file._copier.path, manifest.path, tree.path],
        inputs = depset([ctx.file._copier, manifest] + [file for file, _ in mappings], transitive = [runtime.files]),
        outputs = [tree],
        mnemonic = "ChromiumNpmTree",
    )
    return [
        DefaultInfo(files = depset([tree])),
        ChromiumFilesInfo(mappings = depset([(tree, ctx.attr.logical_root)]), node_symlinks = True),
    ]

_package_inputs = rule(
    implementation = _package_inputs_impl,
    attrs = {
        "src": attr.label(mandatory = True),
        "packages": attr.string_list(),
        "manifest": attr.label(allow_single_file = True, mandatory = True),
        "logical_root": attr.string(mandatory = True),
        "_copier": attr.label(default = Label("//native:npm_tree.py"), allow_single_file = True),
        "_python": attr.label(default = "@rules_python//python:current_py_toolchain", cfg = "exec"),
    },
)

def chromium_npm_inputs(name, src = "@chromium_node_modules//:files", manifest = "@chromium_node_modules//:node_modules/typescript/package.json", logical_root = "third_party/node/node_modules", packages = []):
    """Declare selected locked npm sources at their installed dependency paths.

    Args:
        name: Target collecting installed runtime packages.
        src: Locked npm source archive.
        manifest: TypeScript package anchor within the archive.
        logical_root: Original checkout path for installed packages.
        packages: Installed runtime package closure; empty includes all packages.
    """
    _package_inputs(
        name = name + "_archive",
        src = src,
        packages = packages,
        manifest = manifest,
        logical_root = logical_root,
    )
    chromium_filegroup(
        name = name,
        deps = [":" + name + "_archive"],
    )

# tools/npm_runtime_closure.py node_modules glob yargs typescript
DEVTOOLS_I18N_PACKAGES = [
    "balanced-match",
    "brace-expansion",
    "concat-map",
    "emoji-regex",
    "escalade",
    "fs.realpath",
    "get-caller-file",
    "glob",
    "inflight",
    "inherits",
    "is-fullwidth-code-point",
    "minimatch",
    "once",
    "path-is-absolute",
    "require-directory",
    "string-width",
    "string-width/node_modules/ansi-regex",
    "string-width/node_modules/strip-ansi",
    "typescript",
    "wrap-ansi",
    "wrap-ansi/node_modules/ansi-regex",
    "wrap-ansi/node_modules/ansi-styles",
    "wrap-ansi/node_modules/color-convert",
    "wrap-ansi/node_modules/color-name",
    "wrap-ansi/node_modules/strip-ansi",
    "wrappy",
    "y18n",
    "yargs",
    "yargs/node_modules/ansi-regex",
    "yargs/node_modules/cliui",
    "yargs/node_modules/strip-ansi",
    "yargs/node_modules/yargs-parser",
]

# tools/npm_runtime_closure.py node_modules glob yargs typescript @rollup/wasm-node cssnano cssnano-preset-lite postcss esbuild uuid @web/rollup-plugin-import-meta-assets svgo @rollup/plugin-terser rollup-plugin-sourcemaps2
DEVTOOLS_BUILD_PACKAGES = [
    "@jridgewell/gen-mapping",
    "@jridgewell/resolve-uri",
    "@jridgewell/set-array",
    "@jridgewell/source-map",
    "@jridgewell/sourcemap-codec",
    "@jridgewell/trace-mapping",
    "@nodelib/fs.scandir",
    "@nodelib/fs.stat",
    "@nodelib/fs.walk",
    "@rollup/plugin-dynamic-import-vars",
    "@rollup/plugin-terser",
    "@rollup/pluginutils",
    "@rollup/pluginutils/node_modules/picomatch",
    "@rollup/wasm-node",
    "@trysound/sax",
    "@types/estree",
    "@web/rollup-plugin-import-meta-assets",
    "@web/rollup-plugin-import-meta-assets/node_modules/globby",
    "@web/rollup-plugin-import-meta-assets/node_modules/slash",
    "acorn",
    "astring",
    "balanced-match",
    "boolbase",
    "brace-expansion",
    "braces",
    "browserslist",
    "buffer-from",
    "caniuse-api",
    "caniuse-lite",
    "colord",
    "commander",
    "concat-map",
    "css-declaration-sorter",
    "css-select",
    "css-tree",
    "css-what",
    "cssesc",
    "cssnano",
    "cssnano-preset-default",
    "cssnano-preset-lite",
    "cssnano-utils",
    "csso",
    "csso/node_modules/css-tree",
    "csso/node_modules/mdn-data",
    "dir-glob",
    "dom-serializer",
    "domelementtype",
    "domhandler",
    "domutils",
    "electron-to-chromium",
    "emoji-regex",
    "entities",
    "esbuild",
    "escalade",
    "estree-walker",
    "fast-glob",
    "fastq",
    "fill-range",
    "fs.realpath",
    "get-caller-file",
    "glob",
    "glob-parent",
    "ignore",
    "inflight",
    "inherits",
    "is-extglob",
    "is-fullwidth-code-point",
    "is-glob",
    "is-number",
    "lilconfig",
    "lodash.memoize",
    "lodash.uniq",
    "magic-string",
    "mdn-data",
    "merge2",
    "micromatch",
    "minimatch",
    "nanoid",
    "node-releases",
    "nth-check",
    "once",
    "path-is-absolute",
    "path-type",
    "picocolors",
    "picomatch",
    "postcss",
    "postcss-calc",
    "postcss-colormin",
    "postcss-convert-values",
    "postcss-discard-comments",
    "postcss-discard-duplicates",
    "postcss-discard-empty",
    "postcss-discard-overridden",
    "postcss-merge-longhand",
    "postcss-merge-rules",
    "postcss-minify-font-values",
    "postcss-minify-gradients",
    "postcss-minify-params",
    "postcss-minify-selectors",
    "postcss-normalize-charset",
    "postcss-normalize-display-values",
    "postcss-normalize-positions",
    "postcss-normalize-repeat-style",
    "postcss-normalize-string",
    "postcss-normalize-timing-functions",
    "postcss-normalize-unicode",
    "postcss-normalize-url",
    "postcss-normalize-whitespace",
    "postcss-ordered-values",
    "postcss-reduce-initial",
    "postcss-reduce-transforms",
    "postcss-selector-parser",
    "postcss-svgo",
    "postcss-svgo/node_modules/commander",
    "postcss-svgo/node_modules/css-tree",
    "postcss-svgo/node_modules/mdn-data",
    "postcss-svgo/node_modules/svgo",
    "postcss-unique-selectors",
    "postcss-value-parser",
    "queue-microtask",
    "randombytes",
    "require-directory",
    "reusify",
    "rollup-plugin-sourcemaps2",
    "run-parallel",
    "safe-buffer",
    "sax",
    "serialize-javascript",
    "smob",
    "source-map",
    "source-map-js",
    "source-map-support",
    "string-width",
    "string-width/node_modules/ansi-regex",
    "string-width/node_modules/strip-ansi",
    "stylehacks",
    "svgo",
    "svgo/node_modules/commander",
    "terser",
    "to-regex-range",
    "typescript",
    "update-browserslist-db",
    "util-deprecate",
    "uuid",
    "wrap-ansi",
    "wrap-ansi/node_modules/ansi-regex",
    "wrap-ansi/node_modules/ansi-styles",
    "wrap-ansi/node_modules/color-convert",
    "wrap-ansi/node_modules/color-name",
    "wrap-ansi/node_modules/strip-ansi",
    "wrappy",
    "y18n",
    "yargs",
    "yargs/node_modules/ansi-regex",
    "yargs/node_modules/cliui",
    "yargs/node_modules/strip-ansi",
    "yargs/node_modules/yargs-parser",
]
