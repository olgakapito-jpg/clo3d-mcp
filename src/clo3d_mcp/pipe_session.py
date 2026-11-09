"""P1-only sequential diagnostic executor + mutual HMAC handshake. No MCP."""

import hashlib
import hmac
import os

from clo3d_mcp import BUILD
from clo3d_mcp.protocol import CAPABILITIES, SERVICE_CAPABILITIES, PATTERN_CAPABILITIES, ProtocolError, message, validate
from clo3d_mcp.pattern_contract import PATTERN_COMMANDS, ERROR_CODES, CommandError, validate_result


def proof(key, role, session_id, pid):
    return hmac.new(key, (role + ":" + session_id + ":" + str(pid)).encode("ascii"),
                    hashlib.sha256).hexdigest()


def authenticate(frame, key, kind, session_id, expected_pid, capabilities=CAPABILITIES):
    validate(frame, session_id)
    role = "client" if kind == "HELLO" else "server"
    if (frame["kind"] != kind or frame.get("pid") != expected_pid
            or frame.get("capabilities") != capabilities
            or not hmac.compare_digest(frame["proof"], proof(key, role, session_id, expected_pid))):
        raise ProtocolError("Peer authentication failed")


class Executor:
    """Caller must verify the UI thread before receive(). One JOB per READY.

    Seen IDs are retained across reconnects. P1 is bounded to 64 jobs and refuses
    additional IDs rather than evicting and accidentally executing a duplicate.
    This is not the external FIFO or crash-safe exactly-once execution.
    """

    def __init__(self, session_id, key, server_pid, read_count, create_rectangle=None, command_handler=None):
        self.session_id = session_id
        self.key = key
        self.server_pid = server_pid
        self.read_count = read_count
        self.seen = set()
        self.state = "disconnected"
        self.jobs = 0
        self.api_calls = 0
        self.last_count = None
        self.handshakes = 0
        self.create_rectangle = create_rectangle
        self.command_handler = command_handler
        if command_handler is not None and create_rectangle is None:
            raise ValueError("Pattern package requires service profile")
        self.capabilities = SERVICE_CAPABILITIES if create_rectangle is not None else CAPABILITIES
        if command_handler is not None:
            self.capabilities = PATTERN_CAPABILITIES
        self.high_water = 0

    def connected(self, observed_pid):
        if observed_pid != self.server_pid:
            raise ProtocolError("Pipe server PID mismatch")
        self.state = "handshake"
        return message("HELLO", self.session_id, pid=os.getpid(),
                       capabilities=list(self.capabilities), build=BUILD,
                       proof=proof(self.key, "client", self.session_id, os.getpid()))

    def disconnected(self):
        self.state = "disconnected"

    def receive(self, frame):
        validate(frame, self.session_id)
        if self.state == "handshake":
            authenticate(frame, self.key, "HELLO_ACK", self.session_id, self.server_pid, self.capabilities)
            self.handshakes += 1
            self.state = "ready"
            return [message("READY", self.session_id)]
        if self.state != "ready":
            raise ProtocolError("Unexpected executor state")
        if frame["kind"] == "STOP":
            self.state = "stopping"
            return [message("STOP", self.session_id)]
        if frame["kind"] != "JOB":
            raise ProtocolError("Expected one diagnostic JOB")
        if frame["command"] not in self.capabilities:
            raise ProtocolError("Command was not negotiated")
        self.state = "executing"
        job_id = frame["job_id"]
        if self.create_rectangle is not None:
            # Service IDs never reset within a session and are assigned only by
            # the external queue. High-water rejection is bounded for long runs.
            import re
            if not re.fullmatch(r"job_[1-9][0-9]{0,30}", job_id):
                raise ProtocolError("Invalid sequential service job identifier")
            sequence = int(job_id[4:])
            duplicate = sequence <= self.high_water
            self.high_water = max(self.high_water, sequence)
        else:
            duplicate = job_id in self.seen
        if duplicate:
            response = message("ERROR", self.session_id, job_id=job_id, code="duplicate_job")
        else:
            if self.create_rectangle is None and len(self.seen) >= 64:
                raise ProtocolError("P1 diagnostic job limit reached")
            if self.create_rectangle is None:
                self.seen.add(job_id)  # BEFORE API, including commands that raise
            try:
                if frame["command"] == "ping":
                    result = {"pong": True}
                elif frame["command"] == "get_pattern_count":
                    self.api_calls += 1
                    count = self.read_count()
                    if type(count) is not int or count < 0:
                        raise ValueError("Invalid CLO pattern count")
                    self.last_count = count
                    result = {"pattern_count": count}
                elif frame["command"] in PATTERN_COMMANDS:
                    self.api_calls += 1
                    result = self.command_handler(frame["command"], frame["params"])
                    validate_result(frame["command"], result)
                else:
                    self.api_calls += 1
                    result = self.create_rectangle()
                    if (not isinstance(result, dict) or result.get("created") is not True
                            or type(result.get("pattern_count")) is not int
                            or result["pattern_count"] < 0):
                        raise ValueError("Invalid diagnostic creation result")
                    self.last_count = result["pattern_count"]
                response = message("RESULT", self.session_id, job_id=job_id, result=result)
            except CommandError as exc:
                code = exc.code if exc.code in ERROR_CODES else "command_error"
                response = message("ERROR", self.session_id, job_id=job_id, code=code)
            except Exception:
                # No API exception details/scene paths sent to peer or logs.
                response = message("ERROR", self.session_id, job_id=job_id, code="command_error")
            self.jobs += 1
        self.state = "ready"
        return [response, message("READY", self.session_id)]
