"""Bounded outline contracts/faults; synthetic native, not real-CLO evidence."""

import asyncio
from copy import deepcopy
import os

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params, validate_result
from clo3d_mcp.protocol import PATTERN_CAPABILITIES, ProtocolError, message
from clo3d_mcp.jobs import JobQueue
from clo3d_mcp.pipe_session import Executor, proof
from clo3d_mcp.transport_server import build_mcp


COMMAND = "get_pattern_outline"
PARAMS = {"pattern_index": 0, "expected_name": "panel"}
POINTS = [[0.0, 0.0], [120.0, 0.0], [120.0, 80.0], [0.0, 80.0]]


class Native:
    def __init__(self, fault=None):
        self.names = ["panel", "other"]
        self.calls = []
        self.reads = 0
        self.fault = fault
        self.points = deepcopy(POINTS)

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def GetPatternOutlinePoints(self, i):
        self.calls.append("outline")
        self.reads += 1
        assert i == 0
        if self.fault:
            return self.fault(self)
        return self.points


def api(native):
    return PatternAPI({"pattern_api": native})


def result(points=None):
    points = deepcopy(POINTS if points is None else points)
    return {"pattern_index": 0, "pattern_name": "panel", "point_count": len(points),
            "points_mm": points, "units": "mm", "coordinate_frame": "bbox_top_left_y_down"}


def test_get_pattern_outline_exact_order_frame_and_native_call_bound():
    native = Native()
    observed = api(native)(COMMAND, PARAMS)
    assert observed == result()
    assert native.calls == ["count", "name", "name", "count", "outline",
                            "count", "name", "name", "count", "outline",
                            "count", "name", "name", "count"]
    assert observed["points_mm"] is not native.points
    native.points[0][0] = 9
    assert observed["points_mm"][0][0] == 0


