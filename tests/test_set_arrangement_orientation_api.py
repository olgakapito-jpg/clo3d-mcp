"""Bounded set_arrangement_orientation contracts/faults; synthetic native, not 3D evidence."""

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
    def __init__(self, fail_set=False, mismatch=False, name_change=False):
        self.names = ["a", "b"]
        self.values = [entry(), entry(name="Body_Back_Center_2", orientation="0")]
        self.fail_set = fail_set
        self.mismatch = mismatch
        self.name_change = name_change
        self.assigned = None

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def SetArrangementOrientation(self, i, orientation):
        if self.fail_set:
            raise RuntimeError("private path")
        self.assigned = (i, orientation)
        self.values[i] = dict(self.values[i], ArrangementOrientation=str(
            orientation + 1 if self.mismatch else orientation))
        if self.name_change:
            self.values[i]["ArrangementName"] = "other"

    def GetArrangementOfPattern(self, i):
        return dict(self.values[i])


def api(native, utility=None):
    return PatternAPI({"pattern_api": native, "utility_api": utility or Utility()})


PARAMS = {"pattern_index": 0, "expected_name": "a", "orientation": 90}


def test_success_sets_orientation_and_redrapes(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native, utility = Native(), Utility()
    result = api(native, utility)("set_arrangement_orientation", PARAMS)
    assert result == {"verified": True, "pattern_index": 0, "pattern_name": "a",
                      "arrangement_name": "Body_Front_Center_2",
                      "offset": {"x": 50.0, "y": 75.0, "z": 50.0},
                      "orientation": 90.0, "type": "Curved",
                      "units": "native_unspecified", "redrape": True}
    assert native.assigned == (0, 90) and len(utility.calls) == 1
    assert utility.calls[0].bAddArrangementPoints is True


@pytest.mark.parametrize("params", [
    None, {}, {**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
    {**PARAMS, "orientation": "90"}, {**PARAMS, "orientation": True},
    {**PARAMS, "orientation": -1}, {**PARAMS, "orientation": 360},
    {**PARAMS, "expected_name": ""}, {**PARAMS, "expected_name": "x" * 129},
])
def test_invalid_params_no_native(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("set_arrangement_orientation", params)
    assert native.assigned is None


def test_stale_name_or_missing_binding(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native = Native()
    native.names = ["other"]
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)("set_arrangement_orientation", PARAMS)
    native = Native()
    native.SetArrangementOrientation = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)("set_arrangement_orientation", PARAMS)


def test_setter_or_readback_mismatch_is_scene_change(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(fail_set=True))("set_arrangement_orientation", PARAMS)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(mismatch=True))("set_arrangement_orientation", PARAMS)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(name_change=True))("set_arrangement_orientation", PARAMS)


def test_missing_option_or_redrape_failure(monkeypatch):
    class NoOption:
        pass
    monkeypatch.setitem(sys.modules, "ApiTypes", NoOption)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(Native())("set_arrangement_orientation", PARAMS)
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(), Utility(fail=True))("set_arrangement_orientation", PARAMS)


def test_result_validator():
    data = {"verified": True, "pattern_index": 0, "pattern_name": "a",
            "arrangement_name": "Body_Front_Center_2",
            "offset": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": 90.0,
            "type": "Curved", "units": "native_unspecified", "redrape": True}
    validate_result("set_arrangement_orientation", data)
    for bad in ({**data, "redrape": False}, {**data, "units": "degrees"},
                {**data, "offset": {"x": 0}}, {**data, "orientation": "90"},
                {**data, "type": ""}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("set_arrangement_orientation", bad)
