import os

import pytest

from clo3d_mcp.jobs import JobQueue, QueueError
from clo3d_mcp.pipe_session import Executor
from clo3d_mcp.protocol import ProtocolError, message
from clo3d_mcp.queue_session import QueueSession


def pair():
    queue = JobQueue("s")
    server = QueueSession(queue, b"k" * 32, os.getpid())
    executor = Executor("s", b"k" * 32, os.getpid(), lambda: 7)
    server.connect(os.getpid())
    ack = server.receive(executor.connected(os.getpid()))[0]
    server.receive(executor.receive(ack)[0])
    return queue, server, executor


def test_authenticated_sequential_executor_bridge():
    queue, server, executor = pair()
    ids = [queue.submit(command) for command in ("ping", "get_pattern_count", "ping")]
    for job_id in ids:
        job = server.dispatch()
        assert job["job_id"] == job_id
        for reply in executor.receive(job):
            server.receive(reply)
    assert executor.jobs == 3 and executor.api_calls == 1
    assert queue.lookup("s", ids[1]).result == {"pattern_count": 7}


def test_unknown_outcome_quarantined_even_after_authenticated_reconnect():
    queue, server, executor = pair()
    job_id = queue.submit("get_pattern_count")
    server.dispatch()
    server.disconnect()
    executor.disconnected()
    server.connect(os.getpid())
    ack = server.receive(executor.connected(os.getpid()))[0]
    server.receive(executor.receive(ack)[0])
    assert server.dispatch() is None and executor.jobs == 0
    assert queue.lookup("s", job_id).state == "unknown"
    with pytest.raises(QueueError, match="executor_unavailable"):
        queue.submit("ping")


def test_protocol_failure_disconnects_and_never_retries_dispatched_job():
    queue, server, _ = pair()
    job_id = queue.submit("ping")
    server.dispatch()
    with pytest.raises(ProtocolError):
        server.receive(message("RESULT", "s", job_id="wrong", result={"pong": True}))
    assert server.state == "disconnected" and queue.quarantined
    assert queue.lookup("s", job_id).error == "outcome_unknown"


def test_no_ready_or_job_before_authentication():
    server = QueueSession(JobQueue("s"), b"k" * 32, os.getpid())
    server.connect(os.getpid())
    with pytest.raises(ProtocolError):
        server.receive(message("READY", "s"))
    assert server.state == "disconnected" and server.dispatch() is None
