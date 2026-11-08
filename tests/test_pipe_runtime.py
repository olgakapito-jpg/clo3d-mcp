"""Deterministic P1 state-machine faults. No real CLO or OS pipe here."""

from pathlib import Path
import builtins
import importlib.util
from types import SimpleNamespace

import pytest

from clo3d_mcp import pipe_runtime as runtime
from clo3d_mcp.pipe_session import Executor
from clo3d_mcp.protocol import Decoder, ProtocolError, encode, message


class Timer:
    tid = 42
    windows = {42}
    fail_stop = False
    fail_start = False

    def thread_id(self):
        return self.tid

    def visible_window_threads(self):
        return self.windows

    def wrap(self, callback):
        return callback

    def start(self, callback):
        if self.fail_start:
            raise OSError("timer registration")
        return 123

    def stop(self, timer_id):
        assert timer_id == 123
        if self.fail_stop:
            raise OSError("timer cleanup")


class Process:
    pid = 456
    code = None
    terminated = 0

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated += 1
        self.code = 1


class Pipe:
    closed = False
    closing = False
    ready_to_close = True

    def begin_close(self):
        self.closing = True

    def poll_close(self):
        if self.ready_to_close:
            self.closed = True
        return self.closed


class Channel:
    drained = True

    def __init__(self, frames=(), failure=None):
        self.frames = list(frames)
        self.failure = failure
        self.sent = []
        self.decoder = Decoder("s")

    def poll(self):
        if self.failure:
            raise self.failure
        frames, self.frames = self.frames, []
        return frames

    def send(self, frame):
        self.sent.append(frame)


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 100.0)
    result = runtime.PipeProbe(Timer(), lambda: 5, 1, report=lambda _: None)
    result.timer_id = 123
    result.callback = result.on_timer
    result.process = Process()
    result.executor = Executor("s", result.key, 456, result.read_count)
    result.executor.state = "ready"
    result.pipe = Pipe()
    result.channel = Channel()
    result.state = "active"
    return result


def tick(probe):
    probe.on_timer(None, 0x113, 123, 0)


def broken():
    error = OSError("peer disconnected")
    error.winerror = 109
    return error


def test_reentrant_and_stale_callback_never_dispatch(probe):
    probe.busy = True
    tick(probe)
    assert probe.reentrant_ticks == 1 and probe.ticks == 0
    probe.busy = False
    probe.stop()
    tick(probe)  # finish process cleanup
    before = probe.ticks
    tick(probe)
    assert probe.state == "stopped" and probe.ticks == before
    assert probe.process.terminated == 1


def test_wrong_thread_never_calls_api(probe):
    probe.timer.tid = 99
    tick(probe)
    assert probe.executor.jobs == 0 and probe.state == "stopping"
    assert probe.error == "RuntimeError"
    probe.timer.tid = 42
    tick(probe)
    tick(probe)
    assert probe.state == "failed"


def test_stop_retains_pending_pipe_before_terminating_child(probe):
    pipe = probe.pipe
    pipe.ready_to_close = False
    probe.stop()
    tick(probe)
    assert probe.pipe is pipe and probe.process.terminated == 0
    assert probe.timer_id == 123 and probe.key is not None
    pipe.ready_to_close = True
    tick(probe)
    tick(probe)
    assert probe.state == "stopped" and probe.key is None
    assert probe.executor.key is None and probe.timer_id is None


def test_failed_timer_cleanup_remains_retained_and_retriable(probe):
    probe.process.code = 0
    probe.timer.fail_stop = True
    tick(probe)
    tick(probe)
    assert probe.timer_id == 123 and probe.state == "stopping"
    probe.timer.fail_stop = False
    tick(probe)
    assert probe.timer_id is None and probe.state == "failed"


@pytest.mark.parametrize("code", [0, 1])
def test_child_exit_before_stop_is_failure_even_if_zero(probe, code):
    probe.process.code = code
    tick(probe)
    tick(probe)
    assert probe.state == "failed"
    assert probe.stop_reason == "child_exit" and probe.executor.jobs == 0


