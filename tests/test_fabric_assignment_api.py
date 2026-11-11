"""Strict fabric relationship contracts; fake native faults, no real CLO claim."""

import asyncio
from copy import deepcopy
import os

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params, validate_result
from clo3d_mcp.protocol import PATTERN_CAPABILITIES, message
from clo3d_mcp.jobs import JobQueue
from clo3d_mcp.pipe_session import Executor, proof
from clo3d_mcp.transport_server import build_mcp
from test_pattern_api import FakePatterns, POINTS


READ = {"pattern_index": 0, "expected_name": "front"}
ASSIGN = {**READ, "fabric_index": 1, "expected_fabric_name": "jersey",
          "expected_current_fabric_index": 0}


class RelationshipPatterns(FakePatterns):
    """Synthetic composition model, not evidence of CLO copy semantics."""
    def GetFabricCount(self, *, _bCurrentColorway):
        assert _bCurrentColorway is False
        return 2

    def GetFabricName(self, i):
        return ["cotton", "jersey"][i]

    def CreatePatternWithPoints(self, points):
        super().CreatePatternWithPoints(points)
        self.pieces[-1]["fabric"] = 0

    def GetFabricIndexForPattern(self, i):
        return self.pieces[i]["fabric"]

    def AssignFabricToPattern(self, f, i, option):
        assert option == 1
        self.mutations.append("fabric")
        self.pieces[i]["fabric"] = f
        return True


def composition_steps(call):
    """Sequential test recipe with independent reads, never finally cleanup."""
    call("create_pattern", {"points": POINTS, "name": "source"})
    read = call("get_pattern_fabric", {"pattern_index": 0, "expected_name": "source"})
    assert read["fabric_index"] == 0
    call("assign_pattern_fabric", {"pattern_index": 0, "expected_name": "source",
         "fabric_index": 1, "expected_fabric_name": "jersey", "expected_current_fabric_index": 0})
    assert call("get_pattern_fabric", {"pattern_index": 0, "expected_name": "source"})["fabric_index"] == 1
    copied = call("copy_pattern_with_offset", {"pattern_index": 0, "expected_name": "source",
                  "name": "copy", "dx": 200, "dy": 0})
    i = copied["pattern"]["index"]
    assert call("get_pattern_fabric", {"pattern_index": i, "expected_name": "copy"})["fabric_index"] == 1
    call("set_pattern_name", {"pattern_index": i, "expected_name": "copy", "name": "renamed"})
    assert call("get_pattern_fabric", {"pattern_index": i, "expected_name": "renamed"})["fabric_index"] == 1
    call("move_pattern_relative", {"pattern_index": i, "expected_name": "renamed", "dx": 25, "dy": -30})
    assert call("get_pattern_geometry", {"pattern_index": i})["pattern"]["position_mm"] == [225, -30]
    call("assign_pattern_fabric", {"pattern_index": i, "expected_name": "renamed",
         "fabric_index": 0, "expected_fabric_name": "cotton", "expected_current_fabric_index": 1})
    assert call("get_pattern_fabric", {"pattern_index": 0, "expected_name": "source"})["fabric_index"] == 1
    assert call("get_pattern_fabric", {"pattern_index": i, "expected_name": "renamed"})["fabric_index"] == 0
    call("delete_pattern", {"pattern_index": 0, "expected_name": "source"})
    listing = call("get_pattern_list", {})
    assert listing["patterns"] == [{"index": 0, "name": "renamed"}]
    shifted = listing["patterns"][0]
    assert call("get_pattern_fabric", {"pattern_index": shifted["index"],
                                      "expected_name": shifted["name"]})["fabric_index"] == 0
    call("assign_pattern_fabric", {"pattern_index": shifted["index"], "expected_name": shifted["name"],
         "fabric_index": 1, "expected_fabric_name": "jersey", "expected_current_fabric_index": 0})
    assert call("get_pattern_fabric", {"pattern_index": shifted["index"],
                                      "expected_name": shifted["name"]})["fabric_index"] == 1
    call("delete_pattern", {"pattern_index": shifted["index"], "expected_name": shifted["name"]})
    assert call("get_pattern_list", {})["pattern_count"] == 0


def test_pattern_fabric_composition_shifted_indices_and_independent_assignments():
    native = RelationshipPatterns()
    composition_steps(api(native))
    assert native.pieces == []
    assert native.mutations == ["create", "name", "fabric", "copy", "name",
                                "name", "move", "fabric", "delete", "fabric", "delete"]


