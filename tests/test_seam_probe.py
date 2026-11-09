"""Manual seam probe bounds and guards, never real native acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_seam_probe.py"
SPEC = importlib.util.spec_from_file_location("seam_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def lines():
    data = {"status": "success", "lineCount": 4,
            "lines": [{"lineIndex": i, "length": v} for i, v in enumerate((120, 80, 120, 80))]}
    return json.dumps(data)


def groups(count):
    return json.dumps({"status": "success", "groupCount": count, "groups": []})


class Pattern:
    def __init__(self, value=True, fail=False, names=None):
        self.names = names if names is not None else [probe.NAME_A, probe.NAME_B]
        self.value = value
        self.fail = fail
        self.seams = 0
        self.calls = []

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def GetPatternLineInfo(self, i):
        self.calls.append("lines")
        return lines()

    def GetPatternPieceArea(self, i):
        return 9600.0

    def GetBoundingBoxOfPattern(self, i):
        return {"Height": "80", "Width": "120"}

    def GetSeamlinePairGroupCount(self):
        self.calls.append("seam_count")
        return self.seams

    def AddSeamlinePairGroup(self, a, line_a, b, line_b, direct_a, direct_b):
        self.calls.append(("seam", a, line_a, b, line_b, direct_a, direct_b))
        if self.fail:
            raise RuntimeError("private path")
        self.seams += 1
        return self.value

    def GetPatternGroupsBySeamlineConnectivity(self, attachments, components):
        self.calls.append("connectivity")
        return groups(1 if self.seams else 2)


def setup(monkeypatch, pattern):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_seam_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    return runtime


@pytest.mark.parametrize("value", [True, "seam-group-name", 0])
def test_success_records_native_return_free_of_names(monkeypatch, value):
    pattern = Pattern(value)
    runtime = setup(monkeypatch, pattern)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["calls"] == 1
    assert report["seams_before"] == 0 and report["seams_after"] == 1
    assert report["native_return_type"] == type(value).__name__
    if isinstance(value, bool):
        assert report["native_return"] is value
    if isinstance(value, int) and not isinstance(value, bool):
        assert report["native_return_int"] == value
    assert "seam-group-name" not in json.dumps(report)
    assert report["lines_after"] == report["lines_before"]
    assert report["geometry_after"] == report["geometry_before"]
    assert report["connectivity_after"]["group_count"] == 1
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert pattern.calls.count(("seam", 0, 0, 1, 0, True, True)) == 1


def test_native_exception_sanitized_and_no_retry(monkeypatch):
    pattern = Pattern(fail=True)
    runtime = setup(monkeypatch, pattern)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "native_exception_no_retry"
    assert "private" not in json.dumps(report) and not runtime.busy


@pytest.mark.parametrize("names", [[], [probe.NAME_A], [probe.NAME_A, probe.NAME_B, probe.NAME_B]])
def test_fixture_identity_required_before_native(monkeypatch, names):
    pattern = Pattern(names=names)
    setup(monkeypatch, pattern)
    report = probe.run_probe()
    assert report["stop_reason"] == "own_seam_fixtures_missing_or_ambiguous"
    assert not any(isinstance(c, tuple) for c in pattern.calls)


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


def test_missing_service_no_native(monkeypatch):
    pattern = Pattern()
    setup(monkeypatch, pattern)
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    assert pattern.calls == []


def test_source_allowlist_and_no_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo",
                      "GetPatternPieceArea", "GetBoundingBoxOfPattern",
                      "GetSeamlinePairGroupCount", "AddSeamlinePairGroup",
                      "GetPatternGroupsBySeamlineConnectivity"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))
