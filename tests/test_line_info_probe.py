"""Manual probe bounds and guards, never real native acceptance."""

import ast
import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_line_info_probe.py"
SPEC = importlib.util.spec_from_file_location("line_info_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def payload():
    line = {"lineIndex": 8, "length": 120.0, "orientation": "horizontal",
            "location": "top", "start": {"x": 2000, "y": 1250},
            "end": {"x": 2120, "y": 1250}, "mid": {"x": 2060, "y": 1250},
            "midNorm": {"x": 0.5, "y": 0}}
    return {"status": "some_new_status", "patternIndex": 1,
            "patternName": probe.EXPECTED_NAME, "lineCount": 4,
            "boundingBox": {"minX": 2000, "minY": 1250, "maxX": 2120, "maxY": 1330,
                            "width": 120, "height": 80},
            "lines": [line] * 4}


class Pattern:
    def __init__(self, value=None, fail=False):
        self.names = ["private user", probe.EXPECTED_NAME]
        self.value = json.dumps(payload()) if value is None else value
        self.fail = fail
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
        if self.fail:
            raise RuntimeError("private text")
        return self.value


def setup(monkeypatch, native):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", native)
    return runtime


def test_one_shot_busy_guard_unknown_status_observed_no_acceptance(monkeypatch):
    native = Pattern()
    runtime = setup(monkeypatch, native)
    original = native.GetPatternLineInfo
    def read(i):
        assert runtime.busy
        return original(i)
    native.GetPatternLineInfo = read
    report = probe.run_probe()
    assert report["status"] == "observed" and report["line_info_calls"] == 1
    assert report["evidence"] == "single_native_schema_not_acceptance"
    assert report["native"]["status_token"] == "some_new_status"
    assert report["native"]["line_sample"][0]["numbers"]["lineIndex"]["value"] == 8
    assert report["native"]["bounding_box"]["maxX"] == {"type": "int", "value": 2120}
    assert native.calls == ["count", "name", "name", "count", "name", "line"]
    assert not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls.count("line") == 1


@pytest.mark.parametrize("value", ["", "[]", "{}", '{"status":"failed","message":"private text"}',
    '{"status":"success","patternIndex":true}', "not json", [], object()])
def test_bad_results_no_further_native_calls(monkeypatch, value):
    native = Pattern(value)
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "observed"
    assert report["stop_reason"] == "native_result_stop_no_more_reads"
    assert native.calls[-1] == "line" and native.calls.count("line") == 1
    assert not runtime.busy and "private" not in json.dumps(report)


def test_native_exception_consumes_marker_and_releases_busy(monkeypatch):
    native = Pattern(fail=True)
    runtime = setup(monkeypatch, native)
    result = probe.run_probe()
    assert result["status"] == "command_error" and result["line_info_calls"] == 1
    assert "private" not in json.dumps(result) and not runtime.busy
    assert probe.run_probe()["line_info_calls"] == 0
    assert native.calls.count("line") == 1


@pytest.mark.parametrize("fail", [False, True])
def test_explicit_fixture_recreated_attempt_preserves_old_marker_and_no_third(monkeypatch, fail):
    native = Pattern(fail=fail)
    runtime = setup(monkeypatch, native)
    runtime.session_id = probe.FIXTURE_RECREATED_SESSION
    old = {runtime.session_id}
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_probe_runs", old)
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_fixture_recreated_runs", set(), raising=False)
    report = probe.run_probe()
    assert report["attempt"] == "fixture_recreated_2"
    assert report["line_info_calls"] == 1
    assert report["status"] == ("command_error" if fail else "observed")
    assert old == {runtime.session_id} and not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls.count("line") == 1


def test_explicit_second_attempt_missing_fixture_also_consumes_second_marker(monkeypatch):
    native = Pattern()
    native.names = ["user"]
    runtime = setup(monkeypatch, native)
    runtime.session_id = probe.FIXTURE_RECREATED_SESSION
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_probe_runs", {runtime.session_id})
    monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_fixture_recreated_runs", set(), raising=False)
    assert probe.run_probe()["stop_reason"] == "own_fixture_missing_or_ambiguous"
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert "line" not in native.calls


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


@pytest.mark.parametrize("names", [[], ["user"], [probe.EXPECTED_NAME] * 2, [True], ["x"] * 257])
def test_unique_own_target_only(names):
    native = Pattern()
    native.names = names
    result = probe.collect(native)
    expected = "command_error" if not names or names == [True] or len(names) > 256 else "blocked"
    assert result["status"] == expected
    assert "line" not in native.calls


def test_stale_count_or_name_stops_before_line_read():
    native = Pattern()
    calls = []
    def changed_count():
        calls.append(1)
        return 2 if len(calls) == 1 else 3
    native.GetPatternCount = changed_count
    assert probe.collect(native)["stop_reason"] == "stale_fixture"
    assert "line" not in native.calls


def test_missing_service_no_import_or_native(monkeypatch):
    native = Pattern()
    setup(monkeypatch, native)
    monkeypatch.delattr(builtins, "_clo3d_mcp_service")
    assert probe.run_probe()["stop_reason"] == "verified_service_required"
    assert native.calls == []


def test_one_shot_registry_corrupt_or_full_no_native(monkeypatch):
    native = Pattern()
    setup(monkeypatch, native)
    for runs in ([], set(str(i) for i in range(16))):
        monkeypatch.setattr(builtins, "_clo3d_mcp_line_info_probe_runs", runs)
        assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls == []


@pytest.mark.parametrize("text", ['{"status":"a","status":"b"}', '{"x":NaN}', '{"x":Infinity}',
    '{"x":1e400}', '{"x":100000000000000000}', '{"x":' + "9" * 100 + '}',
    '[' * 17 + '0' + ']' * 17, '{"x":"\\ud800"}', '\ud800'])
def test_json_limits_rejected(text):
    assert probe.observe(text, 1)["json_observation"] == "rejected_json_or_limits"


@pytest.mark.parametrize("text", ["x" * 65537, "я" * 40000])
def test_size_limits(text):
    assert probe.observe(text, 1)["json_observation"] == "size_limit"


def test_allowlisted_projection_no_private_strings_unknown_keys_or_coercion():
    data = payload()
    data.update(message="private text", patternName="private name", private_key="secret")
    data["lines"][0].update(orientation="private value", location="private path", length="120",
                            start={"x": True, "y": "private text"}, private_key="secret")
    report = probe.observe(json.dumps(data), 1)
    text = json.dumps(report, allow_nan=False)
    assert "private" not in text and "secret" not in text
    assert report["pattern_name_matches"] is False
    assert report["line_sample"][0]["numbers"]["length"] == {"type": "str"}
    assert report["line_sample"][0]["start"]["x"] == {"type": "bool"}
    assert len(text) < 12000


def test_sample_only_four_lines_and_escaped_brackets_do_not_change_depth():
    data = payload()
    data["lines"] *= 20
    data["message"] = '"' + '[' * 100 + '\\'
    result = probe.observe(json.dumps(data), 1)
    assert result["lines_length"] == 80 and len(result["line_sample"]) == 4


def test_source_native_allowlist_no_outline_length_setter_or_io():
    tree = ast.parse(PATH.read_text(encoding="utf-8"))
    native = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
              and isinstance(n.value, ast.Name) and n.value.id == "pattern"}
    assert native == {"GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo"}
    imports = {n.name for node in ast.walk(tree) if isinstance(node, ast.Import) for n in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imports == {"pathlib", "json", "math", "re", "builtins", "pattern_api"}
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in {"open", "eval", "exec", "compile"} for n in ast.walk(tree))

def test_report_written_to_project_acceptance_output(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "src" / "clo3d_mcp").mkdir(parents=True)
    monkeypatch.setattr(probe, "ROOT", str(tmp_path))
    path = probe.write_report({"a": 1}, "probe.json")
    assert path == tmp_path / "acceptance-output" / "probe.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
