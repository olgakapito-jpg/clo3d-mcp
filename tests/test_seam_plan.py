import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prototypes.mueller_trousers.seam_plan import (  # noqa: E402
    CURVE_LEG_PAIRS,
    REFERENCE_NAME_MAP,
    LineSpan,
    SeamPair,
    SeamPlanError,
    build_curve_plan,
    build_plan,
    decompose_export,
    plan_to_dict,
    validate_plan,
)


def _pattern(pattern_id, name, points):
    lines = []
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        lines.append({
            "ID": f"{name}_L{index}",
            "PointList": [
                {"Position": {"x": point[0], "y": point[1]}},
                {"Position": {"x": nxt[0], "y": nxt[1]}},
            ],
        })
    return {"ID": pattern_id, "Name": name, "ShapeInfo": {"LineList": lines}}


def _export(patterns, groups):
    return {"PatternList": patterns, "SeamLinePairGroupList": groups}


def _side(shape_id, line_id, start, end, direction):
    return {
        "ShapeID": shape_id,
        "LineID": line_id,
        "LengthParam": {"fStart": start, "fEnd": end},
        "Direction": direction,
    }


def _group(name, first, second):
    return {"Name": name, "PairList": [{"First": first, "Second": second}]}


RECT = [(0, 0), (100, 0), (100, 50), (0, 50)]


def test_decompose_full_run_into_whole_lines():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", RECT)
    data = _export(
        [a, b],
        [_group("g", _side("A", "A_L1", 100 / 300, 250 / 300, True),
                _side("B", "B_L1", 100 / 300, 250 / 300, True))],
    )
    pairs = decompose_export(data)
    assert [(p.a.line, p.b.line) for p in pairs] == [(1, 1), (2, 2)]
    assert all(p.whole_line_a and p.whole_line_b for p in pairs)
    assert [round(p.a.start_ratio, 9) for p in pairs] == [0.0, 0.0]
    assert [p.a.end_ratio for p in pairs] == [pytest.approx(1.0, abs=1e-5)] * 2
    assert not validate_plan(pairs)


def test_direction_false_flips_ratio_order_and_keeps_direction_flag():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", RECT)
    data = _export(
        [a, b],
        [_group("g", _side("A", "A_L1", 100 / 300, 250 / 300, True),
                _side("B", "B_L1", 250 / 300, 100 / 300, False))],
    )
    pairs = decompose_export(data)
    assert all(p.a.direction is True for p in pairs)
    assert all(p.b.direction is False for p in pairs)
    assert all(p.a.start_ratio < p.a.end_ratio for p in pairs)
    assert all(p.b.start_ratio < p.b.end_ratio for p in pairs)
    assert not validate_plan(pairs)


def test_partial_interval_converts_perimeter_fraction_to_line_ratio():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", RECT)
    data = _export(
        [a, b],
        [_group("g", _side("A", "A_L1", 105 / 300, 135 / 300, True),
                _side("B", "B_L1", 105 / 300, 135 / 300, True))],
    )
    [pair] = decompose_export(data)
    assert pair.a.line == 1
    assert pair.a.start_ratio == pytest.approx(0.1, abs=1e-9)
    assert pair.a.end_ratio == pytest.approx(0.7, abs=1e-9)
    assert pair.a.length_mm == pytest.approx(30.0, abs=1e-6)
    assert pair.whole_line_a is False


def test_validate_reports_overlapping_intervals_on_one_line():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", RECT)
    data = _export(
        [a, b],
        [
            _group("g1", _side("A", "A_L1", 105 / 300, 135 / 300, True),
                   _side("B", "B_L1", 105 / 300, 135 / 300, True)),
            _group("g2", _side("A", "A_L1", 115 / 300, 145 / 300, True),
                   _side("B", "B_L1", 115 / 300, 145 / 300, True)),
        ],
    )
    problems = validate_plan(decompose_export(data))
    assert any("overlapping" in problem for problem in problems)


