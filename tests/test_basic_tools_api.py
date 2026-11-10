"""Contracts/faults for screenshot, seam/arrangement reads, avatar fit and simulate."""

import json
import sys
from types import SimpleNamespace

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def arrangement(name="Body_Front_Center_2", kind="Curved", orientation="180"):
    return {"ArrangementName": name, "ArrangementOffsetX": "50",
            "ArrangementOffsetY": "75", "ArrangementOffsetZ": "50",
            "ArrangementOrientation": orientation, "ArrangementType": kind}


class Pattern:
    def __init__(self):
        self.names = ["A", "B"]
        self.arrangements = [arrangement(), arrangement("Body_Back_Center_2")]
        self.style_calls = []
        self.edge_calls = []
        self.attachment = {"is_attached": True, "line_index": 0}

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetArrangementList(self):
        values = [arrangement("P%d" % i, "Flat", "0") for i in range(3)]
        return [dict(value, ArrangementIndex=str(i)) for i, value in enumerate(values)]

    def GetArrangementOfPattern(self, i):
        return dict(self.arrangements[i])

    def SetArrangementShapeStyle(self, i, style):
        self.style_calls.append((i, style))
        self.arrangements[i] = dict(self.arrangements[i], ArrangementType=style)

    def GetSeamlinePairGroupCount(self):
        return 2

    def GetSeamlinePairGroupName(self, i):
        return ["seam_a", "seam_b"][i]

    def GetSeamlinePairGroupListInPattern(self, i):
        return [0, 1] if i == 0 else [1]

    def GetAllPatternToAvatarMeasures(self):
        return [("A", "Bust"), ("B", "Waist")]

    def GetPinListSize(self):
        return 3

    def SetPatternEdgeToAvatarMeasure(self, i, line, measure, attach):
        self.edge_calls.append((i, line, measure, attach))
        self.attachment = ({"is_attached": True, "line_index": line} if attach
                           else {"is_attached": False, "line_index": -1})
        return True

    def GetPatternEdgeToAvatarMeasureAttachment(self, i, measure):
        return json.dumps(self.attachment)


class Export:
    def __init__(self, path, fail=False):
        self.path, self.fail, self.calls = path, fail, []

    def ExportThumbnail3D(self, path):
        self.calls.append(path)
        if self.fail:
            raise RuntimeError("private path")
        with open(path, "wb") as file:
            file.write(PNG)
        return path

    def GetAvatarCount(self):
        return 1

    def GetAvatarNameList(self):
        return ["avatar"]


class Utility:
    def __init__(self):
        self.simulate_calls = []

    def GetAvatarMeasurements(self, index):
        return [SimpleNamespace(measurementName="Bust", measurementType="Circumference",
                                value=90.0, basicLength=89.0, surfaceLength=91.0, unit="cm")]

    def Simulate(self, steps):
        self.simulate_calls.append(steps)
        return True


def api(export=None, utility=None, pattern=None):
    return PatternAPI({"pattern_api": pattern or Pattern(),
                       "export_api": export or Export("unused"),
                       "utility_api": utility or Utility()})


def test_arrangement_list_parses_library():
    result = api()("get_arrangement_list", {})
    assert result["library_count"] == 3
    assert result["points"][0] == {"index": 0, "name": "P0", "type": "Flat",
                                   "offset": {"x": 50.0, "y": 75.0, "z": 50.0},
                                   "orientation": 0.0}


def test_seamline_pairs_reads_groups_and_membership():
    result = api()("get_seamline_pairs", {})
    assert result["seam_count"] == 2 and result["pattern_count"] == 2
    assert result["patterns"][0]["group_names"] == ["seam_a", "seam_b"]
    assert result["patterns"][1]["group_indices"] == [1]


def test_avatar_measurements_and_attachments():
    result = api()("get_avatar_measurements", {"avatar_index": 0})
    assert result["avatar_name"] == "avatar" and result["measurement_count"] == 1
    assert result["measurements"][0]["unit"] == "cm"
    attached = api()("get_pattern_avatar_attachments", {})
    assert attached == {"pair_count": 2, "pin_count": 3,
                        "pairs": [{"pattern_name": "A", "avatar_measure": "Bust"},
                                  {"pattern_name": "B", "avatar_measure": "Waist"}]}


