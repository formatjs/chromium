"""Verify the executor ABI before running shared native tools."""

def _marker_impl(_ctx):
    return [platform_common.ToolchainInfo()]

native_linux_marker = rule(implementation = _marker_impl)
