"""Acceptance client's stateful scenario and stop-on-error, no actual CLO."""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_pattern_api import adapter
from clo3d_mcp.pattern_contract import CommandError, PATTERN_COMMANDS


spec = importlib.util.spec_from_file_location("verify_patterns", Path(__file__).parents[1] / "scripts" / "verify_patterns.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Client:
    def __init__(self, fail=False, change_session=False):
        self.native, self.api = adapter()
        self.commands = []
        self.fail = fail
        self.change_session = change_session

    async def call_tool(self, command, params=None):
        self.commands.append(command)
        if command == "get_session_info":
            value = {"ready": True, "session_id": "s", "capabilities": PATTERN_COMMANDS}
        elif command == "transport_status":
            value = {"ready": True, "session_id": "foreign" if self.change_session else "s", "quarantined": False}
        else:
            if self.fail and command == "copy_pattern_with_offset":
                return SimpleNamespace(isError=True, structuredContent={"ok": False, "error": "outcome_unknown"})
            try:
                value = {"ok": True, **self.api(command, {} if params is None else params)}
            except CommandError as exc:
                return SimpleNamespace(isError=True, structuredContent={"ok": False, "error": exc.code})
        return SimpleNamespace(isError=False, structuredContent=value)


@pytest.mark.parametrize("mode,cycles", [("inspect", 0), ("smoke", 1), ("load", 10)])
def test_bounded_scenarios(mode, cycles):
    client = Client()
    output = []
    asyncio.run(module.scenario(client, mode, lambda line, **kw: output.append(line)))
    assert client.native.GetPatternCount() == 0
    assert client.native.mutations.count("copy") == cycles
    assert client.native.mutations.count("move") == cycles
    assert any(line.startswith("PASS") for line in output)


def test_failure_never_repeats_mutation_or_deletes_after_unknown():
    client = Client(fail=True)
    with pytest.raises(RuntimeError):
        asyncio.run(module.scenario(client, "load", lambda *a, **kw: None))
    assert client.commands.count("copy_pattern_with_offset") == 1
    assert "delete_pattern" not in client.commands
    assert client.native.GetPatternCount() == 1


def test_changed_session_stops_before_first_mutation():
    client = Client(change_session=True)
    with pytest.raises(RuntimeError):
        asyncio.run(module.scenario(client, "smoke", lambda *a, **kw: None))
    assert client.native.mutations == []
