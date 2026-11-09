"""Show the CLO-native Start/Stop dock panel; never starts a server on open.

Uses gui_api (documented main-thread callbacks, window survives the script).
If Script Editor omits __file__, set ROOT to the project directory locally.
Closing the window does not stop the server; run this file again to show it.
"""

ROOT = None


def main():
    import builtins
    import importlib
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

    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    # Panel code may have been edited since the last Run; drop only its module.
    sys.modules.pop("clo3d_mcp.control_panel", None)
    importlib.invalidate_caches()
    import gui_api
    from clo3d_mcp.control_panel import GuiPanel, PanelController

    def start_server():
        launcher = load("clo_mcp_panel_launcher", root / "plugin/clo3d_mcp_start.py")
        launcher.ROOT = str(root)
        launcher.main()  # propagates failure to panel; never import legacy listener

    controller = PanelController(lambda: getattr(builtins, "_clo3d_mcp_service", None),
                                 start_server)
    panel = GuiPanel(gui_api, controller)
    # Retain BEFORE native registration: callbacks must not be freed by GC.
    builtins._clo3d_mcp_panel = {"version": 1, "root": str(root), "panel": panel}
    panel.create()
    panel.show()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO MCP] PANEL_FAILED %s; check gui_api/ROOT or restart CLO" % type(exc).__name__)
