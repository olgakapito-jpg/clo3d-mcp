"""Official FastMCP Streamable HTTP, one CLO-bound process and external FIFO."""

import asyncio
from contextlib import suppress
import os
import json
import socket
import time
from typing import Any
from pydantic import StrictFloat, StrictInt, StrictStr

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
import uvicorn

from clo3d_mcp.async_jobs import AsyncJobQueue
from clo3d_mcp.jobs import QueueError
from clo3d_mcp.protocol import SERVICE_CAPABILITIES, PATTERN_CAPABILITIES, ProtocolError, message
from clo3d_mcp.pattern_contract import PATTERN_COMMANDS, CommandError, validate_params
from clo3d_mcp.queue_session import QueueSession
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe
from clo3d_mcp.transport.winprocess import ProcessHandle


def tool_error(code):
    data = {"ok": False, "error": code}
    if code in ("scene_change_unverified", "outcome_unknown", "executor_release_timeout", "executor_release_unavailable"):
        data["scene_may_have_changed"] = True
    return CallToolResult(isError=True, structuredContent=data,
                          content=[TextContent(type="text", text=json.dumps(data))])


class SessionMCP(FastMCP):
    async def call_tool(self, name, arguments):
        # Official SDK 1.26 defaults to ignoring extra arguments and pre-parses
        # JSON strings. Validate the RAW pattern payload before either happens.
        if name in PATTERN_COMMANDS:
            try:
                validate_params(name, arguments)
            except CommandError:
                return tool_error("invalid_parameters")
        return await super().call_tool(name, arguments)


class Service:
    def __init__(self, name, session_id, key, client_pid, parent, port=8765, pattern_package=False):
        self.name, self.key, self.client_pid = name, key, client_pid
        self.parent, self.port = parent, port
        self.queue = AsyncJobQueue(session_id)
        self.pattern_package = pattern_package
        self.capabilities = PATTERN_CAPABILITIES if pattern_package else SERVICE_CAPABILITIES
        self.session = QueueSession(self.queue, key, client_pid, self.capabilities)
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

    async def call(self, command, params=None):
        try:
            if not self.status()["ready"]:
                raise QueueError("executor_unavailable")
            if params is not None:
                validate_params(command, params)
            # RESULT is not READY. Observe release of exactly our completed job,
            # outside CLO's UI callback, before returning a composable success.
            return {"ok": True, **(await self.queue.call(command, params=params, release_timeout=2.0))}
        except (QueueError, CommandError, ProtocolError) as exc:
            code = exc.code if isinstance(exc, (QueueError, CommandError)) else "invalid_parameters"
            return tool_error(code)


def build_mcp(service):
    """No handles/tasks at import. SDK retains its own Host/Origin middleware."""
    mcp = SessionMCP(
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
                    capabilities=list(service.capabilities))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=False, openWorldHint=False))
    async def create_test_rectangle() -> dict[str, Any]:
        """Add ONE fixed 100 x 100 mm diagnostic square at the 2D origin.

        Mutates the disposable scene; no arbitrary geometry/exec. Never retry
        automatically after a timeout, disconnect or unknown outcome.
        """
        return await service.call("create_test_rectangle")

    if service.pattern_package:
        add_pattern_tools(mcp, service, read)
    return mcp


def add_pattern_tools(mcp, service, read):
    """Explicit tools only; no registration of arbitrary CLO functions."""
    mutation = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                               idempotentHint=False, openWorldHint=False)

    @mcp.tool(annotations=read)
    async def list_clo_api() -> dict[str, Any]:
        """List public callable names in five fixed CLO modules, without invoking them.

        Presence is not proof that a native call is safe or compatible.
        """
        return await service.call("list_clo_api", {})

    @mcp.tool(annotations=read)
    async def describe_clo_api(module: StrictStr, functions: list[StrictStr]) -> dict[str, Any]:
        """Read bounded docstrings/signatures, not execute API. At most 16 public names."""
        return await service.call("describe_clo_api", {"module": module, "functions": functions})

    @mcp.tool(annotations=read)
    async def get_pattern_list() -> dict[str, Any]:
        """Read indices/names; bounded to 256 pieces. Indices can change after deletion."""
        return await service.call("get_pattern_list", {})

    @mcp.tool(annotations=read)
    async def get_pattern_geometry(pattern_index: StrictInt) -> dict[str, Any]:
        """Read 2D position in mm, area in mm2 and bounding box from CLO."""
        return await service.call("get_pattern_geometry", {"pattern_index": pattern_index})

    @mcp.tool(annotations=mutation)
    async def create_pattern(points: list[list[StrictInt | StrictFloat]], name: StrictStr) -> dict[str, Any]:
        """Create ONE simple straight polygon, 3-64 [x,y] points in mm, unique name.

        No curves/holes/self-intersection. Verifies count/name/area using CLO.
        No automatic retry or rollback, even if the verification fails.
        """
        return await service.call("create_pattern", {"points": points, "name": name})

    @mcp.tool(annotations=mutation)
    async def set_pattern_name(pattern_index: StrictInt, expected_name: StrictStr,
                               name: StrictStr) -> dict[str, Any]:
        """Rename a uniquely named piece after stale-index check; verify by reading back."""
        return await service.call("set_pattern_name", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "name": name})

    @mcp.tool(annotations=mutation)
    async def copy_pattern_with_offset(pattern_index: StrictInt, expected_name: StrictStr,
                                       name: StrictStr, dx: StrictInt | StrictFloat,
                                       dy: StrictInt | StrictFloat) -> dict[str, Any]:
        """Copy ONE piece by dx/dy mm, unique new name; verify count, position and area.

        Never retry automatically: a failed readback may follow a successful copy.
        """
        return await service.call("copy_pattern_with_offset", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "name": name, "dx": dx, "dy": dy})

    @mcp.tool(annotations=mutation)
    async def move_pattern_relative(pattern_index: StrictInt, expected_name: StrictStr,
                                    dx: StrictInt | StrictFloat, dy: StrictInt | StrictFloat) -> dict[str, Any]:
        """Move whole piece by dx/dy mm; verify actual displacement and unchanged area.

        Does NOT move individual pattern points. Never retry automatically.
        """
        return await service.call("move_pattern_relative", {"pattern_index": pattern_index,
                                  "expected_name": expected_name, "dx": dx, "dy": dy})

    @mcp.tool(annotations=mutation)
    async def delete_pattern(pattern_index: StrictInt, expected_name: StrictStr) -> dict[str, Any]:
        """Delete ONE uniquely named piece after stale-index check; verify remaining list.

        Indices shift. Read the list again before further operations. No automatic retry.
        """
        return await service.call("delete_pattern", {"pattern_index": pattern_index,
                                  "expected_name": expected_name})


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
        pattern_package = os.environ.pop("CLO_MCP_PATTERN_PACKAGE", "0") == "1"
        service = Service(name, session_id, key, client_pid, parent, port=port,
                          pattern_package=pattern_package)
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
