"""Generate CLO pattern JSON (format 1.4) from the prototype.

The schema is taken from a real CLO 2026.1 ExportPatternJSON sample:
PatternList[].ShapeInfo.LineList carries stable line IDs, and
SeamLinePairGroupList[].PairList references those IDs with LengthParam ratios.
ImportPatternJSON is destructive and replaces the scene, so this writer only
creates a file; the caller decides when to import it.
"""

from __future__ import annotations

import json
from pathlib import Path

from .draft import PatternSet, Piece
from .geometry import dist

MM = 10.0
Y_TOP_CM = 120.0  # keep exported CLO JSON above the zero line


class _Ids:
    def __init__(self):
        self.n = 0

    def next(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n:05d}"


def _mm(point):
    # Prototype frame is y-down cm; CLO pattern JSON is y-up mm. The offset
    # lifts every piece above y=0 in the 2D pattern window.
    return {"x": round(point[0] * MM, 6),
            "y": round((Y_TOP_CM - point[1]) * MM, 6)}


def _segments(piece: Piece, line_ids: dict[tuple[int, int], str]):
    """Outline segments with their line IDs and cm lengths."""
    points = list(piece.points)
    result = []
    for i, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
        length = dist(a, b)
        if length <= 1e-9:
            continue
        result.append({"i": i, "a": a, "b": b, "length": length,
                       "line_id": line_ids[(i, (i + 1) % len(points))]})
    return result


def _edge_segments(piece: Piece, edge: str, segments, line_ids):
    indices = piece.edges[edge]
    by_index = {item["i"]: item for item in segments}
    result = []
    for a_index, b_index in zip(indices, indices[1:]):
        key = (a_index, b_index)
        if key not in line_ids:
            key = (b_index, a_index)
        item = by_index.get(a_index)
        if item is None or key not in line_ids:
            continue
        result.append({**item, "line_id": line_ids[key]})
    return result


def _edge_points(piece: Piece, edge: str):
    return [piece.points[i] for i in piece.edges[edge]]


def _pair_edge(a_piece: Piece, a_edge: str, b_piece: Piece, b_edge: str,
               a_segments, b_segments):
    """Map two multi-segment edges by cumulative length; one pair per interval."""
    a_pts, b_pts = _edge_points(a_piece, a_edge), _edge_points(b_piece, b_edge)
    a_len = sum(dist(x, y) for x, y in zip(a_pts, a_pts[1:]))
    b_len = sum(dist(x, y) for x, y in zip(b_pts, b_pts[1:]))
    if a_len <= 1e-9 or b_len <= 1e-9:
        return []

    def cumulative(segments):
        total = sum(s["length"] for s in segments)
        out, acc = [0.0], 0.0
        for segment in segments:
            acc += segment["length"] / total
            out.append(acc)
        out[-1] = 1.0
        return out

    a_cum, b_cum = cumulative(a_segments), cumulative(b_segments)
    cuts = sorted({0.0, 1.0, *a_cum, *b_cum})
    aligned = (dist(a_pts[0], b_pts[0]) + dist(a_pts[-1], b_pts[-1])
               <= dist(a_pts[0], b_pts[-1]) + dist(a_pts[-1], b_pts[0]))
    pairs = []
    for start, end in zip(cuts, cuts[1:]):
        if end - start <= 1e-9:
            continue
        a_i = next(i for i in range(len(a_segments)) if a_cum[i] <= start < a_cum[i + 1])
        b_i = next(i for i in range(len(b_segments)) if b_cum[i] <= start < b_cum[i + 1])
        a0 = (start - a_cum[a_i]) / (a_cum[a_i + 1] - a_cum[a_i])
        a1 = (end - a_cum[a_i]) / (a_cum[a_i + 1] - a_cum[a_i])
        b0 = (start - b_cum[b_i]) / (b_cum[b_i + 1] - b_cum[b_i])
        b1 = (end - b_cum[b_i]) / (b_cum[b_i + 1] - b_cum[b_i])
        if aligned:
            b_start, b_end, direction = b0, b1, True
        else:
            b_start, b_end, direction = 1 - b1, 1 - b0, False

        def clean(value: float) -> float:
            value = round(value, 8)
            return 0.0 if value == 0 else value

        pairs.append({
            "First": {
                "ShapeID": a_piece.name,
                "LengthParam": {"fStart": clean(a0), "fEnd": clean(a1)},
                "Direction": True,
                "LineID": a_segments[a_i]["line_id"],
            },
            "Second": {
                "ShapeID": b_piece.name,
                "LengthParam": {"fStart": clean(b_start), "fEnd": clean(b_end)},
                "Direction": direction,
                "LineID": b_segments[b_i]["line_id"],
            },
        })
    return pairs


