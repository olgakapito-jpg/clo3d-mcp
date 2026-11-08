"""Read-only acceptance client contracts; no network or actual CLO here."""

import importlib.util
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_transport.py"
    spec = importlib.util.spec_from_file_location("verify_transport_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("reply", [
    SimpleNamespace(isError=True, structuredContent={"error": "outcome_unknown"}),
    SimpleNamespace(isError=False, structuredContent=None),
    SimpleNamespace(isError=False, structuredContent={"ok": False, "error": "queue_full"}),
])
def test_acceptance_client_never_accepts_error_as_success(reply):
    with pytest.raises(RuntimeError):
        load().data(reply)


def test_acceptance_client_accepts_structured_status_without_ok_field():
    assert load().data(SimpleNamespace(isError=False, structuredContent={"ready": True})) == {"ready": True}


def test_audit_guard_rejects_mutation_and_allows_reads_and_nul(monkeypatch):
    path = Path(__file__).with_name("service_audit_bootstrap.py")
    spec = importlib.util.spec_from_file_location("audit_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def forbidden(code):
        assert code == 91
        raise RuntimeError("audit rejection")

    monkeypatch.setattr(module.os, "_exit", forbidden)
    monkeypatch.setattr(module.os, "write", lambda *args: None)
    module.audit("open", ("source.py", "r", 0))
    module.audit("open", (module.os.devnull, "w", module.os.O_RDWR))
    for event, args in [("open", ("response.json", "w", module.os.O_WRONLY)),
                        ("open", ("response.json", None, module.os.O_CREAT)),
                        ("os.mkdir", ("queue",)), ("os.rename", ("a", "b"))]:
        with pytest.raises(RuntimeError, match="audit rejection"):
            module.audit(event, args)


@pytest.mark.parametrize("mode, expected", [("load", 1000), ("soak", 360)])
def test_acceptance_client_bounds_duration_and_only_uses_read_tools(monkeypatch, capsys, mode, expected):
    module = load()
    now = [0.0]
    calls = []

    @asynccontextmanager
    async def http(url):
        assert url == "http://127.0.0.1:8765/mcp"
        yield None, None, None

    class Client:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

        async def call_tool(self, command):
            calls.append(command)
            if command == "ping":
                value = {"ok": True, "pong": True}
            elif command == "get_pattern_count":
                value = {"ok": True, "pattern_count": 3}
            else:
                assert command in ("transport_status", "get_session_info")
                value = {"ready": True, "session_id": "s", "server_pid": 1, "clo_pid": 2,
                         "waiting": 0, "cached": 128}
            return SimpleNamespace(isError=False, structuredContent=value)

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(module, "streamable_http_client", http)
    monkeypatch.setattr(module, "ClientSession", Client)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(module, "asyncio", SimpleNamespace(
        wait_for=asyncio.wait_for, gather=asyncio.gather, sleep=sleep))
    asyncio.run(module.check(SimpleNamespace(mode=mode)))
    assert calls.count("ping") + calls.count("get_pattern_count") == expected
    if mode == "soak":
        assert now[0] == 1800
    assert 'PASS ' in capsys.readouterr().out
