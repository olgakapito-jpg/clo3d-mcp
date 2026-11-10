"""Bounded set_arrangement_position contracts/faults; synthetic native, not 3D evidence."""

import sys

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result


def entry(name="Body_Front_Center_2", orientation="180", ox="50", oy="75", oz="50"):
    return {"ArrangementName": name, "ArrangementOffsetX": ox,
            "ArrangementOffsetY": oy, "ArrangementOffsetZ": oz,
            "ArrangementOrientation": orientation, "ArrangementType": "Curved"}


class Option:
    bAddArrangementPoints = False
    bAutoCreateFittingSuit = False
    bMoveGarment = False


class ApiTypes:
    ImportExportOption = Option


class Utility:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def ReDrape3DArrangement(self, option):
        self.calls.append(option)
        if self.fail:
            raise RuntimeError("private path")


class Native:
    def __init__(self, fail_set=False, mismatch=False, orientation_change=False):
        self.names = ["a", "b"]
        self.values = [entry(), entry(name="Body_Back_Center_2", orientation="0")]
        self.fail_set = fail_set
        self.mismatch = mismatch
        self.orientation_change = orientation_change
        self.assigned = None

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def SetArrangementPosition(self, i, x, y, z):
        if self.fail_set:
            raise RuntimeError("private path")
        self.assigned = (i, x, y, z)
        self.values[i] = dict(self.values[i], ArrangementOffsetX=str(x + 1 if self.mismatch else x),
                              ArrangementOffsetY=str(y), ArrangementOffsetZ=str(z))
        if self.orientation_change:
            self.values[i]["ArrangementOrientation"] = "90"

    def GetArrangementOfPattern(self, i):
        return dict(self.values[i])


def api(native, utility=None):
    return PatternAPI({"pattern_api": native, "utility_api": utility or Utility()})


PARAMS = {"pattern_index": 0, "expected_name": "a",
          "position_x": 40, "position_y": 70, "offset": 60}


def test_success_sets_offsets_and_redrapes(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native, utility = Native(), Utility()
    result = api(native, utility)("set_arrangement_position", PARAMS)
    assert result == {"verified": True, "pattern_index": 0, "pattern_name": "a",
                      "arrangement_name": "Body_Front_Center_2",
                      "offset": {"x": 40.0, "y": 70.0, "z": 60.0},
                      "orientation": 180.0, "type": "Curved",
                      "units": "native_unspecified", "redrape": True}
    assert native.assigned == (0, 40, 70, 60) and len(utility.calls) == 1


@pytest.mark.parametrize("params", [
    None, {}, {**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
    {**PARAMS, "position_x": True}, {**PARAMS, "position_x": -1},
    {**PARAMS, "position_y": 101}, {**PARAMS, "offset": 50.0},
    {**PARAMS, "offset": "50"}, {**PARAMS, "expected_name": ""},
])
def test_invalid_params_no_native(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("set_arrangement_position", params)
    assert native.assigned is None


def test_stale_name_or_missing_binding(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native = Native()
    native.names = ["other"]
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)("set_arrangement_position", PARAMS)
    native = Native()
    native.SetArrangementPosition = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)("set_arrangement_position", PARAMS)


def test_setter_or_readback_mismatch_is_scene_change(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(fail_set=True))("set_arrangement_position", PARAMS)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(mismatch=True))("set_arrangement_position", PARAMS)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(orientation_change=True))("set_arrangement_position", PARAMS)


def test_missing_option_or_redrape_failure(monkeypatch):
    class NoOption:
        pass
    monkeypatch.setitem(sys.modules, "ApiTypes", NoOption)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(Native())("set_arrangement_position", PARAMS)
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(), Utility(fail=True))("set_arrangement_position", PARAMS)


def test_result_validator():
    data = {"verified": True, "pattern_index": 0, "pattern_name": "a",
            "arrangement_name": "Body_Front_Center_2",
            "offset": {"x": 40.0, "y": 70.0, "z": 60.0}, "orientation": 180.0,
            "type": "Curved", "units": "native_unspecified", "redrape": True}
    validate_result("set_arrangement_position", data)
    for bad in ({**data, "redrape": False}, {**data, "units": "percent"},
                {**data, "offset": {"x": 40}}, {**data, "orientation": "180"},
                {**data, "type": ""}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("set_arrangement_position", bad)
