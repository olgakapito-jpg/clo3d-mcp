"""External-process FIFO. Single scheduler owner; no threads, IPC or retries.

A dispatch is committed BEFORE handing bytes to a transport. Unknown work pins
the execution slot. Only its correlated result followed by READY releases it;
a disconnect with unresolved work quarantines the session until explicit restart.
"""

from collections import OrderedDict, deque
from copy import deepcopy
from dataclasses import dataclass
import math
import time

from clo3d_mcp.protocol import ProtocolError, encode, message, validate
from clo3d_mcp.pattern_contract import PATTERN_COMMANDS, CommandError, validate_result


TERMINAL = frozenset({"succeeded", "failed", "cancelled", "unknown"})


class QueueError(RuntimeError):
    """Public error code, without peer payloads, API exceptions or credentials."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Outcome:
    session_id: str
    job_id: str
    state: str
    result: object = None
    error: str = None

    def unwrap(self):
        if self.state != "succeeded":
            raise QueueError(self.error or "outcome_unknown")
        return self.result


@dataclass
class _Job:
    job_id: str
    command: str
    queued_deadline: float
    execution_timeout: float
    params: object = None
    state: str = "queued"
    dispatched_deadline: float = None
    result: object = None
    error: str = None
    reply: object = None


class JobQueue:
    """32 waiting + one pinned job + bounded completed history (default 128).

    IDs are server-generated, monotonically increasing within this session;
    lookup/wait never resubmits, and evicted IDs cannot be supplied for replay.
    A new process loses history: this is NOT crash-safe exactly-once delivery.
    `running` requires explicit execution evidence via started(), not mere I/O.
    The P1 protocol has no such receipt, so it remains dispatched until result.
    """

    def __init__(self, session_id, capacity=32, history_limit=128, clock=time.monotonic,
                 outcome_callback=None):
        message("READY", session_id)
        if type(capacity) is not int or not 1 <= capacity <= 32:
            raise ValueError("Waiting capacity must be between 1 and 32")
        if type(history_limit) is not int or not 1 <= history_limit <= 1024:
            raise ValueError("Invalid history limit")
        self.session_id = session_id
        self.capacity = capacity
        self.history_limit = history_limit
        self.clock = clock
        self.waiting = deque()
        self.history = OrderedDict()
        self.jobs = {}
        self.active_id = None
        self.connected = False
        self.ready_credit = False
        self.quarantined = False
        self.closed = False
        self.sequence = 0
        # Synchronous adapter hook only; must not mutate the queue or raise.
        self.outcome_callback = outcome_callback

    @staticmethod
    def _duration(value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError("Deadline duration must be finite and positive")
        return value

    def submit(self, command, *, params=None, queued_timeout=30.0, execution_timeout=30.0):
        # Whitelist and parameter checks precede any mutation.
        params = {} if params is None else deepcopy(params)
        encode(message("JOB", self.session_id, job_id="validate", command=command, params=params))
        self._duration(queued_timeout)
        self._duration(execution_timeout)
        self.tick()
        if self.closed or self.quarantined or not self.connected:
            raise QueueError("executor_unavailable")
        if len(self.waiting) >= self.capacity:
            raise QueueError("queue_full")
        self.sequence += 1
        job_id = "job_%d" % self.sequence
        job = _Job(job_id, command, self.clock() + queued_timeout, execution_timeout, params=params)
        self.jobs[job_id] = job
        self.waiting.append(job_id)
        return job_id

    def lookup(self, session_id, job_id):
        if session_id != self.session_id:
            raise QueueError("stale_session")
        job = self.jobs.get(job_id)
        if job is None:
            raise QueueError("job_not_found")
        return Outcome(self.session_id, job_id, job.state, deepcopy(job.result), job.error)

    def _retire(self, job):
        self._publish(job)
        self.history[job.job_id] = None
        while len(self.history) > self.history_limit:
            old, _ = self.history.popitem(last=False)
            del self.jobs[old]

    def _publish(self, job):
        if self.outcome_callback is not None:
            self.outcome_callback(self.lookup(self.session_id, job.job_id))

    def tick(self):
        now = self.clock()
        for job_id in tuple(self.waiting):
            job = self.jobs[job_id]
            if now >= job.queued_deadline:
                self.waiting.remove(job_id)
                job.state, job.error = "failed", "queue_timeout"
                self._retire(job)
        if self.active_id is not None:
            job = self.jobs[self.active_id]
            if job.state in ("dispatched", "running") and now >= job.dispatched_deadline:
                job.state, job.error = "unknown", "outcome_unknown"
                self._publish(job)
                # Deliberately NOT retired: still occupies the execution slot.

    def on_connected(self):
        if self.closed or self.connected:
            raise ProtocolError("Unexpected executor connection")
        self.connected = True
        self.ready_credit = False

    def on_ready(self):
        if self.closed or not self.connected or self.ready_credit:
            raise ProtocolError("Unexpected executor READY")
        if self.quarantined:
            # Even a fresh READY cannot prove an unknown old command completed.
            return
        if self.active_id is not None:
            job = self.jobs[self.active_id]
            if job.reply is None:
                raise ProtocolError("READY is not an execution result")
            self.active_id = None
            self._retire(job)
        self.ready_credit = True

    def dispatch(self):
        self.tick()
        if (self.closed or self.quarantined or not self.connected
                or not self.ready_credit or self.active_id is not None or not self.waiting):
            return None
        job = self.jobs[self.waiting.popleft()]
        job.state = "dispatched"
        job.dispatched_deadline = self.clock() + job.execution_timeout
        self.active_id = job.job_id
        self.ready_credit = False
        return message("JOB", self.session_id, job_id=job.job_id, command=job.command, params=deepcopy(job.params))

    def started(self, session_id, job_id):
        """Optional explicit execution evidence; never called just for pipe ACK."""
        self.lookup(session_id, job_id)
        job = self.jobs[job_id]
        if self.active_id != job_id or job.state not in ("dispatched", "unknown"):
            raise ProtocolError("Unexpected execution receipt")
        if job.state == "dispatched":
            job.state = "running"

    def receive(self, frame):
        validate(frame, self.session_id)
        if self.closed or not self.connected or self.quarantined:
            raise ProtocolError("Result on an unavailable session")
        if frame["kind"] not in ("RESULT", "ERROR"):
            raise ProtocolError("Expected a job result")
        # Validate serializability and the same 1 MiB bound before caching.
        encode(frame)
        # A delayed event-loop turn must not let an already-expired caller
        # appear successful just because receive() ran before the next tick().
        self.tick()
        job_id = frame["job_id"]
        job = self.jobs.get(job_id)
        if job is None:
            raise ProtocolError("Unknown result identifier")
        if job.reply is not None:
            if encode(job.reply) != encode(frame):
                raise ProtocolError("Conflicting duplicate result")
            return  # Known identical result, no new execution or READY credit.
        if job_id != self.active_id:
            raise ProtocolError("Result was not dispatched")
        if frame["kind"] == "RESULT":
            result = frame["result"]
            if job.command in PATTERN_COMMANDS:
                try:
                    validate_result(job.command, result)
                except CommandError:
                    raise ProtocolError("Invalid pattern result") from None
                valid = True
            elif job.command == "ping":
                valid = set(result) == {"pong"} and result["pong"] is True
            elif job.command == "get_pattern_count":
                valid = (set(result) == {"pattern_count"}
                         and type(result["pattern_count"]) is int and result["pattern_count"] >= 0)
            else:
                valid = (set(result) == {"created", "pattern_count"}
                         and result["created"] is True
                         and type(result["pattern_count"]) is int and result["pattern_count"] >= 0)
            if not valid:
                raise ProtocolError("Invalid diagnostic result")
            job.state, job.result, job.error = "succeeded", deepcopy(result), None
        else:
            # duplicate_job is not proof of success, nor permission to retry.
            code = "outcome_unknown" if frame["code"] == "duplicate_job" else frame["code"]
            job.state = "unknown" if code == "outcome_unknown" else "failed"
            job.error = code
        job.reply = deepcopy(frame)
        self._publish(job)

    def cancel(self, session_id, job_id):
        self.tick()
        self.lookup(session_id, job_id)
        job = self.jobs[job_id]
        if job.state != "queued":
            return False  # Cancellation of a waiter is NOT CLO cancellation.
        self.waiting.remove(job_id)
        job.state, job.error = "cancelled", "cancelled"
        self._retire(job)
        return True

    def on_disconnect(self):
        self.connected = False
        self.ready_credit = False
        if self.active_id is not None:
            job = self.jobs[self.active_id]
            if job.reply is None:
                job.state, job.error = "unknown", "outcome_unknown"
                self._publish(job)
                self.quarantined = True
                self._fail_waiting()
            else:
                # RESULT already proves completion even if READY was lost.
                self.active_id = None
                self._retire(job)

    def _fail_waiting(self):
        while self.waiting:
            job = self.jobs[self.waiting.popleft()]
            job.state, job.error = "failed", "executor_unavailable"
            self._retire(job)

    def close(self):
        if self.closed:
            return
        self.on_disconnect()
        self.closed = True
        self._fail_waiting()
        if self.active_id is not None:
            job = self.jobs[self.active_id]
            self.active_id = None
            self._retire(job)

    def status(self):
        return dict(session_id=self.session_id, connected=self.connected, closed=self.closed,
                    quarantined=self.quarantined, ready=self.ready_credit,
                    waiting=len(self.waiting), capacity=self.capacity,
                    active_id=self.active_id,
                    active_state=self.jobs[self.active_id].state if self.active_id else None,
                    cached=len(self.history), history_limit=self.history_limit)
