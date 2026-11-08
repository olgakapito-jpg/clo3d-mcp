"""Bounded external P1 server: two read-only rounds separated by disconnect.

Launched only by the CLO diagnostic launcher. Session config arrives in the
child environment, never command arguments/files. No MCP endpoint or FIFO yet.
"""

import os
import time

from clo3d_mcp.pipe_session import authenticate, proof
from clo3d_mcp.protocol import CAPABILITIES, ProtocolError, message
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe


def run(name, session_id, key, client_pid, timeout=75.0):
    pipe = Pipe.listen(name)
    deadline = time.monotonic() + timeout
    channel = None
    try:
        for round_number in range(2):
            connect = pipe.connect()
            while connect.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("P1 connect deadline")
                time.sleep(0.005)  # external process only, never CLO
            if pipe.peer_pid() != client_pid:
                raise ProtocolError("Pipe client PID mismatch")
            channel = Channel(pipe, session_id)
            state = "hello"
            ready = False
            awaiting = None
            next_command = 0
            commands = ("ping", "get_pattern_count")
            stopping = False
            stop_ack = False
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("P1 exchange deadline; no dispatched job is retried")
                for frame in channel.poll():
                    kind = frame["kind"]
                    if state == "hello":
                        authenticate(frame, key, "HELLO", session_id, client_pid)
                        channel.send(message("HELLO_ACK", session_id, pid=os.getpid(),
                                             capabilities=list(CAPABILITIES),
                                             proof=proof(key, "server", session_id, os.getpid())))
                        state = "active"
                    elif kind == "READY" and not ready and awaiting is None and not stopping:
                        ready = True
                    elif kind in ("RESULT", "ERROR") and awaiting is not None:
                        job_id, command = awaiting
                        if frame["job_id"] != job_id:
                            raise ProtocolError("Unexpected result identifier")
                        if kind == "ERROR":
                            raise ProtocolError("Diagnostic command failed; not retried")
                        result = frame["result"]
                        if command == "ping":
                            if result != {"pong": True}:
                                raise ProtocolError("Invalid ping result")
                        elif (set(result) != {"pattern_count"}
                              or type(result["pattern_count"]) is not int
                              or result["pattern_count"] < 0):
                            raise ProtocolError("Invalid pattern count result")
                        awaiting = None
                    elif kind == "STOP" and stopping:
                        stop_ack = True
                    else:
                        raise ProtocolError("Unexpected diagnostic reply")
                if ready and awaiting is None and not stopping:
                    if next_command < len(commands):
                        command = commands[next_command]
                        job_id = "round%d_job%d" % (round_number + 1, next_command + 1)
                        channel.send(message("JOB", session_id, job_id=job_id,
                                             command=command, params={}))
                        awaiting = (job_id, command)
                        next_command += 1
                        ready = False
                    elif channel.drained:
                        if round_number == 0:
                            break  # intentional break ONLY after result + READY
                        channel.send(message("STOP", session_id))
                        stopping = True
                        ready = False
                if stop_ack and channel.drained:
                    break
                time.sleep(0.005)
            pipe.begin_close()
            while not pipe.poll_close(reuse=round_number == 0):
                if time.monotonic() >= deadline:
                    raise TimeoutError("P1 cleanup deadline")
                time.sleep(0.005)
        return 0
    finally:
        if not pipe.closed:
            pipe.begin_close()
            cleanup_deadline = time.monotonic() + 2.0
            while not pipe.poll_close():
                if time.monotonic() >= cleanup_deadline:
                    # Pipe remains strongly retained until process exit.
                    break
                time.sleep(0.005)


def main():
    try:
        name = os.environ.pop("CLO_MCP_P1_PIPE")
        session_id = os.environ.pop("CLO_MCP_P1_SESSION")
        key = bytes.fromhex(os.environ.pop("CLO_MCP_P1_KEY"))
        pid = int(os.environ.pop("CLO_MCP_P1_CLO_PID"))
        if len(key) != 32:
            return 2
        return run(name, session_id, key, pid)
    except Exception:
        return 1  # no environment/payload/credential traceback


if __name__ == "__main__":
    raise SystemExit(main())
