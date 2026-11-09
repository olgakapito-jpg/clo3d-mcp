"""Panel contracts and isolated native controls, never real CLO or HTTP."""

import ast
import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import os
import subprocess
import sys

import pytest

from clo3d_mcp.control_panel import GuiPanel, PanelController


ROOT = Path(__file__).resolve().parents[1]


def runtime(state="active", **changes):
    values = dict(state=state, busy=False, timer_id=1, pipe=object(), generation=1,
                  service_ready=True, error=None)
    if state in ("stopped", "failed"):
        values.update(timer_id=None, pipe=None, service_ready=False)
    values.update(changes)
    return SimpleNamespace(**values)


def test_open_and_status_never_start_server():
    calls = []
    controller = PanelController(lambda: None, lambda: calls.append("start"), lambda: 11)
    assert controller.status() == ("Состояние: Остановлен", True, False)
    assert calls == []
    controller.act("start")
    assert calls == ["start"]


@pytest.mark.parametrize("state", ["new", "starting", "connecting", "active", "reconnecting"])
def test_start_disabled_until_terminal_and_clean(state):
    calls = []
    current = runtime(state)
    controller = PanelController(lambda: {"version": 1, "current": current},
                                 lambda: calls.append("start"), lambda: 11)
    assert controller.status()[1:] == (False, True)
    controller.act("start")
    assert calls == []


@pytest.mark.parametrize("state", ["requesting_stop", "stopping", "draining_stop"])
def test_never_restart_during_async_cleanup(state):
    current = runtime(state)
    controller = PanelController(lambda: {"version": 1, "current": current},
                                 lambda: pytest.fail("start"), lambda: 11)
    assert controller.status()[1:] == (False, False)
    controller.act("start")
    controller.act("stop")


def test_stop_then_start_requires_completed_cleanup():
    calls = []
    current = runtime()
    current.stop = lambda: (calls.append("stop"), setattr(current, "state", "requesting_stop"))
    registry = {"version": 1, "current": current, "retained": [current]}
    controller = PanelController(lambda: registry, lambda: calls.append("start"), lambda: 11)
    controller.act("stop")
    controller.act("start")
    assert calls == ["stop"]
    current.state = "stopped"
    assert not controller.status()[1]  # remaining handles
    current.timer_id = current.pipe = None
    assert controller.status()[1:] == (True, False)
    controller.act("start")
    assert calls == ["stop", "start"]


def test_failed_cleanup_can_be_stopped_again_but_not_restarted():
    current = runtime("failed", timer_id=1)
    calls = []
    current.stop = lambda: calls.append("stop")
    controller = PanelController(lambda: {"version": 1, "current": current},
                                 lambda: pytest.fail("start"), lambda: 11)
    assert controller.status()[1:] == (False, True)
    controller.act("stop")
    assert calls == ["stop"]


def test_unknown_registry_fails_closed_and_retained_generations_do_not_block_start():
    controller = PanelController(lambda: {"version": 2}, lambda: pytest.fail("start"), lambda: 11)
    assert controller.status()[1:] == (False, False)
    controller.act("start")

    calls = []
    registry = {"version": 1, "retained": [None] * 40}
    controller = PanelController(lambda: registry, lambda: calls.append("start"), lambda: 11)
    assert controller.status() == ("Состояние: Остановлен", True, False)
    controller.act("start")
    assert calls == ["start"]


def test_reentrant_or_executing_buttons_do_nothing():
    current = runtime(busy=True)
    controller = PanelController(lambda: {"version": 1, "current": current},
                                 lambda: pytest.fail("start"), lambda: 11)
    assert controller.status()[1:] == (False, False)
    calls = []

    def start():
        calls.append("start")
        controller.act("start")

    controller = PanelController(lambda: None, start, lambda: 11)
    controller.act("start")
    assert calls == ["start"]


def test_wrong_thread_rejected_before_actions():
    thread = [11]
    controller = PanelController(lambda: pytest.fail("read"), lambda: pytest.fail("start"), lambda: thread[0])
    thread[0] = 12
    with pytest.raises(RuntimeError, match="thread"):
        controller.act("start")


def test_action_exception_does_not_escape_or_expose_private_text():
    def start():
        raise RuntimeError("private path and token")

    controller = PanelController(lambda: None, start, lambda: 11)
    controller.act("start")
    text, enabled, _ = controller.status()
    assert "RuntimeError" in text and "private" not in text and enabled
    with pytest.raises(ValueError):
        controller.act("restart")


