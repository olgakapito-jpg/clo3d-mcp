"""A pinned Windows process handle, inherited explicitly by the owned child.

Only SYNCHRONIZE access, zero-time polling; no PID rediscovery or termination.
"""

import ctypes as ct
from ctypes import wintypes as wt
import sys


class ProcessHandle:
    def __init__(self, pid=None, *, inherited=None):
        if sys.platform != "win32":
            raise RuntimeError("Process monitor requires Windows")
        self.k = ct.WinDLL("kernel32", use_last_error=True)
        for name, restype, argtypes in [
            ("OpenProcess", wt.HANDLE, [wt.DWORD, wt.BOOL, wt.DWORD]),
            ("WaitForSingleObject", wt.DWORD, [wt.HANDLE, wt.DWORD]),
            ("CloseHandle", wt.BOOL, [wt.HANDLE]),
            ("GetProcessId", wt.DWORD, [wt.HANDLE]),
        ]:
            function = getattr(self.k, name)
            function.restype, function.argtypes = restype, argtypes
        # Query-limited access allows verifying an inherited handle's PID.
        self.handle = inherited if inherited is not None else self.k.OpenProcess(0x101000, True, pid)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())

    def pid(self):
        value = self.k.GetProcessId(self.handle)
        if not value:
            raise ct.WinError(ct.get_last_error())
        return value

    def alive(self):
        status = self.k.WaitForSingleObject(self.handle, 0)
        if status == 0:
            return False
        if status == 258:
            return True
        raise ct.WinError(ct.get_last_error())

    def close(self):
        if self.handle is not None:
            if not self.k.CloseHandle(self.handle):
                raise ct.WinError(ct.get_last_error())
            self.handle = None
