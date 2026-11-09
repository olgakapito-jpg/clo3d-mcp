"""Bounded inventory contracts and fake executor; no real CLO compatibility claim."""

import asyncio
from copy import deepcopy
import os
import importlib.util
from pathlib import Path

import pytest

from clo3d_mcp.inventory_api import InventoryAPI
from clo3d_mcp.jobs import JobQueue
from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result
from clo3d_mcp.pipe_session import Executor, proof
from clo3d_mcp.protocol import PATTERN_CAPABILITIES, ProtocolError, message
from clo3d_mcp.transport_server import build_mcp


class Native:
    def __init__(self, fabrics=None, avatars=None, alter=None):
        self.fabrics = ["cotton", "cotton", ""] if fabrics is None else fabrics
        self.avatars = ["body", ""] if avatars is None else avatars
        self.calls, self.alter = [], alter

    def read(self, label, result, *args):
        self.calls.append((label, args))
        return self.alter(label, result, len(self.calls)) if self.alter else result

    def GetCurrentColorwayIndex(self):
        raise AssertionError("Object Browser inventory must not read colorway")

    def GetFabricCount(self, *, _bCurrentColorway):
        assert _bCurrentColorway is False
        return self.read("fabric_count", len(self.fabrics), _bCurrentColorway)

    def GetFabricName(self, index):
        assert type(index) is int
        return self.read("fabric_name", self.fabrics[index], index)

    def GetAvatarCount(self):
        return self.read("avatar_count", len(self.avatars))

    def GetAvatarNameList(self):
        return self.read("avatar_names", list(self.avatars))


def adapter(native):
    return InventoryAPI({"fabric_api": native, "export_api": native})


@pytest.mark.parametrize("command", ["get_fabric_list", "get_avatars"])
@pytest.mark.parametrize("empty", [False, True])
def test_inventory_preserves_indices_duplicates_empty_names_and_checks_consistency(command, empty):
    native = Native(fabrics=[] if empty else None, avatars=[] if empty else None)
    result = adapter(native)(command, {})
    validate_result(command, result)
    key = "fabric" if command == "get_fabric_list" else "avatar"
    names = native.fabrics if key == "fabric" else native.avatars
    assert result[key + "_count"] == len(names)
    assert result[key + "s"] == [{"index": i, "name": n} for i, n in enumerate(names)]
    if key == "fabric":
        assert "colorway_index" not in result
        assert len(native.calls) == 3 + 2 * len(names)
    else:
        assert len(native.calls) == 5


