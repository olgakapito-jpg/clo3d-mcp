"""Stateful fake geometry; native CLO compatibility is a separate gate."""

from copy import deepcopy
import os
from types import SimpleNamespace

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, PATTERN_COMMANDS, validate_params
from clo3d_mcp.jobs import JobQueue
from clo3d_mcp.pipe_session import Executor, proof
from clo3d_mcp.protocol import PATTERN_CAPABILITIES, ProtocolError, message


POINTS = [[0, 0], [120, 0], [100, 80], [0, 60]]


class FakePatterns:
    def __init__(self):
        self.pieces = []
        self.mutations = []
        self.fail_after_create = False
        self.ignore_move = False

    def GetPatternCount(self):
        return len(self.pieces)

    def GetPatternPieceName(self, i):
        return self.pieces[i]["name"]

    def GetPatternPiecePos(self, i):
        return tuple(self.pieces[i]["position"])

    def GetPatternPieceArea(self, i):
        return self.pieces[i]["area"]

    def GetBoundingBoxOfPattern(self, i):
        return self.pieces[i]["box"]

    def CreatePatternWithPoints(self, points):
        assert all(type(x) is float and type(y) is float and t == 0 for x, y, t in points)
        area = abs(sum(a[0] * b[1] - b[0] * a[1]
                       for a, b in zip(points, points[1:] + points[:1]))) / 2
        self.pieces.append({"name": "Pattern", "position": [0.0, 0.0], "area": area,
                            "box": [0.0, 0.0, 120.0, 80.0]})
        self.mutations.append("create")
        if self.fail_after_create:
            raise RuntimeError("private path")

    def SetPatternPieceName(self, i, name):
        self.mutations.append("name")
        self.pieces[i]["name"] = name

    def CopyPatternPieceMove(self, i, dx, dy):
        self.mutations.append("copy")
        self.pieces.append(deepcopy(self.pieces[i]))
        new = len(self.pieces) - 1
        self.pieces[new]["position"] = [a + b for a, b in zip(self.pieces[i]["position"], (dx, dy))]
        return new

    def SetPatternPieceMove(self, i, dx, dy):
        self.mutations.append("move")
        if not self.ignore_move:
            self.pieces[i]["position"] = [a + b for a, b in zip(self.pieces[i]["position"], (dx, dy))]

    def DeletePatternPiece(self, i):
        self.mutations.append("delete")
        del self.pieces[i]


def adapter():
    native = FakePatterns()
    return native, PatternAPI({"pattern_api": native})


def test_full_mutation_readback_and_shifted_index_guard():
    native, api = adapter()
    created = api("create_pattern", {"points": POINTS, "name": "test-a"})
    assert created["verified"] and created["pattern_count"] == 1
    assert created["pattern"]["area_mm2"] == 7800
    assert created["executor_ms"] >= 0
    renamed = api("set_pattern_name", {"pattern_index": 0, "expected_name": "test-a", "name": "front"})
    assert renamed["pattern"]["name"] == "front"
    copied = api("copy_pattern_with_offset", {"pattern_index": 0, "expected_name": "front",
                                             "name": "back", "dx": 250, "dy": -30})
    assert copied["pattern"]["position_mm"] == [250.0, -30.0]
    moved = api("move_pattern_relative", {"pattern_index": 1, "expected_name": "back", "dx": -10, "dy": 20})
    assert moved["pattern"]["position_mm"] == [240.0, -10.0]
    api("delete_pattern", {"pattern_index": 0, "expected_name": "front"})
    assert api("get_pattern_geometry", {"pattern_index": 0})["pattern"]["name"] == "back"
    calls = list(native.mutations)
    with pytest.raises(CommandError, match="stale_pattern"):
        api("delete_pattern", {"pattern_index": 0, "expected_name": "front"})
    assert native.mutations == calls


@pytest.mark.parametrize("command,params", [
    ("get_pattern_geometry", {"pattern_index": True}),
    ("get_pattern_geometry", {"pattern_index": "0"}),
    ("get_pattern_geometry", {"pattern_index": -1}),
    ("get_pattern_geometry", {"pattern_index": 256}),
    ("get_pattern_list", {"extra": 1}),
    ("get_pattern_list", []),
    ("create_pattern", {"points": "[]", "name": "a"}),
    ("create_pattern", {"points": POINTS, "name": "\ud800"}),
    ("create_pattern", {"points": POINTS, "name": "a\n"}),
    ("move_pattern_relative", {"pattern_index": 0, "expected_name": "a", "dx": float("nan"), "dy": 0}),
    ("move_pattern_relative", {"pattern_index": 0, "expected_name": "a", "dx": True, "dy": 0}),
    ("move_pattern_relative", {"pattern_index": 0, "expected_name": "a", "dx": 100001, "dy": 0}),
    ("describe_clo_api", {"module": "os", "functions": ["system"]}),
    ("describe_clo_api", {"module": "pattern_api", "functions": ["__dict__"]}),
    ("describe_clo_api", {"module": "pattern_api", "functions": ["GetPatternCount"] * 17}),
])
def test_bad_parameters_rejected_before_api_and_queue(command, params):
    native, api = adapter()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(command, params)
    queue = JobQueue("s")
    queue.on_connected()
    with pytest.raises(ProtocolError):
        queue.submit(command, params=params)
    assert not native.mutations and queue.sequence == 0 and not queue.waiting


@pytest.mark.parametrize("points", [
    [[0, 0], [1, 1]], [[0, 0], [1, 0], [1, 0]],
    [[0, 0], [1, 1], [2, 2]], [[0, 0], [2, 2], [0, 2], [2, 0]],
    [[0, 0], [2, 0], [1, 0], [0, 2]], [[0, 0], [1, float("inf")], [0, 1]],
    [[0, 0, 3], [1, 0], [0, 1]], [[0, 0], [1, True], [0, 1]],
    [[i, i % 2] for i in range(65)],
])
def test_invalid_polygons(points):
    with pytest.raises(CommandError):
        validate_params("create_pattern", {"points": points, "name": "a"})


