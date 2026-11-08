"""Isolated actual-Windows tests. Not pytest-collected, not a CLO script."""

import ctypes as ct
from ctypes import wintypes as wt
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

from clo3d_mcp.protocol import message
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe, WindowsAPI, OVERLAPPED, _live


def until(action, predicate=lambda value: value is not None, seconds=3):
    deadline = time.monotonic() + seconds
    while True:
        value = action()
        if predicate(value):
            return value
        if time.monotonic() > deadline:
            raise TimeoutError("worker deadline")
        threading.Event().wait(0.001)


def close(pipe, reuse=False):
    pipe.begin_close()
    until(lambda: pipe.poll_close(reuse), bool)


def pair(race=False):
    name = "clo3d_mcp_" + secrets.token_hex(16)
    server = Pipe.listen(name)
    connect = None if race else server.connect()
    client = Pipe.try_open(name)
    assert client is not None
    if race:
        connect = server.connect()
    until(connect.poll)
    assert server.peer_pid() == client.peer_pid() == os.getpid()
    return server, client


def basic():
    assert ct.sizeof(OVERLAPPED) == (32 if ct.sizeof(ct.c_void_p) == 8 else 20)
    for race in (False, True):
        server, client = pair(race)
        read = server.read()
        assert read.poll() is None
        try:
            server.read()
            raise AssertionError("duplicate read allowed")
        except RuntimeError:
            pass
        write = client.write("日本語😀".encode("utf-8"))
        assert until(write.poll) == len("日本語😀".encode("utf-8"))
        assert until(read.poll).decode("utf-8") == "日本語😀"
        pending = server.read()
        close(server)
        assert pending.done and pending.error == 995
        close(client)
    assert not _live


def reconnect():
    name = "clo3d_mcp_" + secrets.token_hex(16)
    server = Pipe.listen(name)
    try:
        try:
            Pipe.listen(name)
            raise AssertionError("duplicate listener allowed")
        except OSError as exc:
            # FIRST_PIPE_INSTANCE / max-instances collision: both reject it.
            assert exc.winerror in (5, 231)
        for _ in range(3):
            op = server.connect()
            client = Pipe.try_open(name)
            until(op.poll)
            pending = client.read()
            close(server, reuse=True)
            try:
                until(pending.poll)
                raise AssertionError("broken peer was not detected")
            except OSError as exc:
                assert exc.winerror in (109, 232, 233)
            close(client)
    finally:
        close(server)
    assert not _live


def fragmentation():
    server, client = pair()
    receiver = Channel(server, "s")
    sender = Channel(client, "s")
    value = message("RESULT", "s", job_id="j", result={"text": "лекало😀" * 20000})
    sender.send(value)
    received = []

    def exchange():
        sender.poll()
        received.extend(receiver.poll())
        return bool(received) and sender.drained

    until(exchange, bool, 5)
    assert received == [value]
    close(server)
    close(client)
    assert not _live


def stalled_writer():
    server, client = pair()
    # No peer reads. Eventually an OVERLAPPED write is pending, not a UI wait.
    pending = None
    for _ in range(256):
        pending = server.write(b"x" * 16384)
        if pending.poll() is None:
            break
    assert pending is not None and not pending.done
    close(server)
    assert pending.done
    close(client)
    assert not _live


def pending_connect_and_handles():
    api = WindowsAPI()
    count_fn = api.k.GetProcessHandleCount
    count_fn.argtypes = [wt.HANDLE, ct.POINTER(wt.DWORD)]
    count_fn.restype = wt.BOOL

    def handle_count():
        count = wt.DWORD()
        api.check(count_fn(api.k.GetCurrentProcess(), ct.byref(count)))
        return count.value

    # Warm up DLL bindings/ctypes before taking the process-local baseline.
    server, client = pair()
    close(server)
    close(client)
    before = handle_count()
    for _ in range(10):
        server = Pipe.listen("clo3d_mcp_" + secrets.token_hex(16))
        pending = server.connect()
        assert pending.poll() is None
        close(server)
        assert pending.done and pending.error == 995
        server, client = pair()
        server.read()
        client.read()
        close(client)
        close(server)
    assert not _live
    assert handle_count() == before


