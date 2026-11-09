"""Manual arrange+ReDrape probe bounds and guards."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_arrange_probe.py"
SPEC = importlib.util.spec_from_file_location("arrange_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Option:
    bAddArrangementPoints = False
    bAutoCreateFittingSuit = False
    bMoveGarment = False


class ApiTypes:
    ImportExportOption = Option


class Utility:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def ReDrape3DArrangement(self, option):
        self.calls.append(option)
        if self.fail:
            raise RuntimeError("private path")


class Export:
    def GetAvatarCount(self):
        return 1


class Pattern:
    def __init__(self, names=None, fail=False):
        self.names = names if names is not None else list(probe.ASSIGNMENT)
        self.fail = fail
        self.assigned = {}

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetArrangementList(self):
        return [{"ArrangementIndex": str(i)} for i in range(110)]

    def SetArrangement(self, i, arrangement):
        if self.fail:
            raise RuntimeError("private path")
        self.assigned[self.names[i]] = arrangement

    def GetArrangementOfPattern(self, i):
        return {"ArrangementName": "assigned"}


def setup(monkeypatch, pattern, utility, api_types=ApiTypes, export=None):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_arrange_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    monkeypatch.setitem(sys.modules, "utility_api", utility)
    monkeypatch.setitem(sys.modules, "export_api", export or Export())
    monkeypatch.setitem(sys.modules, "ApiTypes", api_types)
    return runtime


def test_success_assigns_all_and_one_redrape(monkeypatch):
    pattern, utility = Pattern(), Utility()
    runtime = setup(monkeypatch, pattern, utility)
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["pattern_count"] == 5 and len(report["applied"]) == 5
    assert pattern.assigned["MCP_3D_TEST"] == 59
    assert len(utility.calls) == 1
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert len(utility.calls) == 1


def test_missing_fixture_or_avatar_blocks(monkeypatch):
    pattern = Pattern(names=["MCP_3D_TEST"])
    setup(monkeypatch, pattern, Utility())
    assert probe.run_probe()["stop_reason"] == "own_fixture_missing_or_ambiguous"
    pattern = Pattern()
    setup(monkeypatch, pattern, Utility(), export=SimpleNamespace(GetAvatarCount=lambda: 0))
    assert probe.run_probe()["stop_reason"] == "avatar_required"


def test_set_arrangement_exception_stops_before_redrape(monkeypatch):
    pattern, utility = Pattern(fail=True), Utility()
    runtime = setup(monkeypatch, pattern, utility)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "set_arrangement_no_retry"
    assert utility.calls == [] and not runtime.busy


def test_redrape_exception_stops(monkeypatch):
    pattern, utility = Pattern(), Utility(fail=True)
    setup(monkeypatch, pattern, utility)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "redrape_no_retry"
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    pattern, utility = Pattern(), Utility()
    runtime = setup(monkeypatch, pattern, utility)
    if fault == "busy": runtime.busy = True
    elif fault == "thread": runtime.timer.thread_id = lambda: 8
    elif fault == "callback": runtime.callback_thread = 8
    elif fault == "windows": runtime.timer.visible_window_threads = lambda: {7, 8}
    elif fault == "executor": runtime.executor.state = "executing"
    elif fault == "state": runtime.state = "stopped"
    elif fault == "profile": runtime.profile = "p1"
    else: runtime.service_ready = False
    assert probe.run_probe()["status"] == "blocked"
    assert pattern.assigned == {} and utility.calls == []


def test_source_allowlist():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "GetArrangementList",
                      "SetArrangement", "GetArrangementOfPattern"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api", "export_api", "utility_api", "ApiTypes"}
