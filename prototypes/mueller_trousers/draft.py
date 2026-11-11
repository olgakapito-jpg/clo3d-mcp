"""Parametric women's classic trouser block: Müller & Sohn core, prototype.

This is a drafting prototype, not a certified pattern system. It implements the
core proportion formulas from the published method and approximates curves with
short polylines. The back waist/center construction is simplified for the first
CLO pipeline; see README for the differences.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import (
    Point, add, dist, horizontal_intersection, lerp, mul, polygon_area,
    polygon_bbox, segment_normal, sub, translate, unit, mirror_x, quadratic,
)
from .measurements import TrouserMeasurements

@dataclass(frozen=True)
class Notch:
    point: Point
    normal: Point
    label: str


@dataclass(frozen=True)
class Grainline:
    start: Point
    end: Point


@dataclass(frozen=True)
class Piece:
    name: str
    label: str
    points: tuple[Point, ...]
    notches: tuple[Notch, ...]
    grainline: Grainline
    edges: dict[str, tuple[int, ...]]
    cut_count: int = 1

    @property
    def area_cm2(self) -> float:
        return abs(polygon_area(list(self.points)))

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return polygon_bbox(list(self.points))


@dataclass(frozen=True)
class Seam:
    name: str
    a: str
    a_edge: str
    b: str
    b_edge: str
    note: str = ""


@dataclass(frozen=True)
class PatternSet:
    measurements: TrouserMeasurements
    pieces: tuple[Piece, ...]
    seam_plan: tuple[Seam, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_name(self, name: str) -> Piece:
        return next(piece for piece in self.pieces if piece.name == name)


class _Builder:
    def __init__(self):
        self.points: list[Point] = []

    def add(self, point: Point) -> int:
        if not self.points or dist(self.points[-1], point) > 1e-9:
            self.points.append(point)
        return len(self.points) - 1

    def curve(self, a: Point, control: Point, b: Point, samples: int = 6) -> list[int]:
        indices = []
        for point in quadratic(a, control, b, samples):
            indices.append(self.add(point))
        return indices


def _dart_waist(builder: _Builder, start: Point, end: Point, half: float,
                length: float, position: float = 0.5) -> list[int]:
    """Append a V-shaped waist dart between two points and return its indices."""
    indices = [builder.add(start)]
    direction = unit(start, end)
    middle = lerp(start, end, position)
    left = sub(middle, mul(direction, half))
    right = add(middle, mul(direction, half))
    apex = (middle[0], middle[1] + length)
    indices += [builder.add(left), builder.add(apex), builder.add(right), builder.add(end)]
    return indices


def _notch(point: Point, a: Point, b: Point, label: str) -> Notch:
    return Notch(point=point, normal=segment_normal(a, b), label=label)


def _front(m: TrouserMeasurements) -> Piece:
    y_hip, y_seat, y_knee, y_hem = m.y_hip, m.y_seat, m.y_knee, m.y_hem
    x_crease = (m.front_hip_width + m.step_width) / 2
    A7 = (0.0, y_hip)
    A8 = (m.front_hip_width, y_hip)
    A9 = (m.front_hip_width + m.step_width, y_hip)
    A10 = (A8[0], 0.0)
    A14 = (x_crease, 0.0)
    A15 = (x_crease - m.hem_front_half, y_hem)
    A16 = (x_crease + m.hem_front_half, y_hem)
    A15a = (A15[0], y_hem - 4.0)
    A16a = (A16[0], y_hem - 4.0)
    A18 = (x_crease - m.knee_front_half, y_knee)
    A19 = (x_crease + m.knee_front_half, y_knee)
    A20 = (A10[0] - 1.0, 0.0)
    A21 = (A20[0] - m.front_waist_width, 0.0)
    A22 = (A21[0], -m.hip_drop)
    a = (A14[0] + 4.0, 0.0)
    a1 = (a[0], 0.0)
    a3 = horizontal_intersection(A15a, A7, y_seat)
    A17 = horizontal_intersection(A16a, A9, y_seat)
    a5 = (A8[0] + 0.5, y_seat)

    builder = _Builder()
    edges: dict[str, list[int]] = {}
    waist = _dart_waist(builder, A22, A14, m.front_dart / 2, 9.5)
    edges["waist"] = waist + [builder.add(a1), builder.add(A20)]

    center = [builder.add(A20)]
    center += builder.curve(A20, (A20[0] + 1.2, y_seat * 0.65), a5, 5)
    center.append(builder.add(A17))
    edges["center"] = center

    inseam = [builder.add(A17)]
    inseam += builder.curve(A17, (A19[0] + 1.0, (A17[1] + A19[1]) / 2), A19, 4)
    inseam += [builder.add(A16a), builder.add(A16)]
    edges["inseam"] = inseam

    hem = [builder.add(A16), builder.add(A15)]
    edges["hem"] = hem

    side = [builder.add(A15), builder.add(A15a), builder.add(A18)]
    side += builder.curve(A18, (a3[0] - 1.2, (a3[1] + A18[1]) / 2), a3, 4)
    side += [builder.add(A7)]
    edges["side"] = side + [0]  # closing segment A7 -> A22

    points = list(builder.points)
    if dist(points[-1], points[0]) < 1e-9:
        points.pop()
    notches = (
        _notch(a3, A18, A7, "side_hip"),
        _notch(A18, A15a, A18, "side_knee"),
        _notch(A15a, A15, A15a, "side_hem"),
        _notch(A19, A17, A19, "inseam_knee"),
        _notch(A16a, A19, A16a, "inseam_hem"),
        _notch(a5, A20, a5, "center_seat"),
        _notch(A22, A7, A22, "waist_side"),
    )
    return Piece(
        name="FRONT_L",
        label="Front left",
        points=tuple(points),
        notches=notches,
        grainline=Grainline((x_crease, y_hip + 8.0), (x_crease, y_hem - 8.0)),
        edges={key: tuple(value) for key, value in edges.items()},
    )


def _back(m: TrouserMeasurements) -> Piece:
    y_hip, y_seat, y_knee, y_hem = m.y_hip, m.y_seat, m.y_knee, m.y_hem
    x_crease = (m.front_hip_width + m.step_width) / 2
    A11 = (x_crease, y_hip)
    A23 = (A11[0] + 1.5, y_hip)
    A24 = (A23[0] + m.back_hip_width / 4, y_hip)
    A27 = (0.0 - m.back_side_extra, y_hip)
    A35 = (A24[0], -m.hip_drop)
    A36 = (A35[0] - m.back_waist_width, -m.hip_drop)
    A18 = (x_crease - m.knee_front_half, y_knee)
    A19 = (x_crease + m.knee_front_half, y_knee)
    A15 = (x_crease - m.hem_front_half, y_hem)
    A16 = (x_crease + m.hem_front_half, y_hem)
    A15a = (A15[0], y_hem - 4.0)
    A16a = (A16[0], y_hem - 4.0)
    A30 = (A18[0] - m.back_side_extra, y_knee)
    A31a = (A15a[0] - m.back_side_extra, y_hem - 4.0)
    A31 = (A15[0] - m.back_side_extra, y_hem)
    A32 = (A16[0] + m.back_side_extra, y_hem)
    A32a = (A16a[0] + m.back_side_extra, y_hem - 4.0)
    A29 = (A19[0] + m.back_side_extra, y_knee)
    A17 = horizontal_intersection(A16a, (m.front_hip_width + m.step_width, y_hip), y_seat)

    builder = _Builder()
    edges: dict[str, list[int]] = {}
    waist = _dart_waist(builder, A35, A36, m.back_dart / 2, 14.0, position=0.68)
    edges["waist"] = waist

    side = [builder.add(A36), builder.add(A27)]
    side += builder.curve(A27, (A27[0] - 0.5, (A27[1] + A30[1]) / 2), A30, 4)
    side += [builder.add(A31a), builder.add(A31)]
    edges["side"] = side

    hem = [builder.add(A31), builder.add(A32)]
    edges["hem"] = hem

    inseam = [builder.add(A32), builder.add(A32a), builder.add(A29)]
    inseam += builder.curve(A29, (A29[0] + 0.8, (A29[1] + A17[1]) / 2), A17, 4)
    edges["inseam"] = inseam

    center = [builder.add(A17)]
    center += builder.curve(A17, (A24[0] + 1.0, y_seat - 2.0), A24, 5)
    center += builder.curve(A24, (A35[0], 8.0), A35, 6)
    edges["center"] = center

    points = list(builder.points)
    if dist(points[-1], points[0]) < 1e-9:
        removed = len(builder.points) - 1
        points.pop()
        for key, indices in edges.items():
            if removed in indices:
                edges[key] = [index for index in indices if index != removed] + [0]
    notches = (
        _notch(A27, A36, A30, "side_hip"),
        _notch(A30, A27, A31a, "side_knee"),
        _notch(A31a, A30, A31, "side_hem"),
        _notch(A29, A32a, A17, "inseam_knee"),
        _notch(A32a, A32, A29, "inseam_hem"),
        _notch(A24, A17, A35, "center_seat"),
        _notch(A36, A35, A27, "waist_side"),
    )
    return Piece(
        name="BACK_L",
        label="Back left",
        points=tuple(points),
        notches=notches,
        grainline=Grainline(
            ((A27[0] + A24[0]) / 2, y_hip + 8.0),
            ((A27[0] + A24[0]) / 2, y_hem - 8.0),
        ),
        edges={key: tuple(value) for key, value in edges.items()},
    )


def _mirror_piece(piece: Piece, axis_x: float, dx: float, name: str, label: str) -> Piece:
    points = translate(mirror_x(list(piece.points), axis_x), dx, 0.0)
    notches = tuple(
        Notch(point=(2 * axis_x - item.point[0] + dx, item.point[1]),
              normal=(-item.normal[0], item.normal[1]), label=item.label)
        for item in piece.notches
    )
    grain = Grainline(
        (2 * axis_x - piece.grainline.start[0] + dx, piece.grainline.start[1]),
        (2 * axis_x - piece.grainline.end[0] + dx, piece.grainline.end[1]),
    )
    return Piece(name=name, label=label, points=tuple(points), notches=notches,
                 grainline=grain, edges=dict(piece.edges), cut_count=piece.cut_count)


def _waistband(m: TrouserMeasurements, x: float, y: float) -> Piece:
    length = 2 * m.waist_half + m.waist_ease + m.waistband_overlap
    height = m.waistband_height
    points = ((x, y), (x + length, y), (x + length, y + height), (x, y + height))
    notches = (
        _notch((x, y), (x, y + height), (x + length, y), "center_back"),
        _notch((x + length / 2, y), (x, y), (x + length, y), "center_front"),
        _notch((x + length, y), (x + length, y + height), (x, y), "side"),
    )
    return Piece(
        name="WAISTBAND",
        label="Waistband",
        points=points,
        notches=notches,
        grainline=Grainline((x + length / 2, y + 0.5), (x + length / 2, y + height - 0.5)),
        edges={"waist": (0, 1, 2, 3), "hem": (3, 2, 1, 0)},
    )


def draft_trousers(m: TrouserMeasurements = TrouserMeasurements()) -> PatternSet:
    front = _front(m)
    back = _back(m)
    # Keep the 2D layout close to the origin so CLO opens on the pieces rather
    # than a far-away empty grid. Arrangement points, not 2D coordinates,
    # decide the 3D body side.
    # Orientation matches the manually sewn reference: front-right and
    # back-left keep the drafted orientation; front-left and back-right are
    # mirrored. This keeps reference seam line indices valid.
    front_l = _mirror_piece(front, 15.0, -250.0, "FRONT_L", "Front left")
    back_l = _translate_piece(back, -100.0, 0.0)
    front_r = _translate_piece(front, 50.0, 0.0)
    front_r = Piece(front_r.name.replace("FRONT_L", "FRONT_R"), "Front right",
                    front_r.points, front_r.notches, front_r.grainline,
                    dict(front_r.edges), front_r.cut_count)
    back_r = _mirror_piece(back, 15.0, 169.5, "BACK_R", "Back right")
    waistband = _waistband(m, -220.0, -80.0)
    pieces = (front_l, back_l, front_r, back_r, waistband)
    seams = (
        Seam("left_side", "FRONT_L", "side", "BACK_L", "side", "whole-line candidate"),
        Seam("left_inseam", "FRONT_L", "inseam", "BACK_L", "inseam", "whole-line candidate"),
        Seam("right_side", "FRONT_R", "side", "BACK_R", "side", "whole-line candidate"),
        Seam("right_inseam", "FRONT_R", "inseam", "BACK_R", "inseam", "whole-line candidate"),
        Seam("center_front", "FRONT_L", "center", "FRONT_R", "center", "front fly/crotch seam"),
        Seam("center_back", "BACK_L", "center", "BACK_R", "center", "back crotch seam"),
        Seam("waistband_front", "WAISTBAND", "waist", "FRONT_L", "waist", "waistband; split by CF/CB"),
        Seam("waistband_back", "WAISTBAND", "waist", "BACK_L", "waist", "waistband; split by CF/CB"),
    )
    notes = (
        "Prototype only: core Müller & Sohn proportions, curves approximated by polylines.",
        "Back waist/center and waistband are simplified; no fly, pockets, belt loops or seam allowance.",
        "All coordinates are sewing lines in cm before DXF export; export converts to mm.",
        "Four leg panels are generated; front-left/back-right are mirrored to match the reference seam line order.",
    )
    return PatternSet(m, pieces, seams, notes)


def _translate_piece(piece: Piece, dx: float, dy: float) -> Piece:
    return Piece(
        name=piece.name,
        label=piece.label,
        points=tuple(translate(list(piece.points), dx, dy)),
        notches=tuple(Notch((item.point[0] + dx, item.point[1] + dy),
                            item.normal, item.label) for item in piece.notches),
        grainline=Grainline((piece.grainline.start[0] + dx, piece.grainline.start[1] + dy),
                            (piece.grainline.end[0] + dx, piece.grainline.end[1] + dy)),
        edges=dict(piece.edges),
        cut_count=piece.cut_count,
    )
