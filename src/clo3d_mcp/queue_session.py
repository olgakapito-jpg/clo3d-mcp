"""External authenticated protocol driver for JobQueue / AsyncJobQueue.

Transport owner polls its Channel and sends returned frames; dispatch is marked
before send. Any pipe/protocol failure must call disconnect(), never retry JOB.
No pipe handles, timers, HTTP or background work are created by this module.
"""

import os

from clo3d_mcp.pipe_session import authenticate, proof
from clo3d_mcp.protocol import CAPABILITIES, ProtocolError, message, validate


class QueueSession:
    def __init__(self, queue, key, client_pid, capabilities=CAPABILITIES):
        self.queue = queue
        self.key = key
        self.client_pid = client_pid
        self.state = "disconnected"
        self.capabilities = list(capabilities)
        self.executor_build = None

    def connect(self, observed_pid):
        if self.state != "disconnected" or observed_pid != self.client_pid:
            raise ProtocolError("Unexpected pipe client")
        self.state = "hello"

    def receive(self, frame):
        try:
            validate(frame, self.queue.session_id)
            if self.state == "hello":
                authenticate(frame, self.key, "HELLO", self.queue.session_id, self.client_pid, self.capabilities)
                self.executor_build = frame["build"]
                self.queue.on_connected()
                self.state = "active"
                return [message("HELLO_ACK", self.queue.session_id, pid=os.getpid(),
                                capabilities=list(self.capabilities),
                                proof=proof(self.key, "server", self.queue.session_id, os.getpid()))]
            if self.state != "active":
                raise ProtocolError("Executor has no authenticated connection")
            if frame["kind"] == "READY":
                self.queue.on_ready()
            elif frame["kind"] in ("RESULT", "ERROR"):
                self.queue.receive(frame)
            else:
                raise ProtocolError("Unexpected executor message")
            return []
        except ProtocolError:
            self.disconnect()
            raise

    def dispatch(self):
        self.queue.tick()
        if self.state != "active":
            return None
        return self.queue.dispatch()

    def disconnect(self):
        self.queue.on_disconnect()
        self.state = "disconnected"
