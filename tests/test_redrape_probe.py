"""Manual ReDrape probe bounds and guards, visual-only evidence."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_redrape_probe.py"
SPEC = importlib.util.spec_from_file_location("redrape_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Option:
    bAddArrangementPoints = False
    bAutoCreateFittingSuit = False
    bMoveGarment = False


class ApiTypes:
    ImportExportOption = Option


class Utility:
    def __init__(self, avatars=1, fail=False):
        self.avatars, self.fail, self.calls = avatars, fail, []

    def GetAvatarCount(self):
        return self.avatars

    def ReDrape3DArrangement(self, option):
        self.calls.append(option)
        if self.fail:
            raise RuntimeError("private path")
        return None


class Pattern:
    def __init__(self, count=3):
        self.count = count

    def GetPatternCount(self):
        return self.count


def setup(monkeypatch, utility, pattern, api_types=ApiTypes):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_redrape_probe_runs_v2", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    monkeypatch.setitem(sys.modules, "utility_api", utility)
    monkeypatch.setitem(sys.modules, "export_api", utility)
    monkeypatch.setitem(sys.modules, "ApiTypes", api_types)
    return runtime


def test_success_sets_flags_and_one_call(monkeypatch):
    utility, pattern = Utility(), Pattern()
    runtime = setup(monkeypatch, utility, pattern)
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["flags"] == ["bAddArrangementPoints", "bAutoCreateFittingSuit", "bMoveGarment"]
    assert len(utility.calls) == 1 and isinstance(utility.calls[0], Option)
    assert utility.calls[0].bAddArrangementPoints is True
    assert report["pattern_count_after"] == 3 and not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert len(utility.calls) == 1


def test_missing_option_or_avatar_no_call(monkeypatch):
    class NoOption:
        pass
    utility = Utility()
    setup(monkeypatch, utility, Pattern(), NoOption)
    assert probe.run_probe()["stop_reason"] == "api_types_option_unavailable"
    assert utility.calls == []
    utility = Utility(avatars=0)
    setup(monkeypatch, utility, Pattern())
    assert probe.run_probe()["stop_reason"] == "avatar_required"
    assert utility.calls == []


def test_native_exception_sanitized(monkeypatch):
    utility = Utility(fail=True)
    runtime = setup(monkeypatch, utility, Pattern())
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "native_exception_no_retry"
    assert "private" not in json.dumps(report) and not runtime.busy


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    utility = Utility()
    runtime = setup(monkeypatch, utility, Pattern())
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
    util = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "utility"}
    assert util == {"ReDrape3DArrangement"}
    exp = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
           and isinstance(n.value, ast.Name) and n.value.id == "export_api"}
    assert exp == {"GetAvatarCount"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api", "export_api", "utility_api", "ApiTypes"}
