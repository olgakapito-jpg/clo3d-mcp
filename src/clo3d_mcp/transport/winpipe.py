"""Local-user byte-mode Windows pipes, entirely overlapped after local open.

No waits, threads, sleeps or automatic command retries. Owners drive poll/close
from their scheduler. Pending buffers/events are retained until terminal I/O.
"""

import ctypes as ct
from ctypes import wintypes as wt
import re
import sys


INVALID_HANDLE = ct.c_void_p(-1).value
ERROR_IO_PENDING = 997
ERROR_IO_INCOMPLETE = 996
ERROR_OPERATION_ABORTED = 995
ERROR_PIPE_CONNECTED = 535
ERROR_NOT_FOUND = 1168
OVERLAPPED_FLAG = 0x40000000
FIRST_INSTANCE = 0x00080000
REJECT_REMOTE = 0x00000008
CHUNK_SIZE = 16384
_live = set()  # Explicit close releases. No destructor may free a pending buffer.


class OVERLAPPED(ct.Structure):
    # The union's Offset/OffsetHigh layout is pointer-sized on x64 and x86.
    _fields_ = [("Internal", ct.c_size_t), ("InternalHigh", ct.c_size_t),
                ("Offset", wt.DWORD), ("OffsetHigh", wt.DWORD), ("hEvent", wt.HANDLE)]


class SECURITY_ATTRIBUTES(ct.Structure):
    _fields_ = [("nLength", wt.DWORD), ("lpSecurityDescriptor", ct.c_void_p),
                ("bInheritHandle", wt.BOOL)]


class SID_AND_ATTRIBUTES(ct.Structure):
    _fields_ = [("Sid", ct.c_void_p), ("Attributes", wt.DWORD)]


def pipe_name(value):
    """Never accept a remote name, disk path or arbitrary device name."""
    if not isinstance(value, str) or not re.fullmatch(r"clo3d_mcp_[a-f0-9]{32}", value):
        raise ValueError("Invalid local pipe identifier")
    return "\\\\.\\pipe\\" + value


