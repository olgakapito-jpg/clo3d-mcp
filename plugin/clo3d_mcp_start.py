"""Start one CLO-bound official MCP HTTP server. See docs/P3_MCP_CHECK.md."""

ROOT = None


def main():
    import builtins
    import importlib.util
    from pathlib import Path
    import sys

    if ROOT:
        root = Path(ROOT).resolve()
    elif globals().get("__file__"):
        root = Path(__file__).resolve().parent.parent
    else:
        raise RuntimeError("CLO omitted __file__; set ROOT to the project directory")
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file() or not (root / "src" / "clo3d_mcp" / "transport_server.py").is_file():
        raise RuntimeError("Expected project src, plugin and prepared Windows .venv")
    for name in ("p0", "p1", "p2"):
        other = getattr(builtins, "_clo3d_mcp_" + name, {}).get("current")
        if other is not None and (other.timer_id is not None or other.busy):
            raise RuntimeError("Stop active probes before starting MCP")
    registry = getattr(builtins, "_clo3d_mcp_service", None)
    if registry is None:
        registry = {"version": 1, "retained": []}
        builtins._clo3d_mcp_service = registry
    if registry.get("version") != 1:
        raise RuntimeError("Unknown MCP registry; restart CLO")
    current = registry.get("current")
    if current is not None and current.state not in ("stopped", "failed"):
        current.emit("ALREADY_STARTED")
        return
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    spec = importlib.util.spec_from_file_location("clo_mcp_timer_adapter", root / "plugin" / "clo3d_mcp_probe.py")
    timer_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(timer_module)
    import pattern_api
    import export_api
    import fabric_api
    import import_api
    import utility_api
    from clo3d_mcp.pattern_api import PatternAPI
    from clo3d_mcp.pipe_runtime import start

    def create_rectangle():
        # Same CreatePatternWithPoints conversion as the preserved legacy handler,
        # without importing it (its module can auto-start a file listener).
        before = pattern_api.GetPatternCount()
        points = [(0.0, 0.0, 0), (100.0, 0.0, 0), (100.0, 100.0, 0), (0.0, 100.0, 0)]
        pattern_api.CreatePatternWithPoints(points)
        after = pattern_api.GetPatternCount()
        if type(after) is not int or after != before + 1:
            raise RuntimeError("Diagnostic pattern creation could not be verified; do not retry")
        return {"created": True, "pattern_count": after}

    start(registry, timer_module.WindowsTimer(), pattern_api.GetPatternCount,
          python, root, profile="service", create_rectangle=create_rectangle,
          command_handler=PatternAPI({"pattern_api": pattern_api, "export_api": export_api,
                                      "fabric_api": fabric_api, "import_api": import_api,
                                      "utility_api": utility_api}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO MCP] NOT_STARTED %s: %s" % (type(exc).__name__, exc))