@pytest.mark.parametrize("command", ["get_fabric_list", "get_avatars"])
@pytest.mark.parametrize("params", [{"extra": 1}, [], None, "{}"])
def test_raw_parameters_rejected_without_any_read(command, params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        adapter(native)(command, params)
    queue = JobQueue("s")
    queue.on_connected()
    with pytest.raises(ProtocolError):
        queue.submit(command, params=params) if params is not None else message(
            "JOB", "s", job_id="job_1", command=command, params=None)
    assert not native.calls and queue.sequence == 0


@pytest.mark.parametrize("command", ["get_fabric_list", "get_avatars"])
def test_every_native_failure_stops_without_retry_and_hides_exception(command):
    baseline = Native()
    adapter(baseline)(command, {})
    for step in range(1, len(baseline.calls) + 1):
        def failure(label, result, index):
            if index == step:
                raise RuntimeError("C:/private token=secret")
            return result
        native = Native(alter=failure)
        with pytest.raises(CommandError, match="^command_error$"):
            adapter(native)(command, {})
        assert native.calls == baseline.calls[:step]


@pytest.mark.parametrize("command,label,maximum", [
    ("get_fabric_list", "fabric_count", 256), ("get_avatars", "avatar_count", 64),
])
@pytest.mark.parametrize("value", [True, -1, 1.0, "1", None, 1000])
def test_invalid_count_and_bounds_do_not_read_names(command, label, maximum, value):
    native = Native(alter=lambda key, result, _: value if key == label else result)
    with pytest.raises(CommandError, match="inventory_limit" if value == 1000 else "invalid_native_result"):
        adapter(native)(command, {})
    assert not any(key in ("fabric_name", "avatar_names") for key, _ in native.calls)


def test_object_browser_inventory_has_no_export_or_colorway_dependency():
    native = Native()
    result = InventoryAPI({"fabric_api": native})("get_fabric_list", {})
    assert result["fabric_count"] == 3
    assert all(label != "colorway" for label, _ in native.calls)
    assert all(args == (False,) and type(args[0]) is bool
               for label, args in native.calls if label == "fabric_count")


def test_maximum_object_browser_inventory_is_bounded_to_515_native_reads():
    native = Native(fabrics=["fabric"] * 256)
    result = InventoryAPI({"fabric_api": native})("get_fabric_list", {})
    assert result["fabric_count"] == 256
    assert result["fabrics"][-1] == {"index": 255, "name": "fabric"}
    assert len(native.calls) == 515


@pytest.mark.parametrize("command,label", [("get_fabric_list", "fabric_name"), ("get_avatars", "avatar_names")])
@pytest.mark.parametrize("value", [None, 1, "x" * 257, "bad\n", "\ud800"])
def test_invalid_names_no_coercion(command, label, value):
    native = Native(alter=lambda key, result, _: (value if label == "fabric_name" else [value, ""])
                    if key == label else result)
    with pytest.raises(CommandError, match="invalid_native_result"):
        adapter(native)(command, {})


@pytest.mark.parametrize("value", [("a", "b"), "ab", ["a"], ["a"] * 65, {}])
def test_avatar_native_container_and_count_mismatch(value):
    native = Native(alter=lambda key, result, _: value if key == "avatar_names" else result)
    with pytest.raises(CommandError, match="invalid_native_result"):
        adapter(native)("get_avatars", {})
    assert len(native.calls) == 2


@pytest.mark.parametrize("command,step,value", [
    ("get_fabric_list", 3, 3),  # changed count after first name pass (one fabric)
    ("get_fabric_list", 4, "changed"),  # second name read
    ("get_fabric_list", 5, 2),  # final count read
    ("get_avatars", 3, 2),
    ("get_avatars", 4, ["changed"]),
    ("get_avatars", 5, 2),
])
def test_changed_inventory_never_returns_partial_success(command, step, value):
    # One fabric calls: count,name,count,name,count.
    native = Native(fabrics=["a"], avatars=["a"],
                    alter=lambda key, result, i: value if i == step else result)
    with pytest.raises(CommandError, match="inventory_changed"):
        adapter(native)(command, {})
    assert len(native.calls) == step


def test_missing_api_preflight_and_no_namespace_fallback():
    native = Native()
    api = InventoryAPI({"utility_api": native})
    for command in ("get_fabric_list", "get_avatars"):
        with pytest.raises(CommandError, match="api_unavailable"):
            api(command, {})
    assert not native.calls


def test_missing_name_preflight_and_keyword_binding_failure_never_fallback():
    native = Native()
    native.GetFabricName = None
    with pytest.raises(CommandError, match="api_unavailable"):
        adapter(native)("get_fabric_list", {})
    assert not native.calls
    calls = []

    def positional_count(*args, **kwargs):
        calls.append((args, kwargs))
        raise TypeError("keyword rejected")

    native = Native()
    native.GetFabricCount = positional_count
    with pytest.raises(CommandError, match="command_error"):
        adapter(native)("get_fabric_list", {})
    assert calls == [((), {"_bCurrentColorway": False})]
    assert not native.calls


@pytest.mark.parametrize("command", ["get_fabric_list", "get_avatars"])
def test_result_contract_rejects_bool_index_count_extras_and_invalid_names(command):
    result = adapter(Native())(command, {})
    key = "fabric" if command == "get_fabric_list" else "avatar"
    for alter in (lambda r: r.update(extra=1), lambda r: r.update({key + "_count": True}),
                  lambda r: r.update(colorway_index=0),
                  lambda r: r[key + "s"][0].update(index=False),
                  lambda r: r[key + "s"][0].update(name="\ud800"),
                  lambda r: r[key + "s"].pop()):
        invalid = deepcopy(result)
        alter(invalid)
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result(command, invalid)


def test_integrated_executor_queue_result_cache_and_capability_contract():
    native = Native()
    handler = PatternAPI({"pattern_api": object(), "export_api": native, "fabric_api": native})
    key = b"k" * 32
    executor = Executor("s", key, os.getpid(), lambda: 0, lambda: {}, handler)
    executor.connected(os.getpid())
    executor.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=PATTERN_CAPABILITIES,
                             proof=proof(key, "server", "s", os.getpid())))
    queue = JobQueue("s")
    queue.on_connected()
    for command in ("get_fabric_list", "get_avatars"):
        queue.on_ready()
        job_id = queue.submit(command, params={})
        frame = queue.dispatch()
        reply = executor.receive(frame)[0]
        assert reply["kind"] == "RESULT"
        queue.receive(reply)
        assert queue.lookup("s", job_id).state == "succeeded"
        calls = len(native.calls)
        assert executor.receive(frame)[0]["code"] == "duplicate_job"
        assert len(native.calls) == calls


