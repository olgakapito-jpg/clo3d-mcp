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

from clo3d_mcp.control_panel import PanelController


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


def test_generation_limit_and_unknown_registry_fail_closed():
    for registry in ({"version": 1, "retained": [None] * 16}, {"version": 2}):
        controller = PanelController(lambda: registry, lambda: pytest.fail("start"), lambda: 11)
        assert controller.status()[1:] == (False, False)
        controller.act("start")


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
    panel = SimpleNamespace(show=lambda: calls.append("show"))
    monkeypatch.setattr(builtins, "_clo3d_mcp_panel",
                        {"version": 1, "root": str(ROOT), "panel": panel}, raising=False)
    module.main()
    module.main()
    assert calls == ["show", "show"]


def test_panel_has_no_blocking_loop_network_or_external_dependency():
    tree = ast.parse((ROOT / "src/clo3d_mcp/control_panel.py").read_text(encoding="utf-8"))
    assert not any(isinstance(node, (ast.While, ast.AsyncFunctionDef)) for node in ast.walk(tree))
    names = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not names & {"sleep", "wait", "GetMessageW", "PostQuitMessage", "exec", "exec_", "poll"}
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {"re", "ctypes", "sys"}


@pytest.mark.skipif(sys.platform != "win32", reason="real Win32 panel test")
def test_native_window_buttons_hide_and_reopen_in_isolated_process():
    code = r'''
import ctypes
import gc
from clo3d_mcp.control_panel import PanelController, WindowsPanel
from ctypes import wintypes as wt
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetCurrentThreadId.argtypes = []
kernel.GetCurrentThreadId.restype = wt.DWORD
calls = []
controller = PanelController(lambda: None, lambda: calls.append("start"), kernel.GetCurrentThreadId)
panel = WindowsPanel(controller)
panel.create()
panel.show()
gc.collect()
assert panel.visible and panel.timer_id
panel.user.SendMessageW(panel.hwnd, 0x0111, panel.START, panel.controls["start"])
assert calls == ["start"]
panel.user.SendMessageW(panel.hwnd, 0x0113, panel.TIMER, 0)
panel.user.SendMessageW(panel.hwnd, 0x0010, 0, 0)
assert not panel.visible and panel.timer_id is None
assert calls == ["start"]
panel.show()
assert panel.visible and panel.timer_id
panel.hide()
assert not panel.visible and panel.timer_id is None
print("native-panel-pass")
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "native-panel-pass" in result.stdout
