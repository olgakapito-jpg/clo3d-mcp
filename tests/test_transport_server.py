"""Real HTTP and official SDK; simulated CLO/pipe tested separately on Windows."""

import asyncio
import socket

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CancelledNotification, CancelledNotificationParams, ClientNotification

from clo3d_mcp.protocol import message
from clo3d_mcp.transport_server import Service, build_mcp, run


class Parent:
    is_alive = True
    closed = False

    def alive(self):
        return self.is_alive

    def close(self):
        self.closed = True


async def bounded_until(predicate, seconds=3):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.001)
    await asyncio.wait_for(poll(), timeout=seconds)


def service(port):
    return Service("unused", "s", b"k" * 32, 123, Parent(), port=port)


def test_http_sdk_initialize_list_concurrent_calls_and_busy_status(monkeypatch):
    async def scenario():
        import clo3d_mcp.transport_server as module

        # No Windows pipe in this test; drive queue exactly like authenticated
        # pipe_loop. HTTP socket, SDK sessions and tools are real.
        async def simulated_pipe(svc):
            svc.queue.on_connected()
            svc.queue.on_ready()
            svc.executor_verified = True
            svc.ready_acknowledged = True
            while svc.parent.alive() and not svc.stop_requested:
                svc.queue.tick()
                await asyncio.sleep(0.001)
        monkeypatch.setattr(module, "pipe_loop", simulated_pipe)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        svc = service(port)
        running = asyncio.create_task(run(svc))
        try:
            await bounded_until(lambda: svc.status()["ready"])
            url = "http://127.0.0.1:%d/mcp" % port
            async with streamable_http_client(url) as (read, write, _):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    assert init.serverInfo.name == "CLO session"
                    tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                    assert set(tools) == {"ping", "get_pattern_count", "transport_status",
                                          "get_session_info", "create_test_rectangle"}
                    assert tools["create_test_rectangle"].annotations.idempotentHint is False
                    assert tools["get_pattern_count"].annotations.readOnlyHint is True
                    calls = [asyncio.create_task(client.call_tool("ping")),
                             asyncio.create_task(client.call_tool("get_pattern_count"))]
                    await bounded_until(lambda: svc.queue.status()["waiting"] == 2)
                    first = svc.queue.dispatch()
                    assert first["command"] == "ping"
                    status = await client.call_tool("transport_status")
                    assert status.structuredContent["active_state"] == "dispatched"
                    assert not calls[0].done()
                    svc.queue.receive(message("RESULT", "s", job_id=first["job_id"], result={"pong": True}))
                    svc.queue.on_ready()
                    second = svc.queue.dispatch()
                    assert second["command"] == "get_pattern_count"
                    svc.queue.receive(message("RESULT", "s", job_id=second["job_id"], result={"pattern_count": 8}))
                    svc.queue.on_ready()
                    replies = await asyncio.gather(*calls)
                    assert replies[0].structuredContent == {"ok": True, "pong": True}
                    assert replies[1].structuredContent == {"ok": True, "pattern_count": 8}
                    info = await client.call_tool("get_session_info")
                    assert info.structuredContent["session_id"] == "s"
                    assert info.structuredContent["clo_pid"] == 123
                    assert info.structuredContent["server_build"] == module.BUILD
                    assert "executor_build" in info.structuredContent
                    mutation = asyncio.create_task(client.call_tool("create_test_rectangle"))
                    await bounded_until(lambda: svc.queue.status()["waiting"] == 1)
                    job = svc.queue.dispatch()
                    assert job["command"] == "create_test_rectangle"
                    svc.queue.receive(message("RESULT", "s", job_id=job["job_id"],
                                              result={"created": True, "pattern_count": 9}))
                    svc.queue.on_ready()
                    assert (await mutation).structuredContent["created"] is True
                    # Explicit MCP cancellation notification over real HTTP.
                    # Cancelling only the local Python await is not a protocol
                    # cancellation and is deliberately not claimed as one.
                    for dispatched in (False, True):
                        request_id = client._request_id
                        pending = asyncio.create_task(client.call_tool("create_test_rectangle"))
                        await bounded_until(lambda: svc.queue.status()["waiting"] == 1)
                        job_id = svc.queue.queue.waiting[0]
                        if dispatched:
                            active = svc.queue.dispatch()
                        await client.send_notification(ClientNotification(CancelledNotification(
                            method="notifications/cancelled",
                            params=CancelledNotificationParams(requestId=request_id))))
                        await bounded_until(lambda: svc.queue.status()["waiters"] == 0)
                        await asyncio.gather(pending, return_exceptions=True)
                        if dispatched:
                            assert svc.queue.lookup("s", job_id).state == "dispatched"
                            assert svc.queue.dispatch() is None
                            svc.queue.receive(message("RESULT", "s", job_id=active["job_id"],
                                                      result={"created": True, "pattern_count": 10}))
                            svc.queue.on_ready()
                            assert svc.queue.lookup("s", job_id).state == "succeeded"
                        else:
                            assert svc.queue.lookup("s", job_id).state == "cancelled"
                            assert svc.queue.dispatch() is None
                    svc.queue.close()
                    unavailable = await client.call_tool("ping")
                    assert unavailable.isError is True
                    assert unavailable.structuredContent == {"ok": False, "error": "executor_unavailable"}
            async with httpx.AsyncClient() as http:
                headers = {"accept": "application/json, text/event-stream"}
                invalid_host = await http.post(url, headers={**headers, "host": "evil.example"}, json={})
                assert invalid_host.status_code == 421
                origin = await http.post(url, headers={**headers, "origin": "https://evil.example"}, json={})
                assert origin.status_code == 403
            svc.parent.is_alive = False
            assert await asyncio.wait_for(running, 4) == 0
            assert svc.parent.closed and svc.queue.status()["closed"]
        finally:
            svc.parent.is_alive = False
            if not running.done():
                await asyncio.wait_for(running, 4)
    asyncio.run(scenario())