def to_clo(pattern: PatternSet) -> dict:
    ids = _Ids()
    pattern_ids = {piece.name: ids.next("P") for piece in pattern.pieces}
    line_ids_by_piece: dict[str, dict[tuple[int, int], str]] = {}
    segments_by_piece: dict[str, list] = {}

    rows = []
    for piece in pattern.pieces:
        points = list(piece.points)
        point_ids = [ids.next("T") for _ in points]
        line_ids = {}
        lines = []
        for i, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
            line_id = ids.next("L")
            line_ids[(i, (i + 1) % len(points))] = line_id
            lines.append({
                "ID": line_id,
                "PointList": [
                    {"ID": point_ids[i], "PointType": "Straight", "GradingRuleID": 0,
                     "Position": _mm(a)},
                    {"ID": point_ids[(i + 1) % len(points)], "PointType": "Straight",
                     "GradingRuleID": 0, "Position": _mm(b)},
                ],
            })
        line_ids_by_piece[piece.name] = line_ids
        segments_by_piece[piece.name] = _segments(piece, line_ids)
        rows.append({
            "ID": pattern_ids[piece.name],
            "CurrentFabricUUID": "FABRIC1",
            "Name": piece.name,
            "fGrainlineAngle": 0.0,
            "strGrainlineOrientation": "One Way",
            "IsClosed": True,
            "strSuperImposeSide": "None",
            "IsHalfSymmetric": False,
            "ShapeInfo": {"IsSlashed": False, "LineList": lines},
            "InternalLineList": [],
            "ButtonHeadList": [],
            "ButtonHoleList": [],
            "NotchList": [],
            "AnnotationList": [],
            "ArrangementPointDataMap": {
                "PointName": "Arrangement Point",
                "fOffSetX": 0.5, "fOffSetY": 0.5, "fAngle": 0.0,
            },
            "OuterSeamAllowanceList": [],
            "SegmentTopStitchList": [],
        })

    by_name = {piece.name: piece for piece in pattern.pieces}
    seam_groups = []
    for index, seam in enumerate(pattern.seam_plan, 1):
        if seam.a == "WAISTBAND" or seam.b == "WAISTBAND":
            # Waistband needs a proper multi-piece chain; do not emit a partial guess.
            continue
        a_piece, b_piece = by_name[seam.a], by_name[seam.b]
        a_segments = _edge_segments(a_piece, seam.a_edge,
                                    segments_by_piece[seam.a], line_ids_by_piece[seam.a])
        b_segments = _edge_segments(b_piece, seam.b_edge,
                                    segments_by_piece[seam.b], line_ids_by_piece[seam.b])
        pairs = _pair_edge(a_piece, seam.a_edge, b_piece, seam.b_edge,
                           a_segments, b_segments)
        if not pairs:
            continue
        for pair in pairs:
            pair["First"]["ShapeID"] = pattern_ids[seam.a]
            pair["Second"]["ShapeID"] = pattern_ids[seam.b]
            # The native export sample keeps one PairList entry per seam group.
            # Emit one group per mapped line interval instead of assuming that
            # ImportPatternJSON accepts a multi-pair group.
            seam_groups.append({
                "Name": f"Sewing_{100000 + len(seam_groups) + 1}",
                "bIsTurned": False,
                "FoldData": {"iAngle": 180, "iStrength": 5},
                "PairList": [pair],
            })

    return {
        "formatVersion": 1,
        "formatMinorVersion": 4,
        "Unit": "mm",
        "generator": {"name": "trouser-draft", "organization": "clo3d_mcp",
                      "version": "1"},
        "FabricList": [{
            "FabricName": "FABRIC 1", "FabricUUID": "FABRIC1", "FabricType": "None",
            "strBaseColorHexCode": "#FFFFFF", "FabricContent": "None",
        }],
        "GradingRuleTableList": [],
        "InstanceDataList": [
            {"OriginPatternID": pattern_ids[piece.name], "InstancePatternIDArray": []}
            for piece in pattern.pieces
        ],
        "POMList": [],
        "PatternList": rows,
        "SeamLinePairGroupList": seam_groups,
        "SymmetricDataList": [
            {"SymmetricPatternID": "None", "OriginPatternID": pattern_ids[piece.name]}
            for piece in pattern.pieces
        ],
        "TopStitchStyleList": [],
    }


def write_clo_json(pattern: PatternSet, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_clo(pattern), ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8", newline="\n")
    return target
