"""Bounded first pattern package. Stdlib only, shared by HTTP/queue/CLO.

Not a generic API dispatcher. Coordinates are millimetres; polygons are simple
straight outlines only on creation. Outline reads expose boundary endpoints,
not curve controls. Includes bounded fabric/avatar inventories and pattern fabric
assignment, not material editing. Sewing and simulation are not enabled.
"""

import math


PATTERN_COMMANDS = [
    "list_clo_api", "describe_clo_api", "get_pattern_list", "get_pattern_geometry",
    "create_pattern", "set_pattern_name", "copy_pattern_with_offset",
    "move_pattern_relative", "delete_pattern",
    "get_fabric_list", "get_avatars",
    "get_pattern_fabric", "assign_pattern_fabric",
    "get_pattern_outline", "get_pattern_lines",
]
API_MODULES = ("pattern_api", "export_api", "fabric_api", "import_api", "utility_api")
ERROR_CODES = ("api_unavailable", "stale_pattern", "scene_change_unverified", "invalid_parameters",
               "inventory_limit", "inventory_changed", "invalid_native_result", "stale_fabric")
MAX_PATTERNS = 256
MAX_FABRICS = 256
MAX_AVATARS = 64
MAX_COORDINATE = 100000.0
MAX_OUTLINE_POINTS = 512
MAX_LINES = 512
MAX_LINE_JSON_BYTES = 65536