def test_mcp_metadata_raw_validation_and_success():
    async def scenario():
        native = Native()
        api = adapter(native)
        calls = []

        class Service:
            port, pattern_package = 8765, True

            async def call(self, command, params):
                calls.append(command)
                return {"ok": True, **api(command, params)}

        mcp = build_mcp(Service())
        tools = {t.name: t for t in await mcp.list_tools()}
        assert len(tools) == 18
        for command in ("get_fabric_list", "get_avatars"):
            tool = tools[command]
            assert tool.inputSchema["properties"] == {}
            assert not tool.inputSchema.get("required")
            assert tool.annotations.readOnlyHint and tool.annotations.idempotentHint
            assert not tool.annotations.destructiveHint and not tool.annotations.openWorldHint
            assert "no automatic retry" in tool.description
            if command == "get_fabric_list":
                assert "Object Browser" in tool.description
                assert "Returns fabric_count and fabrics" in tool.description
                assert "colorway_index" not in tool.description
            reply = await mcp.call_tool(command, {"extra": True})
            assert reply.isError and not calls
        for command in ("get_fabric_list", "get_avatars"):
            result = await mcp.call_tool(command, {})
            # FastMCP direct success returns (content, structuredContent).
            assert result[1]["ok"] is True
            validate_result(command, {k: v for k, v in result[1].items() if k != "ok"})
        assert calls == ["get_fabric_list", "get_avatars"]
    asyncio.run(scenario())


def test_fabric_diagnostic_fixed_calls_first_failure_stop_and_import_is_inert():
    spec = importlib.util.spec_from_file_location(
        "fabric_probe", Path(__file__).parents[1] / "plugin/clo3d_mcp_fabric_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    calls = []

    class Counts:
        fail_at = None

        def GetFabricCount(self, *args):
            calls.append(args)
            if len(calls) == self.fail_at:
                raise RuntimeError("C:/private token=secret")
            return 2

        def GetCurrentColorwayIndex(self):
            return 0

    native = Counts()
    assert probe.collect_counts(native, native)["status"] == "completed"
    expected = [(), (True,), (False,), (-2,), (-1,), (0,)]
    assert calls == expected
    # Compare types too: bool==int in Python must not mask the overload inputs.
    assert [type(args[0]) if args else None for args in calls] == [None, bool, bool, int, int, int]
    for step in range(1, 7):
        calls.clear()
        native.fail_at = step
        report = probe.collect_counts(native, native)
        assert report["status"] == "command_error" and calls == expected[:step]
        assert "private" not in str(report) and "secret" not in str(report)