def test_validate_warns_about_ease_but_does_not_reject():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", [(0, 0), (100, 0), (100, 55), (0, 55)])
    data = _export(
        [a, b],
        [_group("g", _side("A", "A_L1", 100 / 300, 250 / 300, True),
                _side("B", "B_L1", 100 / 310, 260 / 310, True))],
    )
    pairs = decompose_export(data)
    problems = validate_plan(pairs)
    assert any("differ" in problem for problem in problems)
    assert not any("overlapping" in problem for problem in problems)


def test_reference_name_map_is_applied():
    a = _pattern("A", "0", RECT)
    b = _pattern("B", "1", RECT)
    data = _export(
        [a, b],
        [_group("g", _side("A", "0_L1", 100 / 300, 250 / 300, True),
                _side("B", "1_L1", 100 / 300, 250 / 300, True))],
    )
    [pair_a, pair_b] = decompose_export(data, REFERENCE_NAME_MAP)
    assert (pair_a.a.pattern, pair_a.b.pattern) == ("FRONT_R", "BACK_L")
    assert (pair_b.a.pattern, pair_b.b.pattern) == ("FRONT_R", "BACK_L")


def test_zero_length_run_is_rejected():
    a = _pattern("A", "A", RECT)
    data = _export([a], [_group("g", _side("A", "A_L1", 0.5, 0.5, True),
                                _side("A", "A_L1", 0.5, 0.5, True))])
    with pytest.raises(SeamPlanError, match="zero length"):
        decompose_export(data)


def test_sub_half_millimetre_sliver_is_skipped():
    a = _pattern("A", "A", RECT)
    b = _pattern("B", "B", RECT)
    data = _export(
        [a, b],
        [_group("g", _side("A", "A_L1", 100 / 300, 100.1 / 300, True),
                _side("B", "B_L1", 100 / 300, 100.1 / 300, True))],
    )
    built = build_plan(data)
    assert built.pairs == []
    assert built.skipped_small == 1
    assert built.max_skipped_mm == pytest.approx(0.1, abs=1e-6)


def test_same_pattern_whole_line_pair_uses_partial_tool():
    span = LineSpan("BACK_L", 1, 0.0, 1.0, True, 0.0, 100.0, 100.0)
    pair = SeamPair("dart", span, span, 100.0, 100.0, 0.0, True, True)
    [entry] = plan_to_dict([pair])["pairs"]
    assert entry["tool"] == "add_seamline_pair_partial"


def test_curve_plan_merges_leg_edges_and_remaps_center_back():
    def pair(group, a_pattern, a_line, b_pattern, b_line):
        span_a = LineSpan(a_pattern, a_line, 0.0, 1.0, True, 0.0, 100.0, 100.0)
        span_b = LineSpan(b_pattern, b_line, 0.0, 1.0, True, 0.0, 100.0, 100.0)
        return SeamPair(group, span_a, span_b, 100.0, 100.0, 0.0, True, True)

    pairs = [
        pair("Sewing_580825", "BACK_L", 4, "FRONT_L", 26),
        pair("Sewing_583232", "BACK_R", 4, "FRONT_R", 26),
        pair("Sewing_645874", "FRONT_R", 12, "BACK_R", 18),
        pair("Sewing_694406", "BACK_L", 17, "FRONT_L", 12),
        pair("Sewing_690044", "BACK_L", 18, "BACK_R", 18),
        pair("Sewing_687376", "FRONT_R", 6, "FRONT_L", 6),
    ]
    result = build_curve_plan(pairs)
    assert len(result) == 6
    legs = {item.group: item for item in result if item.group in CURVE_LEG_PAIRS}
    assert (legs["Sewing_580825"].a.pattern, legs["Sewing_580825"].a.line) == ("BACK_L", 4)
    assert (legs["Sewing_580825"].b.pattern, legs["Sewing_580825"].b.line) == ("FRONT_L", 14)
    assert (legs["Sewing_583232"].b.line) == 14
    assert (legs["Sewing_645874"].a.line, legs["Sewing_645874"].b.line) == (12, 6)
    assert (legs["Sewing_694406"].a.line, legs["Sewing_694406"].b.line) == (6, 12)
    center = next(item for item in result if item.group == "Sewing_690044")
    assert (center.a.line, center.b.line) == (7, 7)
