"""Bounded first pattern package. Stdlib only, shared by HTTP/queue/CLO.

Not a generic API dispatcher. Coordinates are millimetres; polygons are simple
straight outlines only on creation. Outline reads expose boundary endpoints,
not curve controls. Includes bounded fabric/avatar inventories and pattern fabric
assignment, not material editing. Sewing and simulation are not enabled.
"""

import math
import os


PATTERN_COMMANDS = [
    "list_clo_api", "describe_clo_api", "get_pattern_list", "get_pattern_geometry",
    "create_pattern", "set_pattern_name", "copy_pattern_with_offset",
    "move_pattern_relative", "delete_pattern",
    "get_fabric_list", "get_avatars",
    "get_pattern_fabric", "assign_pattern_fabric",
    "get_pattern_outline", "get_pattern_lines",
    "add_seamline_pair", "add_seamline_pair_partial", "import_avatar",
    "get_arrangement", "set_arrangement",
    "set_arrangement_orientation", "set_arrangement_position",
    "get_3d_screenshot", "get_arrangement_list", "get_seamline_pairs",
    "get_avatar_measurements", "get_pattern_avatar_attachments",
    "set_arrangement_shape_style", "set_pattern_edge_to_avatar_measure", "simulate",
    "export_view_image", "export_snapshot_2d", "set_camera_view",
    "reset_cloth_arrangement", "import_avatar_measurements",
    "get_pattern_body_details", "get_pattern_details",
    "set_pattern_grain_direction", "get_mesh_counts", "set_particle_distance",
    "import_dxf", "export_pattern_json", "import_pattern_json", "import_avatar_size",
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
        "add_seamline_pair": {"pattern_a_index", "expected_name_a", "line_a_index",
                              "pattern_b_index", "expected_name_b", "line_b_index",
                              "direction_a", "direction_b"},
        "add_seamline_pair_partial": {"pattern_a_index", "expected_name_a", "line_a_index",
                                      "start_ratio_a", "end_ratio_a",
                                      "pattern_b_index", "expected_name_b", "line_b_index",
                                      "start_ratio_b", "end_ratio_b",
                                      "direction_a", "direction_b"},
        "import_avatar": {"file_path"},
        "get_arrangement": set(),
        "set_arrangement": {"pattern_index", "expected_name", "arrangement_index"},
        "set_arrangement_orientation": {"pattern_index", "expected_name", "orientation"},
        "set_arrangement_position": {"pattern_index", "expected_name",
                                     "position_x", "position_y", "offset"},
        "get_3d_screenshot": {"output_path"},
        "get_arrangement_list": set(),
        "get_seamline_pairs": set(),
        "get_avatar_measurements": {"avatar_index"},
        "get_pattern_avatar_attachments": set(),
        "set_arrangement_shape_style": {"pattern_index", "expected_name", "style"},
        "set_pattern_edge_to_avatar_measure": {"pattern_index", "expected_name", "line_index",
                                               "avatar_measure", "attach"},
        "simulate": {"steps"},
        "export_view_image": {"output_path", "view", "width", "height",
                              "fit_all_objects"},
        "export_snapshot_2d": {"output_path"},
        "set_camera_view": {"view", "zoom_to_fit"},
        "reset_cloth_arrangement": set(),
        "import_avatar_measurements": {"csv_path"},
        "get_pattern_body_details": set(),
        "get_pattern_details": {"pattern_index", "expected_name"},
        "set_pattern_grain_direction": {"pattern_index", "expected_name", "degrees"},
        "get_mesh_counts": {"pattern_index", "expected_name"},
        "set_particle_distance": {"pattern_index", "expected_name", "distance"},
        "import_dxf": {"file_path"},
        "export_pattern_json": {"output_path"},
        "import_pattern_json": {"file_path"},
        "import_avatar_size": {"file_path"},
        "assign_pattern_fabric": {"pattern_index", "expected_name", "fabric_index",
                                  "expected_fabric_name", "expected_current_fabric_index"},
    }
    optional = {"create_pattern": {"vertex_types"}}
    valid = (command in fields
             and fields[command] <= set(params) <= fields[command] | optional.get(command, set()))
    if valid:
        curve_types = params.get("vertex_types")
        curved = (isinstance(curve_types, list)
                  and any(type(t) is int and t in (2, 3) for t in curve_types))
        for key, value in params.items():
            if key in ("pattern_index", "fabric_index", "expected_current_fabric_index",
                       "pattern_a_index", "pattern_b_index", "line_a_index", "line_b_index",
                       "arrangement_index"):
                valid = index(value)
            elif key == "expected_fabric_name":
                valid = inventory_name(value)
            elif key in ("name", "expected_name", "expected_name_a", "expected_name_b"):
                valid = name(value)
            elif key in ("direction_a", "direction_b"):
                valid = type(value) is bool
            elif key == "orientation":
                valid = type(value) is int and 0 <= value <= 359
            elif key in ("position_x", "position_y", "offset"):
                valid = type(value) is int and 0 <= value <= 100
            elif key == "line_index":
                valid = type(value) is int and 0 <= value < MAX_LINES
            elif key in ("start_ratio_a", "end_ratio_a", "start_ratio_b", "end_ratio_b"):
                valid = number(value) and 0 <= value <= 1
            elif key == "avatar_index":
                valid = type(value) is int and 0 <= value < MAX_AVATARS
            elif key == "steps":
                valid = type(value) is int and 1 <= value <= 300
            elif key == "style":
                valid = value in ("Flat", "Curved")
            elif key == "avatar_measure":
                valid = (type(value) is str and 1 <= len(value) <= 256
                         and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF
                                 for c in value))
            elif key == "attach":
                valid = type(value) is bool
            elif key == "output_path":
                suffix = ".json" if command == "export_pattern_json" else ".png"
                valid = (type(value) is str and 1 <= len(value) <= 260
                         and value.lower().endswith(suffix) and os.path.isabs(value)
                         and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF
                                 for c in value))
            elif key == "csv_path":
                valid = (type(value) is str and 1 <= len(value) <= 260
                         and value.lower().endswith(".csv") and os.path.isabs(value)
                         and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF
                                 for c in value))
            elif key == "view":
                valid = type(value) is int and 0 <= value <= 8
            elif key in ("width", "height"):
                valid = type(value) is int and 64 <= value <= 2048
            elif key in ("fit_all_objects", "zoom_to_fit"):
                valid = type(value) is bool
            elif key == "degrees":
                valid = number(value) and 0 <= value <= 359
            elif key == "distance":
                valid = number(value) and 1 <= value <= 1000
            elif key == "vertex_types":
                valid = (isinstance(value, list) and 3 <= len(value) <= 64
                         and all(type(v) is int and v in (0, 2, 3) for v in value)
                         and len(value) == len(params.get("points", [])))
            elif key in ("dx", "dy"):
                valid = number(value)
            elif key == "file_path":
                suffix = (".dxf" if command == "import_dxf"
                          else ".json" if command == "import_pattern_json"
                          else ".avs" if command == "import_avatar_size" else ".avt")
                valid = (isinstance(value, str) and 1 <= len(value) <= 260
                         and value.lower().endswith(suffix) and os.path.isabs(value)
                         and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF
                                 for c in value))
            elif key == "points":
                if curved:
                    valid = (isinstance(value, list) and 3 <= len(value) <= 64
                             and all(isinstance(point, list) and len(point) == 2
                                     and all(number(v) for v in point) for point in value))
                else:
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
    # Native AddSeamlinePairGroupPartial rejects a descending range even though
    # the exported LengthParam of a direction=false pair is descending. Input
    # ratios are always ascending; Direction encodes stitch orientation.
    if command == "add_seamline_pair_partial" and not (
            params["start_ratio_a"] < params["end_ratio_a"]
            and params["start_ratio_b"] < params["end_ratio_b"]):
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
    elif command in ("add_seamline_pair", "add_seamline_pair_partial"):
        valid = (keys == {"verified", "seam_count"}
                 and result["verified"] is True
                 and type(result["seam_count"]) is int and result["seam_count"] >= 0)
    elif command == "import_dxf":
        valid = (keys == {"imported", "pattern_count_before", "pattern_count_after",
                          "imported_count", "imported_names", "executor_ms"}
                 and result["imported"] is True
                 and type(result["pattern_count_before"]) is int
                 and type(result["pattern_count_after"]) is int
                 and 0 <= result["pattern_count_before"] <= result["pattern_count_after"] <= MAX_PATTERNS
                 and type(result["imported_count"]) is int
                 and result["imported_count"] == result["pattern_count_after"] - result["pattern_count_before"]
                 and 1 <= result["imported_count"] <= MAX_PATTERNS
                 and isinstance(result["imported_names"], list)
                 and len(result["imported_names"]) == result["imported_count"]
                 and all(name(v) for v in result["imported_names"])
                 and number(result["executor_ms"], 1e12) and result["executor_ms"] >= 0)
    elif command == "export_pattern_json":
        valid = (keys == {"verified", "file_name", "bytes"}
                 and result["verified"] is True
                 and type(result["file_name"]) is str and 1 <= len(result["file_name"]) <= 128
                 and type(result["bytes"]) is int and 1 <= result["bytes"] <= 67108864)
    elif command == "import_pattern_json":
        patterns = result.get("patterns_after")
        valid = (keys == {"imported", "pattern_count_before", "pattern_count_after",
                          "patterns_after", "seam_count_after", "executor_ms"}
                 and result["imported"] is True
                 and type(result["pattern_count_before"]) is int
                 and type(result["pattern_count_after"]) is int
                 and 0 <= result["pattern_count_after"] <= MAX_PATTERNS
                 and isinstance(patterns, list)
                 and len(patterns) == result["pattern_count_after"]
                 and all(type(item) is dict and set(item) == {"index", "name"}
                         and type(item["index"]) is int and item["index"] == i
                         and name(item["name"]) for i, item in enumerate(patterns))
                 and type(result["seam_count_after"]) is int
                 and 0 <= result["seam_count_after"] <= 4096
                 and number(result["executor_ms"], 1e12) and result["executor_ms"] >= 0)
    elif command == "import_avatar_size":
        valid = (keys == {"verified", "measurement_count_before",
                          "measurement_count_after", "added"}
                 and result["verified"] is True
                 and type(result["measurement_count_before"]) is int
                 and type(result["measurement_count_after"]) is int
                 and 0 <= result["measurement_count_before"] <= 512
                 and 0 <= result["measurement_count_after"] <= 512
                 and type(result["added"]) is int
                 and result["added"] == result["measurement_count_after"] - result["measurement_count_before"])
    elif command == "import_avatar":
        valid = (keys == {"verified", "avatar_count"}
                 and result["verified"] is True
                 and type(result["avatar_count"]) is int
                 and 0 <= result["avatar_count"] <= MAX_AVATARS)
    elif command in ("set_arrangement", "set_arrangement_orientation",
                     "set_arrangement_position"):
        valid = (keys == {"verified", "pattern_index", "pattern_name", "arrangement_name",
                          "offset", "orientation", "type", "units", "redrape"}
                 and result["verified"] is True and result["redrape"] is True
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and inventory_name(result["arrangement_name"])
                 and isinstance(result["offset"], dict)
                 and set(result["offset"]) == {"x", "y", "z"}
                 and all(number(v) for v in result["offset"].values())
                 and number(result["orientation"])
                 and type(result["type"]) is str and 1 <= len(result["type"]) <= 32
                 and result["units"] == "native_unspecified")
    elif command == "get_arrangement":
        pieces = result.get("pieces")
        valid = (keys == {"pattern_count", "arrangement_library_count", "pieces", "units"}
                 and type(result["pattern_count"]) is int
                 and 0 <= result["pattern_count"] <= MAX_PATTERNS
                 and type(result["arrangement_library_count"]) is int
                 and result["arrangement_library_count"] >= 0
                 and isinstance(pieces, list) and len(pieces) == result["pattern_count"]
                 and result["units"] == "native_unspecified"
                 and all(isinstance(item, dict)
                         and set(item) == {"pattern_index", "pattern_name", "arrangement_name",
                                           "offset", "orientation", "type"}
                         and type(item["pattern_index"]) is int
                         and item["pattern_index"] == i
                         and name(item["pattern_name"])
                         and inventory_name(item["arrangement_name"])
                         and isinstance(item["offset"], dict)
                         and set(item["offset"]) == {"x", "y", "z"}
                         and all(number(v) for v in item["offset"].values())
                         and number(item["orientation"])
                         and type(item["type"]) is str and 1 <= len(item["type"]) <= 32
                         for i, item in enumerate(pieces)))
    elif command == "get_arrangement_list":
        points = result.get("points")
        valid = (keys == {"library_count", "points", "units"}
                 and type(result["library_count"]) is int
                 and 0 <= result["library_count"] <= 4096
                 and isinstance(points, list) and len(points) == result["library_count"]
                 and result["units"] == "native_unspecified"
                 and all(isinstance(item, dict)
                         and set(item) == {"index", "name", "type", "offset", "orientation"}
                         and item["index"] == i and type(item["index"]) is int
                         and name(item["name"])
                         and type(item["type"]) is str and 1 <= len(item["type"]) <= 32
                         and isinstance(item["offset"], dict)
                         and set(item["offset"]) == {"x", "y", "z"}
                         and all(number(v) for v in item["offset"].values())
                         and number(item["orientation"])
                         for i, item in enumerate(points)))
    elif command == "get_seamline_pairs":
        groups = result.get("groups")
        patterns = result.get("patterns")
        valid = (keys == {"seam_count", "pattern_count", "groups", "patterns"}
                 and type(result["seam_count"]) is int and 0 <= result["seam_count"] <= 4096
                 and type(result["pattern_count"]) is int
                 and 0 <= result["pattern_count"] <= MAX_PATTERNS
                 and isinstance(groups, list) and len(groups) == result["seam_count"]
                 and isinstance(patterns, list) and len(patterns) == result["pattern_count"]
                 and all(isinstance(item, dict) and set(item) == {"index", "name"}
                         and item["index"] == i and type(item["index"]) is int
                         and inventory_name(item["name"])
                         for i, item in enumerate(groups))
                 and all(isinstance(item, dict)
                         and set(item) == {"pattern_index", "pattern_name",
                                           "group_indices", "group_names"}
                         and item["pattern_index"] == i and type(item["pattern_index"]) is int
                         and name(item["pattern_name"])
                         and isinstance(item["group_indices"], list)
                         and isinstance(item["group_names"], list)
                         and len(item["group_indices"]) == len(item["group_names"])
                         and all(type(v) is int and 0 <= v < result["seam_count"]
                                 for v in item["group_indices"])
                         and all(inventory_name(v) for v in item["group_names"])
                         for i, item in enumerate(patterns)))
    elif command == "get_avatar_measurements":
        items = result.get("measurements")
        valid = (keys == {"avatar_index", "avatar_name", "measurement_count",
                          "measurements", "units"}
                 and type(result["avatar_index"]) is int
                 and 0 <= result["avatar_index"] < MAX_AVATARS
                 and name(result["avatar_name"])
                 and type(result["measurement_count"]) is int
                 and 0 <= result["measurement_count"] <= 512
                 and isinstance(items, list) and len(items) == result["measurement_count"]
                 and result["units"] == "native_display_unit"
                 and all(isinstance(item, dict)
                         and set(item) == {"name", "type", "value", "basic_length",
                                           "surface_length", "unit"}
                         and inventory_name(item["name"])
                         and type(item["type"]) is str and 1 <= len(item["type"]) <= 32
                         and all(number(item[k]) for k in ("value", "basic_length", "surface_length"))
                         and type(item["unit"]) is str and 1 <= len(item["unit"]) <= 8
                         for item in items))
    elif command == "get_pattern_avatar_attachments":
        pairs = result.get("pairs")
        valid = (keys == {"pair_count", "pin_count", "pairs"}
                 and type(result["pair_count"]) is int and 0 <= result["pair_count"] <= 1024
                 and type(result["pin_count"]) is int and 0 <= result["pin_count"] <= 65536
                 and isinstance(pairs, list) and len(pairs) == result["pair_count"]
                 and all(isinstance(item, dict)
                         and set(item) == {"pattern_name", "avatar_measure"}
                         and inventory_name(item["pattern_name"])
                         and inventory_name(item["avatar_measure"])
                         for item in pairs))
    elif command == "set_arrangement_shape_style":
        valid = (keys == {"verified", "pattern_index", "pattern_name", "arrangement_name",
                          "offset", "orientation", "type", "units"}
                 and result["verified"] is True
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and inventory_name(result["arrangement_name"])
                 and isinstance(result["offset"], dict)
                 and set(result["offset"]) == {"x", "y", "z"}
                 and all(number(v) for v in result["offset"].values())
                 and number(result["orientation"])
                 and result["type"] in ("Flat", "Curved")
                 and result["units"] == "native_unspecified")
    elif command == "set_pattern_edge_to_avatar_measure":
        valid = (keys == {"verified", "pattern_index", "pattern_name", "line_index",
                          "avatar_measure", "attached"}
                 and result["verified"] is True
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and type(result["line_index"]) is int
                 and 0 <= result["line_index"] < MAX_LINES
                 and inventory_name(result["avatar_measure"])
                 and type(result["attached"]) is bool)
    elif command == "simulate":
        valid = (keys == {"verified", "steps", "pattern_count", "avatar_count", "elapsed_ms"}
                 and result["verified"] is True
                 and type(result["steps"]) is int and 1 <= result["steps"] <= 300
                 and type(result["pattern_count"]) is int
                 and 0 <= result["pattern_count"] <= MAX_PATTERNS
                 and type(result["avatar_count"]) is int
                 and 0 <= result["avatar_count"] <= MAX_AVATARS
                 and number(result["elapsed_ms"], 1e12) and result["elapsed_ms"] >= 0)
    elif command == "get_3d_screenshot":
        valid = (keys == {"verified", "bytes"}
                 and result["verified"] is True
                 and type(result["bytes"]) is int
                 and 0 < result["bytes"] <= 16777216)
    elif command == "export_view_image":
        fname = result.get("file_name")
        valid = (keys == {"verified", "view", "width", "height", "file_name", "bytes"}
                 and result["verified"] is True
                 and type(result["view"]) is int and 0 <= result["view"] <= 8
                 and type(result["width"]) is int and 64 <= result["width"] <= 2048
                 and type(result["height"]) is int and 64 <= result["height"] <= 2048
                 and type(fname) is str and 1 <= len(fname) <= 128
                 and "/" not in fname and "\\" not in fname
                 and type(result["bytes"]) is int
                 and 0 < result["bytes"] <= 16777216)
    elif command == "export_snapshot_2d":
        fname = result.get("file_name")
        valid = (keys == {"verified", "file_name", "bytes"}
                 and result["verified"] is True
                 and type(fname) is str and 1 <= len(fname) <= 128
                 and "/" not in fname and "\\" not in fname
                 and type(result["bytes"]) is int
                 and 0 < result["bytes"] <= 16777216)
    elif command == "set_camera_view":
        valid = (keys == {"verified", "view", "zoom_to_fit"}
                 and result["verified"] is True
                 and type(result["view"]) is int and 0 <= result["view"] <= 8
                 and type(result["zoom_to_fit"]) is bool)
    elif command == "reset_cloth_arrangement":
        valid = (keys == {"verified", "pattern_count"}
                 and result["verified"] is True
                 and type(result["pattern_count"]) is int
                 and 0 <= result["pattern_count"] <= MAX_PATTERNS)
    elif command == "import_avatar_measurements":
        valid = (keys == {"verified", "avatar_index", "before_count",
                          "after_count", "added"}
                 and result["verified"] is True
                 and type(result["avatar_index"]) is int
                 and 0 <= result["avatar_index"] < MAX_AVATARS
                 and type(result["before_count"]) is int
                 and type(result["after_count"]) is int
                 and 0 <= result["before_count"] <= 512
                 and 0 <= result["after_count"] <= 512
                 and type(result["added"]) is int
                 and result["added"] == result["after_count"] - result["before_count"]
                 and result["added"] > 0)
    elif command == "get_pattern_body_details":
        upper, lower = result.get("upperBody"), result.get("lowerBody")
        body_keys = {"patternName", "patternIndex", "arrangementPosition",
                     "semanticLabel", "bodyRegion", "patternPosition"}
        def body_ok(item):
            return (isinstance(item, dict) and set(item) == body_keys
                    and type(item["patternIndex"]) is int
                    and 0 <= item["patternIndex"] < MAX_PATTERNS
                    and all(type(item[k]) is str and 0 <= len(item[k]) <= 128
                            for k in body_keys - {"patternIndex"}))
        valid = (keys == {"upperBody", "lowerBody"}
                 and isinstance(upper, list) and isinstance(lower, list)
                 and len(upper) + len(lower) <= MAX_PATTERNS
                 and all(body_ok(item) for item in upper + lower))
    elif command == "get_pattern_details":
        valid = (keys == {"pattern_index", "pattern_name", "grain_direction",
                          "category", "classification"}
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and number(result["grain_direction"])
                 and type(result["category"]) is int and -1 <= result["category"] <= 999
                 and type(result["classification"]) is str
                 and 0 <= len(result["classification"]) <= 256)
    elif command == "set_pattern_grain_direction":
        valid = (keys == {"verified", "pattern_index", "pattern_name",
                          "grain_direction"}
                 and result["verified"] is True
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and number(result["grain_direction"]))
    elif command == "get_mesh_counts":
        meshes = result.get("meshes")
        valid = (keys == {"pattern_index", "pattern_name", "meshes"}
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and isinstance(meshes, list) and len(meshes) <= 16
                 and all(isinstance(item, dict) and set(item) == {"type", "value"}
                         and type(item["type"]) is str and 1 <= len(item["type"]) <= 64
                         and type(item["value"]) is str and 1 <= len(item["value"]) <= 64
                         for item in meshes))
    elif command == "set_particle_distance":
        valid = (keys == {"verified", "pattern_index", "pattern_name", "distance"}
                 and result["verified"] is True
                 and index(result["pattern_index"]) and name(result["pattern_name"])
                 and number(result["distance"]) and 1 <= result["distance"] <= 1000)
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
