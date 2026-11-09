"""Bounded pattern-lines contracts/faults; synthetic native, not real-CLO evidence."""

import json

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params, validate_result
from clo3d_mcp.protocol import PATTERN_CAPABILITIES, ProtocolError, message
from clo3d_mcp.jobs import JobQueue


COMMAND = "get_pattern_lines"
PARAMS = {"pattern_index": 0, "expected_name": "panel"}
BOX = {"minX": 2000, "minY": 1250, "maxX": 2120, "maxY": 1330, "width": 120, "height": 80}


def line(index, length, orientation, location, start, end, mid, norm):
    return {"lineIndex": index, "length": length, "orientation": orientation,
            "location": location, "start": {"x": start[0], "y": start[1]},
            "end": {"x": end[0], "y": end[1]}, "mid": {"x": mid[0], "y": mid[1]},
            "midNorm": {"x": norm[0], "y": norm[1]}}


def native_lines():
    return [
        line(0, 120.0, "horizontal", "bottom", (2000, 1250), (2120, 1250), (2060, 1250), (0.5, 0.0)),
        line(1, 80.0, "vertical", "right", (2120, 1250), (2120, 1330), (2120, 1290), (1.0, 0.5)),
        line(2, 120.0, "horizontal", "top", (2120, 1330), (2000, 1330), (2060, 1330), (0.5, 1.0)),
        line(3, 80.0, "vertical", "left", (2000, 1330), (2000, 1250), (2000, 1290), (0.0, 0.5)),
    ]


def payload(lines=None, **overrides):
    lines = native_lines() if lines is None else lines
    data = {"status": "success", "patternIndex": 0, "patternName": "panel",
            "lineCount": len(lines), "boundingBox": dict(BOX), "lines": lines}
    data.update(overrides)
    return json.dumps(data)


def expected(lines=None):
    lines = native_lines() if lines is None else lines
    return {"pattern_index": 0, "pattern_name": "panel", "line_count": len(lines),
            "bounding_box_mm": {"min_x": 2000.0, "min_y": 1250.0, "max_x": 2120.0,
                                "max_y": 1330.0, "width": 120.0, "height": 80.0},
            "lines": [{"line_index": item["lineIndex"], "length_mm": float(item["length"]),
                       "orientation": item["orientation"], "location": item["location"],
                       "start_mm": {k: float(v) for k, v in item["start"].items()},
                       "end_mm": {k: float(v) for k, v in item["end"].items()},
                       "mid_mm": {k: float(v) for k, v in item["mid"].items()},
                       "mid_norm": {k: float(v) for k, v in item["midNorm"].items()}}
                      for item in lines],
            "coordinate_frame": "api_2d_mm", "units": "mm"}


class Native:
    def __init__(self, value=None, fail=False):
        self.names = ["panel", "other"]
        self.value = payload() if value is None else value
        self.fail = fail
        self.calls = []
        self.reads = 0

    def GetPatternCount(self):
        self.calls.append("count")
        return len(self.names)

    def GetPatternPieceName(self, i):
        self.calls.append("name")
        return self.names[i]

    def GetPatternLineInfo(self, i):
        self.calls.append("line")
        self.reads += 1
        assert i == 0
        if self.fail:
            raise RuntimeError("private path or native exception")
        return self.value


def api(native):
    return PatternAPI({"pattern_api": native})


def test_lines_success_shape_names_order_and_single_native_read():
    native = Native()
    observed = api(native)(COMMAND, PARAMS)
    assert observed == expected()
    assert native.calls == ["count", "name", "name", "count", "line",
                            "count", "name", "name", "count"]
    assert native.reads == 1


def test_lines_preserve_native_order_and_float_conversion():
    lines = native_lines()
    lines = [lines[2], lines[0], lines[3], lines[1]]
    native = Native(payload(lines))
    observed = api(native)(COMMAND, PARAMS)
    assert [item["line_index"] for item in observed["lines"]] == [2, 0, 3, 1]
    assert all(type(item["length_mm"]) is float for item in observed["lines"])


