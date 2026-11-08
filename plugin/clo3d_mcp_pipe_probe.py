"""P1 launcher: read-only two-round pipe test, no MCP. See docs/P1_PIPE_CHECK.md."""

# Only if CLO omits __file__, set ROOT to this project's absolute directory.
# Do not use CLO's arbitrary working directory as a source path.
ROOT = None


def main(profile="p1"):
    import builtins
    import importlib.util
    from pathlib import Path
    import sys

    if profile not in ("p1", "p2"):
        raise RuntimeError("Unknown diagnostic profile")

    if ROOT:
        root = Path(ROOT).resolve()
    elif globals().get("__file__"):
        root = Path(__file__).resolve().parent.parent
    else:
        raise RuntimeError("CLO omitted __file__; set ROOT at top of this launcher to project directory")
    source = root / "src"
    probe_path = root / "plugin" / "clo3d_mcp_probe.py"
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file() or not probe_path.is_file() or not (source / "clo3d_mcp" / "pipe_runtime.py").is_file():
        raise RuntimeError("ROOT must contain plugin, src and prepared .venv/Scripts/python.exe")
    p0 = getattr(builtins, "_clo3d_mcp_p0", {}).get("current")
    if p0 is not None and (p0.timer_id is not None or p0.busy):
        raise RuntimeError("Stop P0 first with clo3d_mcp_probe_stop.py")
    for other_profile in ("p1", "p2", "service"):
        if other_profile == profile:
            continue
        other = getattr(builtins, "_clo3d_mcp_" + other_profile, {}).get("current")
        if other is not None and (other.timer_id is not None or other.busy
                                  or (other.process is not None and other.process.poll() is None)):
            raise RuntimeError("Stop the other pipe diagnostic before starting this one")
    registry_name = "_clo3d_mcp_" + profile
    registry = getattr(builtins, registry_name, None)
    if registry is None:
        registry = {"version": 1, "retained": []}
        setattr(builtins, registry_name, registry)
    if registry.get("version") != 1:
        raise RuntimeError("Unknown P1 registry; restart CLO")
    current = registry.get("current")
    if current is not None and current.state not in ("stopped", "failed"):
        current.emit("ALREADY_STARTED")
        return
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    # Load P0's tested native timer adapter WITHOUT its main/auto-start.
    spec = importlib.util.spec_from_file_location("clo_p1_timer_adapter", probe_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pattern_api
    from clo3d_mcp.pipe_runtime import start
    start(registry, module.WindowsTimer(), pattern_api.GetPatternCount, python, root, profile=profile)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P1] NOT_STARTED %s: %s" % (type(exc).__name__, exc))
