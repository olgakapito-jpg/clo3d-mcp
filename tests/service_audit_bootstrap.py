"""Test-only child bootstrap: abort on filesystem mutations, never IPC to disk.

Loaded before transport_server/SDK imports. Reads of source/venv configuration
are allowed. Exit 91 is deliberately not catchable by application code.
"""

import os
import sys


def audit(event, args):
    forbidden = event in {
        "os.mkdir", "os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink",
        "os.truncate", "tempfile.mkstemp", "tempfile.mkdtemp",
    }
    if event == "open":
        path, mode, flags = args
        if isinstance(path, str) and path.lower() == os.devnull.lower():
            return  # Windows NUL device is not a filesystem IPC file.
        forbidden = (isinstance(mode, str) and any(char in mode for char in "wax+")) or (
            isinstance(flags, int) and bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
    if forbidden:
        os.write(2, ("AUDIT rejected " + event + "\n").encode("ascii"))
        os._exit(91)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.addaudithook(audit)
    import runpy

    runpy.run_module("clo3d_mcp.transport_server", run_name="__main__")
