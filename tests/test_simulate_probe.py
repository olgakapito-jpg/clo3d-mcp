"""Manual short-simulation probe bounds and guards."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_simulate_probe.py"
SPEC = importlib.util.spec_from_file_location("simulate_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Pattern:
    def __init__(self, names=None, fail=False):
        self.names = names if names is not None else ["A", "B", "C", "D", "TEST"]
        self.fail = fail

    def GetPatternCount(self):
        if self.fail:
            raise RuntimeError("private path")
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]


class Export:
    def __init__(self, avatars=1):
        self.avatars = avatars

    def GetAvatarCount(self):
        return self.avatars


class Utility:
    def __init__(self, result=True, fail=False):
        self.result = result
        self.fail = fail
        self.calls = []

    def Simulate(self, steps):
        self.calls.append(steps)
        if self.fail:
            raise RuntimeError("private path")
        return self.result


def setup(monkeypatch, pattern, utility, export=None):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_simulate_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    monkeypatch.setitem(sys.modules, "utility_api", utility)
    monkeypatch.setitem(sys.modules, "export_api", export or Export())
    return runtime


def test_success_calls_once_with_bounded_steps(monkeypatch):
    utility = Utility()
    runtime = setup(monkeypatch, Pattern(), utility)
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["native_return"] is True and report["steps"] == probe.STEPS
    assert report["names_unchanged"] is True and report["pattern_count_after"] == 5
    assert utility.calls == [probe.STEPS]
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert utility.calls == [probe.STEPS]


def test_missing_avatar_or_bad_count_blocks(monkeypatch):
    setup(monkeypatch, Pattern(), Utility(), export=Export(avatars=0))
    assert probe.run_probe()["stop_reason"] == "avatar_required"
    setup(monkeypatch, Pattern(names=[]), Utility())
    assert probe.run_probe()["stop_reason"] == "unexpected_pattern_count"


def test_simulate_exception_or_non_bool_stops(monkeypatch):
    setup(monkeypatch, Pattern(), Utility(fail=True))
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "simulate_no_retry"
    assert "private" not in json.dumps(report)
    setup(monkeypatch, Pattern(), Utility(result=1))
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "invalid_native_result"
    assert report["native_return_type"] == "int"


def test_native_false_is_observed_not_success(monkeypatch):
    setup(monkeypatch, Pattern(), Utility(result=False))
    report = probe.run_probe()
    assert report["status"] == "observed" and report["native_return"] is False


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    utility = Utility()
    runtime = setup(monkeypatch, Pattern(), utility)
    if fault == "busy": runtime.busy = True
    elif fault == "thread": runtime.timer.thread_id = lambda: 8
    elif fault == "callback": runtime.callback_thread = 8
    elif fault == "windows": runtime.timer.visible_window_threads = lambda: {7, 8}
    elif fault == "executor": runtime.executor.state = "executing"
    elif fault == "state": runtime.state = "stopped"
    elif fault == "profile": runtime.profile = "p1"
    else: runtime.service_ready = False
    assert probe.run_probe()["status"] == "blocked"
    assert utility.calls == []


def test_source_allowlist():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    pattern_native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                      and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    utility_native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                      and isinstance(n.value, ast.Name) and n.value.id == "utility"}
    assert pattern_native == {"GetPatternCount", "GetPatternPieceName"}
    assert utility_native == {"Simulate"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "time", "builtins", "pattern_api", "export_api", "utility_api"}
