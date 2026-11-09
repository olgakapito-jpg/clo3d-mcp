"""Bounded arrangement read contracts/faults; synthetic native, not 3D evidence."""

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result


def arrangement(name="Arrangement_0", ox="10", oy="-5", oz="0", orientation="90",
                kind="Avatar"):
    return {"ArrangementName": name, "ArrangementOffsetX": ox, "ArrangementOffsetY": oy,
            "ArrangementOffsetZ": oz, "ArrangementOrientation": orientation,
            "ArrangementType": kind}


class Native:
    def __init__(self, value=None, lib=None, drift=False, bad_index=None):
        self.names = ["a", "b"]
        self.value = value if value is not None else arrangement()
        self.lib = lib if lib is not None else [{}, {}]
        self.drift = drift
        self.bad_index = bad_index
        self.reads = 0

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetArrangementList(self):
        return self.lib

    def GetArrangementOfPattern(self, i):
        self.reads += 1
        if self.bad_index == i:
            return {**self.value, "ArrangementOffsetX": "NaN"}
        if self.drift and self.reads == len(self.names):
            self.names = ["a", "changed"]
        return self.value


def api(native):
    return PatternAPI({"pattern_api": native})


def test_arrangement_success_parses_numbers_and_keeps_units_unspecified():
    native = Native()
    result = api(native)("get_arrangement", {})
    assert result["pattern_count"] == 2 and result["arrangement_library_count"] == 2
    assert result["units"] == "native_unspecified"
    assert result["pieces"][0] == {
        "pattern_index": 0, "pattern_name": "a", "arrangement_name": "Arrangement_0",
        "offset": {"x": 10.0, "y": -5.0, "z": 0.0}, "orientation": 90.0, "type": "Avatar"}


@pytest.mark.parametrize("bad", [
    {}, {"ArrangementName": "x"}, {**arrangement(), "Extra": "1"},
    arrangement(ox="1e3"), arrangement(orientation="90deg"), arrangement(name=1),
    arrangement(kind=""), arrangement(kind="x" * 33),
])
def test_bad_arrangement_shape_or_numeric_rejected(bad):
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(Native(value=bad))("get_arrangement", {})


def test_arrangement_library_or_list_drift_stops():
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(Native(lib="not-list"))("get_arrangement", {})
    with pytest.raises(CommandError, match="inventory_changed"):
        api(Native(drift=True))("get_arrangement", {})


def test_missing_binding_fails_before_reads():
    native = Native()
    native.GetArrangementOfPattern = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api(native)("get_arrangement", {})


def test_arrangement_result_validator():
    data = {"pattern_count": 1, "arrangement_library_count": 2, "units": "native_unspecified",
            "pieces": [{"pattern_index": 0, "pattern_name": "a",
                        "arrangement_name": "Arrangement_0",
                        "offset": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "orientation": 0.0, "type": "Avatar"}]}
    validate_result("get_arrangement", data)
    for bad in ({**data, "pattern_count": 2},
                {**data, "units": "mm"},
                {**data, "pieces": [{**data["pieces"][0], "orientation": "0"}]}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("get_arrangement", bad)
