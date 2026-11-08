"""P0 only: bounded Win32 callback probe; no legacy listener, MCP or IPC.

Run this file in CLO's Script Editor. Re-running reports the active probe.
Auto-stops after 60 seconds. Stop/report with clo3d_mcp_probe_stop.py.
See docs/P0_CALLBACK_CHECK.md.
"""

import builtins
import collections
import importlib
import os
import struct
import sys
import time


class WindowsTimer:
    """Explicit pointer-width Win32 ABI; no message loop or blocking fallback."""

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("P0 requires Windows inside CLO")
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wt = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.timer_proc = ctypes.WINFUNCTYPE(
            None, wintypes.HWND, wintypes.UINT, ctypes.c_size_t, wintypes.DWORD
        )
        self.enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user32.SetTimer.argtypes = [
            wintypes.HWND, ctypes.c_size_t, wintypes.UINT, self.timer_proc
        ]
        self.user32.SetTimer.restype = ctypes.c_size_t
        self.user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        self.user32.KillTimer.restype = wintypes.BOOL
        self.user32.EnumWindows.argtypes = [self.enum_proc, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
        ]
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.kernel32.GetCurrentThreadId.argtypes = []
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def thread_id(self):
        return int(self.kernel32.GetCurrentThreadId())

    def visible_window_threads(self):
        """Conservative UI evidence: all visible process windows share a thread."""
        threads = set()
        errors = []
        pid = os.getpid()

        def visit(hwnd, _):
            try:
                owner = self.wt.DWORD()
                tid = self.user32.GetWindowThreadProcessId(hwnd, self.ctypes.byref(owner))
                if not tid:
                    raise self.ctypes.WinError(self.ctypes.get_last_error())
                if owner.value == pid and self.user32.IsWindowVisible(hwnd):
                    threads.add(int(tid))
                return True
            except BaseException as exc:
                errors.append(exc)
                return False

        callback = self.enum_proc(visit)
        if not self.user32.EnumWindows(callback, 0):
            error = self.ctypes.get_last_error()
            if errors:
                raise errors[0]
            raise self.ctypes.WinError(error)
        return threads

    def wrap(self, callback):
        return self.timer_proc(callback)

    def start(self, callback):
        timer_id = self.user32.SetTimer(None, 0, 250, callback)
        if not timer_id:
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return int(timer_id)

    def stop(self, timer_id):
        if not self.user32.KillTimer(None, timer_id):
            # KillTimer does not document extended error information.
            raise RuntimeError("KillTimer returned zero; cleanup not confirmed")


