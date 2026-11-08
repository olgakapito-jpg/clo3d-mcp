"""Stop/report only the MCP child owned by this CLO interpreter."""


def main():
    import builtins

    registry = getattr(builtins, "_clo3d_mcp_service", None)
    if registry is None:
        print("[CLO MCP] No server in this interpreter")
        return
    if registry.get("version") != 1:
        raise RuntimeError("Unknown MCP registry; references left untouched")
    current = registry.get("current")
    if current is not None:
        current.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO MCP] STOP_FAILED %s" % type(exc).__name__)