@pytest.mark.parametrize("params", [None, {}, {"pattern_index": 0},
    {**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
    {**PARAMS, "pattern_index": 0.0}, {**PARAMS, "pattern_index": "0"},
    {**PARAMS, "pattern_index": -1}, {**PARAMS, "pattern_index": 256},
    {**PARAMS, "expected_name": ""}, {**PARAMS, "expected_name": "x" * 129},
    {**PARAMS, "expected_name": "bad\n"}, {**PARAMS, "expected_name": "\ud800"}])
def test_invalid_raw_outline_params_no_native_or_queue(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)(COMMAND, params)
    queue = JobQueue("s")
    queue.on_connected()
    with pytest.raises(ProtocolError):
        queue.submit(COMMAND, params=params)
    assert not native.calls and not queue.waiting


@pytest.mark.parametrize("names", [[], ["other"], ["panel", "panel"]])
def test_outline_stale_or_ambiguous_never_enters_getter(names):
    native = Native()
    native.names = names
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 0


@pytest.mark.parametrize("bad", [None, {}, (), [], [[0, 0]] * 513,
    [[True, 0]], [[float("nan"), 0]], [[float("inf"), 0]], [[100001, 0]],
    [[-100001, 0]], [["1", 0]], [[0, 0, 0]], [(0, 0)], [0], [[0]], "[]"])
@pytest.mark.parametrize("bad_read", [1, 2])
def test_invalid_native_outline_not_coerced_truncated_or_retried(bad, bad_read):
    native = Native(lambda n: bad if n.reads == bad_read else n.points)
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == bad_read


@pytest.mark.parametrize("points", [[[0, 0]], [[0, 0], [0, 0]],
    [[0, 0], [1, 0], [1, 1], [0, 0]], [[-100000, 100000]] * 512])
def test_preserves_native_closure_duplicates_and_limits_without_polygon_claim(points):
    native = Native()
    native.points = deepcopy(points)
    assert api(native)(COMMAND, PARAMS)["points_mm"] == points


@pytest.mark.parametrize("when", [1, 2])
def test_outline_list_change_stops_without_retry(when):
    def change(n):
        if n.reads == when:
            n.names[1] = "changed"
        return n.points
    native = Native(change)
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == when


def test_outline_reused_list_changes_are_detected_not_alias_compared():
    def change(n):
        if n.reads == 2:
            n.points[0][0] = 9
        return n.points
    native = Native(change)
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 2


@pytest.mark.parametrize("when", [1, 2])
def test_outline_native_exception_sanitized_and_not_retried(when):
    def fail(n):
        if n.reads == when:
            raise RuntimeError("private path or native exception")
        return n.points
    native = Native(fail)
    with pytest.raises(CommandError, match="^command_error$"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == when


@pytest.mark.parametrize("method", ["GetPatternCount", "GetPatternPieceName", "GetPatternOutlinePoints"])
def test_outline_missing_binding_fails_before_reads(method):
    native = Native()
    setattr(native, method, None)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)(COMMAND, PARAMS)
    assert native.calls == []


@pytest.mark.parametrize("count_call", range(1, 7))
def test_outline_invalid_count_at_each_snapshot_is_native_error(count_call):
    native = Native()
    original = native.GetPatternCount
    counts = []
    def read():
        counts.append(1)
        value = original()
        return True if len(counts) == count_call else value
    native.GetPatternCount = read
    with pytest.raises(CommandError, match="^invalid_native_result$"):
        api(native)(COMMAND, PARAMS)
    assert len(counts) == count_call


@pytest.mark.parametrize("count_call", [2, 4, 6])
def test_outline_count_changes_after_list_stop_before_next_getter(count_call):
    native = Native()
    original = native.GetPatternCount
    counts = []
    def read():
        counts.append(1)
        value = original()
        return value + 1 if len(counts) == count_call else value
    native.GetPatternCount = read
    with pytest.raises(CommandError, match="^inventory_changed$"):
        api(native)(COMMAND, PARAMS)
    assert len(counts) == count_call and native.reads == count_call // 2 - 1


def test_outline_invalid_name_snapshot_sanitized_no_outline():
    native = Native()
    native.names = [True]
    with pytest.raises(CommandError, match="^invalid_native_result$"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 0


def test_outline_maximum_scene_native_call_bound():
    native = Native()
    native.names = ["panel"] + ["other_" + str(i) for i in range(255)]
    assert api(native)(COMMAND, PARAMS) == result()
    assert native.calls.count("name") == 768
    assert native.calls.count("count") == 6
    assert native.calls.count("outline") == 2


@pytest.mark.parametrize("patch", [{"point_count": True}, {"point_count": 3},
    {"coordinate_frame": "global_2d"}, {"units": "cm"}, {"pattern_index": True},
    {"pattern_name": ""}, {"extra": 1}, {"points_mm": []}])
def test_outline_result_schema_rejects_drift(patch):
    with pytest.raises(CommandError, match="invalid_result"):
        validate_result(COMMAND, {**result(), **patch})


def test_outline_queue_executor_cache_and_invalid_result_failure():
    native = Native()
    executor = Executor("s", b"k" * 32, os.getpid(), lambda: 0, lambda: {}, api(native))
    executor.connected(os.getpid())
    executor.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=PATTERN_CAPABILITIES,
                             proof=proof(b"k" * 32, "server", "s", os.getpid())))
    queue = JobQueue("s")
    queue.on_connected()
    queue.on_ready()
    job = queue.submit(COMMAND, params=PARAMS)
    frame = queue.dispatch()
    reply = executor.receive(frame)[0]
    queue.receive(reply)
    assert queue.lookup("s", job).state == "succeeded"
    before = list(native.calls)
    assert executor.receive(frame)[0]["code"] == "duplicate_job"
    assert native.calls == before

    queue.on_ready()
    job = queue.submit(COMMAND, params=PARAMS)
    frame = queue.dispatch()
    with pytest.raises(ProtocolError):
        queue.receive(message("RESULT", "s", job_id=frame["job_id"],
                              result={**result(), "point_count": 0}))
    assert queue.lookup("s", job).state != "succeeded"


def test_outline_sdk_metadata_and_raw_validation_without_dispatch():
    async def scenario():
        class Service:
            port, pattern_package = 8765, True
            calls = []

            async def call(self, command, params):
                self.calls.append((command, params))
                return {"ok": True, **api(Native())(command, params)}

        service = Service()
        mcp = build_mcp(service)
        tools = {t.name: t for t in await mcp.list_tools()}
        assert len(tools) == 21
        t = tools[COMMAND]
        assert set(t.inputSchema["required"]) == set(PARAMS)
        assert t.inputSchema["properties"]["pattern_index"]["type"] == "integer"
        assert t.annotations.readOnlyHint and t.annotations.idempotentHint
        assert not t.annotations.destructiveHint and not t.annotations.openWorldHint
        for text in ("endpoints", "not curve controls", "TOP-LEFT", "Y down", "NOT global2D",
                     "1-512", "+/-100000mm", "no closure/lineIndex", "no automatic retry"):
            assert text in t.description
        for p in ({**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
                  {**PARAMS, "pattern_index": "0"}):
            assert (await mcp.call_tool(COMMAND, p)).isError
        assert not service.calls
        observed = await mcp.call_tool(COMMAND, PARAMS)
        assert observed[1] == {"ok": True, **result()}
        assert service.calls == [(COMMAND, PARAMS)]
    asyncio.run(scenario())
