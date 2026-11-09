"""Bounded set_arrangement contracts/faults; synthetic native, visual-only fit."""

import sys

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result


def entry(index=0, name="Body_Front_Center_1"):
    return {"ArrangementIndex": str(index), "ArrangementName": name,
            "ArrangementOffsetX": "50", "ArrangementOffsetY": "90",
            "ArrangementOffsetZ": "50", "ArrangementOrientation": "180",
            "ArrangementType": "Curved"}


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
    def __init__(self, library=None, fail_set=False, mismatch=False):
        self.names = ["a", "b"]
        self.library = library if library is not None else [entry(0), entry(1, "Body_Back_1")]
        self.fail_set = fail_set
        self.mismatch = mismatch
        self.assigned = None

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetArrangementList(self):
        return self.library

    def SetArrangement(self, i, arrangement_index):
        if self.fail_set:
            raise RuntimeError("private path")
        self.assigned = (i, arrangement_index)

    def GetArrangementOfPattern(self, i):
        value = dict(self.library[self.assigned[1]])
        if self.mismatch:
            value["ArrangementName"] = "other"
        return value


def api(native, utility=None):
    return PatternAPI({"pattern_api": native, "utility_api": utility or Utility()})


PARAMS = {"pattern_index": 0, "expected_name": "a", "arrangement_index": 1}


def test_success_assigns_and_redrapes(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native, utility = Native(), Utility()
    result = api(native, utility)("set_arrangement", PARAMS)
    assert result == {"verified": True, "pattern_index": 0, "pattern_name": "a",
                      "arrangement_name": "Body_Back_1", "offset": {"x": 50.0, "y": 90.0, "z": 50.0},
                      "orientation": 180.0, "type": "Curved", "units": "native_unspecified",
                      "redrape": True}
    assert native.assigned == (0, 1) and len(utility.calls) == 1
    assert utility.calls[0].bAddArrangementPoints is True


@pytest.mark.parametrize("params", [
    None, {}, {**PARAMS, "extra": 1}, {**PARAMS, "pattern_index": True},
    {**PARAMS, "arrangement_index": "0"}, {**PARAMS, "arrangement_index": 256},
    {**PARAMS, "expected_name": ""}, {**PARAMS, "expected_name": "x" * 129},
])
def test_invalid_params_no_native(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("set_arrangement", params)
    assert native.assigned is None


def test_out_of_range_index_and_stale_name(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("set_arrangement", {**PARAMS, "arrangement_index": 2})
    native.names = ["other"]
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)("set_arrangement", PARAMS)
    assert native.assigned is None


def test_set_or_readback_mismatch_is_scene_change(monkeypatch):
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(fail_set=True))("set_arrangement", PARAMS)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(mismatch=True))("set_arrangement", PARAMS)


def test_missing_option_or_redrape_failure(monkeypatch):
    class NoOption:
        pass
    monkeypatch.setitem(sys.modules, "ApiTypes", NoOption)
    with pytest.raises(CommandError, match="api_unavailable"):
        api(Native())("set_arrangement", PARAMS)
    monkeypatch.setitem(sys.modules, "ApiTypes", ApiTypes)
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(), Utility(fail=True))("set_arrangement", PARAMS)


def test_result_validator():
    data = {"verified": True, "pattern_index": 0, "pattern_name": "a",
            "arrangement_name": "Body_Front_Center_1",
            "offset": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": 180.0,
            "type": "Curved", "units": "native_unspecified", "redrape": True}
    validate_result("set_arrangement", data)
    for bad in ({**data, "redrape": False}, {**data, "units": "mm"},
                {**data, "offset": {"x": 0}}, {**data, "type": ""}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("set_arrangement", bad)