@pytest.mark.parametrize("params", [None, {}, {"pattern_index": 0},
    {**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
    {**PARAMS, "pattern_index": 0.0}, {**PARAMS, "pattern_index": "0"},
    {**PARAMS, "pattern_index": -1}, {**PARAMS, "pattern_index": 256},
    {**PARAMS, "expected_name": ""}, {**PARAMS, "expected_name": "x" * 129},
    {**PARAMS, "expected_name": "bad\n"}, {**PARAMS, "expected_name": "\ud800"}])
def test_invalid_raw_line_params_no_native_or_queue(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)(COMMAND, params)
    queue = JobQueue("s")
    queue.on_connected()
    with pytest.raises(ProtocolError):
        queue.submit(COMMAND, params=params)
    assert not native.calls and not queue.waiting


@pytest.mark.parametrize("names", [[], ["other"], ["panel", "panel"]])
def test_lines_stale_or_ambiguous_never_enters_getter(names):
    native = Native()
    native.names = names
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 0


@pytest.mark.parametrize("bad", [
    "",
    "[]",
    "{}",
    "not json",
    object(),
    [],
    '{"status":"failed","message":"private text"}',
    payload(status="failed"), payload(patternIndex=1), payload(patternIndex=True),
    payload(patternName="other"), payload(lineCount=5), payload(lineCount=True),
    payload(lines=[]), payload(lines=native_lines()[:3], lineCount=5),
    json.dumps({**json.loads(payload()), "lines": "private"}),
    '{"status":"success","status":"success"}',
    '{"status":"success","patternIndex":0,"patternName":"panel","lineCount":1,"lines":[{"lineIndex":0,"length":NaN}]}',
    payload(lines=[line(0, -1.0, "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, 1.0, "curve", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, 1.0, "horizontal", "TOP", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, 1.0, "horizontal", "private path", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, 1.0, "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (1.5, 0))]),
    payload(lines=[line(0, 1.0, "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0)),
                   line(0, 1.0, "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(True, 1.0, "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, "1", "horizontal", "top", (0, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(lines=[line(0, 1.0, "horizontal", "top", (True, 0), (1, 0), (0.5, 0), (0.5, 0))]),
    payload(boundingBox={"minX": 2120, "minY": 1250, "maxX": 2000, "maxY": 1330,
                         "width": 120, "height": 80}),
    payload(boundingBox={"minX": 0, "minY": 0, "maxX": 1, "maxY": 1, "width": -1, "height": 1}),
    '{"status":"success","patternIndex":0,"patternName":"panel","lineCount":1,"boundingBox":{},"lines":[]}',
])
def test_invalid_native_line_info_stops_single_read_no_retry(bad):
    native = Native(bad)
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 1


def test_oversized_line_json_rejected_without_retry():
    native = Native('{"status":"' + "x" * 70000 + '"}')
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 1


def test_line_native_exception_sanitized_and_not_retried():
    native = Native(fail=True)
    with pytest.raises(CommandError, match="^command_error$"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 1


@pytest.mark.parametrize("method", ["GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo"])
def test_line_missing_binding_fails_before_reads(method):
    native = Native()
    setattr(native, method, None)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)(COMMAND, PARAMS)
    assert native.calls == []


def test_line_list_change_after_read_stops_without_second_read():
    native = Native()
    original = native.GetPatternLineInfo
    def read(i):
        value = original(i)
        native.names[1] = "changed"
        return value
    native.GetPatternLineInfo = read
    with pytest.raises(CommandError, match="inventory_changed"):
        api(native)(COMMAND, PARAMS)
    assert native.reads == 1


def test_line_capability_registered_without_extra_native_tools():
    from clo3d_mcp.pattern_contract import PATTERN_COMMANDS
    assert COMMAND in PATTERN_COMMANDS and COMMAND in PATTERN_CAPABILITIES


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=1),
    lambda d: d.pop("units"),
    lambda d: d.update(line_count=0),
    lambda d: d["lines"][0].update(length_mm=-1),
    lambda d: d["lines"][0].update(orientation="curve"),
    lambda d: d["lines"][0].update(location="Private"),
    lambda d: d["lines"][0].update(mid_norm={"x": 2, "y": 0}),
    lambda d: d["bounding_box_mm"].update(width=-1),
    lambda d: d.update(coordinate_frame="bbox_top_left_y_down"),
])
def test_result_validator_rejects_bad_line_shapes(mutate):
    data = expected()
    mutate(data)
    with pytest.raises(CommandError, match="invalid_result"):
        validate_result(COMMAND, data)
