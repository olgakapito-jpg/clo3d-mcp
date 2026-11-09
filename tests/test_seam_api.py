"""Bounded whole-line seam contracts/faults; synthetic native, not real CLO."""

import json

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params, validate_result


PARAMS = {"pattern_a_index": 0, "expected_name_a": "a", "line_a_index": 0,
          "pattern_b_index": 1, "expected_name_b": "b", "line_b_index": 0,
          "direction_a": True, "direction_b": True}


class Native:
    def __init__(self, value=True, fail=False, seam_gain=1, line_change=False,
                 geometry_change=False, list_change=False):
        self.names = ["a", "b"]
        self.value = value
        self.fail = fail
        self.seam_gain = seam_gain
        self.line_change = line_change
        self.geometry_change = geometry_change
        self.list_change = list_change
        self.seams = 0
        self.calls = []
        self.line_reads = 0
        self.geometry_reads = 0

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetPatternLineInfo(self, i):
        self.line_reads += 1
        lengths = [120, 80, 120, 80]
        if self.line_change and self.line_reads > 2:
            lengths = [121, 80, 120, 80]
        return json.dumps({"status": "success", "lineCount": 4,
                           "lines": [{"lineIndex": k, "length": v}
                                     for k, v in enumerate(lengths)]})

    def GetPatternPiecePos(self, i):
        return [0.0, 0.0] if i == 0 else [200.0, 0.0]

    def GetPatternPieceArea(self, i):
        self.geometry_reads += 1
        return 9600.0 + (1.0 if self.geometry_change and self.geometry_reads > 2 else 0.0)

    def GetBoundingBoxOfPattern(self, i):
        return {"Height": "80", "Width": "120"}

    def GetSeamlinePairGroupCount(self):
        self.calls.append("seam_count")
        return self.seams

    def AddSeamlinePairGroup(self, *args):
        self.calls.append(("seam", args))
        if self.fail:
            raise RuntimeError("private path")
        self.seams += self.seam_gain
        if self.list_change:
            self.names = ["a", "changed"]
        return self.value


def api(native):
    return PatternAPI({"pattern_api": native})


def test_seam_success_readback_and_exact_native_call():
    native = Native()
    result = api(native)( "add_seamline_pair", PARAMS)
    assert result == {"verified": True, "seam_count": 1}
    assert ("seam", (0, 0, 1, 0, True, True)) in native.calls


@pytest.mark.parametrize("native", [Native(value=False), Native(value=1), Native(value="name")])
def test_native_false_or_nonbool_is_invalid_result(native):
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(native)("add_seamline_pair", PARAMS)
    assert len([c for c in native.calls if isinstance(c, tuple)]) == 1


def test_seam_count_not_incremented_is_unknown():
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(seam_gain=0))("add_seamline_pair", PARAMS)


def test_native_exception_is_scene_change_unverified():
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(Native(fail=True))("add_seamline_pair", PARAMS)


@pytest.mark.parametrize("change", ["line_change", "geometry_change"])
def test_post_effect_drift_is_scene_change_unverified(change):
    native = Native(**{change: True})
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(native)("add_seamline_pair", PARAMS)


def test_list_change_is_inventory_changed():
    with pytest.raises(CommandError, match="inventory_changed"):
        api(Native(list_change=True))("add_seamline_pair", PARAMS)


def test_same_piece_or_bad_line_rejected_before_native():
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("add_seamline_pair", {**PARAMS, "pattern_b_index": 0})
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("add_seamline_pair", {**PARAMS, "line_a_index": 4})
    assert not [c for c in native.calls if isinstance(c, tuple)]


@pytest.mark.parametrize("names", [[], ["a"], ["a", "a"], ["a", "b", "b"]])
def test_stale_names_rejected(names):
    native = Native()
    native.names = names
    with pytest.raises(CommandError, match="stale_pattern"):
        api(native)("add_seamline_pair", PARAMS)
    assert not [c for c in native.calls if isinstance(c, tuple)]


@pytest.mark.parametrize("params", [
    None, {}, {**PARAMS, "extra": 1}, {**PARAMS, "direction_a": 1},
    {**PARAMS, "direction_b": 0}, {**PARAMS, "line_a_index": True},
    {**PARAMS, "pattern_a_index": "0"}, {**PARAMS, "expected_name_b": ""},
    {**PARAMS, "expected_name_a": "x" * 129},
])
def test_invalid_raw_seam_params_no_native(params):
    native = Native()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(native)("add_seamline_pair", params)
    assert not [c for c in native.calls if isinstance(c, tuple)]


def test_missing_binding_fails_before_calls():
    native = Native()
    native.AddSeamlinePairGroup = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)("add_seamline_pair", PARAMS)
    assert native.calls == []


def test_result_validator_requires_verified_and_count():
    validate_result("add_seamline_pair", {"verified": True, "seam_count": 3})
    for bad in ({"verified": False, "seam_count": 3},
                {"verified": True, "seam_count": -1},
                {"verified": True, "seam_count": True},
                {"verified": True}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("add_seamline_pair", bad)