def midframe():
    from clo3d_mcp.protocol import ProtocolError, encode

    server, client = pair()
    receiver = Channel(server, "s")
    fragment = encode(message("READY", "s"))[:7]
    read = server.read()
    until(client.write(fragment).poll)
    data = until(read.poll)
    assert receiver.decoder.feed(data) == []
    close(client)
    try:
        until(server.read().poll)
        raise AssertionError("broken writer was not detected")
    except OSError as exc:
        assert exc.winerror in (109, 232, 233)
    try:
        receiver.decoder.eof()
        raise AssertionError("incomplete frame was accepted")
    except ProtocolError:
        pass
    close(server)
    assert not _live


def python_identity():
    from clo3d_mcp.child_python import command

    env = os.environ.copy()
    args = command(sys.executable, env)
    args[1:] = ["-c", "import json, os, sys; print(json.dumps([os.getpid(), sys.executable, sys.prefix]))"]
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, text=True)
    stdout = process.communicate(timeout=5)[0]
    assert process.returncode == 0
    pid, executable, prefix = json.loads(stdout)
    assert pid == process.pid, "Popen must own the actual interpreter, not a venv redirector"
    assert Path(executable).resolve() == Path(sys.executable).resolve()
    assert Path(prefix).resolve() == Path(sys.prefix).resolve()