def test_unknown_native_methods_refused_before_mutation():
    native, api = adapter()
    native.GetPatternPieceArea = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api("create_pattern", {"points": POINTS, "name": "a"})
    assert native.mutations == []


def test_native_side_effect_then_exception_explicit_and_no_rollback_or_retry():
    native, api = adapter()
    native.fail_after_create = True
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api("create_pattern", {"points": POINTS, "name": "a"})
    assert native.mutations == ["create"] and len(native.pieces) == 1


def test_silent_setter_failure_is_not_success():
    native, api = adapter()
    api("create_pattern", {"points": POINTS, "name": "a"})
    native.ignore_move = True
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api("move_pattern_relative", {"pattern_index": 0, "expected_name": "a", "dx": 5, "dy": 0})
    assert native.mutations.count("move") == 1


def test_duplicate_names_and_stale_index_refused_before_setter():
    native, api = adapter()
    api("create_pattern", {"points": POINTS, "name": "a"})
    with pytest.raises(CommandError, match="stale_pattern"):
        api("create_pattern", {"points": POINTS, "name": "a"})
    native.pieces.append(deepcopy(native.pieces[0]))
    calls = list(native.mutations)
    with pytest.raises(CommandError, match="stale_pattern"):
        api("delete_pattern", {"pattern_index": 0, "expected_name": "a"})
    assert calls == native.mutations


def test_introspection_does_not_call_functions_and_reports_absence():
    _, api = adapter()
    api.modules["utility_api"] = SimpleNamespace(Explode=lambda: pytest.fail("must not execute"))
    listed = api("list_clo_api", {})["modules"]
    assert listed["utility_api"] == ["Explode"] and listed["export_api"] == []
    docs = api("describe_clo_api", {"module": "utility_api", "functions": ["Explode", "Absent"]})
    assert docs["functions"]["Explode"]["available"]
    assert docs["functions"]["Absent"] == {"available": False, "doc": ""}


def test_queue_copies_params_and_rejects_wrong_result_shape():
    queue = JobQueue("s")
    queue.on_connected()
    queue.on_ready()
    params = {"points": deepcopy(POINTS), "name": "a"}
    job = queue.submit("create_pattern", params=params)
    params["points"][0][0] = 99
    params["name"] = "changed"
    dispatched = queue.dispatch()
    assert dispatched["params"]["name"] == "a" and dispatched["params"]["points"][0][0] == 0
    with pytest.raises(ProtocolError, match="pattern result"):
        queue.receive(message("RESULT", "s", job_id=job, result={"verified": True}))
    assert queue.active_id == job and queue.dispatch() is None


def test_parameterized_mutation_dedup_after_error_and_reconnect():
    native, api = adapter()
    native.fail_after_create = True
    executor = Executor("s", b"k" * 32, os.getpid(), native.GetPatternCount,
                        lambda: {}, command_handler=api)
    def connect():
        executor.connected(os.getpid())
        executor.receive(message("HELLO_ACK", "s", pid=os.getpid(), capabilities=PATTERN_CAPABILITIES,
                                 proof=proof(executor.key, "server", "s", os.getpid())))
    connect()
    frame = message("JOB", "s", job_id="job_1", command="create_pattern", params={"points": POINTS, "name": "a"})
    assert executor.receive(frame)[0]["code"] == "scene_change_unverified"
    executor.disconnected()
    connect()
    assert executor.receive(frame)[0]["code"] == "duplicate_job"
    assert native.mutations == ["create"]


def test_value_record_geometry_conversion_and_unknown_shape():
    native, api = adapter()
    api("create_pattern", {"points": POINTS, "name": "a"})
    native.GetPatternPiecePos = lambda i: SimpleNamespace(x=5.0, y=6.0)
    native.GetBoundingBoxOfPattern = lambda i: SimpleNamespace(minX=0.0, minY=0.0, maxX=120.0, maxY=80.0)
    value = api("get_pattern_geometry", {"pattern_index": 0})["pattern"]
    assert value["position_mm"] == [5.0, 6.0]
    assert value["bounding_box"]["maxX"] == 120.0
    native.GetBoundingBoxOfPattern = lambda i: object()
    with pytest.raises(CommandError, match="api_unavailable"):
        api("get_pattern_geometry", {"pattern_index": 0})


def test_native_box_string_dictionary_preserved_without_guessing_numeric_layout():
    native, api = adapter()
    # Regression for real CLO docstring: GetBoundingBoxOfPattern(int) -> Dict[str, str].
    # These are synthetic values, not a claim about the actual key names/format.
    box = {"native_field": "(0.0, 0.0)", "another_field": "120.0"}
    native.GetBoundingBoxOfPattern = lambda i: dict(box)
    created = api("create_pattern", {"points": POINTS, "name": "a"})
    assert created["pattern"]["bounding_box"] == box
    read = api("get_pattern_geometry", {"pattern_index": 0})
    assert read["pattern"]["bounding_box"] == box
    assert read["pattern"]["area_mm2"] == 7800


@pytest.mark.parametrize("box", [
    {"field": "x" * 257}, {"field": "\ud800"}, {"field": "bad\nvalue"},
    {1: "0.0"}, {"field": object()}, {"field": float("nan")},
])
def test_native_box_rejects_unbounded_or_invalid_fields(box):
    with pytest.raises(CommandError, match="api_unavailable"):
        PatternAPI._box(box)