def test_occupied_port_is_error_and_never_touched():
    async def scenario():
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            svc = service(occupied.getsockname()[1])
            with pytest.raises(OSError):
                await run(svc)
            assert occupied.fileno() != -1
            assert svc.parent.closed
            assert svc.queue.status()["closed"]
    asyncio.run(scenario())


def test_sdk_security_and_only_official_framework():
    svc = service(8765)
    mcp = build_mcp(svc)
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mcp, FastMCP)
    assert FastMCP.__module__ == "mcp.server.fastmcp.server"
    assert mcp.settings.host == "127.0.0.1"
    security = mcp.settings.transport_security
    assert security.enable_dns_rebinding_protection
    assert security.allowed_hosts == ["127.0.0.1:8765"]
    assert security.allowed_origins == []


def test_service_success_waits_for_own_ready_without_blocking_status():
    async def scenario():
        svc = service(8765)
        svc.queue.on_connected()
        svc.queue.on_ready()
        svc.http_serving = svc.executor_verified = svc.ready_acknowledged = True
        task = asyncio.create_task(svc.call("get_pattern_count"))
        await bounded_until(lambda: svc.queue.status()["waiting"] == 1)
        job = svc.queue.dispatch()["job_id"]
        svc.queue.receive(message("RESULT", "s", job_id=job, result={"pattern_count": 0}))
        await bounded_until(lambda: bool(svc.queue.release_waiters))
        assert not task.done()
        assert svc.status()["active_state"] == "succeeded" and svc.status()["waiters"] == 1
        svc.queue.on_ready()
        assert await task == {"ok": True, "pattern_count": 0}
        assert svc.status()["active_id"] is None and svc.status()["waiters"] == 0
    asyncio.run(scenario())