def bad_authentication():
    from clo3d_mcp.child_python import command
    from clo3d_mcp.pipe_session import Executor

    root = Path(__file__).resolve().parents[1]
    name = "clo3d_mcp_" + secrets.token_hex(16)
    env = os.environ.copy()
    env.update(CLO_MCP_P1_PIPE=name, CLO_MCP_P1_SESSION="s",
               CLO_MCP_P1_KEY=(b"a" * 32).hex(), CLO_MCP_P1_CLO_PID=str(os.getpid()))
    process = subprocess.Popen(command(sys.executable, env), env=env, cwd=root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = None
    try:
        client = until(lambda: Pipe.try_open(name))
        executor = Executor("s", b"b" * 32, process.pid, lambda: 0)
        channel = Channel(client, "s")
        channel.send(executor.connected(client.peer_pid()))
        until(lambda: (channel.poll(), channel.drained)[1], bool)
        assert process.wait(timeout=5) == 1
        assert executor.jobs == 0 and executor.handshakes == 0
    finally:
        if client is not None:
            close(client)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
    assert not _live


def external_roundtrip(profile="p1"):
    from clo3d_mcp.pipe_runtime import PipeProbe

    class Timer:
        def thread_id(self):
            return 42

        def visible_window_threads(self):
            return {42}

        def wrap(self, fn):
            return fn

        def start(self, fn):
            return 123

        def stop(self, timer_id):
            assert timer_id == 123

    root = Path(__file__).resolve().parents[1]
    calls = []

    def read():
        calls.append(1)
        return 9

    probe = PipeProbe(Timer(), read, 1, report=lambda _: None, profile=profile)
    try:
        probe.start(sys.executable, root)
        next_tick = 0.0

        def tick():
            nonlocal next_tick
            now = time.monotonic()
            if now < next_tick:
                return False
            # P0's actual timer interval, not an unrealistically fast UI pump.
            next_tick = now + 0.25
            probe.on_timer(None, 0x113, 123, 0)
            return probe.state in ("stopped", "failed")

        until(tick, bool, 12)
        status = probe.snapshot()
        assert probe.state == "stopped", status
        expected = (2, 1, 2, 4) if profile == "p1" else (1, 0, 1, 5)
        assert (probe.connections, probe.disconnects, probe.executor.handshakes,
                probe.executor.jobs) == expected, status
        assert calls == [1, 1] and probe.exit_code == 0, status
        assert probe.timer_id is None and probe.pipe is None
    finally:
        probe.stop()
        if probe.process is not None and probe.process.poll() is None:
            probe.process.terminate()
            probe.process.wait(timeout=3)
    assert not _live


def queue_probe_roundtrip():
    external_roundtrip(profile="p2")


def queue_executor():
    """Separate Python process, real pipe client, fake read-only CLO API."""
    from clo3d_mcp.pipe_session import Executor

    name = os.environ.pop("CLO_MCP_TEST_PIPE")
    key = bytes.fromhex(os.environ.pop("CLO_MCP_TEST_KEY"))
    parent_pid = int(os.environ.pop("CLO_MCP_TEST_PID"))
    client = until(lambda: Pipe.try_open(name))
    executor = Executor("s", key, parent_pid, lambda: 7)
    channel = Channel(client, "s")
    channel.send(executor.connected(client.peer_pid()))
    try:
        def pump():
            for frame in channel.poll():
                for response in executor.receive(frame):
                    channel.send(response)
            return executor.state == "stopping" and channel.drained

        until(pump, bool, 8)
        assert executor.jobs == 3 and executor.api_calls == 1
    finally:
        close(client)
    assert not _live


def queue_roundtrip():
    """External async FIFO + authenticated pipe to a separate executor process."""
    import asyncio
    from clo3d_mcp.async_jobs import AsyncJobQueue
    from clo3d_mcp.child_python import command
    from clo3d_mcp.jobs import QueueError
    from clo3d_mcp.queue_session import QueueSession

    async def scenario():
        name = "clo3d_mcp_" + secrets.token_hex(16)
        key = secrets.token_bytes(32)
        pipe = Pipe.listen(name)
        connect = pipe.connect()
        env = os.environ.copy()
        env.update(CLO_MCP_TEST_PIPE=name, CLO_MCP_TEST_KEY=key.hex(),
                   CLO_MCP_TEST_PID=str(os.getpid()))
        args = command(sys.executable, env)
        args[1:] = [str(Path(__file__).resolve()), "queue_executor"]
        process = subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        queue = None
        session = None
        tasks = []
        try:
            until(connect.poll)
            now = [0.0]
            queue = AsyncJobQueue("s", clock=lambda: now[0])
            session = QueueSession(queue, key, process.pid)
            session.connect(pipe.peer_pid())
            channel = Channel(pipe, "s")
            deadline = time.monotonic() + 8
            scheduled = False
            stop_sent = False
            stop_ack = False
            order = []
            while not stop_ack:
                assert time.monotonic() < deadline, queue.status()
                for frame in channel.poll():
                    if frame["kind"] == "STOP" and stop_sent:
                        stop_ack = True
                    else:
                        for response in session.receive(frame):
                            channel.send(response)
                if queue.status()["ready"] and not scheduled:
                    tasks = [asyncio.create_task(queue.call(command, execution_timeout=1))
                             for command in ("ping", "get_pattern_count", "ping", "ping")]
                    await asyncio.sleep(0)
                    tasks[2].cancel()  # queued cancellation must not reach API
                    await asyncio.sleep(0)
                    scheduled = True
                frame = session.dispatch()
                if frame is not None:
                    order.append(frame["job_id"])
                    channel.send(frame)
                    if frame["command"] == "get_pattern_count":
                        # Deterministic dispatch deadline before next I/O poll:
                        # no timing assumption about child scheduling.
                        now[0] = 1.0
                        queue.tick()
                        assert queue.status()["active_state"] == "unknown"
                        assert session.dispatch() is None
                        await asyncio.sleep(0)
                if (scheduled and len(order) == 3 and queue.status()["ready"]
                        and queue.status()["active_id"] is None and not stop_sent):
                    assert order == ["job_1", "job_2", "job_4"]
                    assert queue.lookup("s", "job_2").state == "succeeded"
                    channel.send(message("STOP", "s"))
                    stop_sent = True
                await asyncio.sleep(0.001)  # external process, never UI
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            assert outcomes[0] == outcomes[3] == {"pong": True}
            assert isinstance(outcomes[1], QueueError) and outcomes[1].code == "outcome_unknown"
            assert isinstance(outcomes[2], asyncio.CancelledError)
            assert process.wait(timeout=3) == 0
        finally:
            if session is not None:
                session.disconnect()
            if queue is not None:
                queue.close()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            close(pipe)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=3)
        assert not _live

    asyncio.run(scenario())


