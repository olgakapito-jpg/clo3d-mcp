"""CLO UI state machine; no MCP imports or blocking waits in callbacks."""

from collections import deque
import os
import secrets
import subprocess
import time

from clo3d_mcp import BUILD
from clo3d_mcp.pipe_session import Executor
from clo3d_mcp.child_python import command
from clo3d_mcp.protocol import ProtocolError
from clo3d_mcp.transport.channel import Channel
from clo3d_mcp.transport.winpipe import Pipe


class PipeProbe:
    def __init__(self, timer, read_count, generation, report=print, profile="p1", create_rectangle=None,
                 port=8765, command_handler=None):
        if profile not in ("p1", "p2", "service"):
            raise ValueError("Unknown diagnostic profile")
        self.profile = profile
        self.create_rectangle = create_rectangle
        self.command_handler = command_handler
        self.service_ready = False
        self.port = port
        self.timer = timer
        self.owner_thread = timer.thread_id()
        self.callback_thread = None
        self.read_count = read_count
        self.generation = generation
        self.report = report
        self.state = "new"
        self.timer_id = None
        self.callback = None
        self.process = None
        self.executor = None
        self.pipe = None
        self.channel = None
        self.name = "clo3d_mcp_" + secrets.token_hex(16)
        self.session_id = secrets.token_hex(16)
        self.key = secrets.token_bytes(32)
        self.started_at = time.monotonic()
        self.next_connect = 0.0
        self.connect_deadline = None
        self.stop_at = None
        self.busy = False
        self.ticks = 0
        self.reentrant_ticks = 0
        self.connections = 0
        self.disconnects = 0
        self.error = None
        self.stop_reason = None
        self.exit_code = None
        self.terminate_sent = False
        self.events = deque(maxlen=32)

    def emit(self, kind):
        label = "MCP" if self.profile == "service" else self.profile.upper()
        text = "[CLO %s] %s %s" % (label, kind, self.snapshot())
        self.events.append(text[:1500])
        try:
            self.report(text)
        except BaseException:
            pass

    def snapshot(self):
        executor = self.executor
        return dict(
            generation=self.generation, state=self.state, ticks=self.ticks,
            owner_thread=self.owner_thread, callback_thread=self.callback_thread,
            connections=self.connections, disconnects=self.disconnects,
            handshakes=executor.handshakes if executor else 0,
            jobs=executor.jobs if executor else 0,
            api_calls=executor.api_calls if executor else 0,
            pattern_count=executor.last_count if executor else None,
            reentrant_ticks=self.reentrant_ticks, stop_reason=self.stop_reason,
            pipe_cleanup_pending=self.pipe is not None,
            timer_cleanup_pending=self.timer_id is not None,
            child_exit_code=self.exit_code, error=self.error,
            service_ready=self.service_ready, build=BUILD,
        )

    def start(self, python, root):
        if self.timer.visible_window_threads() != {self.owner_thread}:
            raise RuntimeError("P1 script must run on the verified CLO UI thread")
        self.callback = self.timer.wrap(self.on_timer)
        self.timer_id = self.timer.start(self.callback)
        self.state = "starting"
        env = os.environ.copy()
        # Standalone process receives only local source path, not embedded CLO paths.
        env.pop("PYTHONHOME", None)
        env["PYTHONPATH"] = str(root / "src")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.update(CLO_MCP_P1_PIPE=self.name, CLO_MCP_P1_SESSION=self.session_id,
                   CLO_MCP_P1_KEY=self.key.hex(), CLO_MCP_P1_CLO_PID=str(os.getpid()))
        try:
            args = command(python, env)
            if self.profile == "p2":
                args[-1] = "clo3d_mcp.queue_diagnostic"
            parent = None
            try:
                options = {}
                if self.profile == "service":
                    from clo3d_mcp.transport.winprocess import ProcessHandle
                    parent = ProcessHandle(os.getpid())
                    env["CLO_MCP_PARENT_HANDLE"] = str(parent.handle)
                    env["CLO_MCP_HTTP_PORT"] = str(self.port)
                    env["CLO_MCP_PATTERN_PACKAGE"] = "1" if self.command_handler is not None else "0"
                    startup = subprocess.STARTUPINFO()
                    startup.lpAttributeList = {"handle_list": [parent.handle]}
                    options["startupinfo"] = startup
                    args[-1] = "clo3d_mcp.transport_server"
                self.process = subprocess.Popen(
                    args, cwd=str(root), env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True, **options,
                )
            finally:
                if parent is not None:
                    parent.close()
            self.executor = Executor(self.session_id, self.key, self.process.pid, self.read_count,
                                     self.create_rectangle if self.profile == "service" else None,
                                     self.command_handler if self.profile == "service" else None)
            self.state = "connecting"
            self.emit("STARTED (not yet connected)")
        except BaseException:
            self.stop("launch_failed")
            raise

    def stop(self, reason="manual"):
        if self.timer.thread_id() != self.owner_thread:
            raise RuntimeError("P1 stop must run on registering thread")
        if self.stop_at is None:
            self.stop_at = time.monotonic()
            self.stop_reason = reason
        self.service_ready = False
        if self.profile == "service" and self.state == "requesting_stop" and reason == "manual" and self.process.poll() is None:
            self.emit("STOP_STATUS")
            return
        if (self.profile == "service" and self.state == "active" and not self.busy
                and self.channel is not None and reason == "manual"):
            # Ask external server to shut down HTTP/queue. ACK is its exit;
            # retain native operations, with a specific-child fallback below.
            from clo3d_mcp.protocol import message
            try:
                self.channel.send(message("STOP", self.session_id))
            except (OSError, ProtocolError):
                self.error = "server_stop_send_failed"
            else:
                self.state = "requesting_stop"
                self.emit("STOP_REQUESTED")
                return
        if self.state not in ("stopped", "failed"):
            self.state = "stopping"
        if self.pipe is not None:
            self.pipe.begin_close()
        if not self.busy:
            self._cleanup()
        self.emit("STOP_STATUS")

    def _cleanup(self):
        if self.pipe is not None:
            if not self.pipe.poll_close():
                return
            self.pipe = None
            self.channel = None
        if self.process is not None:
            self.exit_code = self.process.poll()
            if self.exit_code is None:
                if (self.stop_reason != "peer_stop" or time.monotonic() - self.stop_at >= 2.0):
                    if not self.terminate_sent:
                        self.process.terminate()  # specific Popen handle, never name/port
                        self.terminate_sent = True
                return
            if self.stop_reason == "peer_stop" and self.exit_code != 0:
                self.error = "diagnostic_child_failed"
        if self.timer_id is not None:
            self.timer.stop(self.timer_id)
            self.timer_id = None
        self.state = "failed" if self.error else "stopped"
        self.key = None
        if self.executor:
            self.executor.key = None
        self.emit("FINISHED")

    def on_timer(self, hwnd, msg, timer_id, timestamp):
        try:
            if timer_id != self.timer_id or self.state in ("stopped", "failed", "new"):
                return
            if self.busy:
                self.reentrant_ticks += 1
                return
            self.busy = True
            try:
                self.callback_thread = self.timer.thread_id()
                if self.callback_thread != self.owner_thread:
                    raise RuntimeError("P1 callback thread mismatch")
                self.ticks += 1
                if self.state == "stopping":
                    self._cleanup()
                    return
                now = time.monotonic()
                if ((self.profile != "service" or not self.service_ready)
                        and self.stop_at is None and now - self.started_at > 90.0):
                    self.error = "diagnostic_timeout"
                    self.stop("ninety_second_limit")
                    return
                exit_code = self.process.poll()
                if exit_code is not None:
                    if self.state == "requesting_stop":
                        if exit_code != 0:
                            self.error = "server_shutdown_failed"
                        self.stop("manual")
                        return
                    if self.state == "draining_stop" and exit_code == 0:
                        # Successful child exit proves it received our STOP ACK;
                        # its final pipe close may race the next UI tick.
                        self.stop("peer_stop")
                        return
                    self.error = ("http_bind_failed" if self.profile == "service" and exit_code == 3
                                  else "diagnostic_child_exited_before_stop")
                    self.stop("child_exit")
                    return
                if self.state == "requesting_stop":
                    if now - self.stop_at >= 3.0:
                        self.error = "server_shutdown_timeout"
                        self.stop("shutdown_fallback")
                        return
                    try:
                        self.channel.poll()
                    except OSError:
                        pass  # child-exit check above, bounded fallback below
                    return
                if self.state == "reconnecting":
                    if not self.pipe.poll_close():
                        return
                    self.pipe = None
                    self.channel = None
                    self.state = "connecting"
                if self.state == "connecting":
                    if now < self.next_connect:
                        return
                    self.next_connect = now + 0.25
                    self.pipe = Pipe.try_open(self.name)
                    if self.pipe is None:
                        return
                    hello = self.executor.connected(self.pipe.peer_pid())
                    self.channel = Channel(self.pipe, self.session_id)
                    self.channel.send(hello)
                    self.connect_deadline = now + 15.0
                    self.connections += 1
                    self.state = "active"
                if self.state == "draining_stop":
                    try:
                        frames = self.channel.poll()
                    except OSError as exc:
                        if getattr(exc, "winerror", None) not in (109, 232, 233):
                            raise
                        # Peer may have read ACK and closed before Popen notices
                        # its exit. Only exit code 0 confirms a successful test.
                        if not self.channel.drained:
                            raise ProtocolError("Peer closed before STOP ACK drain") from None
                        self.stop("peer_stop")
                        return
                    if frames:
                        raise ProtocolError("Messages after STOP are forbidden")
                    if self.channel.drained:
                        self.stop("peer_stop")
                    return
                try:
                    frames = self.channel.poll()
                except OSError as exc:
                    if getattr(exc, "winerror", None) not in (109, 232, 233):
                        raise
                    self.channel.decoder.eof()
                    self.disconnects += 1
                    if self.disconnects > 2:
                        raise ProtocolError("P1 reconnect limit")
                    self.pipe.begin_close()
                    self.executor.disconnected()
                    self.state = "reconnecting"
                    self.emit("DISCONNECTED (no job replay)")
                    return
                # P1 server issues one JOB only after READY. Reject unsolicited
                # batches BEFORE executing even the first API call.
                if len(frames) > 1:
                    raise ProtocolError("Expected one server message per exchange")
                for frame in frames:
                    if self.state != "active":
                        raise ProtocolError("Messages after STOP are forbidden")
                    if frame["kind"] == "SERVICE_READY":
                        if (self.profile != "service" or self.service_ready
                                or self.executor.state != "ready"):
                            raise ProtocolError("Unexpected service readiness")
                        self.service_ready = True
                        from clo3d_mcp.protocol import message
                        self.channel.send(message("SERVICE_READY", self.session_id))
                        self.emit("READY http://127.0.0.1:%d/mcp" % self.port)
                        continue
                    replies = self.executor.receive(frame)
                    if self.state == "stopping":
                        # CLO API may pump messages and allow a manual stop.
                        # Do not queue a response on an already closing pipe.
                        return
                    for reply in replies:
                        self.channel.send(reply)
                    if self.executor.state == "stopping":
                        self.state = "draining_stop"
                    if self.profile != "service" or frame["kind"] != "JOB":
                        self.emit("RECEIVED_" + frame["kind"])
                if self.executor.state == "handshake" and now >= self.connect_deadline:
                    raise ProtocolError("P1 handshake deadline")
            finally:
                self.busy = False
        except BaseException as exc:
            # Type only: do not print peer payloads, tokens or scene paths.
            self.error = type(exc).__name__
            try:
                self.stop("callback_failure")
            except BaseException:
                # Still retained. Next owner-thread tick/stop can retry cleanup.
                self.state = "stopping"


def start(registry, timer, read_count, python, root, profile="p1", create_rectangle=None, command_handler=None):
    current = registry.get("current")
    if current is not None:
        if current.state not in ("stopped", "failed"):
            current.emit("ALREADY_STARTED")
            return current
        if current.timer_id is not None or current.pipe is not None or current.busy:
            raise RuntimeError("Previous P1 generation needs cleanup")
    retained = registry.setdefault("retained", [])
    probe = PipeProbe(timer, read_count, len(retained) + 1, profile=profile,
                      create_rectangle=create_rectangle, command_handler=command_handler)
    retained.append(probe)
    registry["current"] = probe
    try:
        probe.start(python, root)
    except BaseException:
        probe.error = "startup_failed"
        probe.stop("startup_failed")
        raise
    return probe
