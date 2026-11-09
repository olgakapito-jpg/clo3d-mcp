"""Show the modeless Start/Stop panel inside CLO; never starts a server on open.

If Script Editor omits __file__, set ROOT to the project directory locally.
Close hides the panel, not the server. Run again to show the same window.
"""

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
    if not (root / "plugin/clo3d_mcp_start.py").is_file():
        raise RuntimeError("Expected project plugin directory")
    registry = getattr(builtins, "_clo3d_mcp_panel", None)
    if registry is not None:
        if registry.get("version") != 1 or registry.get("root") != str(root):
            raise RuntimeError("Panel belongs to another version/project; restart CLO")
        registry["panel"].show()
        return

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    timer_module = load("clo_mcp_panel_thread_check", root / "plugin/clo3d_mcp_probe.py")
    timer = timer_module.WindowsTimer()
    if timer.visible_window_threads() != {timer.thread_id()}:
        raise RuntimeError("Panel must run on the verified CLO UI thread")
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from clo3d_mcp.control_panel import PanelController, WindowsPanel

    def start_server():
        launcher = load("clo_mcp_panel_launcher", root / "plugin/clo3d_mcp_start.py")
        launcher.ROOT = str(root)
        launcher.main()  # propagates failure to panel; never import legacy listener

    controller = PanelController(lambda: getattr(builtins, "_clo3d_mcp_service", None),
                                 start_server, timer.thread_id)
    panel = WindowsPanel(controller)
    # Retain BEFORE native registration: failure/queued messages must not free WNDPROC.
    builtins._clo3d_mcp_panel = {"version": 1, "root": str(root), "panel": panel}
    panel.create()
    panel.show()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO MCP] PANEL_FAILED %s; check ROOT/UI thread or restart CLO" % type(exc).__name__)
