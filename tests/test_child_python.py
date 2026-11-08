"""Resolver contracts; actual PID + venv identity covered by Windows worker."""

from pathlib import Path

import pytest

from clo3d_mcp.child_python import command


def venv(tmp_path, home=None):
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    if home is None:
        home = tmp_path / "base"
        home.mkdir()
        (home / "python.exe").touch()
    (python.parent.parent / "pyvenv.cfg").write_text("home = " + str(home), encoding="utf-8")
    return python


def test_explicit_base_and_venv_hint_no_path_discovery(tmp_path):
    python = venv(tmp_path)
    env = {}
    args = command(python, env)
    assert Path(args[0]) == tmp_path / "base" / "python.exe"
    assert args[1:] == ["-m", "clo3d_mcp.pipe_diagnostic"]
    assert env == {"__PYVENV_LAUNCHER__": str(python.resolve())}


@pytest.mark.parametrize("home", ["relative-base", "missing-base"])
def test_no_silent_fallback_to_another_python(tmp_path, home):
    path = home if home == "relative-base" else tmp_path / home
    python = venv(tmp_path, path)
    with pytest.raises(RuntimeError):
        command(python, {})


def test_arbitrary_executable_rejected(tmp_path):
    with pytest.raises(RuntimeError):
        command(tmp_path / "CLO.exe", {})