@pytest.mark.parametrize("after_effect", [False, True])
def test_composition_error_at_every_step_never_follows_with_retry_or_cleanup(after_effect):
    baseline = []
    adapter = api(RelationshipPatterns())
    def record(command, params):
        baseline.append((command, deepcopy(params)))
        return adapter(command, params)
    composition_steps(record)
    for fail_at in range(len(baseline)):
        native = RelationshipPatterns()
        adapter = api(native)
        calls = []
        def fail(command, params):
            calls.append((command, deepcopy(params)))
            if len(calls) - 1 == fail_at:
                if after_effect:
                    adapter(command, params)
                raise CommandError("scene_change_unverified")
            return adapter(command, params)
        with pytest.raises(CommandError, match="scene_change_unverified"):
            composition_steps(fail)
        assert calls == baseline[:fail_at + 1]
        expected = RelationshipPatterns()
        expected_api = api(expected)
        for command, params in baseline[:fail_at + int(after_effect)]:
            expected_api(command, params)
        assert native.pieces == expected.pieces and native.mutations == expected.mutations


def test_fabric_stale_index_after_lower_delete_rejected_without_assignment():
    native = RelationshipPatterns()
    adapter = api(native)
    for name in ("source", "copy"):
        adapter("create_pattern", {"points": POINTS, "name": name})
    adapter("delete_pattern", {"pattern_index": 0, "expected_name": "source"})
    before = deepcopy(native.pieces), list(native.mutations)
    for command, params in (
        ("get_pattern_fabric", {"pattern_index": 1, "expected_name": "copy"}),
        ("assign_pattern_fabric", {"pattern_index": 1, "expected_name": "copy",
         "fabric_index": 1, "expected_fabric_name": "jersey", "expected_current_fabric_index": 0}),
    ):
        with pytest.raises(CommandError, match="stale_pattern"):
            adapter(command, params)
    assert (native.pieces, native.mutations) == before


class Native:
    def __init__(self, alter=None):
        self.names = ["front", "back"]
        self.fabrics = ["cotton", "jersey"]
        self.mapping = [0, 0]
        self.calls = []
        self.alter = alter
        self.setters = 0
        self.box = {"Height": "80.000000", "Width": "120.000000"}

    def emit(self, label, result, *args):
        self.calls.append((label, args))
        return self.alter(self, label, result, len(self.calls)) if self.alter else result

    def GetPatternCount(self):
        return self.emit("patterns", len(self.names))

    def GetPatternPieceName(self, i):
        return self.emit("pattern_name", self.names[i], i)

    def GetFabricCount(self, *, _bCurrentColorway):
        assert _bCurrentColorway is False
        return self.emit("fabrics", len(self.fabrics))

    def GetFabricName(self, i):
        return self.emit("fabric_name", self.fabrics[i], i)

    def GetFabricIndexForPattern(self, i):
        return self.emit("mapping", self.mapping[i], i)

    def GetPatternPiecePos(self, i):
        return self.emit("position", (0.0, 0.0), i)

    def GetPatternPieceArea(self, i):
        return self.emit("area", 9600.0, i)

    def GetBoundingBoxOfPattern(self, i):
        return self.emit("box", dict(self.box), i)

    def AssignFabricToPattern(self, f, i, option):
        assert type(f) is int and type(i) is int and option == 1
        self.setters += 1
        self.mapping[i] = f
        return self.emit("assign", True, f, i, option)


def api(native):
    return PatternAPI({"pattern_api": native, "fabric_api": native})


def test_read_then_assign_preserves_other_mappings_and_geometry():
    native = Native()
    adapter = api(native)
    before = adapter("get_pattern_fabric", READ)
    assert before == {"pattern_index": 0, "pattern_name": "front",
                      "fabric_index": 0, "fabric_name": "cotton"}
    result = adapter("assign_pattern_fabric", ASSIGN)
    assert result["verified"] and result["previous_fabric_index"] == 0
    assert result["fabric_index"] == 1 and result["executor_ms"] >= 0
    assert native.mapping == [1, 0] and native.setters == 1
    assert adapter("get_pattern_fabric", READ)["fabric_name"] == "jersey"
    assert [c for c in native.calls if c[0] == "assign"] == [("assign", (1, 0, 1))]


