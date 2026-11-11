"""Offline tests for the stand-alone Müller & Sohn trouser prototype."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes"))

from prototypes.mueller_trousers import (  # noqa: E402
    SIZE_PRESETS,
    TrouserMeasurements,
    draft_trousers,
    to_clo,
    write_clo_json,
    write_dxf,
    write_json,
)
from prototypes.mueller_trousers.geometry import dist, is_simple_polygon  # noqa: E402


def edge_length(piece, name):
    indices = piece.edges[name]
    points = [piece.points[i] for i in indices]
    return sum(dist(a, b) for a, b in zip(points, points[1:]))


def test_measurements_are_derived_from_mueller_core():
    m = TrouserMeasurements()
    assert m.hip_line_drop == pytest.approx(8.0)
    assert m.front_hip_width == pytest.approx(24.0)
    assert m.back_hip_width == pytest.approx(26.0)
    assert m.step_width == pytest.approx(6.0)
    assert m.front_waist_width == pytest.approx(21.5)
    assert m.back_waist_width == pytest.approx(22.5)
    assert m.knee_height == pytest.approx(31.8)
    assert m.y_hip == pytest.approx(18.5)
    assert m.y_knee == pytest.approx(58.3)
    assert m.y_hem == pytest.approx(105.0)


def test_invalid_measurements_are_rejected():
    with pytest.raises(ValueError):
        TrouserMeasurements(waist_half=50, hip_half=50)
    with pytest.raises(ValueError):
        TrouserMeasurements(knee_half=20, hem_half=20)
    with pytest.raises(ValueError):
        TrouserMeasurements(seat_height=106, side_length=106)


def test_draft_has_five_simple_pieces_with_area():
    pattern = draft_trousers()
    assert [piece.name for piece in pattern.pieces] == [
        "FRONT_L", "BACK_L", "FRONT_R", "BACK_R", "WAISTBAND"]
    for piece in pattern.pieces:
        assert len(piece.points) >= 4
        assert piece.area_cm2 > 100
        assert is_simple_polygon(list(piece.points)), piece.name


def test_front_and_back_leg_edges_are_balanced():
    pattern = draft_trousers()
    front, back = pattern.by_name("FRONT_L"), pattern.by_name("BACK_L")
    assert edge_length(front, "side") == pytest.approx(edge_length(back, "side"), abs=1.0)
    assert edge_length(front, "inseam") == pytest.approx(edge_length(back, "inseam"), abs=1.0)
    assert edge_length(front, "hem") < edge_length(back, "hem")


def test_notches_and_grainlines_are_present():
    pattern = draft_trousers()
    for piece in pattern.pieces:
        assert piece.notches
        assert piece.grainline.start[1] < piece.grainline.end[1]
        for notch in piece.notches:
            assert notch.label
            assert abs(notch.normal[0]) + abs(notch.normal[1]) > 0


def test_right_pieces_are_translated_copies_with_identical_line_order():
    pattern = draft_trousers()
    left, right = pattern.by_name("FRONT_L"), pattern.by_name("FRONT_R")
    assert left.area_cm2 == pytest.approx(right.area_cm2, rel=1e-9)
    assert len(left.points) == len(right.points)
    left_back, right_back = pattern.by_name("BACK_L"), pattern.by_name("BACK_R")
    assert left_back.area_cm2 == pytest.approx(right_back.area_cm2, rel=1e-9)
    # Right leg sits to the right of the left leg.
    assert left.bbox[2] < right.bbox[0]
    assert left_back.bbox[2] < right_back.bbox[0]


def test_custom_size_changes_geometry():
    base = draft_trousers(SIZE_PRESETS[40])
    larger = draft_trousers(SIZE_PRESETS[44])
    assert larger.by_name("FRONT_L").area_cm2 > base.by_name("FRONT_L").area_cm2
    assert larger.measurements.hip_half > base.measurements.hip_half


def test_dxf_writer_outputs_standard_polylines_and_markers(tmp_path):
    pattern = draft_trousers()
    path = write_dxf(pattern, tmp_path / "trousers.dxf")
    text = path.read_text(encoding="ascii")
    assert text.startswith("0\nSECTION")
    assert text.rstrip().endswith("EOF")
    assert text.count("\nPOLYLINE\n") == 5
    assert "FRONT_L" in text and "BACK_R" in text
    assert "NOTCH" in text and "GRAIN" in text
    assert "AC1009" in text


def test_clo_json_has_pieces_and_referentially_valid_seams():
    data = to_clo(draft_trousers())
    assert data["formatVersion"] == 1 and data["formatMinorVersion"] == 4
    assert data["Unit"] == "mm"
    assert len(data["PatternList"]) == 5
    assert len(data["SeamLinePairGroupList"]) >= 6

    pattern_ids = {piece["ID"] for piece in data["PatternList"]}
    line_ids = {
        piece["ID"]: {line["ID"] for line in piece["ShapeInfo"]["LineList"]}
        for piece in data["PatternList"]
    }
    assert len(pattern_ids) == 5
    all_line_ids = [line["ID"] for piece in data["PatternList"]
                    for line in piece["ShapeInfo"]["LineList"]]
    point_owner = {}
    for piece in data["PatternList"]:
        for line in piece["ShapeInfo"]["LineList"]:
            for point in line["PointList"]:
                point_owner.setdefault(point["ID"], set()).add(piece["Name"])
    assert len(all_line_ids) == len(set(all_line_ids))
    assert all(len(owners) == 1 for owners in point_owner.values())
    names = [piece["Name"] for piece in data["PatternList"]]
    assert names == ["FRONT_L", "BACK_L", "FRONT_R", "BACK_R", "WAISTBAND"]
    line_counts = {piece["Name"]: len(piece["ShapeInfo"]["LineList"])
                   for piece in data["PatternList"]}
    assert line_counts == {"FRONT_L": 15, "BACK_L": 18,
                           "FRONT_R": 15, "BACK_R": 18, "WAISTBAND": 4}
    merged = [line for piece in data["PatternList"]
              if piece["Name"] != "WAISTBAND"
              for line in piece["ShapeInfo"]["LineList"]
              if len(line["PointList"]) > 2]
    assert len(merged) == 8
    assert all(any(point["PointType"] == "Polyline"
                   for point in line["PointList"][1:-1]) for line in merged)
    assert len({group["Name"] for group in data["SeamLinePairGroupList"]}) == len(
        data["SeamLinePairGroupList"])
    for group in data["SeamLinePairGroupList"]:
        assert len(group["PairList"]) == 1
        pair = group["PairList"][0]
        for side in ("First", "Second"):
            item = pair[side]
            assert item["ShapeID"] in pattern_ids
            assert item["LineID"] in line_ids[item["ShapeID"]]
            assert 0.0 <= item["LengthParam"]["fStart"] <= 1.0
            assert 0.0 <= item["LengthParam"]["fEnd"] <= 1.0
            assert type(item["Direction"]) is bool


def test_clo_json_writer_is_utf8_and_deterministic(tmp_path):
    first = write_clo_json(draft_trousers(), tmp_path / "first.json")
    second = write_clo_json(draft_trousers(), tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
    data = json.loads(first.read_text(encoding="utf-8"))
    assert data["FabricList"][0]["FabricUUID"] == "FABRIC1"


def test_json_writer_keeps_measurements_and_seam_plan(tmp_path):
    pattern = draft_trousers()
    path = write_json(pattern, tmp_path / "trousers.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "mueller_trousers_prototype_v1"
    assert data["units"] == "cm"
    assert len(data["pieces"]) == 5
    assert len(data["seam_plan"]) == 8
    assert data["measurements"]["hip_half"] == 50.0
    assert data["pieces"][0]["name"] == "FRONT_L"
    assert data["pieces"][0]["notches"]
