"""P0 contracts with fake scheduling; NOT real-CLO acceptance."""

import builtins
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name="clo3d_mcp_probe.py"):
    spec = importlib.util.spec_from_file_location("p0_test", ROOT / "plugin" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Timer:
    tid = 42
    windows = {42}
    fail_start = False
    fail_stop = False

    def __init__(self):
        self.starts = []
        self.stops = []

    def thread_id(self):
        return self.tid

    def visible_window_threads(self):
        return self.windows

    def wrap(self, fn):
        return fn

    def start(self, callback):
        self.starts.append(callback)
        if self.fail_start:
            raise OSError("SetTimer failed")
        return 123  # deliberately reuse timer ID across generations

    def stop(self, timer_id):
        self.stops.append(timer_id)
        if self.fail_stop:
            raise OSError("KillTimer failed")


@pytest.fixture
def env():
    module = load()
    timer = Timer()
    clock = Clock()
    calls = []
    messages = []
    registry = {"version": 1}

    def read():
        calls.append(clock())
        return 7

    def start(reader=read):
        return module.start_probe(registry, timer, reader, clock, messages.append)

    return module, timer, clock, calls, messages, registry, start


def fire(probe):
    probe.callback(None, 0x113, 123, 0)


def test_import_has_no_autostart_or_optional_runtime_dependencies(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"ctypes", "mcp", "uvicorn", "pattern_api", "clo3d_mcp_plugin"}:
            raise AssertionError("Unexpected import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    load()
    load("clo3d_mcp_probe_stop.py")


def test_api_only_from_scheduled_tick_and_throttled(env):
    _, timer, clock, calls, _, _, start = env
    probe = start()
    assert not calls
    fire(probe)
    assert not calls
    clock.now = 2
    fire(probe)
    assert calls == [2]
    assert probe.last_count == 7
    assert probe.callback_thread == timer.tid
    clock.now = 6
    fire(probe)
    assert len(calls) == 1
    clock.now = 7
    fire(probe)
    assert calls == [2, 7]


@pytest.mark.parametrize("windows", [set(), {43}, {42, 43}])
def test_ui_evidence_required_before_timer_or_api(env, windows):
    _, timer, _, calls, _, registry, start = env
    timer.windows = windows
    with pytest.raises(RuntimeError, match="window thread"):
        start()
    assert not timer.starts and not calls
    assert registry["current"].state == "failed"


def test_registration_failure_no_loop_or_retry(env):
    _, timer, _, calls, _, registry, start = env
    timer.fail_start = True
    with pytest.raises(OSError, match="SetTimer"):
        start()
    assert len(timer.starts) == 1 and not calls
    assert registry["current"].state == "failed"
    assert registry["retained"][0].callback is not None


def test_unarmed_and_wrong_id_do_not_dispatch(env):
    _, _, clock, calls, _, _, start = env
    probe = start()
    clock.now = 3
    probe.callback(None, 0x113, 999, 0)
    probe.armed = False
    fire(probe)
    assert not calls and probe.ignored_ticks == 2


def test_repeat_start_idempotent(env):
    _, timer, _, _, _, registry, start = env
    probe = start()
    assert start() is probe
    assert len(timer.starts) == len(registry["retained"]) == 1


def test_ten_cycles_stale_callback_and_reused_id(env):
    _, timer, clock, calls, _, registry, start = env
    for index in range(10):
        probe = start()
        clock.now += 3
        fire(probe)
        probe.stop()
        before = len(calls)
        fire(probe)
        assert len(calls) == before
        assert probe.generation == index + 1
    new = start()
    clock.now += 3
    for retired in registry["retained"][:-1]:
        fire(retired)
    assert new.api_calls == 0
    fire(new)
    assert new.api_calls == 1
    assert len(timer.stops) == 10


def test_reentrancy_does_not_execute_second_api(env):
    _, _, clock, calls, _, _, start = env

    def read():
        calls.append(1)
        fire(probe)
        return 2

    probe = start(read)
    clock.now = 3
    fire(probe)
    assert calls == [1] and probe.reentrant_ticks == 1
    assert not probe.busy


def test_restart_refused_while_retired_api_still_unwinding(env):
    _, _, clock, _, _, _, start = env

    def read():
        probe.stop()
        with pytest.raises(RuntimeError, match="before restart"):
            start()
        return 0

    probe = start(read)
    clock.now = 3
    fire(probe)
    assert start() is not probe


@pytest.mark.parametrize("error", [ValueError("API failed"), KeyboardInterrupt(), SystemExit(1)])
def test_native_boundary_catches_baseexceptions(env, error):
    _, timer, clock, _, _, _, start = env

    def read():
        raise error

    probe = start(read)
    clock.now = 3
    fire(probe)
    assert probe.state == "failed" and not probe.busy
    assert type(error).__name__ in probe.error
    assert timer.stops == [123]
    fire(probe)
    assert probe.api_calls == 0


def test_wrong_thread_fails_closed_and_requires_owner_cleanup(env):
    _, timer, clock, calls, _, _, start = env
    probe = start()
    timer.tid = 43
    clock.now = 3
    fire(probe)
    assert not calls and probe.state == "failed"
    assert probe.snapshot()["timer_cleanup_pending"]
    with pytest.raises(RuntimeError, match="before restart"):
        start()
    timer.tid = 42
    probe.stop()
    assert start() is not probe


def test_stop_failure_keeps_reference_and_blocks_new_generation(env):
    _, timer, _, _, _, registry, start = env
    probe = start()
    timer.fail_stop = True
    with pytest.raises(OSError):
        probe.stop()
    assert not probe.armed and probe.timer_id == 123
    assert registry["retained"][0] is probe
    with pytest.raises(RuntimeError, match="before restart"):
        start()
    timer.fail_stop = False
    probe.stop()
    probe.stop()
    assert start() is not probe


def test_stop_must_use_owner_thread(env):
    _, timer, _, _, _, _, start = env
    probe = start()
    timer.tid = 43
    with pytest.raises(RuntimeError, match="registering"):
        probe.stop()
    assert not timer.stops


def test_bounded_one_minute_run(env):
    _, timer, clock, calls, _, _, start = env
    probe = start()
    clock.now = 60
    fire(probe)
    assert probe.state == "stopped" and timer.stops == [123]
    assert not calls
    assert probe.snapshot()["stop_reason"] == "one_minute_limit"
    assert probe.snapshot()["elapsed_seconds"] == 60


def test_auto_stop_boundary_and_late_ticks_do_not_call_api(env):
    _, timer, clock, calls, _, _, start = env
    probe = start()
    clock.now = 59.999
    fire(probe)
    assert probe.state == "running" and len(calls) == 1
    clock.now = 60
    fire(probe)
    assert probe.state == "stopped" and timer.stops == [123]
    clock.now = 90
    fire(probe)
    probe.stop()
    status = probe.snapshot()
    assert len(calls) == 1
    assert status["elapsed_seconds"] == 60
    assert status["stop_reason"] == "one_minute_limit"
    assert not status["timer_cleanup_pending"]
    assert timer.stops == [123]


def test_delayed_callback_stops_at_first_delivery_after_limit(env):
    _, _, clock, calls, _, _, start = env
    probe = start()
    clock.now = 75
    fire(probe)
    assert not calls and probe.state == "stopped"
    assert probe.snapshot()["elapsed_seconds"] == 75


def test_manual_stop_reason_and_elapsed_are_preserved(env):
    _, _, clock, _, _, _, start = env
    probe = start()
    clock.now = 4
    probe.stop()
    clock.now = 20
    probe.stop()
    assert probe.snapshot()["elapsed_seconds"] == 4
    assert probe.snapshot()["stop_reason"] == "manual"


def test_generation_and_diagnostics_memory_bounded(env):
    _, _, _, _, _, registry, start = env
    for _ in range(16):
        probe = start()
        probe.stop()
    for _ in range(100):
        probe.emit("x" * 1000)
    assert len(probe.events) == 32
    assert all(len(event) <= 500 for event in probe.events)
    with pytest.raises(RuntimeError, match="16 generations"):
        start()
    assert len(registry["retained"]) == 16


def test_closed_console_does_not_break_callbacks(env):
    _, _, clock, _, _, _, start = env
    probe = start()

    def broken_report(_):
        raise OSError("Console closed")

    probe.report = broken_report
    clock.now = 3
    fire(probe)
    assert probe.api_calls == 1 and probe.error is None


def test_stop_script_uses_retained_state(monkeypatch, env):
    _, timer, _, _, _, registry, start = env
    probe = start()
    monkeypatch.setattr(builtins, "_clo3d_mcp_p0", registry, raising=False)
    load("clo3d_mcp_probe_stop.py").main()
    assert probe.state == "stopped" and timer.stops == [123]
    assert builtins._clo3d_mcp_p0["retained"][0] is probe


def test_probe_path_does_not_write_ipc_files(monkeypatch, env):
    _, _, clock, _, _, _, start = env

    def forbidden(*args, **kwargs):
        raise AssertionError("File access from probe")

    monkeypatch.setattr(builtins, "open", forbidden)
    probe = start()
    clock.now = 3
    fire(probe)
    probe.stop()
    assert probe.api_calls == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Win32 timer ABI test")
def test_real_windows_timer_in_isolated_process():
    """Real user32 handles/dispatch, no CLO/API/UI automation. Hard process timeout."""
    script = '''
import ctypes
from ctypes import wintypes as wt
import importlib.util
import sys
spec = importlib.util.spec_from_file_location("probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
backend = module.WindowsTimer()
assert isinstance(backend.visible_window_threads(), set)
user32 = backend.user32
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.GetMessageW.restype = wt.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
owner = backend.thread_id()
seen = []
def tick(hwnd, msg, timer_id, timestamp):
    seen.append((backend.thread_id(), timer_id))
    if len(seen) == 2:
        backend.stop(timer_id)
        user32.PostQuitMessage(0)
callback = backend.wrap(tick)
timer_id = backend.start(callback)
message = wt.MSG()
while True:
    result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
    if result == 0:
        break
    if result == -1:
        raise ctypes.WinError(ctypes.get_last_error())
    user32.DispatchMessageW(ctypes.byref(message))
assert seen == [(owner, timer_id), (owner, timer_id)], seen
print("real Windows timer: two callbacks on registering thread; killed")
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT / "plugin" / "clo3d_mcp_probe.py")],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "two callbacks" in result.stdout