@pytest.mark.parametrize("command,params", [("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)])
def test_every_native_failure_stops_at_exact_step_without_retry(command, params):
    baseline = Native()
    api(baseline)(command, params)
    setter_step = next((i for i, v in enumerate(baseline.calls, 1) if v[0] == "assign"), None)
    for step in range(1, len(baseline.calls) + 1):
        def failure(native, label, result, current):
            if current == step:
                raise RuntimeError("C:/private token=secret")
            return result
        native = Native(failure)
        code = "scene_change_unverified" if setter_step and step >= setter_step else "command_error"
        with pytest.raises(CommandError, match="^" + code + "$"):
            api(native)(command, params)
        assert native.calls == baseline.calls[:step]
        assert native.setters == int(bool(setter_step and step >= setter_step))


@pytest.mark.parametrize("command,params", [("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)])
def test_strict_params_no_native_reads_or_enqueue(command, params):
    variants = [{**params, "colorway_index": 0}, {**params, "pattern_index": True},
                {**params, "pattern_index": "0"}, {**params, "pattern_index": 256},
                {**params, "expected_name": ""}, {**params, "expected_name": "bad\n"},
                {k: v for k, v in params.items() if k != "expected_name"}]
    if command == "assign_pattern_fabric":
        variants += [{**params, "fabric_index": True}, {**params, "fabric_index": -1},
                     {**params, "expected_current_fabric_index": False},
                     {**params, "expected_fabric_name": "x" * 257},
                     {**params, "expected_fabric_name": "\ud800"}]
    native = Native()
    queue = JobQueue("s")
    queue.on_connected()
    for value in variants:
        with pytest.raises(CommandError, match="invalid_parameters"):
            api(native)(command, value)
        with pytest.raises(ValueError):
            queue.submit(command, params=value)
    assert not native.calls and not native.setters and queue.sequence == 0


@pytest.mark.parametrize("update,code", [
    ({"expected_name": "stale"}, "stale_pattern"),
    ({"pattern_index": 3}, "stale_pattern"),
    ({"fabric_index": 4}, "stale_fabric"),
    ({"expected_fabric_name": "stale"}, "stale_fabric"),
    ({"expected_current_fabric_index": 1}, "stale_fabric"),
])
def test_stale_guards_before_setter(update, code):
    native = Native()
    with pytest.raises(CommandError, match=code):
        api(native)("assign_pattern_fabric", {**ASSIGN, **update})
    assert native.setters == 0


def test_duplicate_names_fail_closed_but_single_empty_fabric_name_allowed():
    native = Native()
    native.names = ["front", "front"]
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)("get_pattern_fabric", READ)
    native = Native()
    native.fabrics = ["jersey", "jersey"]
    with pytest.raises(CommandError, match="stale_fabric"):
        api(native)("assign_pattern_fabric", ASSIGN)
    assert native.setters == 0
    native = Native()
    native.fabrics[1] = ""
    assert api(native)("assign_pattern_fabric", {**ASSIGN, "expected_fabric_name": ""})["fabric_name"] == ""


@pytest.mark.parametrize("value", [True, -1, 2, None, "0", 0.0])
def test_invalid_native_mapping_no_undocumented_sentinel(value):
    native = Native(lambda n, k, r, s: value if k == "mapping" else r)
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(native)("get_pattern_fabric", READ)
    assert native.setters == 0


@pytest.mark.parametrize("method", ["GetFabricIndexForPattern", "AssignFabricToPattern",
                                     "GetBoundingBoxOfPattern", "GetFabricName"])
def test_missing_api_preflight_before_native_reads(method):
    native = Native()
    setattr(native, method, None)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)("assign_pattern_fabric", ASSIGN)
    assert not native.calls and native.setters == 0


def test_changed_read_and_preflight_mapping_stop_before_setter():
    seen = [0]

    def change(native, key, result, step):
        if key == "mapping":
            seen[0] += 1
            return 1 if seen[0] == 2 else result
        return result

    native = Native(change)
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)("get_pattern_fabric", READ)
    assert native.setters == 0


def test_maximum_fixture_has_documented_native_call_bounds():
    native = Native()
    native.names = ["panel-%d" % i for i in range(256)]
    native.fabrics = ["fabric-%d" % i for i in range(256)]
    native.mapping = [0] * 256
    read = {"pattern_index": 0, "expected_name": "panel-0"}
    api(native)("get_pattern_fabric", read)
    assert len(native.calls) == 1546
    native.calls.clear()
    api(native)("assign_pattern_fabric", {**read, "fabric_index": 1,
         "expected_fabric_name": "fabric-1", "expected_current_fabric_index": 0})
    assert len(native.calls) == 4123 and native.setters == 1
    assert native.mapping == [1] + [0] * 255


@pytest.mark.parametrize("command,params", [("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)])
def test_changed_preentry_lists_never_set(command, params):
    seen = [0]
    def change(native, key, result, step):
        if key == "mapping":
            seen[0] += 1
            if seen[0] == 2:
                native.names[1] = "changed"
        return result
    native = Native(change)
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)(command, params)
    assert native.setters == 0
def test_changed_preentry_mapping_never_set():
    seen = [0]
    def before_set(native, key, result, step):
        if key == "mapping":
            seen[0] += 1
            return 1 if seen[0] == 3 else result
        return result

    native = Native(before_set)
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)("assign_pattern_fabric", ASSIGN)
    assert native.setters == 0


@pytest.mark.parametrize("fault", ["false", "wrong_target", "other_mapping", "fabric_names", "pattern_names",
                                    "position", "area", "box", "bad_index", "nonbool"])
def test_post_entry_mismatch_never_cleanup_or_return_success(fault):
    def alter(native, key, result, step):
        if key == "assign":
            if fault == "false":
                return False
            if fault == "nonbool":
                return 1
            if fault == "wrong_target":
                native.mapping[0] = 0
            if fault == "other_mapping":
                native.mapping[1] = 1
            if fault == "bad_index":
                native.mapping[0] = -1
            if fault == "fabric_names":
                native.fabrics[1] = "changed"
            if fault == "pattern_names":
                native.names[1] = "changed"
        if native.setters:
            if key == "position" and fault == "position":
                return (1.0, 0.0)
            if key == "area" and fault == "area":
                return 200.0
            if key == "box" and fault == "box":
                return {"Height": "90", "Width": "120"}
        return result

    native = Native(alter)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(native)("assign_pattern_fabric", ASSIGN)
    assert native.setters == 1


def test_raw_result_schema_rejects_legacy_extra_bool_fields():
    for command, p in (("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)):
        result = api(Native())(command, p)
        for field, value in (("fabric_index", True), ("pattern_index", False),
                             ("fabric_name", 1), ("colorway_index", 0)):
            bad = {**deepcopy(result), field: value}
            with pytest.raises(CommandError, match="invalid_result"):
                validate_result(command, bad)


def test_protocol_executor_cache_and_official_sdk_metadata():
    async def scenario():
        native = Native()
        adapter = api(native)
        executor = Executor("s", b"k" * 32, os.getpid(), lambda: 0, lambda: {}, adapter)
        executor.connected(os.getpid())
        executor.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=PATTERN_CAPABILITIES,
                                 proof=proof(b"k" * 32, "server", "s", os.getpid())))
        queue = JobQueue("s")
        queue.on_connected()
        for command, p in (("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)):
            queue.on_ready()
            job_id = queue.submit(command, params=p)
            frame = queue.dispatch()
            reply = executor.receive(frame)[0]
            assert reply["kind"] == "RESULT"
            queue.receive(reply)
            assert queue.lookup("s", job_id).state == "succeeded"
            count = len(native.calls)
            assert executor.receive(frame)[0]["code"] == "duplicate_job"
            assert len(native.calls) == count

        class Service:
            port, pattern_package = 8765, True

            async def call(self, command, params):
                validate_params(command, params)
                return {"ok": True, **api(Native())(command, params)}

        mcp = build_mcp(Service())
        tools = {t.name: t for t in await mcp.list_tools()}
        assert len(tools) == 50
        for command, p in (("get_pattern_fabric", READ), ("assign_pattern_fabric", ASSIGN)):
            tool = tools[command]
            assert set(tool.inputSchema["required"]) == set(p)
            assert "no automatic retry" in tool.description
            assert tool.annotations.readOnlyHint == (command == "get_pattern_fabric")
            assert tool.annotations.idempotentHint == (command == "get_pattern_fabric")
            assert tool.annotations.destructiveHint == (command == "assign_pattern_fabric")
            bad = await mcp.call_tool(command, {**p, "extra": 1})
            assert bad.isError
            result = await mcp.call_tool(command, p)
            assert result[1]["ok"] is True
    asyncio.run(scenario())
