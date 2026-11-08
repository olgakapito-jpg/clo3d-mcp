"""Deterministic external FIFO tests, injected clock and simulated replies."""

import pytest

from clo3d_mcp.jobs import JobQueue, QueueError
from clo3d_mcp.protocol import ProtocolError, message


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    clock = Clock()
    queue = JobQueue("s", clock=clock)
    queue.on_connected()
    queue.on_ready()
    return queue, clock


def reply(queue, job_id, count=None):
    result = {"pong": True} if count is None else {"pattern_count": count}
    return message("RESULT", queue.session_id, job_id=job_id, result=result)


def test_fifo_32_waiting_plus_one_executing(env):
    queue, _ = env
    first = queue.submit("ping")
    assert queue.dispatch()["job_id"] == first
    waiting = [queue.submit("ping") for _ in range(32)]
    with pytest.raises(QueueError, match="queue_full"):
        queue.submit("ping")
    assert queue.status()["waiting"] == 32
    for job_id in [first] + waiting:
        assert queue.dispatch() is None
        queue.receive(reply(queue, job_id))
        assert queue.dispatch() is None  # RESULT is not a READY credit
        queue.on_ready()
        if waiting:
            assert queue.dispatch()["job_id"] == waiting.pop(0)
    assert queue.status()["active_id"] is None


def test_expire_all_queued_not_only_head_and_distinct_deadlines(env):
    queue, clock = env
    a = queue.submit("ping", queued_timeout=100, execution_timeout=5)
    b = queue.submit("ping", queued_timeout=2)
    clock.now = 2
    queue.tick()
    assert queue.lookup("s", b).error == "queue_timeout"
    clock.now = 50
    assert queue.dispatch()["job_id"] == a
    assert queue.lookup("s", a).state == "dispatched"
    clock.now = 54.9
    queue.tick()
    assert queue.lookup("s", a).state == "dispatched"
    clock.now = 55
    queue.tick()
    assert queue.lookup("s", a).error == "outcome_unknown"


def test_timeout_pins_slot_until_late_result_and_ready(env):
    queue, clock = env
    a = queue.submit("get_pattern_count", execution_timeout=1)
    b = queue.submit("ping")
    queue.dispatch()
    queue.started("s", a)
    assert queue.lookup("s", a).state == "running"
    clock.now = 1
    queue.tick()
    assert queue.lookup("s", a).state == "unknown"
    assert queue.dispatch() is None
    with pytest.raises(ProtocolError, match="not an execution result"):
        queue.on_ready()
    queue.receive(reply(queue, a, 5))
    assert queue.lookup("s", a).unwrap() == {"pattern_count": 5}
    assert queue.dispatch() is None
    queue.on_ready()
    assert queue.dispatch()["job_id"] == b


def test_queued_cancellation_removes_job_but_dispatched_cancellation_does_not(env):
    queue, _ = env
    a, b, c = [queue.submit("ping") for _ in range(3)]
    assert queue.cancel("s", b)
    assert queue.lookup("s", b).state == "cancelled"
    assert queue.dispatch()["job_id"] == a
    assert not queue.cancel("s", a)
    assert queue.lookup("s", a).state == "dispatched"
    queue.receive(reply(queue, a))
    queue.on_ready()
    assert queue.dispatch()["job_id"] == c


def test_error_does_not_retry_and_duplicate_reply_does_not_mint_credit(env):
    queue, _ = env
    a, b = [queue.submit("ping") for _ in range(2)]
    queue.dispatch()
    error = message("ERROR", "s", job_id=a, code="command_error")
    queue.receive(error)
    queue.receive(error)
    assert queue.lookup("s", a).error == "command_error"
    queue.on_ready()
    queue.receive(error)
    assert queue.dispatch()["job_id"] == b
    assert queue.dispatch() is None
    with pytest.raises(ProtocolError, match="Conflicting"):
        queue.receive(reply(queue, a))


def test_duplicate_job_error_is_unknown_not_success(env):
    queue, _ = env
    a = queue.submit("ping")
    queue.dispatch()
    queue.receive(message("ERROR", "s", job_id=a, code="duplicate_job"))
    assert queue.lookup("s", a).state == "unknown"
    assert queue.lookup("s", a).error == "outcome_unknown"
    queue.on_ready()  # explicit error means executor returned; no resend
    assert queue.dispatch() is None


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_disconnect_before_or_after_dispatch(env, after_dispatch):
    queue, _ = env
    a, b = [queue.submit("ping") for _ in range(2)]
    if after_dispatch:
        queue.dispatch()
    queue.on_disconnect()
    queue.on_connected()
    queue.on_ready()
    if after_dispatch:
        assert queue.lookup("s", a).state == "unknown"
        assert queue.lookup("s", b).error == "executor_unavailable"
        assert queue.status()["quarantined"]
        assert queue.dispatch() is None
        with pytest.raises(QueueError, match="executor_unavailable"):
            queue.submit("ping")
        with pytest.raises(ProtocolError):
            queue.receive(reply(queue, a))
    else:
        assert queue.dispatch()["job_id"] == a


