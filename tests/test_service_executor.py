"""Service whitelist/dedup tests; no native CLO calls."""

import os

import pytest

from clo3d_mcp.pipe_session import Executor, proof
from clo3d_mcp.protocol import CAPABILITIES, SERVICE_CAPABILITIES, ProtocolError, message


def executor(create=None):
    calls = []

    def mutation():
        calls.append(1)
        return {"created": True, "pattern_count": len(calls)}

    key = b"k" * 32
    value = Executor("s", key, os.getpid(), lambda: 2, mutation if create is None else create)
    value.connected(os.getpid())
    value.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=SERVICE_CAPABILITIES,
                          proof=proof(key, "server", "s", os.getpid())))
    return value, calls


def job(index, command="ping"):
    return message("JOB", "s", job_id="job_%d" % index, command=command, params={})


def test_long_service_lifetime_uses_bounded_high_water_not_diagnostic_seen_limit():
    value, _ = executor()
    for index in range(1, 201):
        assert value.receive(job(index))[0]["kind"] == "RESULT"
    assert value.high_water == 200 and not value.seen and value.jobs == 200
    assert value.receive(job(199))[0]["code"] == "duplicate_job"


def test_mutation_never_reexecutes_duplicate_even_after_reconnect():
    value, calls = executor()
    first = value.receive(job(1, "create_test_rectangle"))
    assert first[0]["result"] == {"created": True, "pattern_count": 1}
    value.disconnected()
    value.connected(os.getpid())
    value.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=SERVICE_CAPABILITIES,
                          proof=proof(value.key, "server", "s", os.getpid())))
    assert value.receive(job(1, "create_test_rectangle"))[0]["code"] == "duplicate_job"
    assert calls == [1]


def test_mutation_error_not_retried():
    calls = []

    def fail():
        calls.append(1)
        raise RuntimeError("private scene")

    value, _ = executor(fail)
    assert value.receive(job(1, "create_test_rectangle"))[0]["code"] == "command_error"
    assert value.receive(job(1, "create_test_rectangle"))[0]["code"] == "duplicate_job"
    assert calls == [1]


def test_p1_cannot_gain_mutation_capability():
    value = Executor("s", b"k" * 32, 123, lambda: 0)
    value.state = "ready"
    with pytest.raises(ProtocolError, match="not negotiated"):
        value.receive(job(1, "create_test_rectangle"))
    assert value.api_calls == 0


def test_capabilities_must_match_not_merely_have_valid_shape():
    value = Executor("s", b"k" * 32, 123, lambda: 0)
    value.connected(123)
    with pytest.raises(ProtocolError):
        value.receive(message("HELLO_ACK", "s", pid=123, capabilities=SERVICE_CAPABILITIES,
                              proof=proof(value.key, "server", "s", 123)))


@pytest.mark.parametrize("identifier", ["job_0", "job_01", "random", "job_-1"])
def test_service_requires_server_generated_monotonic_ids(identifier):
    value, _ = executor()
    with pytest.raises(ProtocolError):
        value.receive(message("JOB", "s", job_id=identifier, command="ping", params={}))
