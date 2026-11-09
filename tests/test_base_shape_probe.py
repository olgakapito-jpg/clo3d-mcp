"""Manual base-shape probe bounds and guards, never real native acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_base_shape_probe.py"
SPEC = importlib.util.spec_from_file_location("base_shape_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def line_info(status="success", lengths=(120, 80, 120, 80)):
    lines = [{"lineIndex": i, "length": v} for i, v in enumerate(lengths)]
    return json.dumps({"status": status, "lineCount": len(lines), "lines": lines})


class Pattern:
    def __init__(self, fail_base=False, create_gain=1):
        self.names = []
        self.fail_base = fail_base
        self.create_gain = create_gain
        self.area = 9600.0
        self.value = line_info()
        self.calls = []

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def CreatePatternWithPoints(self, points):
        self.calls.append("create")
        if self.create_gain:
            self.names.append("Pattern")
        return len(self.names) - 1

    def SetPatternPieceName(self, i, name):
        self.calls.append("set_name")
        self.names[i] = name

    def CreateBaseShapeWithPoints(self, i, points, closed):
        self.calls.append(("base", [t for _, _, t in points], closed))
        if self.fail_base:
            raise RuntimeError("private path")
        self.area += 1.0
        self.value = line_info(lengths=(100, 90, 110))
        return 7

    def GetPatternPieceArea(self, i):
        return self.area

    def GetBoundingBoxOfPattern(self, i):
        return {"Height": "80", "Width": "120"}

    def GetPatternLineInfo(self, i):
        return self.value


class Utility:
    def __init__(self):
        self.payload = []

    def GetInternalShapeInformation(self, i):
        return self.payload


def setup(monkeypatch, pattern, utility):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_base_shape_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", pattern)
    monkeypatch.setitem(sys.modules, "utility_api", utility)
    return runtime


def test_success_sequence_records_each_variant_and_one_shot(monkeypatch):
    pattern, utility = Pattern(), Utility()
    runtime = setup(monkeypatch, pattern, utility)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["created_index"] == 0
    assert [step["step"] for step in report["steps"]] == [
        "created", "same_straight", "one_spline", "two_spline", "one_bezier", "two_bezier"]
    assert [step["return"] for step in report["steps"][1:]] == [7] * 5
    assert pattern.calls.count("set_name") == 1
    assert len([c for c in pattern.calls if isinstance(c, tuple)]) == 5
    assert report["steps"][1]["lines"]["line_count"] == 3
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"


def test_existing_probe_fixture_blocks_without_create(monkeypatch):
    pattern = Pattern()
    pattern.names = [probe.NAME]
    setup(monkeypatch, pattern, Utility())
    report = probe.run_probe()
    assert report["stop_reason"] == "own_fixture_already_exists"
    assert "create" not in pattern.calls


def test_create_not_verified_stops_before_base_shape(monkeypatch):
    pattern = Pattern(create_gain=0)
    setup(monkeypatch, pattern, Utility())
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "create_not_verified"
    assert not any(isinstance(c, tuple) for c in pattern.calls)


def test_native_exception_stops_sanitized(monkeypatch):
    pattern = Pattern(fail_base=True)
    runtime = setup(monkeypatch, pattern, Utility())
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "native_exception_no_retry"
    assert "private" not in json.dumps(report) and not runtime.busy
    assert len(report["steps"]) == 1


def test_line_summary_rejects_bad_payloads():
    assert probe.line_summary(None) == {"type": "NoneType"}
    assert probe.line_summary("not json")["json"] == "invalid"
    assert probe.line_summary("[]")["json"] == "not_object"
    assert probe.line_summary(line_info(lengths=(1, 2)))["lengths"] == [1.0, 2.0]


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    pattern = Pattern()
    runtime = setup(monkeypatch, pattern, Utility())
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
    setup(monkeypatch, pattern, Utility())
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    assert pattern.calls == []


def test_source_allowlist_and_no_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "CreatePatternWithPoints",
                      "SetPatternPieceName", "GetPatternPieceArea", "GetBoundingBoxOfPattern",
                      "GetPatternLineInfo", "CreateBaseShapeWithPoints"}
    utility = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
               and isinstance(n.value, ast.Name) and n.value.id == "utility"}
    assert utility == {"GetInternalShapeInformation"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "builtins", "pattern_api", "utility_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))