class WindowsAPI:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Named Pipe transport requires Windows")
        self.k = ct.WinDLL("kernel32", use_last_error=True)
        self.a = ct.WinDLL("advapi32", use_last_error=True)
        ptr_ov = ct.POINTER(OVERLAPPED)
        ptr_dw = ct.POINTER(wt.DWORD)
        declarations = [
            (self.k, "CreateNamedPipeW", wt.HANDLE,
             [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD,
              wt.DWORD, ct.POINTER(SECURITY_ATTRIBUTES)]),
            (self.k, "CreateFileW", wt.HANDLE,
             [wt.LPCWSTR, wt.DWORD, wt.DWORD, ct.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]),
            (self.k, "ConnectNamedPipe", wt.BOOL, [wt.HANDLE, ptr_ov]),
            (self.k, "DisconnectNamedPipe", wt.BOOL, [wt.HANDLE]),
            (self.k, "CreateEventW", wt.HANDLE, [ct.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]),
            (self.k, "ReadFile", wt.BOOL, [wt.HANDLE, ct.c_void_p, wt.DWORD, ptr_dw, ptr_ov]),
            (self.k, "WriteFile", wt.BOOL, [wt.HANDLE, ct.c_void_p, wt.DWORD, ptr_dw, ptr_ov]),
            (self.k, "GetOverlappedResult", wt.BOOL, [wt.HANDLE, ptr_ov, ptr_dw, wt.BOOL]),
            (self.k, "CancelIoEx", wt.BOOL, [wt.HANDLE, ptr_ov]),
            (self.k, "CloseHandle", wt.BOOL, [wt.HANDLE]),
            (self.k, "GetNamedPipeClientProcessId", wt.BOOL, [wt.HANDLE, ptr_dw]),
            (self.k, "GetNamedPipeServerProcessId", wt.BOOL, [wt.HANDLE, ptr_dw]),
            (self.k, "GetCurrentProcess", wt.HANDLE, []),
            (self.k, "LocalFree", ct.c_void_p, [ct.c_void_p]),
            (self.a, "OpenProcessToken", wt.BOOL, [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]),
            (self.a, "GetTokenInformation", wt.BOOL,
             [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ptr_dw]),
            (self.a, "ConvertSidToStringSidW", wt.BOOL,
             [ct.c_void_p, ct.POINTER(wt.LPWSTR)]),
            (self.a, "ConvertStringSecurityDescriptorToSecurityDescriptorW", wt.BOOL,
             [wt.LPCWSTR, wt.DWORD, ct.POINTER(ct.c_void_p), ptr_dw]),
        ]
        for dll, name, result, args in declarations:
            function = getattr(dll, name)
            function.argtypes = args
            function.restype = result

    def check(self, success):
        if not success:
            raise ct.WinError(ct.get_last_error())

    def close(self, handle):
        self.check(self.k.CloseHandle(handle))

    def user_sid(self):
        token = wt.HANDLE()
        self.check(self.a.OpenProcessToken(self.k.GetCurrentProcess(), 0x0008, ct.byref(token)))
        try:
            size = wt.DWORD()
            ok = self.a.GetTokenInformation(token, 1, None, 0, ct.byref(size))
            error = ct.get_last_error()
            if ok or error != 122:
                raise RuntimeError("Cannot size TokenUser")
            buffer = ct.create_string_buffer(size.value)
            self.check(self.a.GetTokenInformation(token, 1, buffer, size, ct.byref(size)))
            sid = ct.cast(buffer, ct.POINTER(SID_AND_ATTRIBUTES)).contents.Sid
            text = wt.LPWSTR()
            self.check(self.a.ConvertSidToStringSidW(sid, ct.byref(text)))
            try:
                return text.value
            finally:
                self.k.LocalFree(ct.cast(text, ct.c_void_p))
        finally:
            self.close(token)

    def create_server(self, name):
        # Explicit protected DACL, current account only; never default Everyone ACL.
        descriptor = ct.c_void_p()
        sddl = "D:P(A;;GA;;;%s)" % self.user_sid()
        self.check(self.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ct.byref(descriptor), None))
        try:
            attributes = SECURITY_ATTRIBUTES(ct.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
            handle = self.k.CreateNamedPipeW(
                pipe_name(name), 3 | OVERLAPPED_FLAG | FIRST_INSTANCE,
                REJECT_REMOTE, 1, CHUNK_SIZE, CHUNK_SIZE, 0, ct.byref(attributes))
            if handle == INVALID_HANDLE:
                raise ct.WinError(ct.get_last_error())
            return handle
        finally:
            self.k.LocalFree(descriptor)


class Operation:
    """Lifetime is owned by Pipe.operations, even if a caller drops its reference."""

    def __init__(self, pipe, kind, data=None):
        self.pipe = pipe
        self.kind = kind
        self.buffer = None if kind == "connect" else (
            ct.create_string_buffer(CHUNK_SIZE) if kind == "read"
            else ct.create_string_buffer(data, len(data)))
        self.ov = OVERLAPPED()
        self.ov.hEvent = pipe.api.k.CreateEventW(None, True, False, None)
        if not self.ov.hEvent:
            raise ct.WinError(ct.get_last_error())
        self.done = False
        self.result = None
        self.error = None
        self.cancel_requested = False
        pipe.operations.add(self)
        try:
            if kind == "connect":
                ok = pipe.api.k.ConnectNamedPipe(pipe.handle, ct.byref(self.ov))
            else:
                function = pipe.api.k.ReadFile if kind == "read" else pipe.api.k.WriteFile
                length = CHUNK_SIZE if kind == "read" else len(data)
                ok = function(pipe.handle, self.buffer, length, None, ct.byref(self.ov))
        except BaseException:
            # ctypes argument/submission failure: no operation was queued.
            self._finish(0, 87)
            raise
        error = ct.get_last_error() if not ok else 0
        if kind == "connect" and error == ERROR_PIPE_CONNECTED:
            self._finish(0, 0)
        elif not ok and error != ERROR_IO_PENDING:
            self._finish(0, error)
        elif ok:
            # Never release pending storage if a later poll itself fails.
            self.poll()

    def _finish(self, count, error):
        self.done = True
        self.error = error
        self.result = bytes(self.buffer.raw[:count]) if self.kind == "read" else count
        self._release_event()

    def _release_event(self):
        if self.ov.hEvent:
            self.pipe.api.close(self.ov.hEvent)
            self.ov.hEvent = None
        self.pipe.operations.discard(self)

    def poll(self):
        if not self.done:
            count = wt.DWORD()
            ok = self.pipe.api.k.GetOverlappedResult(
                self.pipe.handle, ct.byref(self.ov), ct.byref(count), False)
            error = ct.get_last_error() if not ok else 0
            if error == ERROR_IO_INCOMPLETE:
                return None
            self._finish(count.value, error)
        elif self.ov.hEvent:
            self._release_event()
        if self.error:
            raise ct.WinError(self.error)
        return self.result

    def cancel(self):
        if self.done or self.cancel_requested:
            return
        ok = self.pipe.api.k.CancelIoEx(self.pipe.handle, ct.byref(self.ov))
        error = ct.get_last_error() if not ok else 0
        if error not in (0, ERROR_NOT_FOUND):
            raise ct.WinError(error)
        self.cancel_requested = True


class Pipe:
    """At most one read, one write and one connect. Explicit staged shutdown."""

    def __init__(self, api, handle, server=False):
        self.api = api
        self.handle = handle
        self.server = server
        self.operations = set()
        self.closing = False
        self.closed = False
        _live.add(self)

    @classmethod
    def listen(cls, name):
        if len(_live) >= 64:
            raise RuntimeError("Too many retained pipes; finish pending cleanup")
        api = WindowsAPI()
        return cls(api, api.create_server(name), server=True)

    @classmethod
    def try_open(cls, name):
        if len(_live) >= 64:
            raise RuntimeError("Too many retained pipes; finish pending cleanup")
        api = WindowsAPI()
        # Local namespace only. No WaitNamedPipe; absent/busy returns to scheduler.
        # Identification SQOS prevents the peer from impersonating this client.
        handle = api.k.CreateFileW(pipe_name(name), 0xC0000000, 0, None, 3,
                                   OVERLAPPED_FLAG | 0x00100000 | 0x00010000, None)
        if handle == INVALID_HANDLE:
            error = ct.get_last_error()
            if error in (2, 231):
                return None
            raise ct.WinError(error)
        return cls(api, handle)

    def _start(self, kind, data=None):
        if self.closing or self.closed:
            raise RuntimeError("Pipe is closing")
        if any(op.kind == kind for op in self.operations):
            raise RuntimeError("Operation already pending")
        return Operation(self, kind, data)

    def connect(self):
        if not self.server:
            raise RuntimeError("Only server can accept a connection")
        return self._start("connect")

    def read(self):
        return self._start("read")

    def write(self, data):
        if not isinstance(data, bytes) or not 0 < len(data) <= CHUNK_SIZE:
            raise ValueError("Write requires one bounded nonempty bytes chunk")
        return self._start("write", data)

    def peer_pid(self):
        pid = wt.DWORD()
        function = (self.api.k.GetNamedPipeClientProcessId if self.server
                    else self.api.k.GetNamedPipeServerProcessId)
        self.api.check(function(self.handle, ct.byref(pid)))
        return pid.value

    def begin_close(self):
        self.closing = True
        for operation in tuple(self.operations):
            operation.cancel()

    def poll_close(self, reuse=False):
        """False = retained pending buffers; caller must schedule another poll.

        reuse=True disconnects the server but retains its unique listener name.
        Never FlushFileBuffers: it could block waiting for a peer to read.
        """
        if self.closed:
            return True
        if not self.closing:
            self.begin_close()
        for operation in tuple(self.operations):
            try:
                operation.poll()
            except OSError:
                # Any terminal completion (aborted, broken or success) is safe.
                if not operation.done:
                    raise
        if self.operations:
            return False
        if reuse:
            if not self.server:
                raise RuntimeError("Only server pipes can be reused")
            ok = self.api.k.DisconnectNamedPipe(self.handle)
            error = ct.get_last_error() if not ok else 0
            if error not in (0, 233):  # ERROR_PIPE_NOT_CONNECTED
                raise ct.WinError(error)
            self.closing = False
            return True
        self.api.close(self.handle)
        self.handle = None
        self.closed = True
        _live.discard(self)
        return True