def service_roundtrip(load=False):
    """Full CLO launcher model -> child -> official HTTP -> pipe -> fake API."""
    import asyncio
    import socket
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from clo3d_mcp.pipe_runtime import PipeProbe
    from unittest.mock import patch

    class Timer:
        def thread_id(self):
            return 42

        def visible_window_threads(self):
            return {42}

        def wrap(self, fn):
            return fn

        def start(self, fn):
            return 123

        def stop(self, timer_id):
            assert timer_id == 123

    async def scenario():
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        count = [3]

        def create():
            count[0] += 1
            return {"created": True, "pattern_count": count[0]}

        probe = PipeProbe(Timer(), lambda: count[0], 1, report=lambda _: None,
                          profile="service", create_rectangle=create, port=port)
        root = Path(__file__).resolve().parents[1]
        spawn = subprocess.Popen

        def audited_spawn(args, **kwargs):
            # Real owned child, same pinned handle/env/venv; only test bootstrap
            # differs. Any filesystem mutation exits 91, even if SDK catches errors.
            args = [args[0], str(Path(__file__).with_name("service_audit_bootstrap.py"))]
            kwargs["stderr"] = None  # inherited worker stderr, captured by pytest
            return spawn(args, **kwargs)

        with patch("clo3d_mcp.pipe_runtime.subprocess.Popen", audited_spawn if load else spawn):
            probe.start(sys.executable, root)

        async def pump():
            while probe.state not in ("stopped", "failed"):
                probe.on_timer(None, 0x113, 123, 0)
                await asyncio.sleep(0.001 if load else 0.05)

        pumping = asyncio.create_task(pump())
        try:
            async def ready():
                while not probe.service_ready:
                    assert probe.state != "failed", probe.snapshot()
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(ready(), 10)
            url = "http://127.0.0.1:%d/mcp" % port
            async with streamable_http_client(url) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    # Readiness ACK is flushed by another UI tick. Poll observable
                    # state with a bound instead of assuming a scheduling delay.
                    async def acknowledged():
                        while not (await client.call_tool("transport_status")).structuredContent["ready"]:
                            await asyncio.sleep(0.001)
                    await asyncio.wait_for(acknowledged(), 3)
                    if load:
                        async def requests():
                            for batch in range(100):
                                results = await asyncio.gather(*[
                                    client.call_tool("ping" if n % 2 else "get_pattern_count")
                                    for n in range(10)])
                                for n, reply in enumerate(results):
                                    expected = {"ok": True, "pong": True} if n % 2 else {
                                        "ok": True, "pattern_count": 3}
                                    assert not reply.isError and reply.structuredContent == expected
                            # Status may race the final READY credit; wait for it.
                            while True:
                                status = (await client.call_tool("transport_status")).structuredContent
                                if status["active_id"] is None:
                                    break
                                await asyncio.sleep(0.001)
                            assert status["cached"] == 128 and status["waiting"] == status["waiters"] == 0
                            assert status["ready"] and not status["quarantined"]
                        started = time.monotonic()
                        await asyncio.wait_for(requests(), 75)
                        assert probe.executor.jobs == 1001  # includes startup verification
                        assert probe.executor.high_water == 1001 and not probe.executor.seen
                        assert probe.executor.api_calls == 500 and count == [3]
                        print("LOAD requests=1000 concurrency=10 elapsed=%.3f cached=128 no_file_writes=True" % (
                            time.monotonic() - started))
                    else:
                        await service_client_checks(client, probe, count)
            probe.stop()
            await asyncio.wait_for(pumping, 6)
            assert probe.state == "stopped", probe.snapshot()
            assert probe.exit_code == 0 and probe.timer_id is None and probe.pipe is None
        finally:
            if probe.state not in ("stopped", "failed"):
                probe.stop()
            if probe.process.poll() is None:
                probe.process.terminate()
                probe.process.wait(timeout=3)
            if not pumping.done():
                await asyncio.wait_for(pumping, 3)
        assert not _live

    asyncio.run(scenario())


