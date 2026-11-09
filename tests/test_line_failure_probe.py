"""Manual line-failure probe bounds and guards, never real native acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_line_failure_probe.py"
SPEC = importlib.util.spec_from_file_location("line_failure_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Pattern:
    def __init__(self, value=None, fail=False, names=None):
        self.names = names if names is not None else [probe.EXPECTED_NAME]
        self.value = value
        self.fail = fail
        self.calls = []

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def GetPatternLineInfo(self, i):
        self.calls.append(("line", i))
        if self.fail:
            raise RuntimeError("private path")
        return self.value


def setup(monkeypatch, native):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_failure_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", native)
    return runtime


def failed():
    return json.dumps({"status": "failed", "message": "private text"})


def empty_success():
    return json.dumps({"status": "success", "patternIndex": 1, "patternName": "x",
                       "lineCount": 0, "boundingBox": {}, "lines": []})


def test_failed_native_shape_reports_token_but_not_message(monkeypatch):
    native = Pattern(failed())
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "observed" and report["stop_reason"] == "stop_no_retry"
    assert report["invalid_index"] == 1 and report["calls"] == 1
    assert report["native"]["status_token"] == "failed"
    assert report["native"]["message_present"] is True
    assert "private" not in json.dumps(report)
    assert native.calls == ["count", "name", ("line", 1)]
    assert not runtime.busy


def test_empty_success_is_observed_not_acceptance(monkeypatch):
    native = Pattern(empty_success())
    setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["native"]["status_token"] == "success"
    assert report["native"]["lines_length"] == 0


def test_native_exception_sanitized_and_not_retried(monkeypatch):
    native = Pattern(fail=True)
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["stop_reason"] == "native_exception_no_retry"
    assert "private" not in json.dumps(report) and not runtime.busy
    assert native.calls.count(("line", 1)) == 1


def test_missing_fixture_or_ambiguous_never_calls_line(monkeypatch):
    for names in (["user"], [probe.EXPECTED_NAME, probe.EXPECTED_NAME]):
        native = Pattern(names=names)
        setup(monkeypatch, native)
        report = probe.run_probe()
        assert report["stop_reason"] == "own_fixture_missing_or_ambiguous"
        assert ("line", 1) not in native.calls
    native = Pattern(names=[])
    setup(monkeypatch, native)
    assert probe.run_probe()["stop_reason"] == "unexpected_count_for_invalid_index"
    assert native.calls == ["count"]


def test_one_shot_marker_blocks_second_run(monkeypatch):
    native = Pattern(failed())
    setup(monkeypatch, native)
    assert probe.run_probe()["status"] == "observed"
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls.count(("line", 1)) == 1


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_guard_failure_no_native(monkeypatch, fault):
    native = Pattern(failed())
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


def test_missing_service_no_native(monkeypatch):
    native = Pattern(failed())
    setup(monkeypatch, native)
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    assert native.calls == []


def test_source_allowlist_one_line_call_and_no_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    assert imports == {"json", "re", "builtins", "pattern_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))
