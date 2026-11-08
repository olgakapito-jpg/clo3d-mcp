"""Bounded P2 acceptance driver, external process only; no HTTP or scene writes."""

import asyncio
import os
import time

from clo3d_mcp.async_jobs import AsyncJobQueue
from clo3d_mcp.jobs import QueueError
from clo3d_mcp.protocol import ProtocolError, message
from clo3d_mcp.queue_session import QueueSession
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe


async def run(name, session_id, key, client_pid, timeout=60.0):
    pipe = Pipe.listen(name)
    queue = AsyncJobQueue(session_id)
    session = QueueSession(queue, key, client_pid)
    tasks = []
    deadline = time.monotonic() + timeout
    channel = None
    try:
        connect = pipe.connect()
        while connect.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("Queue probe connect deadline")
            await asyncio.sleep(0.005)
        session.connect(pipe.peer_pid())
        channel = Channel(pipe, session_id)
        scheduled = False
        stop_sent = False
        stop_ack = False
        order = []
        ids = []
        while not stop_ack:
            if time.monotonic() >= deadline:
                raise TimeoutError("Queue probe exchange deadline")
            for frame in channel.poll():
                if frame["kind"] == "STOP" and stop_sent:
                    stop_ack = True
                else:
                    for response in session.receive(frame):
                        channel.send(response)
            if queue.status()["ready"] and not scheduled:
                commands = ("ping", "get_pattern_count", "get_pattern_count",
                            "ping", "get_pattern_count", "ping")
                for index, command in enumerate(commands):
                    tasks.append(asyncio.create_task(queue.call(
                        command, execution_timeout=0.001 if index == 3 else 15.0)))
                await asyncio.sleep(0)  # all six callers enqueue in task order
                ids = list(queue.queue.waiting)
                if len(ids) != 6:
                    raise ProtocolError("Expected six concurrent queued callers")
                tasks[2].cancel()
                await asyncio.sleep(0)
                # Capacity test: fill exactly 32 waiting without dispatch/API.
                extra = [queue.submit("ping") for _ in range(27)]
                try:
                    queue.submit("ping")
                except QueueError as exc:
                    if exc.code != "queue_full":
                        raise
                else:
                    raise ProtocolError("Missing queue_full rejection")
                for job_id in extra:
                    queue.cancel(session_id, job_id)
                expired = queue.submit("get_pattern_count", queued_timeout=0.001)
                # External-only fault injection: expiry BEFORE any transport send.
                await asyncio.sleep(0.02)
                queue.tick()
                if queue.lookup(session_id, expired).error != "queue_timeout":
                    raise ProtocolError("Missing queued deadline")
                scheduled = True
            frame = session.dispatch()
            if frame is not None:
                order.append(frame["job_id"])
                if frame["job_id"] == ids[3]:
                    # Commit dispatch, expire it before handing bytes to pipe.
                    # Do NOT sleep in CLO or modify the scene to emulate slow API.
                    await asyncio.sleep(0.02)
                    queue.tick()
                    if (queue.lookup(session_id, ids[3]).state != "unknown"
                            or session.dispatch() is not None):
                        raise ProtocolError("Timed-out dispatch did not pin slot")
                channel.send(frame)
            if (scheduled and len(order) == 5 and queue.status()["ready"]
                    and queue.status()["active_id"] is None and not stop_sent):
                if order != [ids[i] for i in (0, 1, 3, 4, 5)]:
                    raise ProtocolError("FIFO order or cancellation failed")
                outcomes = await asyncio.gather(*tasks, return_exceptions=True)
                if not isinstance(outcomes[2], asyncio.CancelledError):
                    raise ProtocolError("Missing queued cancellation")
                if not isinstance(outcomes[3], QueueError) or outcomes[3].code != "outcome_unknown":
                    raise ProtocolError("Missing dispatched deadline")
                for index in (0, 1, 4, 5):
                    if not isinstance(outcomes[index], dict):
                        raise ProtocolError("Concurrent caller failed")
                if queue.lookup(session_id, ids[3]).state != "succeeded":
                    raise ProtocolError("Late result was not retained")
                channel.send(message("STOP", session_id))
                stop_sent = True
            await asyncio.sleep(0.005)
        return 0
    finally:
        session.disconnect()
        queue.close()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        pipe.begin_close()
        cleanup_deadline = time.monotonic() + 2.0
        while not pipe.poll_close():
            if time.monotonic() >= cleanup_deadline:
                break  # Pipe retains pending native buffers until process exit.
            await asyncio.sleep(0.005)


def main():
    try:
        # Same private transport bootstrap as P1; no environment in diagnostics.
        name = os.environ.pop("CLO_MCP_P1_PIPE")
        session_id = os.environ.pop("CLO_MCP_P1_SESSION")
        key = bytes.fromhex(os.environ.pop("CLO_MCP_P1_KEY"))
        client_pid = int(os.environ.pop("CLO_MCP_P1_CLO_PID"))
        if len(key) != 32:
            return 2
        return asyncio.run(run(name, session_id, key, client_pid))
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
