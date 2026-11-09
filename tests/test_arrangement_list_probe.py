"""Manual arrangement-list probe bounds and guards."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_arrangement_list_probe.py"
SPEC = importlib.util.spec_from_file_location("arrangement_list_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Pattern:
    def __init__(self, values=None, fail=False):
        self.values = values if values is not None else [{"ArrangementName": "Front", "x": 1}]
        self.fail = fail

    def GetArrangementList(self):
        if self.fail:
            raise RuntimeError("private path")
        return self.values


def setup(monkeypatch, pattern):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_arrangement_list_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    return runtime


def test_success_and_one_shot(monkeypatch):
    runtime = setup(monkeypatch, Pattern([{"ArrangementName": "Front", "offsetX": "50"}]))
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["entries"] == [{"ArrangementName": "Front", "offsetX": "50"}]
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"


def test_exception_and_bad_list(monkeypatch):
    runtime = setup(monkeypatch, Pattern(fail=True))
    report = probe.run_probe()
    assert report["status"] == "command_error" and "private" not in json.dumps(report)
    assert not runtime.busy
    setup(monkeypatch, Pattern(values="bad"))
    assert probe.run_probe()["stop_reason"] == "unexpected_arrangement_list"


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    pattern = Pattern()
    runtime = setup(monkeypatch, pattern)
    if fault == "busy": runtime.busy = True
    elif fault == "thread": runtime.timer.thread_id = lambda: 8
    elif fault == "callback": runtime.callback_thread = 8
    elif fault == "windows": runtime.timer.visible_window_threads = lambda: {7, 8}
    elif fault == "executor": runtime.executor.state = "executing"
    elif fault == "state": runtime.state = "stopped"
    elif fault == "profile": runtime.profile = "p1"
    else: runtime.service_ready = False
    assert probe.run_probe()["status"] == "blocked"


def test_source_allowlist():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetArrangementList"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api"}