def test_existing_panel_reused_without_loading_native_modules(monkeypatch):
    spec = importlib.util.spec_from_file_location("test_panel_launcher", ROOT / "plugin/clo3d_mcp_panel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    panel = SimpleNamespace(show=lambda: calls.append("show"), report=lambda: "fake")
    monkeypatch.setattr(builtins, "_clo3d_mcp_panel",
                        {"version": 1, "root": str(ROOT), "panel": panel}, raising=False)
    module.main()
    module.main()
    assert calls == ["show", "show"]


class FakeGui:
    """Minimal gui_api double; records handles/callbacks, never a real window."""

    def __init__(self, available=True, dock=True, tool=True, widgets=True, show=True):
        self.available, self.dock, self.tool = available, dock, tool
        self.widgets, self.show_result = widgets, show
        self.calls, self.buttons, self.texts, self.enabled = [], {}, {}, {}
        self.close_callback = None
        self._next = 100

    def _handle(self):
        self._next += 1
        return self._next

    def IsGuiAvailable(self):
        self.calls.append("available")
        return self.available

    def CreateDockPanel(self, title, side, name):
        self.calls.append(("dock", title, side, name))
        return self._handle() if self.dock else 0

    def CreateToolWindow(self, title, width, height):
        self.calls.append(("tool", title, width, height))
        return self._handle() if self.tool else 0

    def AddLabel(self, parent, text):
        handle = self._handle() if self.widgets else 0
        if handle:
            self.texts[handle] = text
        return handle

    def AddButton(self, parent, text, callback):
        handle = self._handle() if self.widgets else 0
        if handle:
            self.buttons[text] = callback
        return handle

    def SetWindowCloseCallback(self, window, callback):
        self.close_callback = callback
        return True

    def ShowWindow(self, window):
        self.calls.append(("show", window))
        return self.show_result

    def SetWidgetText(self, handle, text):
        self.texts[handle] = text
        return True

    def SetWidgetEnabled(self, handle, enabled):
        self.enabled[handle] = enabled
        return True


def test_gui_panel_uses_dock_panel_wires_buttons_and_never_autostarts():
    gui, calls = FakeGui(), []
    controller = PanelController(lambda: None, lambda: calls.append("start"))
    panel = GuiPanel(gui, controller)
    panel.create()
    panel.show()
    assert ("dock", "CLO MCP", "right", "clo_mcp_controller") in gui.calls
    assert set(gui.buttons) == {"Старт", "Стоп", "Обновить"}
    assert gui.close_callback is not None
    assert "Остановлен" in gui.texts[panel.status]
    assert calls == []
    assert gui.calls[-1][0] == "show"


def test_gui_panel_start_and_stop_buttons_call_controller_once():
    calls = []
    gui = FakeGui()
    controller = PanelController(lambda: None, lambda: calls.append("start"))
    panel = GuiPanel(gui, controller)
    panel.create()
    gui.buttons["Старт"]()
    assert calls == ["start"]

    current = runtime()
    current.stop = lambda: (calls.append("stop"), setattr(current, "state", "requesting_stop"))
    registry = {"version": 1, "current": current, "retained": [current]}
    gui = FakeGui()
    controller = PanelController(lambda: registry, lambda: None)
    panel = GuiPanel(gui, controller)
    panel.create()
    gui.buttons["Стоп"]()
    assert calls == ["start", "stop"]
    panel.on_refresh()
    assert gui.texts[panel.status]


def test_gui_panel_dock_falls_back_to_tool_window_only_when_needed():
    gui = FakeGui(dock=False)
    panel = GuiPanel(gui, PanelController(lambda: None, lambda: None)).create()
    assert gui.calls[1][0] == "dock" and gui.calls[2][0] == "tool"
    assert panel.window > 0


def test_gui_panel_headless_or_unbuildable_fails_closed():
    with pytest.raises(RuntimeError, match="GUI"):
        GuiPanel(FakeGui(available=False), PanelController(lambda: None, lambda: None)).create()
    with pytest.raises(RuntimeError, match="window"):
        GuiPanel(FakeGui(dock=False, tool=False), PanelController(lambda: None, lambda: None)).create()
    with pytest.raises(RuntimeError, match="widgets"):
        GuiPanel(FakeGui(widgets=False), PanelController(lambda: None, lambda: None)).create()


def test_gui_panel_close_then_show_rebuilds_window():
    gui = FakeGui()
    panel = GuiPanel(gui, PanelController(lambda: None, lambda: None))
    panel.create()
    first = panel.window
    gui.close_callback()
    assert panel.closed and panel.window == 0
    panel.show()
    assert not panel.closed and panel.window != first


def test_gui_panel_stale_show_handle_rebuilds_once():
    gui = FakeGui(show=False)
    panel = GuiPanel(gui, PanelController(lambda: None, lambda: None))
    panel.create()
    with pytest.raises(RuntimeError, match="show"):
        panel.show()
    assert panel.kind == "tool"
    assert [c[0] for c in gui.calls].count("tool") == 1
    assert "shown=False" in panel.report()


def test_panel_has_no_blocking_loop_network_or_external_dependency():
    tree = ast.parse((ROOT / "src/clo3d_mcp/control_panel.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.While, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    names = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not names & {"sleep", "wait", "GetMessageW", "PostQuitMessage", "exec", "exec_", "poll"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {"re"}
