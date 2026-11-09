"""Async waiter adapter for the external event loop. No tasks at import/start.

The transport owner must drive tick() even with no HTTP callers. All methods
run on that same loop. call() owns cancellation-before-dispatch; wait() merely
observes a known ID and never resubmits or cancels work shared by other waiters.
"""

import asyncio
from copy import deepcopy

from clo3d_mcp.jobs import JobQueue, QueueError, TERMINAL


class AsyncJobQueue:
    def __init__(self, session_id, *, waiter_limit=128, **kwargs):
        if type(waiter_limit) is not int or not 1 <= waiter_limit <= 1024:
            raise ValueError("Invalid waiter limit")
        self.waiter_limit = waiter_limit
        self.waiters = {}
        self.waiter_count = 0
        self.release_waiters = {}
        self.queue = JobQueue(session_id, outcome_callback=self._notify, **kwargs)

    @property
    def session_id(self):
        return self.queue.session_id

    def _notify(self, outcome):
        future = self.waiters.pop(outcome.job_id, None)
        if future is not None and not future.done():
            future.set_result(outcome)

    def _change(self, name, *args, **kwargs):
        return getattr(self.queue, name)(*args, **kwargs)

    def submit(self, command, **kwargs):
        return self._change("submit", command, **kwargs)

    def tick(self):
        self._change("tick")

    def on_connected(self):
        self._change("on_connected")

    def on_ready(self):
        job_id = self.queue.active_id
        self._change("on_ready")
        if job_id is not None and self.queue.active_id != job_id:
            self._release(job_id, True)

    def _release(self, job_id, ready):
        future = self.release_waiters.pop(job_id, None)
        if future is not None and not future.done():
            future.set_result(ready)

    def _release_unavailable(self):
        for job_id in tuple(self.release_waiters):
            self._release(job_id, False)

    def on_disconnect(self):
        self._change("on_disconnect")
        self._release_unavailable()

    def dispatch(self):
        return self._change("dispatch")

    def receive(self, frame):
        self._change("receive", frame)

    def cancel(self, session_id, job_id):
        return self._change("cancel", session_id, job_id)

    def close(self):
        self._change("close")
        self._release_unavailable()

    def status(self):
        return dict(self.queue.status(), waiters=self.waiter_count + len(self.release_waiters))

    def lookup(self, session_id, job_id):
        return self.queue.lookup(session_id, job_id)

    async def wait(self, session_id, job_id):
        self.tick()
        outcome = self.lookup(session_id, job_id)
        if outcome.state in TERMINAL:
            return outcome
        if self.waiter_count >= self.waiter_limit:
            raise QueueError("waiter_limit")
        future = self.waiters.get(job_id)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            self.waiters[job_id] = future
        self.waiter_count += 1
        try:
            # Shield the shared completion from an individual client's timeout.
            outcome = await asyncio.shield(future)
            # Never share a mutable result dict between different observers.
            return deepcopy(outcome)
        finally:
            self.waiter_count -= 1

    async def wait_released(self, job_id, timeout):
        """Observe this completed job's READY, never global idle or another job.

        Only call() owns this observer; no public lookup/poll/replay endpoint.
        A timeout does not cancel execution, release the slot or resend work.
        """
        if self.queue.closed or not self.queue.connected or self.queue.quarantined:
            raise QueueError("executor_release_unavailable")
        if self.queue.active_id != job_id:
            return  # already retired by its READY; another client may own the slot
        future = asyncio.get_running_loop().create_future()
        self.release_waiters[job_id] = future
        try:
            try:
                ready = await asyncio.wait_for(asyncio.shield(future), timeout)
            except TimeoutError:
                raise QueueError("executor_release_timeout") from None
            if not ready:
                raise QueueError("executor_release_unavailable")
        finally:
            if self.release_waiters.get(job_id) is future:
                del self.release_waiters[job_id]
            if not future.done():
                future.cancel()

    async def call(self, command, *, release_timeout=None, **kwargs):
        if release_timeout is not None:
            JobQueue._duration(release_timeout)
        job_id = self.submit(command, **kwargs)
        try:
            result = (await self.wait(self.session_id, job_id)).unwrap()
            if release_timeout is not None:
                await self.wait_released(job_id, release_timeout)
            return result
        except asyncio.CancelledError:
            self._cancel_owned(job_id)
            raise
        except QueueError:
            # E.g. waiter capacity: do not leave an unobserved queued command.
            self._cancel_owned(job_id)
            raise

    def _cancel_owned(self, job_id):
        try:
            self.cancel(self.session_id, job_id)
        except QueueError as exc:
            # A batch expiry/shutdown may evict history before a waiter resumes.
            # Its Future already owns the correct outcome; never replace that
            # error (or CancelledError) with a cache lookup failure.
            if exc.code != "job_not_found":
                raise
