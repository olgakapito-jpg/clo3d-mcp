"""Manual line-length probe bounds and guards, never real native acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_line_length_probe.py"
SPEC = importlib.util.spec_from_file_location("line_length_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

LENGTHS = {0: 120.0, 1: 80.0, 2: 120.0, 3: 80.0}


def payload(lengths=None, indices=None):
    lengths = LENGTHS if lengths is None else lengths
    indices = sorted(lengths) if indices is None else indices
    lines = []
    for index in indices:
        lines.append({
            "lineIndex": index, "length": lengths.get(index, 80.0),
            "orientation": "horizontal", "location": "top",
            "start": {"x": 2000, "y": 1250}, "end": {"x": 2120, "y": 1250},
            "mid": {"x": 2060, "y": 1250}, "midNorm": {"x": 0.5, "y": 0}})
    return {"status": "success", "patternIndex": 1,
            "patternName": probe.EXPECTED_NAME, "lineCount": len(lines),
            "boundingBox": {"minX": 2000, "minY": 1250, "maxX": 2120, "maxY": 1330,
                            "width": 120, "height": 80},
            "lines": lines}


class Pattern:
    def __init__(self, value=None, lengths=None, fail_at=None, bad_at=None):
        self.names = ["private user", probe.EXPECTED_NAME]
        self.value = json.dumps(payload()) if value is None else value
        self.lengths = dict(LENGTHS) if lengths is None else lengths
        self.fail_at = fail_at
        self.bad_at = bad_at
        self.calls = []

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def GetPatternLineInfo(self, i):
        assert i == 1
        self.calls.append("line")
        return self.value

    def GetLineLength(self, i, k):
        assert i == 1
        self.calls.append(("length", k))
        if self.fail_at == k:
            raise RuntimeError("private text")
        if self.bad_at == k:
            return "120"
        return self.lengths[k]


def setup(monkeypatch, native):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_length_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", native)
    return runtime


def test_success_four_lengths_one_shot_multiset_and_per_index(monkeypatch):
    native = Pattern()
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["stop_reason"] == "stop_no_retry"
    assert report["line_info_calls"] == 1 and report["line_length_calls"] == 4
    assert report["line_indices"] == [0, 1, 2, 3]
    assert report["multiset_match"] is True and report["per_index_match"] is True
    assert report["max_abs_delta_mm"] == 0
    assert native.calls == ["count", "name", "name", "count", "name", "line",
                            ("length", 0), ("length", 1), ("length", 2), ("length", 3)]
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert len([c for c in native.calls if c == "line"]) == 1
    assert len([c for c in native.calls if isinstance(c, tuple)]) == 4


@pytest.mark.parametrize("value", ["", "[]", '{"status":"failed","message":"private text"}',
    json.dumps({"status": "success", "patternIndex": 1, "patternName": "other",
                "lineCount": 0, "lines": []}),
    json.dumps(payload(indices=[0, 1, 2])),
    json.dumps(payload(indices=[0, 1, 2, 5])),
    '{"status":"success","status":"success"}', "not json", []])
def test_unexpected_line_info_stops_before_any_length(monkeypatch, value):
    native = Pattern(value)
    setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["stop_reason"] == "line_info_stop_no_length_calls"
    assert report["line_info_calls"] == 1 and report["line_length_calls"] == 0
    assert [c for c in native.calls if c == "line"] == ["line"]
    assert "private" not in json.dumps(report)


def test_length_mismatch_reported_without_retry(monkeypatch):
    native = Pattern(lengths={0: 120.0, 1: 80.0, 2: 121.0, 3: 80.0})
    setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["line_length_calls"] == 4
    assert report["per_index_match"] is False and report["multiset_match"] is False
    assert len([c for c in native.calls if isinstance(c, tuple)]) == 4


def test_length_exception_stops_remaining_calls(monkeypatch):
    native = Pattern(fail_at=1)
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "length_call_error_no_retry"
    assert report["line_length_calls"] == 1
    assert [c for c in native.calls if isinstance(c, tuple)] == [("length", 0), ("length", 1)]
    assert "private" not in json.dumps(report) and not runtime.busy


def test_invalid_length_type_stops(monkeypatch):
    native = Pattern(bad_at=0)
    setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["stop_reason"] == "invalid_length_result"
    assert report["line_length_calls"] == 1
    assert [c for c in native.calls if isinstance(c, tuple)] == [("length", 0)]


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    native = Pattern()
    runtime = setup(monkeypatch, native)
    if fault == "busy": runtime.busy = True
    elif fault == "thread": runtime.timer.thread_id = lambda: 8
    elif fault == "callback": runtime.callback_thread = 8
    elif fault == "windows": runtime.timer.visible_window_threads = lambda: {7, 8}
    elif fault == "executor": runtime.executor.state = "executing"
    elif fault == "state": runtime.state = "stopped"
    elif fault == "profile": runtime.profile = "p1"
    else: runtime.service_ready = False
    assert probe.run_probe()["status"] == "blocked"
    assert native.calls == []


def test_missing_fixture_or_service_never_calls_lengths(monkeypatch):
    native = Pattern()
    setup(monkeypatch, native)
    native.names = ["user"]
    assert probe.run_probe()["stop_reason"] == "own_fixture_missing_or_ambiguous"
    assert [c for c in native.calls if c in ("line",) or isinstance(c, tuple)] == []
    native.names = ["user", probe.EXPECTED_NAME]
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    assert isinstance(native.calls, list)


def test_one_shot_registry_corrupt_or_full_no_native(monkeypatch):
    native = Pattern()
    setup(monkeypatch, native)
    for runs in ([], set(str(i) for i in range(16)), {"private-session"}):
        monkeypatch.setattr(builtins, "_clo3d_mcp_line_length_probe_runs", runs)
        assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls == []


def test_source_allowlist_two_argument_length_and_no_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo", "GetLineLength"}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "GetLineLength"):
            assert len(node.args) == 2 and not node.keywords
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"pathlib", "json", "math", "builtins", "pattern_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))

def test_report_written_to_project_acceptance_output(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "src" / "clo3d_mcp").mkdir(parents=True)
    monkeypatch.setattr(probe, "ROOT", str(tmp_path))
    path = probe.write_report({"a": 1}, "probe.json")
    assert path == tmp_path / "acceptance-output" / "probe.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