def test_disconnect_after_result_before_ready_retains_known_outcome(env):
    queue, _ = env
    a, b = [queue.submit("ping") for _ in range(2)]
    queue.dispatch()
    queue.receive(reply(queue, a))
    queue.on_disconnect()
    assert not queue.quarantined
    queue.on_connected()
    queue.on_ready()
    assert queue.dispatch()["job_id"] == b
    assert queue.lookup("s", a).state == "succeeded"


def test_shutdown_resolves_waiters_and_unknown_active_once(env):
    queue, _ = env
    a, b = [queue.submit("ping") for _ in range(2)]
    queue.dispatch()
    queue.close()
    queue.close()
    assert queue.lookup("s", a).error == "outcome_unknown"
    assert queue.lookup("s", b).error == "executor_unavailable"
    assert queue.dispatch() is None
    assert queue.status()["active_id"] is None
    with pytest.raises(QueueError, match="executor_unavailable"):
        queue.submit("ping")


def test_bounded_cache_eviction_lookup_never_replays(env):
    queue, _ = env
    queue.history_limit = 2
    ids = []
    for _ in range(5):
        job_id = queue.submit("ping")
        ids.append(job_id)
        queue.dispatch()
        queue.receive(reply(queue, job_id))
        queue.on_ready()
    assert len(queue.jobs) == len(queue.history) == 2
    with pytest.raises(QueueError, match="job_not_found"):
        queue.lookup("s", ids[0])
    assert queue.dispatch() is None
    assert queue.submit("ping") not in ids


def test_stale_session_wrong_ids_and_invalid_results_never_release_active(env):
    queue, _ = env
    job_id = queue.submit("ping")
    queue.dispatch()
    for frame in [message("RESULT", "old", job_id=job_id, result={"pong": True}),
                  reply(queue, "never_dispatched"),
                  message("RESULT", "s", job_id=job_id, result={"pong": 1})]:
        with pytest.raises(ProtocolError):
            queue.receive(frame)
    assert queue.active_id == job_id and queue.dispatch() is None
    with pytest.raises(QueueError, match="stale_session"):
        queue.cancel("old", job_id)
    new = JobQueue("new")
    with pytest.raises(ProtocolError):
        new.receive(reply(queue, job_id))


def test_results_are_defensively_copied(env):
    queue, _ = env
    job_id = queue.submit("get_pattern_count")
    queue.dispatch()
    frame = reply(queue, job_id, 7)
    queue.receive(frame)
    frame["result"]["pattern_count"] = 999
    outcome = queue.lookup("s", job_id)
    outcome.result["pattern_count"] = 888
    assert queue.lookup("s", job_id).result == {"pattern_count": 7}


def test_late_receive_notifies_timeout_before_success_without_intermediate_tick():
    clock = Clock()
    outcomes = []
    queue = JobQueue("s", clock=clock, outcome_callback=outcomes.append)
    queue.on_connected()
    queue.on_ready()
    job_id = queue.submit("ping", execution_timeout=1)
    queue.dispatch()
    clock.now = 2
    queue.receive(reply(queue, job_id))
    assert [item.state for item in outcomes] == ["unknown", "succeeded"]
    assert queue.lookup("s", job_id).state == "succeeded"


@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "5"])
def test_invalid_deadlines_rejected_without_queue_mutation(env, value):
    queue, _ = env
    with pytest.raises(ValueError):
        queue.submit("ping", queued_timeout=value)
    with pytest.raises(ValueError):
        queue.submit("ping", execution_timeout=value)
    assert queue.sequence == 0 and not queue.waiting


def test_submission_requires_authenticated_executor():
    queue = JobQueue("s")
    with pytest.raises(QueueError, match="executor_unavailable"):
        queue.submit("ping")
    with pytest.raises(ProtocolError):
        queue.submit("exec")


@pytest.mark.parametrize("options", [{"capacity": 0}, {"capacity": 33}, {"capacity": True},
                                    {"history_limit": 0}, {"history_limit": 1025}])
def test_invalid_bounds(options):
    with pytest.raises(ValueError):
        JobQueue("s", **options)
