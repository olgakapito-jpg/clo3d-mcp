"""Decompose exported CLO seam groups into per-line seam pairs.

CLO's ``export_pattern_json`` stores a seam side as one ``LineID`` plus a
``LengthParam`` that is a fraction of the whole pattern perimeter.  A manually
sewn edge usually spans several ``LineList`` segments, so one exported group
cannot be replayed as one ``add_seamline_pair_partial`` call.  This module
splits every run at line boundaries, converts perimeter fractions back to
line-relative ratios and validates the resulting plan.

No CLO connection is used here: input is a previously exported JSON file.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

REFERENCE_NAME_MAP = {
    "0": "FRONT_R",
    "1": "BACK_L",
    "2": "FRONT_L",
    "3": "BACK_R",
    "4": "WAISTBAND",
}

# Indices of the generated `trousers_olga_clo.json` scene after import.
OLGA_TARGET_INDEX = {
    "FRONT_L": 0,
    "BACK_L": 1,
    "FRONT_R": 2,
    "BACK_R": 3,
    "WAISTBAND": 4,
}

EPS = 1e-9


class SeamPlanError(ValueError):
    """The exported file cannot be converted into a safe seam plan."""


@dataclass(frozen=True)
class LineSpan:
    pattern: str
    line: int
    start_ratio: float
    end_ratio: float
    direction: bool
    start_mm: float
    end_mm: float
    length_mm: float


@dataclass(frozen=True)
class SeamPair:
    group: str
    a: LineSpan
    b: LineSpan
    run_length_a_mm: float
    run_length_b_mm: float
    run_length_delta_mm: float
    whole_line_a: bool
    whole_line_b: bool


@dataclass(frozen=True)
class _Run:
    pattern: str
    line: int
    fs_mm: float
    fe_mm: float
    direction: bool
    start_mm: float
    end_mm: float


def _pattern_table(data: dict) -> dict[str, dict]:
    table: dict[str, dict] = {}
    for pattern in data["PatternList"]:
        lengths: list[float] = []
        for line in pattern["ShapeInfo"]["LineList"]:
            points = line["PointList"]
            start = points[0]["Position"]
            end = points[-1]["Position"]
            lengths.append(math.hypot(end["x"] - start["x"], end["y"] - start["y"]))
        offsets: list[float] = []
        total = 0.0
        for length in lengths:
            offsets.append(total)
            total += length
        table[pattern["ID"]] = {
            "name": pattern["Name"],
            "line_index": {line["ID"]: i for i, line in enumerate(pattern["ShapeInfo"]["LineList"])},
            "lengths": lengths,
            "offsets": offsets,
            "perimeter": total,
        }
    return table


def _locate(offsets: list[float], lengths: list[float], position: float) -> int:
    for index, (offset, length) in enumerate(zip(offsets, lengths)):
        if position < offset + length - EPS:
            return index
    return len(lengths) - 1


def _make_run(side: dict, table: dict[str, dict]) -> _Run:
    pattern = table.get(side["ShapeID"])
    if pattern is None:
        raise SeamPlanError(f"unknown ShapeID {side['ShapeID']!r}")
    line = pattern["line_index"].get(side["LineID"])
    if line is None:
        raise SeamPlanError(f"unknown LineID {side['LineID']!r} in {pattern['name']}")
    start = side["LengthParam"]["fStart"] * pattern["perimeter"]
    end = side["LengthParam"]["fEnd"] * pattern["perimeter"]
    direction = bool(side["Direction"])
    # Export fStart is the stitch start and fEnd the stitch end regardless of
    # Direction; a direction=false pair is exported descending.
    return _Run(pattern["name"], line, start, end, direction, start, end)


def _boundary_ts(run: _Run, table: dict[str, dict]) -> list[float]:
    pattern = next(p for p in table.values() if p["name"] == run.pattern)
    low, high = sorted((run.start_mm, run.end_mm))
    span = high - low
    result = []
    if span <= EPS:
        raise SeamPlanError(f"{run.pattern} seam run has zero length")
    for boundary in pattern["offsets"][1:] + [pattern["perimeter"]]:
        if low + EPS < boundary < high - EPS:
            result.append((run.start_mm - boundary) / (run.start_mm - run.end_mm))
    return result


def _line_ratio(pattern: dict, position: float) -> tuple[int, float]:
    line = _locate(pattern["offsets"], pattern["lengths"], position)
    length = pattern["lengths"][line]
    if length <= EPS:
        raise SeamPlanError(f"{pattern['name']} line {line} is zero length")
    return line, (position - pattern["offsets"][line]) / length


def _span(pattern: dict, run: _Run, t0: float, t1: float) -> LineSpan:
    delta = run.end_mm - run.start_mm
    p0 = run.start_mm + t0 * delta
    p1 = run.start_mm + t1 * delta
    mid = (p0 + p1) / 2.0
    line, ratio0 = _line_ratio(pattern, p0)
    mid_line, _ = _line_ratio(pattern, mid)
    if mid_line != line:
        line = mid_line
        ratio0 = (p0 - pattern["offsets"][line]) / pattern["lengths"][line]
    ratio1 = (p1 - pattern["offsets"][line]) / pattern["lengths"][line]
    lo = min(ratio0, ratio1)
    hi = max(ratio0, ratio1)
    # Position drift from merged boundary t values is sub-micron. Clamp only
    # values that fall just outside the line; never expand an inner value to
    # 0/1, which would overlap the neighbouring sub-pair.
    if -1e-4 <= lo < 0.0:
        lo = 0.0
    if 1.0 < hi <= 1.0 + 1e-4:
        hi = 1.0
    if not (0.0 <= lo < hi <= 1.0):
        raise SeamPlanError(
            f"{pattern['name']} line {line}: ratio [{lo}, {hi}] outside 0..1"
        )
    return LineSpan(
        pattern=pattern["name"],
        line=line,
        start_ratio=round(max(lo, 0.0), 9),
        end_ratio=round(min(hi, 1.0), 9),
        direction=ratio1 > ratio0,
        start_mm=round(min(p0, p1), 6),
        end_mm=round(max(p0, p1), 6),
        length_mm=round(abs(p1 - p0), 6),
    )


@dataclass(frozen=True)
class PlanBuild:
    pairs: list[SeamPair]
    skipped_small: int
    max_skipped_mm: float


def build_plan(
    data: dict,
    name_map: dict[str, str] | None = None,
    min_segment_mm: float = 0.5,
) -> PlanBuild:
    """Split every seam group into line-aligned pairs.

    Sub-pairs shorter than ``min_segment_mm`` on both sides are float-noise
    slivers at a line boundary, not useful seams; they are skipped.
    """

    table = _pattern_table(data)
    name_map = name_map or {}
    patterns_by_name = {pattern["name"]: pattern for pattern in table.values()}
    pairs: list[SeamPair] = []
    skipped_small = 0
    max_skipped_mm = 0.0
    for group in data.get("SeamLinePairGroupList", []):
        pair = group["PairList"][0]
        run_a = _make_run(pair["First"], table)
        run_b = _make_run(pair["Second"], table)
        pattern_a = patterns_by_name[run_a.pattern]
        pattern_b = patterns_by_name[run_b.pattern]
        ts = _boundary_ts(run_a, table) + _boundary_ts(run_b, table)
        # Boundaries that differ only by float noise (~1e-7 in t) are the same
        # physical line boundary; merging them avoids 1e-5 mm sliver pairs.
        ts = [0.0] + sorted({round(t, 6) for t in ts if 1e-6 < t < 1 - 1e-6}) + [1.0]
        for t0, t1 in zip(ts, ts[1:]):
            span_a = _span(pattern_a, run_a, t0, t1)
            span_b = _span(pattern_b, run_b, t0, t1)
            longest = max(span_a.length_mm, span_b.length_mm)
            if longest < min_segment_mm:
                skipped_small += 1
                max_skipped_mm = max(max_skipped_mm, longest)
                continue
            if name_map:
                span_a = LineSpan(**{**asdict(span_a), "pattern": name_map.get(span_a.pattern, span_a.pattern)})
                span_b = LineSpan(**{**asdict(span_b), "pattern": name_map.get(span_b.pattern, span_b.pattern)})
            run_a_length = abs(run_a.end_mm - run_a.start_mm)
            run_b_length = abs(run_b.end_mm - run_b.start_mm)
            pairs.append(
                SeamPair(
                    group=group.get("Name", "Sewing"),
                    a=span_a,
                    b=span_b,
                    run_length_a_mm=round(run_a_length, 6),
                    run_length_b_mm=round(run_b_length, 6),
                    run_length_delta_mm=round(abs(run_a_length - run_b_length), 6),
                    whole_line_a=span_a.start_ratio <= 1e-5 and span_a.end_ratio >= 1 - 1e-5,
                    whole_line_b=span_b.start_ratio <= 1e-5 and span_b.end_ratio >= 1 - 1e-5,
                )
            )
    return PlanBuild(pairs, skipped_small, round(max_skipped_mm, 6))


def decompose_export(
    data: dict,
    name_map: dict[str, str] | None = None,
    min_segment_mm: float = 0.5,
) -> list[SeamPair]:
    """Backward-compatible pair list; see :func:`build_plan`."""

    return build_plan(data, name_map, min_segment_mm).pairs


def validate_plan(pairs: list[SeamPair], run_delta_warn_mm: float = 1.0) -> list[str]:
    """Return plan problems and warnings; only empty means dispatchable.

    Run-length differences are warnings because CLO seams may carry ease
    (front/back crotch curves differ by up to ~20 mm in the reference).
    Exact duplicate coverage by two different groups is also a warning: the
    reference shares one short segment between two seams.
    """

    problems: list[str] = []
    warnings: list[str] = []
    covered: dict[tuple[str, int], list[tuple[float, float, str]]] = {}
    ease: dict[str, tuple[float, float, float, str, str]] = {}
    for index, pair in enumerate(pairs):
        for side in (pair.a, pair.b):
            if not (0.0 <= side.start_ratio < side.end_ratio <= 1.0):
                problems.append(
                    f"pair {index}: {side.pattern} line {side.line} has ratio "
                    f"[{side.start_ratio}, {side.end_ratio}]"
                )
            if side.length_mm <= EPS:
                problems.append(f"pair {index}: {side.pattern} line {side.line} is zero length")
            if not math.isfinite(side.start_mm) or not math.isfinite(side.end_mm):
                problems.append(f"pair {index}: non-finite seam position")
            covered.setdefault((side.pattern, side.line), []).append(
                (side.start_ratio, side.end_ratio, pair.group)
            )
        if pair.run_length_delta_mm > run_delta_warn_mm and pair.group not in ease:
            ease[pair.group] = (
                pair.run_length_delta_mm,
                pair.run_length_a_mm,
                pair.run_length_b_mm,
                pair.a.pattern,
                pair.b.pattern,
            )
    for group, (delta, length_a, length_b, name_a, name_b) in ease.items():
        warnings.append(
            f"{group}: run lengths differ by {delta:.2f} mm "
            f"({name_a} {length_a:.2f} mm vs {name_b} {length_b:.2f} mm); "
            "assume proportional ease"
        )
    for key, intervals in covered.items():
        ordered = sorted(intervals)
        for (start, end, group), (next_start, next_end, next_group) in zip(ordered, ordered[1:]):
            if next_start < end - 1e-6:
                if (group != next_group
                        and abs(start - next_start) <= 1e-4
                        and abs(end - next_end) <= 1e-4):
                    warnings.append(
                        f"{key[0]} line {key[1]}: {group} and {next_group} both cover "
                        f"[{start:.6f}, {end:.6f}] (reference shares this segment)"
                    )
                else:
                    problems.append(
                        f"{key[0]} line {key[1]}: overlapping intervals "
                        f"{group} [{start:.9f}, {end:.9f}] and "
                        f"{next_group} [{next_start:.9f}, {next_end:.9f}]"
                    )
    return problems + warnings


# Group names are the ones in trousers_sewn_reference.json; a fresh CLO
# re-export may rename them, so refresh this map with the new reference.
CURVE_LEG_PAIRS = {
    # group: (pattern_a, line_a, pattern_b, line_b, direction_a, direction_b)
    "Sewing_580825": ("BACK_L", 4, "FRONT_L", 14, True, False),
    "Sewing_583232": ("BACK_R", 4, "FRONT_R", 14, True, False),
    "Sewing_645874": ("FRONT_R", 12, "BACK_R", 6, True, False),
    "Sewing_694406": ("BACK_L", 6, "FRONT_L", 12, False, True),
}

# Center-back target lines: original BACK_L/BACK_R lines 18..28 shift to 7..17
# after the side and inseam merges in clo_json.py.
CURVE_CENTER_BACK_SHIFT = -11
CURVE_CENTER_BACK_GROUP = "Sewing_690044"


def _whole_span(pattern: str, line: int, direction: bool, length: float) -> LineSpan:
    return LineSpan(pattern, line, 0.0, 1.0, direction, 0.0, length, length)


def build_curve_plan(pairs: list[SeamPair]) -> list[SeamPair]:
    """Convert the reference seam plan to the curve-edge target topology.

    Side and inseam edges are one line each; center-back lines shift because
    of the four merges. Center front, darts and waistband keep their ratios.
    """

    grouped: dict[str, list[SeamPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.group, []).append(pair)

    result: list[SeamPair] = []
    done: set[str] = set()
    for pair in pairs:
        if pair.group in CURVE_LEG_PAIRS:
            if pair.group in done:
                continue
            done.add(pair.group)
            pattern_a, line_a, pattern_b, line_b, direction_a, direction_b = \
                CURVE_LEG_PAIRS[pair.group]
            members = grouped[pair.group]
            length_a = sum(item.a.length_mm for item in members)
            length_b = sum(item.b.length_mm for item in members)
            result.append(SeamPair(
                group=pair.group,
                a=_whole_span(pattern_a, line_a, direction_a, length_a),
                b=_whole_span(pattern_b, line_b, direction_b, length_b),
                run_length_a_mm=round(length_a, 6),
                run_length_b_mm=round(length_b, 6),
                run_length_delta_mm=round(abs(length_a - length_b), 6),
                whole_line_a=True,
                whole_line_b=True,
            ))
            continue
        if pair.group == CURVE_CENTER_BACK_GROUP:
            def shifted(span: LineSpan) -> LineSpan:
                return LineSpan(
                    span.pattern,
                    span.line + CURVE_CENTER_BACK_SHIFT,
                    span.start_ratio, span.end_ratio, span.direction,
                    span.start_mm, span.end_mm, span.length_mm,
                )
            result.append(SeamPair(
                group=pair.group,
                a=shifted(pair.a),
                b=shifted(pair.b),
                run_length_a_mm=pair.run_length_a_mm,
                run_length_b_mm=pair.run_length_b_mm,
                run_length_delta_mm=pair.run_length_delta_mm,
                whole_line_a=pair.whole_line_a,
                whole_line_b=pair.whole_line_b,
            ))
            continue
        result.append(pair)
    return result


def plan_to_dict(pairs: list[SeamPair], target_index: dict[str, int] | None = None) -> dict:
    entries = []
    for pair in pairs:
        entry = {
            "group": pair.group,
            "a": asdict(pair.a),
            "b": asdict(pair.b),
            "run_length_a_mm": pair.run_length_a_mm,
            "run_length_b_mm": pair.run_length_b_mm,
            "run_length_delta_mm": pair.run_length_delta_mm,
            "whole_line_a": pair.whole_line_a,
            "whole_line_b": pair.whole_line_b,
            # add_seamline_pair rejects a == b; darts and the waistband
            # self-seam must go through the partial tool with 0..1 ratios.
            "tool": ("add_seamline_pair"
                     if pair.whole_line_a and pair.whole_line_b
                     and pair.a.pattern != pair.b.pattern
                     else "add_seamline_pair_partial"),
        }
        if target_index:
            unknown = {pair.a.pattern, pair.b.pattern} - set(target_index)
            if unknown:
                raise SeamPlanError(f"no target index for {sorted(unknown)}")
            entry["pattern_a_index"] = target_index[pair.a.pattern]
            entry["pattern_b_index"] = target_index[pair.b.pattern]
        entries.append(entry)
    return {
        "pair_count": len(pairs),
        "target_index": target_index or {},
        "pairs": entries,
    }


def load_export(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--reference-names", action="store_true",
                        help="map 0..4 to FRONT_R/BACK_L/FRONT_L/BACK_R/WAISTBAND")
    parser.add_argument("--olga-target", action="store_true",
                        help="add imported-scene pattern indices")
    parser.add_argument("--curve-target", action="store_true",
                        help="apply merged side/inseam line indices")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    built = build_plan(
        load_export(args.export),
        REFERENCE_NAME_MAP if args.reference_names else None,
    )
    pairs = built.pairs
    if args.curve_target:
        pairs = build_curve_plan(pairs)
    problems = validate_plan(pairs)
    print(f"pairs: {len(pairs)}")
    print(f"whole line pairs: {sum(p.whole_line_a and p.whole_line_b for p in pairs)}")
    print(f"groups: {len({p.group for p in pairs})}")
    print(f"skipped small: {built.skipped_small} (max {built.max_skipped_mm} mm)")
    for problem in problems:
        print(problem)
    plan = plan_to_dict(pairs, OLGA_TARGET_INDEX if args.olga_target else None)
    plan["skipped_small"] = built.skipped_small
    plan["max_skipped_mm"] = built.max_skipped_mm
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        print(f"plan: {args.out}")
    return 1 if any("overlapping" in p or "ratio" in p or "zero" in p for p in problems) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