def test_release_errors_are_explicit_and_conservative_for_possible_scene_effects():
    from clo3d_mcp.transport_server import tool_error
    for code in ("executor_release_timeout", "executor_release_unavailable"):
        reply = tool_error(code)
        assert reply.isError
        assert reply.structuredContent == {"ok": False, "error": code, "scene_may_have_changed": True}


def test_missing_readiness_ack_is_bounded_and_never_dispatches_client_job(monkeypatch):
    import clo3d_mcp.transport_server as module

    async def scenario():
        svc = service(8765)
        svc.queue.on_connected()
        svc.queue.on_ready()
        verification = svc.queue.submit("ping")
        svc.queue.dispatch()
        svc.queue.receive(message("RESULT", "s", job_id=verification, result={"pong": True}))
        svc.queue.on_ready()
        svc.http_serving = True
        now = [0]
        sent = []

        class FakePipe:
            def connect(self):
                return self

            def poll(self):
                return True

            def peer_pid(self):
                return 123

            def begin_close(self):
                pass

            def poll_close(self):
                return True

        class FakeChannel:
            def __init__(self, *args):
                pass

            def poll(self):
                return []

            def send(self, frame):
                sent.append(frame)
                now[0] = 31

        monkeypatch.setattr(module.Pipe, "listen", lambda _: FakePipe())
        monkeypatch.setattr(module, "Channel", FakeChannel)
        monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(svc.queue, "submit", lambda *a, **k: verification)
        with pytest.raises(TimeoutError, match="readiness"):
            await module.pipe_loop(svc)
        assert [frame["kind"] for frame in sent] == ["SERVICE_READY"]
        assert not svc.status()["ready"] and svc.queue.status()["closed"]
    asyncio.run(scenario())


def test_http_queue_overflow_and_disconnect_release_all_callers_without_replay(monkeypatch):
    async def scenario():
        import clo3d_mcp.transport_server as module

        disconnect = asyncio.Event()

        async def simulated_pipe(svc):
            svc.queue.on_connected()
            svc.queue.on_ready()
            svc.executor_verified = svc.ready_acknowledged = True
            await disconnect.wait()
            svc.session.disconnect()
            svc.queue.close()
            # Keep HTTP live to observe error delivery/status before stopping.
            while svc.parent.alive():
                await asyncio.sleep(0.001)

        monkeypatch.setattr(module, "pipe_loop", simulated_pipe)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            svc = service(probe.getsockname()[1])
        running = asyncio.create_task(run(svc))
        try:
            await bounded_until(lambda: svc.status()["ready"])
            async with streamable_http_client("http://127.0.0.1:%d/mcp" % svc.port) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    active = asyncio.create_task(client.call_tool("ping"))
                    await bounded_until(lambda: svc.queue.status()["waiting"] == 1)
                    dispatched = svc.queue.dispatch()
                    waiting = [asyncio.create_task(client.call_tool("get_pattern_count")) for _ in range(32)]
                    await bounded_until(lambda: svc.queue.status()["waiting"] == 32)
                    overflow = await client.call_tool("ping")
                    assert overflow.isError and overflow.structuredContent == {"ok": False, "error": "queue_full"}
                    status = (await client.call_tool("transport_status")).structuredContent
                    assert status["waiting"] == 32 and status["active_id"] == dispatched["job_id"]
                    disconnect.set()
                    replies = await asyncio.wait_for(asyncio.gather(active, *waiting), 3)
                    assert replies[0].isError and replies[0].structuredContent["error"] == "outcome_unknown"
                    assert all(reply.isError and reply.structuredContent["error"] == "executor_unavailable"
                               for reply in replies[1:])
                    assert svc.queue.status()["waiters"] == svc.queue.status()["waiting"] == 0
                    assert svc.queue.status()["quarantined"] and svc.queue.dispatch() is None
                    assert svc.queue.queue.sequence == 33  # overflow never assigned an ID
            svc.parent.is_alive = False
            assert await asyncio.wait_for(running, 4) == 0
        finally:
            disconnect.set()
            svc.parent.is_alive = False
            if not running.done():
                await asyncio.wait_for(running, 4)
    asyncio.run(scenario())


