"""Minimal DXF R12 writer for the prototype (closed polylines + markers).

This is a standard DXF with one closed POLYLINE per piece. It is not an
AAMA/ASTM file: CLO can import it as Standard DXF, but native notch/grain
semantics are not guaranteed. The JSON sidecar keeps the full prototype data.
"""

from __future__ import annotations

import math
from pathlib import Path

from .draft import PatternSet, Piece
from .geometry import unit

SCALE = 10.0  # cm -> mm
Y_TOP_CM = 120.0  # keep exported DXF above the zero line
NOTCH_HALF_MM = 5.0
ARROW_MM = 6.0


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") if value else "0"


def _xy(point, dx=0.0, dy=0.0):
    # DXF is y-up; the drafting frame is y-down (waist 0, hem positive).
    # Offset lifts the layout above y=0 in the 2D window.
    return _num((point[0] + dx) * SCALE), _num((Y_TOP_CM - (point[1] + dy)) * SCALE)


def _line(layer: str, a, b) -> list[str]:
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return ["0", "LINE", "8", layer,
            "10", ax, "20", ay, "30", "0",
            "11", bx, "21", by, "31", "0"]


def _text(layer: str, point, value: str, height_mm: float = 8.0) -> list[str]:
    x, y = _xy(point)
    return ["0", "TEXT", "8", layer, "10", x, "20", y, "30", "0",
            "40", _num(height_mm), "1", value]


def _polyline(piece: Piece) -> list[str]:
    out = ["0", "POLYLINE", "8", piece.name, "66", "1", "70", "1",
           "10", "0", "20", "0", "30", "0"]
    for point in piece.points:
        x, y = _xy(point)
        out += ["0", "VERTEX", "8", piece.name, "10", x, "20", y, "30", "0"]
    out += ["0", "SEQEND", "8", piece.name]
    return out


def _notch_lines(piece: Piece) -> list[str]:
    out = []
    for notch in piece.notches:
        nx, ny = notch.normal
        length = math.hypot(nx, ny)
        if length <= 1e-9:
            continue
        nx, ny = nx / length * (NOTCH_HALF_MM / SCALE), ny / length * (NOTCH_HALF_MM / SCALE)
        out += _line("NOTCH", (notch.point[0] - nx, notch.point[1] - ny),
                     (notch.point[0] + nx, notch.point[1] + ny))
    return out


def _grainline(piece: Piece) -> list[str]:
    start, end = piece.grainline.start, piece.grainline.end
    out = _line("GRAIN", start, end)
    ux, uy = unit(start, end)
    for sign in (-1, 1):
        angle = math.radians(150 * sign)
        ax = ux * math.cos(angle) - uy * math.sin(angle)
        ay = ux * math.sin(angle) + uy * math.cos(angle)
        tip = (end[0] + ax * (ARROW_MM / SCALE), end[1] + ay * (ARROW_MM / SCALE))
        out += _line("GRAIN", end, tip)
    return out


def write_dxf(pattern: PatternSet, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    layers = sorted({piece.name for piece in pattern.pieces} | {"NOTCH", "GRAIN", "TEXT"})
    lines = [
        "0", "SECTION", "2", "HEADER",
        "9", "$ACADVER", "1", "AC1009",
        "9", "$INSUNITS", "70", "4",
        "0", "ENDSEC",
        "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LAYER", "70", str(len(layers)),
    ]
    for index, name in enumerate(layers):
        lines += ["0", "LAYER", "2", name, "70", "0", "62", str((index % 6) + 1),
                  "6", "CONTINUOUS"]
    lines += ["0", "ENDTAB", "0", "ENDSEC",
              "0", "SECTION", "2", "ENTITIES"]
    for piece in pattern.pieces:
        lines += _polyline(piece)
        lines += _notch_lines(piece)
        lines += _grainline(piece)
        x0, y0, _, _ = piece.bbox
        lines += _text("TEXT", (x0 + 1.0, y0 + 2.0), piece.name)
    lines += _text("TEXT", (100.0, -30.0),
                   "MUeller&Sohn trousers size %d - prototype" % pattern.measurements.size,
                   height_mm=10.0)
    lines += ["0", "ENDSEC", "0", "EOF"]
    target.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return target


def write_json(pattern: PatternSet, path: str | Path) -> Path:
    import json

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "mueller_trousers_prototype_v1",
        "units": "cm",
        "method": "Mueller & Sohn core proportions; prototype curves and back waist simplified",
        "measurements": pattern.measurements.__dict__,
        "pieces": [
            {
                "name": piece.name,
                "label": piece.label,
                "cut_count": piece.cut_count,
                "area_cm2": round(piece.area_cm2, 3),
                "points_cm": [[round(x, 4), round(y, 4)] for x, y in piece.points],
                "edges": {key: list(value) for key, value in piece.edges.items()},
                "notches": [
                    {"point_cm": [round(n.point[0], 4), round(n.point[1], 4)],
                     "normal": [round(n.normal[0], 6), round(n.normal[1], 6)],
                     "label": n.label}
                    for n in piece.notches
                ],
                "grainline_cm": [[round(x, 4), round(y, 4)]
                                 for x, y in (piece.grainline.start, piece.grainline.end)],
            }
            for piece in pattern.pieces
        ],
        "seam_plan": [
            {"name": seam.name, "a": seam.a, "a_edge": seam.a_edge,
             "b": seam.b, "b_edge": seam.b_edge, "note": seam.note}
            for seam in pattern.seam_plan
        ],
        "notes": list(pattern.notes),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    return target