def test_successful_child_exit_can_race_stop_ack_poll(probe):
    probe.state = "draining_stop"
    probe.process.code = 0
    tick(probe)
    tick(probe)
    assert probe.state == "stopped" and probe.stop_reason == "peer_stop"


def test_peer_close_after_ack_waits_for_actual_exit_code(probe):
    probe.state = "draining_stop"
    probe.channel.failure = broken()
    tick(probe)
    tick(probe)
    assert probe.state == "stopping" and probe.process.terminated == 0
    probe.process.code = 1
    tick(probe)
    assert probe.state == "failed" and probe.error == "diagnostic_child_failed"


def test_stop_ack_does_not_wait_forever_for_child(probe, monkeypatch):
    probe.stop("peer_stop")
    assert probe.process.terminated == 0
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 102.1)
    tick(probe)
    tick(probe)
    assert probe.process.terminated == 1 and probe.state == "failed"


def test_batch_of_jobs_rejected_before_any_api_call(probe):
    job = message("JOB", "s", job_id="j", command="get_pattern_count", params={})
    probe.channel.frames = [job, job]
    tick(probe)
    assert probe.executor.api_calls == 0 and probe.error == "ProtocolError"


def test_manual_stop_during_api_does_not_send_on_closing_pipe(probe):
    channel = probe.channel

    def read():
        tick(probe)  # emulate native API pumping Windows messages
        probe.stop()
        return 3

    probe.executor.read_count = read
    channel.frames = [message("JOB", "s", job_id="j", command="get_pattern_count", params={})]
    tick(probe)
    assert probe.executor.api_calls == 1 and not channel.sent
    assert probe.reentrant_ticks == 1
    tick(probe)
    tick(probe)
    assert probe.state == "stopped"


def test_mid_frame_disconnect_fails_without_reconnect_or_replay(probe):
    probe.channel.decoder.feed(encode(message("READY", "s"))[:7])
    probe.channel.failure = broken()
    tick(probe)
    assert probe.error == "ProtocolError" and probe.disconnects == 0
    assert probe.executor.jobs == 0


def test_clean_disconnect_enters_reconnect_without_job_replay(probe):
    probe.channel.failure = broken()
    tick(probe)
    assert probe.state == "reconnecting" and probe.disconnects == 1
    assert probe.executor.state == "disconnected" and probe.executor.jobs == 0


def test_global_deadline_stops_without_calling_api(probe, monkeypatch):
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 191.0)
    tick(probe)
    assert probe.stop_reason == "ninety_second_limit"
    assert probe.executor.api_calls == 0


def test_idempotent_start_does_not_spawn_another_child(probe):
    registry = {"current": probe, "retained": [probe]}
    assert runtime.start(registry, Timer(), lambda: 0, None, None) is probe
    assert len(registry["retained"]) == 1


@pytest.mark.parametrize("failure", ["ui", "timer", "spawn"])
def test_failed_start_cleans_timer_and_keeps_callback_reference(monkeypatch, failure):
    timer = Timer()
    if failure == "ui":
        timer.windows = {99}
    if failure == "timer":
        timer.fail_start = True
    monkeypatch.setattr(runtime, "command", lambda *_: ["explicit-python"])

    def fail(*args, **kwargs):
        raise OSError("cannot spawn")

    monkeypatch.setattr(runtime.subprocess, "Popen", fail)
    registry = {}
    with pytest.raises((RuntimeError, OSError)):
        runtime.start(registry, timer, lambda: 0, Path("python"), Path("."))
    failed = registry["current"]
    assert failed.state == "failed" and failed.timer_id is None
    assert registry["retained"] == [failed]
    if failure != "ui":
        assert failed.callback is not None


def test_decoder_stops_at_bounded_message_count():
    decoder = Decoder("s")
    with pytest.raises(ProtocolError):
        decoder.feed(encode(message("READY", "s")) * 20, max_messages=4)
    assert decoder.failed and not decoder.buffer


