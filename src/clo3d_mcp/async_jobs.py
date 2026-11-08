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
        self._change("on_ready")

    def on_disconnect(self):
        self._change("on_disconnect")

    def dispatch(self):
        return self._change("dispatch")

    def receive(self, frame):
        self._change("receive", frame)

    def cancel(self, session_id, job_id):
        return self._change("cancel", session_id, job_id)

    def close(self):
        self._change("close")

    def status(self):
        return dict(self.queue.status(), waiters=self.waiter_count)

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

    async def call(self, command, **kwargs):
        job_id = self.submit(command, **kwargs)
        try:
            return (await self.wait(self.session_id, job_id)).unwrap()
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
