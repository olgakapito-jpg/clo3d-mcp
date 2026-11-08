"""Real Windows pipes in timeout-isolated processes; no CLO access."""

from pathlib import Path
import subprocess
import sys

import pytest

from clo3d_mcp.transport.winpipe import pipe_name


@pytest.mark.parametrize("value", ["C:\\file", "\\\\host\\pipe\\x", "x", "clo3d_mcp_" + "z" * 32, None])
def test_reject_arbitrary_devices_and_remote_paths(value):
    with pytest.raises(ValueError):
        pipe_name(value)


@pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows Named Pipe test")
@pytest.mark.parametrize("scenario", [
    "basic", "reconnect", "fragmentation", "stalled_writer", "pending_connect_and_handles",
    "midframe", "python_identity", "bad_authentication", "external_roundtrip", "queue_roundtrip",
    "queue_probe_roundtrip",
    "service_roundtrip", "service_parent_exit", "service_load", "malformed_frames", "service_patterns",
])
def test_real_pipe(scenario):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("pipe_worker.py")), scenario],
        capture_output=True, text=True, timeout=100 if scenario == "service_load" else 20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS " + scenario in result.stdout
