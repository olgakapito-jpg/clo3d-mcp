"""Manual arrangement probe bounds and guards, never fit acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_arrangement_probe.py"
SPEC = importlib.util.spec_from_file_location("arrangement_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Pattern:
    def __init__(self, pieces=2, fail=False):
        self.pieces = pieces
        self.fail = fail
        self.calls = []

    def GetPatternCount(self):
        return self.pieces

    def GetArrangementList(self):
        self.calls.append("list")
        return [{"name": "private", "index": "0"}]

    def GetArrangementOfPattern(self, i):
        self.calls.append(("piece", i))
        if self.fail:
            raise RuntimeError("private path")
        return {"positionX": 10, "positionY": -5, "orientation": 1,
                "shapeStyle": "private name", "nested": {"a": 1}}


def setup(monkeypatch, pattern):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_arrangement_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    return runtime


def test_success_sanitizes_strings_and_reads_each_piece(monkeypatch):
    pattern = Pattern()
    runtime = setup(monkeypatch, pattern)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["count"] == 2
    assert report["list_length"] == 1
    assert report["pieces"][0]["arrangement"]["fields"]["positionX"] == {"type": "int", "value": 10}
    assert report["pieces"][0]["arrangement"]["fields"]["shapeStyle"]["type"] == "str"
    assert "private" not in json.dumps(report)
    assert pattern.calls.count(("piece", 0)) == 1
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"


def test_native_exception_sanitized(monkeypatch):
    pattern = Pattern(fail=True)
    runtime = setup(monkeypatch, pattern)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "native_exception_no_retry"
    assert "private" not in json.dumps(report) and not runtime.busy


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
    assert pattern.calls == []


def test_missing_service_and_bad_count(monkeypatch):
    pattern = Pattern()
    setup(monkeypatch, pattern)
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": SimpleNamespace(
        profile="service", state="active", service_ready=True, busy=False,
        executor=SimpleNamespace(state="ready"),
        timer=SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7}),
        owner_thread=7, callback_thread=7, session_id="s")}, raising=False)
    pattern.pieces = 33
    assert probe.run_probe()["stop_reason"] == "unexpected_count"
    assert pattern.calls == []


def test_source_allowlist_and_no_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetArrangementList", "GetArrangementOfPattern"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))
