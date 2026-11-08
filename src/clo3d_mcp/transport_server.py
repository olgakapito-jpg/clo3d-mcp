"""Official FastMCP Streamable HTTP, one CLO-bound process and external FIFO."""

import asyncio
from contextlib import suppress
import os
import json
import socket
import time
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
import uvicorn

from clo3d_mcp.async_jobs import AsyncJobQueue
from clo3d_mcp.jobs import QueueError
from clo3d_mcp.protocol import SERVICE_CAPABILITIES, ProtocolError, message
from clo3d_mcp.queue_session import QueueSession
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe
from clo3d_mcp.transport.winprocess import ProcessHandle


class Service:
    def __init__(self, name, session_id, key, client_pid, parent, port=8765):
        self.name, self.key, self.client_pid = name, key, client_pid
        self.parent, self.port = parent, port
        self.queue = AsyncJobQueue(session_id)
        self.session = QueueSession(self.queue, key, client_pid, SERVICE_CAPABILITIES)
        self.http_serving = False
        self.executor_verified = False
        self.ready_announced = False
        self.ready_acknowledged = False
        self.failure = None
        self.stop_requested = False

    def status(self):
        queue = self.queue.status()
        return dict(queue, http_serving=self.http_serving,
                    executor_verified=self.executor_verified,
                    ready=self.http_serving and self.executor_verified and self.ready_acknowledged
                    and queue["connected"] and not queue["closed"]
                    and not queue["quarantined"] and not self.stop_requested,
                    endpoint="http://127.0.0.1:%d/mcp" % self.port, error=self.failure)

    async def call(self, command):
        try:
            if not self.status()["ready"]:
                raise QueueError("executor_unavailable")
            return {"ok": True, **(await self.queue.call(command))}
        except QueueError as exc:
            data = {"ok": False, "error": exc.code}
            return CallToolResult(isError=True, structuredContent=data,
                                  content=[TextContent(type="text", text=json.dumps(data))])


def build_mcp(service):
    """No handles/tasks at import. SDK retains its own Host/Origin middleware."""
    mcp = FastMCP(
        "CLO session", host="127.0.0.1", port=service.port,
        streamable_http_path="/mcp", json_response=True, log_level="ERROR",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:%d" % service.port], allowed_origins=[]),
        instructions="One disposable CLO scene. Never automatically retry outcome_unknown or a scene mutation.",
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @mcp.tool(annotations=read)
    async def ping() -> dict[str, Any]:
        """Round trip through FIFO to the CLO UI executor, not an HTTP health ping."""
        return await service.call("ping")

    @mcp.tool(annotations=read)
    async def get_pattern_count() -> dict[str, Any]:
        """Read the number of pattern pieces through the sequential CLO executor."""
        return await service.call("get_pattern_count")

    @mcp.tool(annotations=read)
    async def transport_status() -> dict[str, Any]:
        """External queue/HTTP state; responds even while a CLO API call is busy."""
        return service.status()

    @mcp.tool(annotations=read)
    async def get_session_info() -> dict[str, Any]:
        """CLO session identity and readiness (not the MCP HTTP session identity)."""
        return dict(service.status(), clo_pid=service.client_pid, server_pid=os.getpid(),
                    capabilities=list(SERVICE_CAPABILITIES))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=False, openWorldHint=False))
    async def create_test_rectangle() -> dict[str, Any]:
        """Add ONE fixed 100 x 100 mm diagnostic square at the 2D origin.

        Mutates the disposable scene; no arbitrary geometry/exec. Never retry
        automatically after a timeout, disconnect or unknown outcome.
        """
        return await service.call("create_test_rectangle")

    return mcp