def test_shape_style_sets_and_verifies_type():
    native = Pattern()
    result = api(pattern=native)("set_arrangement_shape_style",
                                 {"pattern_index": 0, "expected_name": "A", "style": "Flat"})
    assert result["verified"] is True and result["type"] == "Flat"
    assert native.style_calls == [(0, "Flat")]


def test_edge_pin_attach_and_detach_readback():
    instance = api()
    instance._lines = lambda p: {"line_count": 4}
    attached = instance("set_pattern_edge_to_avatar_measure",
                        {"pattern_index": 0, "expected_name": "A", "line_index": 0,
                         "avatar_measure": "Bust", "attach": True})
    assert attached["attached"] is True and attached["line_index"] == 0
    detached = instance("set_pattern_edge_to_avatar_measure",
                        {"pattern_index": 0, "expected_name": "A", "line_index": 0,
                         "avatar_measure": "Bust", "attach": False})
    assert detached["attached"] is False


def test_simulate_calls_once_and_returns_timing():
    utility = Utility()
    result = api(utility=utility)("simulate", {"steps": 60})
    assert result["verified"] is True and result["steps"] == 60
    assert result["pattern_count"] == 2 and result["avatar_count"] == 1
    assert utility.simulate_calls == [60]


def test_screenshot_writes_and_reports_bytes(tmp_path):
    path = tmp_path / "shot.png"
    export = Export(str(path))
    result = api(export=export)("get_3d_screenshot", {"output_path": str(path)})
    assert result == {"verified": True, "bytes": len(PNG)}
    assert export.calls == [str(path)]


@pytest.mark.parametrize("command,params", [
    ("get_avatar_measurements", {"avatar_index": 64}),
    ("set_arrangement_shape_style", {"pattern_index": 0, "expected_name": "A", "style": "flat"}),
    ("set_pattern_edge_to_avatar_measure",
     {"pattern_index": 0, "expected_name": "A", "line_index": 512,
      "avatar_measure": "Bust", "attach": True}),
    ("simulate", {"steps": 0}),
    ("get_3d_screenshot", {"output_path": "relative.png"}),
])
def test_invalid_params_rejected(command, params):
    with pytest.raises(CommandError, match="invalid_parameters"):
        api()(command, params)


def test_result_validators():
    validate_result("get_arrangement_list", {"library_count": 0, "points": [],
                                             "units": "native_unspecified"})
    validate_result("get_seamline_pairs", {"seam_count": 0, "pattern_count": 0,
                                           "groups": [], "patterns": []})
    validate_result("get_avatar_measurements", {
        "avatar_index": 0, "avatar_name": "a", "measurement_count": 0,
        "measurements": [], "units": "native_display_unit"})
    validate_result("get_pattern_avatar_attachments",
                    {"pair_count": 0, "pin_count": 0, "pairs": []})
    validate_result("set_arrangement_shape_style", {
        "verified": True, "pattern_index": 0, "pattern_name": "a",
        "arrangement_name": "p", "offset": {"x": 0, "y": 0, "z": 0},
        "orientation": 0, "type": "Flat", "units": "native_unspecified"})
    validate_result("set_pattern_edge_to_avatar_measure", {
        "verified": True, "pattern_index": 0, "pattern_name": "a",
        "line_index": 0, "avatar_measure": "Bust", "attached": True})
    validate_result("simulate", {"verified": True, "steps": 60, "pattern_count": 1,
                                 "avatar_count": 1, "elapsed_ms": 1.0})
    validate_result("get_3d_screenshot", {"verified": True, "bytes": 10})
    for command, bad in (
        ("set_arrangement_shape_style", {"type": "flat"}),
        ("get_3d_screenshot", {"bytes": 0}),
        ("simulate", {"elapsed_ms": -1}),
    ):
        with pytest.raises(CommandError, match="invalid_result"):
            data = {
                "set_arrangement_shape_style": {
                    "verified": True, "pattern_index": 0, "pattern_name": "a",
                    "arrangement_name": "p", "offset": {"x": 0, "y": 0, "z": 0},
                    "orientation": 0, "type": "Flat", "units": "native_unspecified"},
                "get_3d_screenshot": {"verified": True, "bytes": 10},
                "simulate": {"verified": True, "steps": 60, "pattern_count": 1,
                             "avatar_count": 1, "elapsed_ms": 1.0},
            }[command]
            validate_result(command, {**data, **bad})