def test_pattern_package_real_http_validates_raw_arguments_and_runs_stateful_executor(monkeypatch):
    from test_pattern_api import POINTS, adapter
    from clo3d_mcp.pattern_contract import PATTERN_COMMANDS

    async def scenario():
        import clo3d_mcp.transport_server as module
        native, api = adapter()

        async def simulated_pipe(svc):
            svc.queue.on_connected()
            svc.queue.on_ready()
            svc.executor_verified = svc.ready_acknowledged = True
            while svc.parent.alive() and not svc.stop_requested:
                svc.queue.tick()
                job = svc.queue.dispatch()
                if job is not None:
                    result = api(job["command"], job["params"])
                    svc.queue.receive(message("RESULT", "s", job_id=job["job_id"], result=result))
                    svc.queue.on_ready()
                await asyncio.sleep(0.001)

        monkeypatch.setattr(module, "pipe_loop", simulated_pipe)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            svc = Service("unused", "s", b"k" * 32, 123, Parent(),
                          port=probe.getsockname()[1], pattern_package=True)
        running = asyncio.create_task(run(svc))
        try:
            await bounded_until(lambda: svc.status()["ready"])
            async with streamable_http_client("http://127.0.0.1:%d/mcp" % svc.port) as (read, write, _):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = {t.name: t for t in (await client.list_tools()).tools}
                    assert set(PATTERN_COMMANDS) <= set(tools)
                    assert tools["delete_pattern"].annotations.destructiveHint
                    assert not tools["move_pattern_relative"].annotations.idempotentHint
                    for command, args in [
                        ("ping", {"extra": 1}),
                        ("get_pattern_count", {"extra": 1}),
                        ("transport_status", {"extra": 1}),
                        ("get_session_info", {"extra": 1}),
                        ("create_test_rectangle", {"extra": 1}),
                        ("get_pattern_list", {"extra": 1}),
                        ("get_pattern_geometry", {"pattern_index": True}),
                        ("get_pattern_geometry", {"pattern_index": "0"}),
                        ("get_pattern_lines", {"pattern_index": 0, "expected_name": "panel", "extra": 1}),
                        ("get_pattern_lines", {"pattern_index": True, "expected_name": "panel"}),
                        ("create_pattern", {"points": "[[0,0],[10,0],[0,10]]", "name": "a"}),
                        ("create_pattern", {"points": [[0, 0], [10, 0], [0, True]], "name": "a"}),
                        ("create_pattern", {"points": POINTS, "name": "a", "vertex_types": [0, 1, 0, 0]}),
                    ]:
                        reply = await client.call_tool(command, args)
                        assert reply.isError, command
                    assert svc.queue.queue.sequence == 0 and native.mutations == []
                    created = await client.call_tool("create_pattern", {"points": POINTS, "name": "a"})
                    assert not created.isError and created.structuredContent["pattern"]["area_mm2"] == 7800
                    moved = await client.call_tool("move_pattern_relative", {
                        "pattern_index": 0, "expected_name": "a", "dx": 20, "dy": -10})
                    assert moved.structuredContent["pattern"]["position_mm"] == [20.0, -10.0]
                    deleted = await client.call_tool("delete_pattern", {"pattern_index": 0, "expected_name": "a"})
                    assert deleted.structuredContent["pattern_count"] == 0
                    assert native.mutations == ["create", "name", "move", "delete"]
            svc.parent.is_alive = False
            assert await asyncio.wait_for(running, 4) == 0
        finally:
            svc.parent.is_alive = False
            if not running.done():
                await asyncio.wait_for(running, 4)
    asyncio.run(scenario())