async def pipe_loop(service):
    pipe = Pipe.listen(service.name)
    channel = None
    startup_deadline = time.monotonic() + 30
    try:
        connect = pipe.connect()
        while connect.poll() is None:
            if not service.parent.alive():
                return
            if time.monotonic() >= startup_deadline:
                raise TimeoutError("Executor connection deadline")
            await asyncio.sleep(0.01)
        service.session.connect(pipe.peer_pid())
        channel = Channel(pipe, service.queue.session_id)
        verification_id = None
        while not service.stop_requested:
            if not service.parent.alive():
                return
            service.queue.tick()
            for frame in channel.poll():
                if frame["kind"] == "STOP":
                    if service.session.state != "active":
                        raise ProtocolError("Unauthenticated STOP")
                    service.stop_requested = True
                    return
                if frame["kind"] == "SERVICE_READY":
                    if not service.ready_announced or service.ready_acknowledged:
                        raise ProtocolError("Unexpected readiness acknowledgement")
                    service.ready_acknowledged = True
                    continue
                for response in service.session.receive(frame):
                    channel.send(response)
            if verification_id is None and service.queue.status()["ready"]:
                verification_id = service.queue.submit("ping", execution_timeout=15)
            if verification_id is not None and not service.executor_verified:
                outcome = service.queue.lookup(service.queue.session_id, verification_id)
                if outcome.state == "succeeded" and service.queue.status()["ready"]:
                    service.executor_verified = True
                elif outcome.state in ("failed", "unknown", "cancelled"):
                    raise ProtocolError("Executor verification failed")
            if service.http_serving and service.executor_verified and not service.ready_announced:
                # Isolated message: do not batch SERVICE_READY with a JOB.
                channel.send(message("SERVICE_READY", service.queue.session_id))
                service.ready_announced = True
            elif service.ready_acknowledged or not service.executor_verified:
                job = service.session.dispatch()
                if job is not None:
                    channel.send(job)
            if not service.ready_acknowledged and time.monotonic() >= startup_deadline:
                raise TimeoutError("Service readiness deadline")
            await asyncio.sleep(0.01)
    finally:
        service.session.disconnect()
        service.queue.close()
        pipe.begin_close()
        deadline = time.monotonic() + 2
        while not pipe.poll_close():
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(0.005)


async def run(service):
    # Exclusive bind, no SO_REUSEADDR: never hijack a busy Windows port.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_task = pipe_task = None
    server = None
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", service.port))
        except OSError:
            service.failure = "http_bind_failed"
            raise
        sock.listen(64)
        sock.setblocking(False)
        mcp = build_mcp(service)
        config = uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=service.port,
                                log_level="error", access_log=False, proxy_headers=False,
                                timeout_graceful_shutdown=2, ws="none")
        server = uvicorn.Server(config)
        server_task = asyncio.create_task(server.serve(sockets=[sock]))
        pipe_task = asyncio.create_task(pipe_loop(service))
        while not server_task.done() and not pipe_task.done():
            service.http_serving = server.started
            await asyncio.sleep(0.01)
        if pipe_task.done():
            pipe_task.result()
        elif not service.stop_requested:
            server_task.result()
            raise RuntimeError("HTTP stopped unexpectedly")
        return 0
    finally:
        service.stop_requested = True
        service.http_serving = False
        service.queue.close()
        if pipe_task is not None:
            if not pipe_task.done():
                pipe_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pipe_task
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            with suppress(asyncio.CancelledError, Exception):
                await server_task
        sock.close()
        service.parent.close()


def main():
    parent = None
    service = None
    try:
        name = os.environ.pop("CLO_MCP_P1_PIPE")
        session_id = os.environ.pop("CLO_MCP_P1_SESSION")
        key = bytes.fromhex(os.environ.pop("CLO_MCP_P1_KEY"))
        client_pid = int(os.environ.pop("CLO_MCP_P1_CLO_PID"))
        parent = ProcessHandle(inherited=int(os.environ.pop("CLO_MCP_PARENT_HANDLE")))
        if len(key) != 32 or parent.pid() != client_pid or not parent.alive():
            return 2
        port = int(os.environ.pop("CLO_MCP_HTTP_PORT", "8765"))
        if not 1 <= port <= 65535:
            return 2
        service = Service(name, session_id, key, client_pid, parent, port=port)
        return asyncio.run(run(service))
    except Exception:
        # A fixed exit code carries a useful startup diagnosis without IPC files
        # or stdout/stderr pipes, tracebacks, environment or credentials.
        return 3 if service is not None and service.failure == "http_bind_failed" else 1
    finally:
        if parent is not None:
            parent.close()


if __name__ == "__main__":
    raise SystemExit(main())