class Probe:
    """One callback owns one state forever, including after stop/restart."""

    def __init__(self, backend, read_count, generation, clock=time.monotonic, report=print):
        self.backend = backend
        self.read_count = read_count
        self.generation = generation
        self.clock = clock
        self.report = report
        self.owner_thread = backend.thread_id()
        self.callback_thread = None
        self.state = "new"
        self.timer_id = None
        self.callback = None
        self.busy = False
        self.armed = False
        self.started_at = clock()
        self.limit_seconds = 60.0
        self.stopped_at = None
        self.stop_reason = None
        self.api_due = self.started_at + 2.0
        self.report_due = self.started_at + 30.0
        self.ticks = 0
        self.api_calls = 0
        self.reentrant_ticks = 0
        self.ignored_ticks = 0
        self.last_count = None
        self.max_api_ms = 0.0
        self.error = None
        self.events = collections.deque(maxlen=32)

    def emit(self, message):
        text = "[CLO P0] " + message
        self.events.append(text[:500])
        try:
            self.report(text)
        except BaseException:
            # Script Editor may close its output sink. Status remains in memory.
            pass

    def start(self):
        if self.backend.visible_window_threads() != {self.owner_thread}:
            self.state = "failed"
            raise RuntimeError("Script thread is not the sole visible CLO window thread; no API called")
        self.callback = self.backend.wrap(self.on_timer)
        self.state = "registering"
        try:
            self.timer_id = self.backend.start(self.callback)
            self.state = "running"
        except BaseException:
            self.state = "failed"
            raise

    def arm(self):
        self.armed = True
        self.emit("ARMED generation=%d thread=%d auto_stop_seconds=%.0f; "
                  "script returning, callback not yet proven"
                  % (self.generation, self.owner_thread, self.limit_seconds))

    def stop(self, reason="manual"):
        if self.backend.thread_id() != self.owner_thread:
            raise RuntimeError("Stop must run on the registering CLO thread")
        if self.state not in ("failed", "stopped"):
            self.state = "stopped"
        self.armed = False
        if self.stopped_at is None:
            self.stopped_at = self.clock()
            self.stop_reason = reason
        # Disable first: queued/reentrant callbacks must not call the API.
        if self.timer_id is not None:
            self.backend.stop(self.timer_id)
            self.timer_id = None
        self.emit("STOP reason=%s %s" % (reason, self.snapshot()))

    def snapshot(self):
        return {
            "generation": self.generation, "state": self.state,
            "limit_seconds": self.limit_seconds,
            "elapsed_seconds": round(
                (self.clock() if self.stopped_at is None else self.stopped_at) - self.started_at, 3
            ),
            "stop_reason": self.stop_reason,
            "owner_thread": self.owner_thread, "callback_thread": self.callback_thread,
            "ticks": self.ticks, "api_calls": self.api_calls,
            "pattern_count": self.last_count, "reentrant_ticks": self.reentrant_ticks,
            "ignored_ticks": self.ignored_ticks, "max_api_ms": round(self.max_api_ms, 3),
            "timer_cleanup_pending": self.timer_id is not None and self.state != "running",
            "error": self.error,
        }

    def on_timer(self, hwnd, msg, timer_id, timestamp):
        """Nothing, including BaseException, may escape the native boundary."""
        try:
            if self.state != "running" or not self.armed or timer_id != self.timer_id:
                self.ignored_ticks += 1
                return
            if self.busy:
                self.reentrant_ticks += 1
                return
            self.busy = True
            try:
                self.callback_thread = self.backend.thread_id()
                if self.callback_thread != self.owner_thread:
                    raise RuntimeError("Callback thread mismatch; no API called")
                now = self.clock()
                self.ticks += 1
                if now - self.started_at >= self.limit_seconds:
                    self.stop("one_minute_limit")
                    return
                if now >= self.api_due:
                    before = self.clock()
                    count = self.read_count()
                    self.max_api_ms = max(self.max_api_ms, (self.clock() - before) * 1000.0)
                    self.last_count = count
                    self.api_calls += 1
                    self.api_due = self.clock() + 5.0
                    if self.api_calls == 1:
                        self.emit("FIRST_API %s" % self.snapshot())
                if self.state == "running" and now >= self.report_due:
                    self.report_due = now + 30.0
                    self.emit("STATUS %s" % self.snapshot())
            finally:
                self.busy = False
        except BaseException as exc:
            self.state = "failed"
            self.armed = False
            try:
                self.error = (type(exc).__name__ + ": " + str(exc))[:500]
                self.emit("FAILED %s" % self.snapshot())
                self.stop("callback_failure")
            except BaseException:
                # Wrong-thread/failed KillTimer: retain callback + timer ID and
                # refuse future starts until owner-thread cleanup succeeds.
                pass


def start_probe(registry, backend, read_count, clock=time.monotonic, report=print):
    current = registry.get("current")
    if current is not None:
        if current.state == "running":
            current.emit("ALREADY_RUNNING %s" % current.snapshot())
            return current
        if current.timer_id is not None or current.busy:
            raise RuntimeError("Previous callback needs owner-thread stop before restart")
    retained = registry.setdefault("retained", [])
    if len(retained) >= 16:
        raise RuntimeError("P0 limit: 16 generations retained; restart CLO before more tests")
    probe = Probe(backend, read_count, len(retained) + 1, clock, report)
    # Retain BEFORE handing any callback address to Windows. Never discard on
    # KillTimer: queued WM_TIMER can still hold that native address.
    retained.append(probe)
    registry["current"] = probe
    probe.start()
    probe.arm()
    return probe


def main():
    report = print
    report("[CLO P0] Python=%s bits=%d PID=%d platform=%s"
           % (sys.version.replace("\n", " "), struct.calcsize("P") * 8, os.getpid(), sys.platform))
    registry = getattr(builtins, "_clo3d_mcp_p0", None)
    if registry is None:
        registry = {"version": 1, "retained": []}
        builtins._clo3d_mcp_p0 = registry
    if registry.get("version") != 1:
        raise RuntimeError("Unknown P0 registry; restart CLO rather than replacing callback references")
    current = registry.get("current")
    if current is not None and current.state == "running":
        current.emit("ALREADY_RUNNING %s" % current.snapshot())
        return
    backend = WindowsTimer()
    report("[CLO P0] ctypes=available native_thread=%d visible_window_threads=%s"
           % (backend.thread_id(), sorted(backend.visible_window_threads())))
    # Import only CLO modules; NEVER import the legacy plugin (it auto-starts).
    for name in ("pattern_api", "utility_api", "export_api", "import_api", "fabric_api"):
        try:
            importlib.import_module(name)
            report("[CLO P0] module=%s available" % name)
        except ImportError as exc:
            report("[CLO P0] module=%s unavailable: %s" % (name, exc))
    pattern_api = importlib.import_module("pattern_api")
    start_probe(registry, backend, pattern_api.GetPatternCount, report=report)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("[CLO P0] NOT_STARTED %s: %s" % (type(exc).__name__, exc))
