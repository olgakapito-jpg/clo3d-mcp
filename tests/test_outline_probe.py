"""One-shot diagnostic safeguards and bounded structure, not native evidence."""

import builtins
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "diagnostics/clo3d_mcp_outline_probe.py"
SPEC = importlib.util.spec_from_file_location("outline_probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Pattern:
    def __init__(self, value=None, fail=False):
        self.names = ["user", probe.EXPECTED_NAME]
        self.value = [[0, 0], [120, 0], [120, 80], [0, 80]] if value is None else value
        self.calls = 0
        self.fail = fail

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetPatternOutlinePoints(self, i):
        assert i == 1
        self.calls += 1
        if self.fail:
            raise RuntimeError("private information")
        return self.value


def setup(monkeypatch, native):
    timer = SimpleNamespace(thread_id=lambda: 7, visible_window_threads=lambda: {7})
    runtime = SimpleNamespace(profile="service", state="active", service_ready=True,
        busy=False, executor=SimpleNamespace(state="ready"), timer=timer,
        owner_thread=7, callback_thread=7, session_id="private-session")
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {"version": 1, "current": runtime}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_outline_probe_runs", set(), raising=False)
    monkeypatch.setitem(sys.modules, "pattern_api", native)
    return runtime


def test_probe_exactly_one_call_and_busy_guard_released(monkeypatch):
    native = Pattern()
    runtime = setup(monkeypatch, native)
    original = native.GetPatternOutlinePoints
    def read(i):
        assert runtime.busy
        return original(i)
    native.GetPatternOutlinePoints = read
    report = probe.run_probe()
    assert report["status"] == "observed" and report["outline_calls"] == 1
    assert report["native"]["type"] == "list" and report["native"]["length"] == 4
    assert not runtime.busy and native.calls == 1
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls == 1
    assert "private" not in json.dumps(report)


def test_probe_empty_native_observed_is_not_outline_acceptance(monkeypatch):
    native = Pattern(value=[])
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report == {
        "schema": "clo_outline_probe_v1", "status": "observed",
        "evidence": "single_native_structure_not_acceptance", "outline_calls": 1,
        "pattern_index": 1, "native": {"type": "list", "length": 0, "rows": []},
        "stop_reason": "stop_no_retry",
    }
    assert native.calls == 1 and not runtime.busy
    assert probe.run_probe()["stop_reason"] == "one_shot_already_used_or_limit"
    assert native.calls == 1


def test_probe_native_exception_no_retry_or_private_text(monkeypatch):
    native = Pattern(fail=True)
    runtime = setup(monkeypatch, native)
    report = probe.run_probe()
    assert report["status"] == "command_error" and report["outline_calls"] == 1
    assert not runtime.busy and "private" not in json.dumps(report)
    assert probe.run_probe()["outline_calls"] == 0
    assert native.calls == 1


@pytest.mark.parametrize("fault", ["busy", "thread", "callback", "windows", "executor", "state", "profile", "ready"])
def test_probe_wrong_runtime_no_native(monkeypatch, fault):
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
    assert native.calls == 0


@pytest.mark.parametrize("names", [[], ["user"], [probe.EXPECTED_NAME] * 2, [True], ["x"] * 257])
def test_probe_only_unique_own_fixture(names):
    native = Pattern()
    native.names = names
    assert probe.collect(native)["status"] == "blocked"
    assert native.calls == 0


@pytest.mark.parametrize("value", [[], (), [[float("nan"), float("inf"), True, 10**500]],
    [[0, 0, 1]], {"private": "not printed"}, "private text", object()])
def test_probe_structure_safe_bounded_not_coercion(value):
    report = probe.structure(value)
    text = json.dumps(report, allow_nan=False)
    assert "private" not in text and len(text) < 2048


def test_probe_large_values_only_four_rows_four_cells():
    report = probe.structure([[1] * 1000] * 1000)
    assert report["length"] == 1000 and len(report["rows"]) == 4
    assert all(r["length"] == 1000 and len(r["sample"]) == 4 for r in report["rows"])


def test_probe_post_read_inventory_change_not_success():
    native = Pattern()
    original = native.GetPatternOutlinePoints
    def read(i):
        native.names[0] = "changed"
        return original(i)
    native.GetPatternOutlinePoints = read
    report = probe.collect(native)
    assert report["status"] == "blocked" and report["stop_reason"] == "inventory_changed"
    assert native.calls == 1