async def service_client_checks(client, probe, count):
    import asyncio

    assert (await client.call_tool("ping")).structuredContent == {"ok": True, "pong": True}
    assert (await client.call_tool("get_pattern_count")).structuredContent["pattern_count"] == 3
    replies = await asyncio.gather(*[client.call_tool("ping") for _ in range(3)])
    assert all(value.structuredContent["pong"] is True for value in replies)
    made = await client.call_tool("create_test_rectangle")
    assert made.structuredContent == {"ok": True, "created": True, "pattern_count": 4}
    assert count == [4]
    assert (await client.call_tool("get_pattern_count")).structuredContent["pattern_count"] == 4
    info = (await client.call_tool("get_session_info")).structuredContent
    assert info["server_pid"] == probe.process.pid and info["clo_pid"] == os.getpid()
    assert info["ready"]


def service_load():
    service_roundtrip(load=True)


def malformed_frames():
    """Actual pipe bytes, not merely codec unit inputs; reject and release I/O."""
    import struct
    from clo3d_mcp.protocol import ProtocolError

    for payload in (struct.pack("<I", 1024 * 1024 + 1),
                    struct.pack("<I", 1) + b"\xff",
                    struct.pack("<I", 2) + b"[]"):
        server, client = pair()
        try:
            channel = Channel(server, "s")
            op = client.write(payload)
            until(op.poll)
            try:
                until(channel.poll, lambda frames: bool(frames))
            except ProtocolError:
                pass
            else:
                raise AssertionError("Malformed pipe frame accepted")
        finally:
            close(server)
            close(client)
        assert not _live


def service_parent_exit():
    """Real inherited pinned process handle; child exits even without callbacks."""
    import socket
    from clo3d_mcp.child_python import command
    from clo3d_mcp.transport.winprocess import ProcessHandle

    env = os.environ.copy()
    args = command(sys.executable, env)
    args[1:] = ["-c", "import sys; sys.stdin.buffer.read(1)"]
    parent = subprocess.Popen(args, env=env, stdin=subprocess.PIPE)
    monitor = ProcessHandle(parent.pid)
    child = None
    try:
        assert monitor.pid() == parent.pid and monitor.alive()
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        env.update(CLO_MCP_P1_PIPE="clo3d_mcp_" + secrets.token_hex(16),
                   CLO_MCP_P1_SESSION="s", CLO_MCP_P1_KEY=secrets.token_hex(32),
                   CLO_MCP_P1_CLO_PID=str(parent.pid), CLO_MCP_PARENT_HANDLE=str(monitor.handle),
                   CLO_MCP_HTTP_PORT=str(port))
        args = command(sys.executable, env)
        args[-1] = "clo3d_mcp.transport_server"
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": [monitor.handle]}
        child = subprocess.Popen(args, env=env, startupinfo=startup, close_fds=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def listening():
            with socket.socket() as sock:
                sock.settimeout(0.1)
                return sock.connect_ex(("127.0.0.1", port)) == 0

        until(listening, bool, 6)
        assert child.poll() is None
        parent.stdin.close()
        assert parent.wait(timeout=3) == 0
        assert not monitor.alive()
        assert child.wait(timeout=6) == 0
        assert not listening()
    finally:
        monitor.close()
        for process in (parent, child):
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=3)


if __name__ == "__main__":
    globals()[sys.argv[1]]()
    print("PASS " + sys.argv[1])