class CommandError(ValueError):
    """A fixed public error code, never an API exception or private path."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def number(value, bound=MAX_COORDINATE):
    return (type(value) in (int, float) and math.isfinite(value)
            and abs(value) <= bound)


def name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    return all(ord(char) >= 32 and not 0xD800 <= ord(char) <= 0xDFFF for char in value)


def index(value):
    return type(value) is int and 0 <= value < MAX_PATTERNS


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, c):
    return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))


def _intersects(a, b, c, d):
    ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > 0 > ab_d or ab_d > 0 > ab_c)
            and (cd_a > 0 > cd_b or cd_b > 0 > cd_a)):
        return True
    return any(cross == 0 and _on_segment(p, q, r) for cross, p, q, r in (
        (ab_c, a, b, c), (ab_d, a, b, d), (cd_a, c, d, a), (cd_b, c, d, b)))


def polygon(points):
    if (not isinstance(points, list) or not 3 <= len(points) <= 64
            or any(not isinstance(p, list) or len(p) != 2 or not all(number(v) for v in p)
                   for p in points)):
        return False
    if len({tuple(p) for p in points}) != len(points):
        return False
    if abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(points, points[1:] + points[:1]))) < 0.02:
        return False
    n = len(points)
    for i in range(n):
        # Reject adjacent collinear edges too: they may overlap/backtrack.
        if abs(_cross(points[i - 1], points[i], points[(i + 1) % n])) < 1e-8:
            return False
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if _intersects(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]):
                return False
    return True


def validate_params(command, params):
    """Reject extra keys, bool-as-int, non-finite numbers and oversized work."""
    if not isinstance(params, dict):
        raise CommandError("invalid_parameters")
    fields = {
        "list_clo_api": set(), "describe_clo_api": {"module", "functions"},
        "get_pattern_list": set(), "get_pattern_geometry": {"pattern_index"},
        "create_pattern": {"points", "name"},
        "set_pattern_name": {"pattern_index", "expected_name", "name"},
        "copy_pattern_with_offset": {"pattern_index", "expected_name", "name", "dx", "dy"},
        "move_pattern_relative": {"pattern_index", "expected_name", "dx", "dy"},
        "delete_pattern": {"pattern_index", "expected_name"},
        "get_fabric_list": set(), "get_avatars": set(),
        "get_pattern_fabric": {"pattern_index", "expected_name"},
        "get_pattern_outline": {"pattern_index", "expected_name"},
        "get_pattern_lines": {"pattern_index", "expected_name"},
        "assign_pattern_fabric": {"pattern_index", "expected_name", "fabric_index",
                                  "expected_fabric_name", "expected_current_fabric_index"},
    }
    valid = command in fields and set(params) == fields[command]
    if valid:
        for key, value in params.items():
            if key in ("pattern_index", "fabric_index", "expected_current_fabric_index"):
                valid = index(value)
            elif key == "expected_fabric_name":
                valid = inventory_name(value)
            elif key in ("name", "expected_name"):
                valid = name(value)
            elif key in ("dx", "dy"):
                valid = number(value)
            elif key == "points":
                valid = polygon(value)
            elif key == "module":
                valid = value in API_MODULES
            elif key == "functions":
                valid = (isinstance(value, list) and 1 <= len(value) <= 16
                         and all(isinstance(v, str) and 1 <= len(v) <= 128
                                 and v.isascii() and v.isidentifier() and not v.startswith("_")
                                 for v in value))
            if not valid:
                break
    if not valid:
        raise CommandError("invalid_parameters")
    return params


def json_value(value, depth=0):
    """A small JSON tree; explicitly disallow non-finite/bool numeric tricks."""
    if depth > 6:
        return False
    if value is None or type(value) is bool:
        return True
    if type(value) in (int, float):
        return number(value, 1e16)
    if isinstance(value, str):
        return len(value) <= 16384 and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)
    if isinstance(value, list):
        return len(value) <= 512 and all(json_value(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return (len(value) <= 512 and all(isinstance(k, str) and len(k) <= 128
                and json_value(v, depth + 1) for k, v in value.items()))
    return False


def geometry(value):
    return (isinstance(value, dict)
            and set(value) == {"index", "name", "position_mm", "area_mm2", "bounding_box"}
            and index(value["index"]) and name(value["name"])
            and isinstance(value["position_mm"], list) and len(value["position_mm"]) == 2
            and all(number(v) for v in value["position_mm"])
            and number(value["area_mm2"], 1e16) and value["area_mm2"] >= 0
             and value["bounding_box"] is not None and json_value(value["bounding_box"]))


def inventory_name(value):
    """Preserve empty/duplicate names; neither is a durable object identifier."""
    return (type(value) is str and len(value) <= 256
            and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in value))


def outline_points(value):
    """Native boundary endpoints, not a polygon validator or curve tessellation."""
    return (type(value) is list and 1 <= len(value) <= MAX_OUTLINE_POINTS
            and all(type(p) is list and len(p) == 2 and all(number(v) for v in p)
                    for p in value))


def line_token(value):
    """Lowercase native token; location list is documented as non-exhaustive."""
    return (type(value) is str and 1 <= len(value) <= 32
            and all("a" <= c <= "z" or c == "-" for c in value))


def point2(value):
    return (isinstance(value, dict) and set(value) == {"x", "y"}
            and all(number(v) for v in value.values()))


def bounding_box(value):
    return (isinstance(value, dict)
            and set(value) == {"min_x", "min_y", "max_x", "max_y", "width", "height"}
            and all(number(v) for v in value.values())
            and value["max_x"] >= value["min_x"] and value["max_y"] >= value["min_y"]
            and value["width"] >= 0 and value["height"] >= 0)


def line_info(value):
    """One documented line record; no inferred arc/chord or closure semantics."""
    return (isinstance(value, dict)
            and set(value) == {"line_index", "length_mm", "orientation", "location",
                               "start_mm", "end_mm", "mid_mm", "mid_norm"}
            and type(value["line_index"]) is int and 0 <= value["line_index"] < MAX_LINES
            and number(value["length_mm"]) and value["length_mm"] >= 0
            and value["orientation"] in ("horizontal", "vertical", "diagonal")
            and line_token(value["location"])
            and point2(value["start_mm"]) and point2(value["end_mm"]) and point2(value["mid_mm"])
            and point2(value["mid_norm"])
            and all(0 <= v <= 1 for v in value["mid_norm"].values()))


def inventory_result(value, kind, maximum):
    count, items = value.get(kind + "_count"), value.get(kind + "s")
    return (type(count) is int and 0 <= count <= maximum and type(items) is list
            and count == len(items)
            and all(type(item) is dict and set(item) == {"index", "name"}
                    and type(item["index"]) is int and item["index"] == i
                    and inventory_name(item["name"]) for i, item in enumerate(items)))


def validate_result(command, result):
    """Command-specific shape checks before external queue caches a result."""
    valid = isinstance(result, dict) and json_value(result)
    if not valid:
        raise CommandError("invalid_result")
    keys = set(result)
    if command == "list_clo_api":
        valid = (keys == {"modules"} and isinstance(result["modules"], dict)
                 and set(result["modules"]) == set(API_MODULES)
                 and all(isinstance(v, list) and all(isinstance(n, str) for n in v)
                         for v in result["modules"].values()))
    elif command == "describe_clo_api":
        valid = (keys == {"module", "functions"} and result["module"] in API_MODULES
                 and isinstance(result["functions"], dict)
                 and all(isinstance(v, dict) and set(v) == {"available", "doc"}
                         and type(v["available"]) is bool and isinstance(v["doc"], str)
                         for v in result["functions"].values()))
    elif command == "get_pattern_list":
        valid = (keys == {"pattern_count", "patterns"} and type(result["pattern_count"]) is int
                 and isinstance(result["patterns"], list)
                 and result["pattern_count"] == len(result["patterns"]) <= MAX_PATTERNS
                 and all(isinstance(v, dict) and set(v) == {"index", "name"}
                         and v["index"] == i and type(v["index"]) is int and name(v["name"])
                         for i, v in enumerate(result["patterns"])))
    elif command == "get_pattern_geometry":
        valid = keys == {"pattern"} and geometry(result["pattern"])
    elif command == "get_pattern_outline":
        valid = (keys == {"pattern_index", "pattern_name", "point_count", "points_mm",
                          "coordinate_frame", "units"}
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and outline_points(result["points_mm"])
                 and type(result["point_count"]) is int
                 and result["point_count"] == len(result["points_mm"])
                 and result["coordinate_frame"] == "bbox_top_left_y_down"
                 and result["units"] == "mm")
    elif command == "get_pattern_lines":
        lines = result.get("lines")
        valid = (keys == {"pattern_index", "pattern_name", "line_count", "bounding_box_mm",
                          "lines", "coordinate_frame", "units"}
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and type(result["line_count"]) is int
                 and 1 <= result["line_count"] <= MAX_LINES
                 and isinstance(lines, list) and result["line_count"] == len(lines)
                 and all(line_info(v) for v in lines)
                 and len({v["line_index"] for v in lines}) == len(lines)
                 and bounding_box(result["bounding_box_mm"])
                 and result["coordinate_frame"] == "api_2d_mm"
                 and result["units"] == "mm")
    elif command == "get_fabric_list":
        valid = (keys == {"fabric_count", "fabrics"}
                 and inventory_result(result, "fabric", MAX_FABRICS))
    elif command == "get_avatars":
        valid = keys == {"avatar_count", "avatars"} and inventory_result(result, "avatar", MAX_AVATARS)
    elif command in ("get_pattern_fabric", "assign_pattern_fabric"):
        required = {"pattern_index", "pattern_name", "fabric_index", "fabric_name"}
        if command == "assign_pattern_fabric":
            required |= {"verified", "previous_fabric_index", "executor_ms"}
        valid = (keys == required and index(result["pattern_index"])
                 and name(result["pattern_name"]) and index(result["fabric_index"])
                 and inventory_name(result["fabric_name"]))
        if valid and command == "assign_pattern_fabric":
            valid = (result["verified"] is True and index(result["previous_fabric_index"])
                     and number(result["executor_ms"], 1e12) and result["executor_ms"] >= 0)
    elif command in ("create_pattern", "copy_pattern_with_offset", "set_pattern_name", "move_pattern_relative"):
        valid = (keys == {"verified", "pattern_count", "pattern", "executor_ms"}
                 and result["verified"] is True and geometry(result["pattern"])
                 and type(result["pattern_count"]) is int
                 and 0 < result["pattern_count"] <= MAX_PATTERNS
                 and result["pattern"]["index"] < result["pattern_count"]
                 and number(result["executor_ms"], 1e12) and result["executor_ms"] >= 0)
    elif command == "delete_pattern":
        valid = (keys == {"verified", "pattern_count", "deleted_name", "executor_ms"}
                 and result["verified"] is True and name(result["deleted_name"])
                 and type(result["pattern_count"]) is int and 0 <= result["pattern_count"] < MAX_PATTERNS
                 and number(result["executor_ms"], 1e12) and result["executor_ms"] >= 0)
    else:
        valid = False
    if not valid:
        raise CommandError("invalid_result")
    return result
