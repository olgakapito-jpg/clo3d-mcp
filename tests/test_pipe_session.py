import os

import pytest

from clo3d_mcp.pipe_session import Executor, authenticate, proof
from clo3d_mcp.protocol import CAPABILITIES, ProtocolError, message


KEY = b"k" * 32
SID = "session"
SERVER_PID = 123


def ack(key=KEY, pid=SERVER_PID):
    return message("HELLO_ACK", SID, pid=pid, capabilities=CAPABILITIES,
                   proof=proof(key, "server", SID, pid))


def test_handshake_pid_key_role_and_session():
    from clo3d_mcp import BUILD
    executor = Executor(SID, KEY, SERVER_PID, lambda: 5)
    hello = executor.connected(SERVER_PID)
    assert hello["build"] == BUILD
    authenticate(hello, KEY, "HELLO", SID, os.getpid())
    for frame in (ack(b"z" * 32), ack(pid=124), message("READY", SID)):
        with pytest.raises(ProtocolError):
            executor.receive(frame)
    assert executor.receive(ack()) == [message("READY", SID)]
    assert executor.handshakes == 1
    with pytest.raises(ProtocolError):
        executor.connected(124)


def test_read_only_jobs_error_and_duplicate_survive_reconnect():
    calls = []

    def read():
        calls.append(1)
        return 5

    executor = Executor(SID, KEY, SERVER_PID, read)
    executor.connected(SERVER_PID)
    executor.receive(ack())
    ping = message("JOB", SID, job_id="ping", command="ping", params={})
    assert executor.receive(ping)[0]["result"] == {"pong": True}
    job = message("JOB", SID, job_id="read", command="get_pattern_count", params={})
    assert executor.receive(job)[0]["result"] == {"pattern_count": 5}
    executor.disconnected()
    executor.connected(SERVER_PID)
    executor.receive(ack())
    assert executor.receive(job)[0]["code"] == "duplicate_job"
    assert calls == [1]


def test_api_error_is_not_retried_or_logged():
    def read():
        raise RuntimeError("private scene path")

    executor = Executor(SID, KEY, SERVER_PID, read)
    executor.connected(SERVER_PID)
    executor.receive(ack())
    job = message("JOB", SID, job_id="j", command="get_pattern_count", params={})
    reply = executor.receive(job)
    assert reply[0]["code"] == "command_error"
    assert "private" not in str(reply)
    assert executor.receive(job)[0]["code"] == "duplicate_job"
    assert executor.api_calls == 1


def test_job_limit_stop_and_reentrant_state():
    executor = Executor(SID, KEY, SERVER_PID, lambda: 0)
    executor.connected(SERVER_PID)
    executor.receive(ack())
    for index in range(64):
        executor.receive(message("JOB", SID, job_id=str(index), command="ping", params={}))
    assert len(executor.seen) == 64
    with pytest.raises(ProtocolError, match="limit"):
        executor.receive(message("JOB", SID, job_id="65", command="ping", params={}))
    executor.state = "ready"
    assert executor.receive(message("STOP", SID)) == [message("STOP", SID)]
    with pytest.raises(ProtocolError):
        executor.receive(message("STOP", SID))
