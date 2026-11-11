"""Small 2D helpers for the trouser prototype; no third-party dependency."""

from __future__ import annotations

import math

Point = tuple[float, float]


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def mul(a: Point, k: float) -> Point:
    return a[0] * k, a[1] * k


def dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def unit(a: Point, b: Point) -> Point:
    length = dist(a, b)
    if length <= 1e-12:
        raise ValueError("zero-length direction")
    return (b[0] - a[0]) / length, (b[1] - a[1]) / length


def lerp(a: Point, b: Point, t: float) -> Point:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def quadratic(a: Point, control: Point, b: Point, samples: int = 6) -> list[Point]:
    """Inclusive quadratic Bezier samples without the start point."""
    if samples < 2:
        raise ValueError("samples must be >= 2")
    result = []
    for i in range(1, samples + 1):
        t = i / samples
        mt = 1 - t
        result.append((
            mt * mt * a[0] + 2 * mt * t * control[0] + t * t * b[0],
            mt * mt * a[1] + 2 * mt * t * control[1] + t * t * b[1],
        ))
    return result


def line_intersection(a: Point, b: Point, c: Point, d: Point) -> Point:
    """Intersection of infinite lines AB and CD; raises when parallel."""
    r = sub(b, a)
    s = sub(d, c)
    denominator = r[0] * s[1] - r[1] * s[0]
    if abs(denominator) <= 1e-12:
        raise ValueError("parallel lines")
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / denominator
    return a[0] + r[0] * t, a[1] + r[1] * t


def horizontal_intersection(a: Point, b: Point, y: float) -> Point:
    """Intersection of line AB with the horizontal y, clamped by construction."""
    if abs(b[1] - a[1]) <= 1e-12:
        raise ValueError("horizontal line")
    t = (y - a[1]) / (b[1] - a[1])
    return a[0] + (b[0] - a[0]) * t, y


def polygon_area(points: list[Point]) -> float:
    """Signed shoelace area; positive for the prototype's clockwise screen frame."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    for a, b in zip(points, points[1:] + points[:1]):
        total += a[0] * b[1] - b[0] * a[1]
    return total / 2


def polygon_bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(points: list[Point]) -> Point:
    return (sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points))


def mirror_x(points: list[Point], axis_x: float = 0.0) -> list[Point]:
    return [(2 * axis_x - x, y) for x, y in points]


def translate(points: list[Point], dx: float, dy: float) -> list[Point]:
    return [(x + dx, y + dy) for x, y in points]


def segment_normal(a: Point, b: Point) -> Point:
    """Unit normal (left side) of segment AB."""
    ux, uy = unit(a, b)
    return -uy, ux


def is_simple_polygon(points: list[Point]) -> bool:
    """O(n^2) strict segment check for short prototype polygons."""
    n = len(points)
    if n < 3:
        return False

    def cross(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a: Point, b: Point, c: Point) -> bool:
        return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

    def intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
        ab_c, ab_d = cross(a, b, c), cross(a, b, d)
        cd_a, cd_b = cross(c, d, a), cross(c, d, b)
        if (ab_c > 0 > ab_d or ab_d > 0 > ab_c) and (cd_a > 0 > cd_b or cd_b > 0 > cd_a):
            return True
        return any(value == 0 and on_segment(p, q, r) for value, p, q, r in (
            (ab_c, a, b, c), (ab_d, a, b, d), (cd_a, c, d, a), (cd_b, c, d, b)))

    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or j == (i + 1) % n or (j + 1) % n == i:
                continue
            c, d = points[j], points[(j + 1) % n]
            if intersects(a, b, c, d):
                return False
    return True
