"""Resolve the explicit Windows CPython venv without its redirector process."""

from pathlib import Path


def command(python, env):
    """Use the same base interpreter + launcher hint as CPython's venv launcher.

    Popen then owns the actual pipe-server process: PID checks and terminate()
    refer to that exact process, not a redirector. Read only venv configuration,
    never IPC. No interpreter discovery via PATH or embedded sys.executable.
    """
    python = Path(python).resolve()
    config = python.parent.parent / "pyvenv.cfg"
    if python.name.lower() != "python.exe" or python.parent.name.lower() != "scripts":
        raise RuntimeError("Expected an explicit Windows venv/Scripts/python.exe")
    fields = {}
    for line in config.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator:
            fields[name.strip()] = value.strip()
    home = Path(fields.get("home", ""))
    base = home / "python.exe"
    if (not python.is_file() or not home.is_absolute() or not base.is_file()
            or base.resolve() == python):
        raise RuntimeError("The prepared venv needs an existing base CPython")
    # CPython consumes/removes this variable during initialization and locates
    # pyvenv.cfg using the explicit venv path (including its site-packages).
    env["__PYVENV_LAUNCHER__"] = str(python)
    return [str(base), "-m", "clo3d_mcp.pipe_diagnostic"]