def test_p2_profile_selects_only_queue_child_and_preserves_explicit_pid(monkeypatch):
    process = Process()
    captured = {}
    monkeypatch.setattr(runtime, "command", lambda *_: ["explicit-base-python", "-m", "clo3d_mcp.pipe_diagnostic"])

    def spawn(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return process

    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    messages = []
    probe = runtime.PipeProbe(Timer(), lambda: 0, 1, messages.append, profile="p2")
    probe.start(Path("python"), Path("."))
    assert captured["args"] == ["explicit-base-python", "-m", "clo3d_mcp.queue_diagnostic"]
    assert probe.executor.server_pid == process.pid
    assert messages[0].startswith("[CLO P2]")
    assert captured["kwargs"]["close_fds"] is True
    assert "CLO_MCP_P1_KEY" in captured["kwargs"]["env"]
    assert probe.key.hex() not in str(messages)
    probe.stop()
    tick(probe)
    assert probe.state == "stopped"


def load_plugin(name):
    path = Path(__file__).resolve().parents[1] / "plugin" / name
    spec = importlib.util.spec_from_file_location("queue_test_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("profile, other", [("p1", "p2"), ("p2", "p1")])
def test_diagnostics_cannot_overlap(monkeypatch, profile, other):
    monkeypatch.setattr(builtins, "_clo3d_mcp_p0", {}, raising=False)
    active = SimpleNamespace(timer_id=123, busy=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_" + other, {"current": active}, raising=False)
    module = load_plugin("clo3d_mcp_pipe_probe.py")
    with pytest.raises(RuntimeError, match="other pipe diagnostic"):
        module.main(profile=profile)


def test_p2_stop_does_not_touch_p1(monkeypatch):
    calls = []
    monkeypatch.setattr(builtins, "_clo3d_mcp_p1", {
        "version": 1, "current": SimpleNamespace(stop=lambda: calls.append("p1"))}, raising=False)
    monkeypatch.setattr(builtins, "_clo3d_mcp_p2", {
        "version": 1, "current": SimpleNamespace(stop=lambda: calls.append("p2"))}, raising=False)
    load_plugin("clo3d_mcp_queue_probe_stop.py").main()
    assert calls == ["p2"]


def test_p2_launcher_import_does_not_start_runtime_or_legacy(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"mcp", "uvicorn", "clo3d_mcp_plugin", "pattern_api", "ctypes"}:
            raise AssertionError("Unexpected import " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    load_plugin("clo3d_mcp_queue_probe.py")
    load_plugin("clo3d_mcp_queue_probe_stop.py")


def test_service_repeated_stop_waits_for_clean_exit(probe):
    probe.profile = "service"
    probe.service_ready = True
    probe.stop()
    assert probe.state == "requesting_stop" and not probe.service_ready
    probe.stop()
    assert len(probe.channel.sent) == 1 and probe.process.terminated == 0
    probe.process.code = 0
    tick(probe)
    tick(probe)
    assert probe.state == "stopped" and probe.timer_id is None and probe.pipe is None


def test_service_stop_fallback_is_bounded_and_specific(probe, monkeypatch):
    probe.profile = "service"
    probe.stop()
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 103.1)
    tick(probe)
    tick(probe)
    tick(probe)  # observe termination; never wait synchronously inside a tick
    assert probe.process.terminated == 1 and probe.state == "failed"
    assert probe.error == "server_shutdown_timeout"


def test_service_ready_has_no_diagnostic_ninety_second_limit(probe, monkeypatch):
    probe.profile = "service"
    probe.service_ready = True
    monkeypatch.setattr(runtime.time, "monotonic", lambda: 5000)
    tick(probe)
    assert probe.state == "active" and probe.error is None


def test_service_busy_port_exit_is_actionable(probe):
    probe.profile = "service"
    probe.process.code = 3
    tick(probe)
    tick(probe)
    assert probe.state == "failed" and probe.error == "http_bind_failed"


def test_service_launcher_repeat_start_does_not_import_or_spawn(monkeypatch, probe):
    probe.profile = "service"
    monkeypatch.setattr(builtins, "_clo3d_mcp_service", {
        "version": 1, "current": probe, "retained": [probe]}, raising=False)
    for name in ("p0", "p1", "p2"):
        monkeypatch.setattr(builtins, "_clo3d_mcp_" + name, {}, raising=False)
    load_plugin("clo3d_mcp_start.py").main()
    assert "ALREADY_STARTED" in probe.events[-1] and probe.process.terminated == 0
