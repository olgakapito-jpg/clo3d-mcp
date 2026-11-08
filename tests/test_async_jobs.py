"""Async client cancellation and simulated executor; no HTTP/CLO."""

import asyncio

import pytest

from clo3d_mcp.async_jobs import AsyncJobQueue
from clo3d_mcp.jobs import QueueError
from clo3d_mcp.protocol import message


def connected(**kwargs):
    queue = AsyncJobQueue("s", **kwargs)
    queue.on_connected()
    queue.on_ready()
    return queue


def result(job_id):
    return message("RESULT", "s", job_id=job_id, result={"pong": True})


async def turn():
    # A scheduler yield, not a wall-clock delay or deadline-based assumption.
    await asyncio.sleep(0)


def test_concurrent_clients_fifo_and_status_while_busy():
    async def scenario():
        queue = connected()
        tasks = [asyncio.create_task(queue.call("ping")) for _ in range(12)]
        await turn()
        assert queue.status()["waiting"] == 12
        order = []
        for index in range(12):
            frame = queue.dispatch()
            order.append(frame["job_id"])
            assert queue.status()["active_state"] == "dispatched"
            assert queue.dispatch() is None
            queue.receive(result(frame["job_id"]))
            queue.on_ready()
        assert await asyncio.gather(*tasks) == [{"pong": True}] * 12
        assert order == ["job_%d" % index for index in range(1, 13)]
        assert queue.status()["waiters"] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("dispatched", [False, True])
def test_call_cancellation_before_and_after_dispatch(dispatched):
    async def scenario():
        queue = connected()
        task = asyncio.create_task(queue.call("ping"))
        await turn()
        if dispatched:
            queue.dispatch()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        outcome = queue.lookup("s", "job_1")
        assert outcome.state == ("dispatched" if dispatched else "cancelled")
        second = queue.submit("ping")
        if dispatched:
            assert queue.dispatch() is None
            queue.receive(result("job_1"))
            queue.on_ready()
        assert queue.dispatch()["job_id"] == second
    asyncio.run(scenario())


def test_independent_waiter_cancellation_does_not_cancel_shared_future():
    async def scenario():
        queue = connected()
        job_id = queue.submit("ping")
        a = asyncio.create_task(queue.wait("s", job_id))
        b = asyncio.create_task(queue.wait("s", job_id))
        await turn()
        a.cancel()
        with pytest.raises(asyncio.CancelledError):
            await a
        queue.dispatch()
        queue.receive(result(job_id))
        outcome = await b
        outcome.result["pong"] = False
        assert queue.lookup("s", job_id).result == {"pong": True}
        assert not queue.waiters
    asyncio.run(scenario())


def test_timeout_notifies_once_but_late_result_updates_lookup_and_pins_slot():
    async def scenario():
        now = [0.0]
        queue = connected(clock=lambda: now[0])
        task = asyncio.create_task(queue.call("ping", execution_timeout=1))
        await turn()
        queue.dispatch()
        b = queue.submit("ping")
        now[0] = 1
        queue.tick()
        with pytest.raises(QueueError, match="outcome_unknown"):
            await task
        assert queue.dispatch() is None
        queue.receive(result("job_1"))
        assert (await queue.wait("s", "job_1")).state == "succeeded"
        queue.on_ready()
        assert queue.dispatch()["job_id"] == b
    asyncio.run(scenario())


def test_bulk_expiry_and_shutdown_notify_before_small_history_eviction():
    async def scenario():
        now = [0.0]
        queue = connected(history_limit=1, clock=lambda: now[0])
        tasks = [asyncio.create_task(queue.call("ping", queued_timeout=1)) for _ in range(10)]
        await turn()
        now[0] = 1
        queue.tick()
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(error, QueueError) and error.code == "queue_timeout" for error in outcomes)
        assert len(queue.queue.jobs) == 1 and not queue.waiters
        tasks = [asyncio.create_task(queue.call("ping")) for _ in range(10)]
        await turn()
        queue.dispatch()
        queue.close()
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        assert outcomes[0].code == "outcome_unknown"
        assert all(error.code == "executor_unavailable" for error in outcomes[1:])
        assert not queue.waiters
    asyncio.run(scenario())


def test_waiter_capacity_bounded_and_failed_call_not_left_queued():
    async def scenario():
        queue = connected(waiter_limit=1)
        a = asyncio.create_task(queue.call("ping"))
        await turn()
        with pytest.raises(QueueError, match="waiter_limit"):
            await queue.call("ping")
        assert queue.lookup("s", "job_2").state == "cancelled"
        assert queue.status()["waiting"] == 1
        queue.close()
        with pytest.raises(QueueError, match="executor_unavailable"):
            await a
    asyncio.run(scenario())


def test_cancelled_observer_storage_bounded_and_no_completion_leak():
    async def scenario():
        queue = connected(waiter_limit=2)
        job_id = queue.submit("ping")
        for _ in range(10):
            task = asyncio.create_task(queue.wait("s", job_id))
            await turn()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert queue.waiter_count == 0 and len(queue.waiters) == 1
        assert queue.lookup("s", job_id).state == "queued"
        queue.close()
        assert not queue.waiters
    asyncio.run(scenario())
