"""Explicit CLO pattern adapter; never imports CLO modules or legacy listener.

Constructed by launcher with existing embedded modules. Invoked ONLY by the
verified UI executor. A setter plus readback is not an atomic transaction.
"""

import json
import math
import os
import re
import time

from clo3d_mcp.pattern_contract import (
    API_MODULES, MAX_AVATARS, MAX_LINE_JSON_BYTES, MAX_LINES, MAX_PATTERNS, CommandError, number,
    outline_points, validate_params, validate_result,
)
from clo3d_mcp.inventory_api import InventoryAPI
from clo3d_mcp.fabric_assignment_api import FabricAssignmentAPI


def _reject_constant(_text):
    raise ValueError("nonfinite")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_key")
        value[key] = item
    return value


def _line_json(text, depth_limit=16):
    """Strict bounded JSON from GetPatternLineInfo; no raw text ever echoed."""
    if type(text) is not str or not 1 <= len(text) <= MAX_LINE_JSON_BYTES:
        raise CommandError("invalid_native_result")
    try:
        if len(text.encode("utf-8")) > MAX_LINE_JSON_BYTES:
            raise CommandError("invalid_native_result")
    except UnicodeError:
        raise CommandError("invalid_native_result") from None
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > depth_limit:
                raise CommandError("invalid_native_result")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise CommandError("invalid_native_result")
    try:
        data = json.loads(text, object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (ValueError, RecursionError, OverflowError):
        raise CommandError("invalid_native_result") from None
    if type(data) is not dict:
        raise CommandError("invalid_native_result")
    return data


class PatternAPI:
    def __init__(self, modules):
        self.modules = dict(modules)
        self.pattern = self.modules["pattern_api"]
        self.inventory = InventoryAPI(self.modules)
        self.fabric_assignment = FabricAssignmentAPI(self)

    def _require(self, *names):
        if any(not callable(getattr(self.pattern, n, None)) for n in names):
            raise CommandError("api_unavailable")

    def _count(self):
        self._require("GetPatternCount")
        value = self.pattern.GetPatternCount()
        if type(value) is not int or not 0 <= value <= MAX_PATTERNS:
            raise CommandError("scene_change_unverified")
        return value

    def _list(self):
        self._require("GetPatternPieceName")
        count = self._count()
        values = [{"index": i, "name": self.pattern.GetPatternPieceName(i)} for i in range(count)]
        result = {"pattern_count": count, "patterns": values}
        validate_result("get_pattern_list", result)
        return result

    @staticmethod
    def _numeric_text(text):
        if type(text) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", text):
            raise CommandError("invalid_native_result")
        value = float(text)
        if not math.isfinite(value) or abs(value) > 1e16:
            raise CommandError("invalid_native_result")
        return value

    @classmethod
    def _arrangement_record(cls, value):
        keys = ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                "ArrangementOffsetZ", "ArrangementOrientation", "ArrangementType")
        if type(value) is not dict or not set(keys) <= set(value):
            raise CommandError("invalid_native_result")
        if (type(value["ArrangementName"]) is not str
                or type(value["ArrangementType"]) is not str):
            raise CommandError("invalid_native_result")
        for key in ("ArrangementOffsetX", "ArrangementOffsetY",
                    "ArrangementOffsetZ", "ArrangementOrientation"):
            cls._numeric_text(value[key])
        return value

    @staticmethod
    def _position(value):
        if isinstance(value, (tuple, list)) and len(value) == 2:
            output = list(value)
        elif hasattr(value, "x") and hasattr(value, "y"):
            output = [value.x, value.y]
        else:
            raise CommandError("api_unavailable")
        if not all(number(v) for v in output):
            raise CommandError("scene_change_unverified")
        return [float(v) for v in output]

    @classmethod
    def _box(cls, value, depth=0):
        # CLO bindings may return a tuple or a value record. No arbitrary dir()
        # probing/property iteration and no str(object) pretending to be geometry.
        if depth > 4:
            raise CommandError("api_unavailable")
        if type(value) in (int, float) and number(value):
            return float(value)
        # CLO 2026.1 advertises Dict[str, str] for this getter. Preserve
        # bounded native text rather than inventing a numeric layout/units.
        # Position and area remain independently validated numeric getters.
        if (isinstance(value, str) and 1 <= len(value) <= 256
                and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in value)):
            return value
        if isinstance(value, (tuple, list)) and 1 <= len(value) <= 16:
            return [cls._box(v, depth + 1) for v in value]
        if isinstance(value, dict) and 1 <= len(value) <= 16:
            if not all(isinstance(k, str) and 1 <= len(k) <= 128
                       and all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in k)
                       for k in value):
                raise CommandError("api_unavailable")
            return {k: cls._box(v, depth + 1) for k, v in value.items()}
        fields = ("x", "y", "z", "minX", "minY", "maxX", "maxY", "width", "height")
        output = {key: cls._box(getattr(value, key), depth + 1)
                  for key in fields if hasattr(value, key)}
        if not output:
            raise CommandError("api_unavailable")
        return output

    def _geometry(self, i):
        self._require("GetPatternPieceName", "GetPatternPiecePos", "GetPatternPieceArea",
                      "GetBoundingBoxOfPattern")
        if i >= self._count():
            raise CommandError("stale_pattern")
        result = {"index": i, "name": self.pattern.GetPatternPieceName(i),
                  "position_mm": self._position(self.pattern.GetPatternPiecePos(i)),
                  "area_mm2": self.pattern.GetPatternPieceArea(i),
                  "bounding_box": self._box(self.pattern.GetBoundingBoxOfPattern(i))}
        validate_result("get_pattern_geometry", {"pattern": result})
        return result

    def _target(self, params):
        values = self._list()["patterns"]
        i = params["pattern_index"]
        expected = params["expected_name"]
        # A name is a stale-index guard, NOT a durable identity. Require unique
        # names for mutations, and re-read in the same UI callback as the setter.
        if (i >= len(values) or values[i]["name"] != expected
                or sum(v["name"] == expected for v in values) != 1):
            raise CommandError("stale_pattern")
        return i

    def _new_name(self, value, except_index=None):
        if any(v["name"] == value and v["index"] != except_index
               for v in self._list()["patterns"]):
            raise CommandError("stale_pattern")

    def _fresh(self, p):
        """Fresh unique target snapshot shared by read-only getters."""
        before = self._list()
        index = p["pattern_index"]
        items = before["patterns"]
        if (index >= len(items) or items[index]["name"] != p["expected_name"]
                or sum(v["name"] == p["expected_name"] for v in items) != 1):
            raise CommandError("stale_pattern")
        if self._count() != before["pattern_count"]:
            raise CommandError("inventory_changed")
        return before, index

    def _outline(self, p):
        """Bounded read, no inferred closure/control points/line-index mapping."""
        self._require("GetPatternCount", "GetPatternPieceName", "GetPatternOutlinePoints")
        try:
            before, i = self._fresh(p)
            points = self.pattern.GetPatternOutlinePoints(i)
            if not outline_points(points):
                raise CommandError("invalid_native_result")
            # Copy immediately: bindings may reuse mutable native-backed lists.
            points = [[float(x), float(y)] for x, y in points]
            if self._list() != before or self._count() != before["pattern_count"]:
                raise CommandError("inventory_changed")
            repeated = self.pattern.GetPatternOutlinePoints(i)
            if not outline_points(repeated):
                raise CommandError("invalid_native_result")
            if repeated != points:
                raise CommandError("inventory_changed")
            if self._list() != before or self._count() != before["pattern_count"]:
                raise CommandError("inventory_changed")
            return {"pattern_index": i, "pattern_name": p["expected_name"],
                    "point_count": len(points), "points_mm": points,
                    "coordinate_frame": "bbox_top_left_y_down", "units": "mm"}
        except CommandError as exc:
            if exc.code in ("invalid_result", "scene_change_unverified"):
                raise CommandError("invalid_native_result") from None
            raise
        except Exception:
            raise CommandError("command_error") from None

    def _lines(self, p):
        """Bounded outer-line inspection; no outline fallback or curve inference."""
        self._require("GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo")
        before, i = self._fresh(p)
        try:
            native = self.pattern.GetPatternLineInfo(i)
        except Exception:
            raise CommandError("command_error") from None
        data = _line_json(native)
        if data.get("status") != "success":
            raise CommandError("invalid_native_result")
        if type(data.get("patternIndex")) is not int or data["patternIndex"] != i:
            raise CommandError("invalid_native_result")
        if data.get("patternName") != p["expected_name"]:
            raise CommandError("invalid_native_result")
        lines = data.get("lines")
        if (type(data.get("lineCount")) is not int or type(lines) is not list
                or data["lineCount"] != len(lines) or not 1 <= len(lines) <= MAX_LINES):
            raise CommandError("invalid_native_result")
        box = data.get("boundingBox")
        keys = ("minX", "minY", "maxX", "maxY", "width", "height")
        if type(box) is not dict or set(box) != set(keys) or not all(number(box[k]) for k in keys):
            raise CommandError("invalid_native_result")
        if (box["maxX"] < box["minX"] or box["maxY"] < box["minY"]
                or box["width"] < 0 or box["height"] < 0):
            raise CommandError("invalid_native_result")

        def point(value):
            if type(value) is not dict or set(value) != {"x", "y"}:
                raise CommandError("invalid_native_result")
            if not number(value["x"]) or not number(value["y"]):
                raise CommandError("invalid_native_result")
            return {"x": float(value["x"]), "y": float(value["y"])}

        seen = set()
        output = []
        for item in lines:
            if type(item) is not dict or set(item) != {"lineIndex", "length", "orientation",
                    "location", "start", "end", "mid", "midNorm"}:
                raise CommandError("invalid_native_result")
            line_index = item["lineIndex"]
            if type(line_index) is not int or not 0 <= line_index < MAX_LINES or line_index in seen:
                raise CommandError("invalid_native_result")
            if not number(item["length"]) or item["length"] < 0:
                raise CommandError("invalid_native_result")
            if item["orientation"] not in ("horizontal", "vertical", "diagonal"):
                raise CommandError("invalid_native_result")
            location = item["location"]
            if (type(location) is not str or not 1 <= len(location) <= 32
                    or not all("a" <= c <= "z" or c == "-" for c in location)):
                raise CommandError("invalid_native_result")
            seen.add(line_index)
            mid_norm = point(item["midNorm"])
            if not 0 <= mid_norm["x"] <= 1 or not 0 <= mid_norm["y"] <= 1:
                raise CommandError("invalid_native_result")
            output.append({"line_index": line_index, "length_mm": float(item["length"]),
                           "orientation": item["orientation"], "location": location,
                           "start_mm": point(item["start"]), "end_mm": point(item["end"]),
                           "mid_mm": point(item["mid"]), "mid_norm": mid_norm})
        if self._list() != before or self._count() != before["pattern_count"]:
            raise CommandError("inventory_changed")
        return {"pattern_index": i, "pattern_name": p["expected_name"],
                "line_count": len(output),
                "bounding_box_mm": {"min_x": float(box["minX"]), "min_y": float(box["minY"]),
                                    "max_x": float(box["maxX"]), "max_y": float(box["maxY"]),
                                    "width": float(box["width"]), "height": float(box["height"])},
                "lines": output, "coordinate_frame": "api_2d_mm", "units": "mm"}

    def _seam(self, p):
        """One whole-line seam pair with readback; no child overloads or retry."""
        self._require("GetPatternCount", "GetPatternPieceName", "GetPatternLineInfo",
                      "GetPatternPieceArea", "GetBoundingBoxOfPattern",
                      "GetSeamlinePairGroupCount", "AddSeamlinePairGroup")
        before = self._list()
        a, b = p["pattern_a_index"], p["pattern_b_index"]
        if a == b:
            raise CommandError("invalid_parameters")
        for index, expected in ((a, p["expected_name_a"]), (b, p["expected_name_b"])):
            items = before["patterns"]
            if (index >= len(items) or items[index]["name"] != expected
                    or sum(v["name"] == expected for v in items) != 1):
                raise CommandError("stale_pattern")

        def line_lengths(index):
            data = _line_json(self.pattern.GetPatternLineInfo(index))
            lines = data.get("lines")
            if (data.get("status") != "success" or type(data.get("lineCount")) is not int
                    or type(lines) is not list or data["lineCount"] != len(lines)
                    or not 1 <= len(lines) <= MAX_LINES):
                raise CommandError("invalid_native_result")
            lengths = [item.get("length") for item in lines if type(item) is dict]
            if len(lengths) != len(lines) or not all(number(v) and v >= 0 for v in lengths):
                raise CommandError("invalid_native_result")
            return [float(v) for v in lengths]

        lines_a, lines_b = line_lengths(a), line_lengths(b)
        if p["line_a_index"] >= len(lines_a) or p["line_b_index"] >= len(lines_b):
            raise CommandError("invalid_parameters")
        geometry_a, geometry_b = self._geometry(a), self._geometry(b)
        seams = self.pattern.GetSeamlinePairGroupCount()
        if type(seams) is not int or seams < 0:
            raise CommandError("invalid_native_result")
        try:
            created = self.pattern.AddSeamlinePairGroup(
                a, p["line_a_index"], b, p["line_b_index"],
                p["direction_a"], p["direction_b"])
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if type(created) is not bool or created is not True:
            raise CommandError("invalid_native_result")
        if self._list() != before:
            raise CommandError("inventory_changed")
        seams_after = self.pattern.GetSeamlinePairGroupCount()
        if type(seams_after) is not int or seams_after != seams + 1:
            raise CommandError("scene_change_unverified")
        if line_lengths(a) != lines_a or line_lengths(b) != lines_b:
            raise CommandError("scene_change_unverified")
        after_a, after_b = self._geometry(a), self._geometry(b)
        for old, new in ((geometry_a, after_a), (geometry_b, after_b)):
            if (old["name"] != new["name"] or old["index"] != new["index"]
                    or old["bounding_box"] != new["bounding_box"]
                    or not self._near(old["area_mm2"], new["area_mm2"])
                    or not all(self._near(x, y) for x, y in
                               zip(old["position_mm"], new["position_mm"]))):
                raise CommandError("scene_change_unverified")
        return {"verified": True, "seam_count": seams_after}

    def _import_avatar(self, p):
        """Import one .avt avatar via ImportFile; verify count+1, no path echo."""
        imp, exp = self.modules.get("import_api"), self.modules.get("export_api")
        if not callable(getattr(imp, "ImportFile", None)) or not callable(
                getattr(exp, "GetAvatarCount", None)):
            raise CommandError("api_unavailable")
        path = p["file_path"]
        try:
            if not os.path.isfile(path) or not 0 < os.path.getsize(path) <= 134217728:
                raise CommandError("invalid_parameters")
        except OSError:
            raise CommandError("invalid_parameters") from None
        before = exp.GetAvatarCount()
        if type(before) is not int or not 0 <= before < MAX_AVATARS:
            raise CommandError("invalid_native_result")
        try:
            imported = imp.ImportFile(path)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if type(imported) is not bool or imported is not True:
            raise CommandError("invalid_native_result")
        after = exp.GetAvatarCount()
        if type(after) is not int or after != before + 1:
            raise CommandError("scene_change_unverified")
        return {"verified": True, "avatar_count": after}

    def _arrangements(self):
        """Read every piece's current arrangement; numeric text stays un-united."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetArrangementList", "GetArrangementOfPattern")
        before = self._list()
        library = self.pattern.GetArrangementList()
        if type(library) is not list or len(library) > 4096:
            raise CommandError("invalid_native_result")

        def numeric(text):
            if type(text) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", text):
                raise CommandError("invalid_native_result")
            value = float(text)
            if not math.isfinite(value) or abs(value) > 1e16:
                raise CommandError("invalid_native_result")
            return value

        pieces = []
        for i, item in enumerate(before["patterns"]):
            value = self.pattern.GetArrangementOfPattern(i)
            if type(value) is not dict or set(value) != {
                    "ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                    "ArrangementOffsetZ", "ArrangementOrientation", "ArrangementType"}:
                raise CommandError("invalid_native_result")
            name = value["ArrangementName"]
            kind = value["ArrangementType"]
            if (type(name) is not str or len(name) > 128
                    or not all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in name)
                    or type(kind) is not str or not 1 <= len(kind) <= 32
                    or not all(ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF for c in kind)):
                raise CommandError("invalid_native_result")
            pieces.append({"pattern_index": i, "pattern_name": item["name"],
                           "arrangement_name": name,
                           "offset": {"x": numeric(value["ArrangementOffsetX"]),
                                      "y": numeric(value["ArrangementOffsetY"]),
                                      "z": numeric(value["ArrangementOffsetZ"])},
                           "orientation": numeric(value["ArrangementOrientation"]),
                           "type": kind})
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"pattern_count": len(pieces), "arrangement_library_count": len(library),
                "pieces": pieces, "units": "native_unspecified"}

    def _drape_option(self):
        """Construct the native ReDrape option once, before any scene mutation."""
        try:
            import ApiTypes
            option = ApiTypes.ImportExportOption()
        except Exception:
            raise CommandError("api_unavailable") from None
        for flag in ("bAddArrangementPoints", "bAutoCreateFittingSuit", "bMoveGarment"):
            if hasattr(option, flag):
                try:
                    setattr(option, flag, True)
                except Exception:
                    pass
        return option

    def _set_arrangement(self, p):
        """Assign one avatar arrangement point, then ReDrape; assignment is verified."""
        self._require("GetPatternCount", "GetPatternPieceName", "GetArrangementList",
                      "SetArrangement", "GetArrangementOfPattern")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        library = self.pattern.GetArrangementList()
        if type(library) is not list or not 1 <= len(library) <= 4096:
            raise CommandError("invalid_native_result")
        arrangement_index = p["arrangement_index"]
        if arrangement_index >= len(library):
            raise CommandError("invalid_parameters")
        entry = library[arrangement_index]
        keys = ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                "ArrangementOffsetZ", "ArrangementOrientation", "ArrangementType")
        if type(entry) is not dict or not all(type(entry.get(k)) is str for k in keys):
            raise CommandError("invalid_native_result")
        option = self._drape_option()
        try:
            self.pattern.SetArrangement(i, arrangement_index)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        value = self.pattern.GetArrangementOfPattern(i)
        if (type(value) is not dict
                or any(value.get(k) != entry[k] for k in keys)):
            raise CommandError("scene_change_unverified")

        def numeric(text):
            if type(text) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", text):
                raise CommandError("invalid_native_result")
            number_value = float(text)
            if not math.isfinite(number_value) or abs(number_value) > 1e16:
                raise CommandError("invalid_native_result")
            return number_value

        try:
            self.modules["utility_api"].ReDrape3DArrangement(option)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "arrangement_name": entry["ArrangementName"],
                "offset": {"x": numeric(entry["ArrangementOffsetX"]),
                           "y": numeric(entry["ArrangementOffsetY"]),
                           "z": numeric(entry["ArrangementOffsetZ"])},
                "orientation": numeric(entry["ArrangementOrientation"]),
                "type": entry["ArrangementType"], "units": "native_unspecified",
                "redrape": True}

    def _set_arrangement_orientation(self, p):
        """Set one arranged piece's integer orientation, ReDrape; verify readback."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetArrangementOfPattern", "SetArrangementOrientation")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        keys = ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                "ArrangementOffsetZ", "ArrangementOrientation", "ArrangementType")
        baseline = self.pattern.GetArrangementOfPattern(i)
        if type(baseline) is not dict or set(baseline) != set(keys):
            raise CommandError("invalid_native_result")

        def numeric(text):
            if type(text) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", text):
                raise CommandError("invalid_native_result")
            number_value = float(text)
            if not math.isfinite(number_value) or abs(number_value) > 1e16:
                raise CommandError("invalid_native_result")
            return number_value

        for key in ("ArrangementOffsetX", "ArrangementOffsetY", "ArrangementOffsetZ"):
            numeric(baseline[key])
        numeric(baseline["ArrangementOrientation"])
        if (type(baseline["ArrangementName"]) is not str
                or type(baseline["ArrangementType"]) is not str):
            raise CommandError("invalid_native_result")
        option = self._drape_option()
        try:
            self.pattern.SetArrangementOrientation(i, p["orientation"])
        except Exception:
            raise CommandError("scene_change_unverified") from None
        value = self.pattern.GetArrangementOfPattern(i)
        unchanged = ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                     "ArrangementOffsetZ", "ArrangementType")
        if (type(value) is not dict or set(value) != set(keys)
                or any(value.get(key) != baseline[key] for key in unchanged)
                or numeric(value["ArrangementOrientation"]) != p["orientation"]):
            raise CommandError("scene_change_unverified")
        try:
            self.modules["utility_api"].ReDrape3DArrangement(option)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        final = self.pattern.GetArrangementOfPattern(i)
        if type(final) is not dict or set(final) != set(keys):
            raise CommandError("scene_change_unverified")
        orientation = numeric(final["ArrangementOrientation"])
        if orientation != p["orientation"]:
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "arrangement_name": baseline["ArrangementName"],
                "offset": {"x": numeric(baseline["ArrangementOffsetX"]),
                           "y": numeric(baseline["ArrangementOffsetY"]),
                           "z": numeric(baseline["ArrangementOffsetZ"])},
                "orientation": orientation,
                "type": baseline["ArrangementType"], "units": "native_unspecified",
                "redrape": True}

    def _set_arrangement_position(self, p):
        """Set one arranged piece's native x/y/z offsets, ReDrape; verify readback."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetArrangementOfPattern", "SetArrangementPosition")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        keys = ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                "ArrangementOffsetZ", "ArrangementOrientation", "ArrangementType")
        baseline = self.pattern.GetArrangementOfPattern(i)
        if type(baseline) is not dict or set(baseline) != set(keys):
            raise CommandError("invalid_native_result")

        def numeric(text):
            if type(text) is not str or not re.fullmatch(r"-?\d+(\.\d+)?", text):
                raise CommandError("invalid_native_result")
            number_value = float(text)
            if not math.isfinite(number_value) or abs(number_value) > 1e16:
                raise CommandError("invalid_native_result")
            return number_value

        for key in ("ArrangementOffsetX", "ArrangementOffsetY", "ArrangementOffsetZ"):
            numeric(baseline[key])
        numeric(baseline["ArrangementOrientation"])
        if (type(baseline["ArrangementName"]) is not str
                or type(baseline["ArrangementType"]) is not str):
            raise CommandError("invalid_native_result")
        requested = (p["position_x"], p["position_y"], p["offset"])
        option = self._drape_option()
        try:
            self.pattern.SetArrangementPosition(i, *requested)
        except Exception:
            raise CommandError("scene_change_unverified") from None

        def positions(value):
            if type(value) is not dict or set(value) != set(keys):
                raise CommandError("scene_change_unverified")
            try:
                return (numeric(value["ArrangementOffsetX"]),
                        numeric(value["ArrangementOffsetY"]),
                        numeric(value["ArrangementOffsetZ"]))
            except CommandError:
                raise CommandError("scene_change_unverified") from None

        def unchanged(value):
            return (value["ArrangementName"] == baseline["ArrangementName"]
                    and value["ArrangementOrientation"] == baseline["ArrangementOrientation"]
                    and value["ArrangementType"] == baseline["ArrangementType"])

        value = self.pattern.GetArrangementOfPattern(i)
        if positions(value) != requested or not unchanged(value):
            raise CommandError("scene_change_unverified")
        try:
            self.modules["utility_api"].ReDrape3DArrangement(option)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        final = self.pattern.GetArrangementOfPattern(i)
        if positions(final) != requested or not unchanged(final):
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "arrangement_name": baseline["ArrangementName"],
                "offset": {"x": float(requested[0]), "y": float(requested[1]),
                           "z": float(requested[2])},
                "orientation": numeric(baseline["ArrangementOrientation"]),
                "type": baseline["ArrangementType"], "units": "native_unspecified",
                "redrape": True}

    def _screenshot(self, p):
        """Capture the current 3D window to a caller-generated PNG path."""
        export = self.modules.get("export_api")
        if not callable(getattr(export, "ExportThumbnail3D", None)):
            raise CommandError("api_unavailable")
        path = p["output_path"]
        try:
            native = export.ExportThumbnail3D(path)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        try:
            same = (type(native) is str and native
                    and os.path.normcase(os.path.abspath(native))
                    == os.path.normcase(os.path.abspath(path)))
            size = os.path.getsize(path) if os.path.isfile(path) else 0
        except OSError:
            raise CommandError("invalid_native_result") from None
        if not same or not 0 < size <= 16777216:
            raise CommandError("invalid_native_result")
        return {"verified": True, "bytes": size}

    def _arrangement_library(self):
        """Read the avatar arrangement-point library with names and presets."""
        self._require("GetArrangementList")
        library = self.pattern.GetArrangementList()
        if type(library) is not list or len(library) > 4096:
            raise CommandError("invalid_native_result")
        points = []
        for i, entry in enumerate(library):
            value = self._arrangement_record(entry)
            points.append({"index": i, "name": value["ArrangementName"],
                           "type": value["ArrangementType"],
                           "offset": {"x": self._numeric_text(value["ArrangementOffsetX"]),
                                      "y": self._numeric_text(value["ArrangementOffsetY"]),
                                      "z": self._numeric_text(value["ArrangementOffsetZ"])},
                           "orientation": self._numeric_text(value["ArrangementOrientation"])})
        return {"library_count": len(points), "points": points,
                "units": "native_unspecified"}

    def _seamlines(self):
        """Read seam group count/names and per-pattern group membership."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetSeamlinePairGroupCount", "GetSeamlinePairGroupName",
                      "GetSeamlinePairGroupListInPattern")
        before = self._list()
        count = self.pattern.GetSeamlinePairGroupCount()
        if type(count) is not int or not 0 <= count <= 4096:
            raise CommandError("invalid_native_result")
        groups = []
        for i in range(count):
            group_name = self.pattern.GetSeamlinePairGroupName(i)
            if (type(group_name) is not str or not 1 <= len(group_name) <= 256
                    or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF
                           for c in group_name)):
                raise CommandError("invalid_native_result")
            groups.append({"index": i, "name": group_name})
        patterns = []
        for item in before["patterns"]:
            indices = self.pattern.GetSeamlinePairGroupListInPattern(item["index"])
            if (type(indices) is not list or len(indices) > count
                    or any(type(v) is not int or not 0 <= v < count for v in indices)):
                raise CommandError("invalid_native_result")
            patterns.append({"pattern_index": item["index"],
                             "pattern_name": item["name"],
                             "group_indices": indices,
                             "group_names": [groups[v]["name"] for v in indices]})
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"seam_count": count, "pattern_count": before["pattern_count"],
                "groups": groups, "patterns": patterns}

    @staticmethod
    def _field(value, key):
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    def _avatar_measurements(self, p):
        """Read one avatar's measurement names, types and lengths."""
        export = self.modules.get("export_api")
        utility = self.modules.get("utility_api")
        for name in ("GetAvatarCount", "GetAvatarNameList"):
            if not callable(getattr(export, name, None)):
                raise CommandError("api_unavailable")
        if not callable(getattr(utility, "GetAvatarMeasurements", None)):
            raise CommandError("api_unavailable")
        index = p["avatar_index"]
        count = export.GetAvatarCount()
        names = export.GetAvatarNameList()
        if (type(count) is not int or not 0 <= count <= MAX_AVATARS
                or type(names) is not list or len(names) != count):
            raise CommandError("invalid_native_result")
        if index >= count:
            raise CommandError("invalid_parameters")
        avatar_name = names[index]
        if (type(avatar_name) is not str or not 1 <= len(avatar_name) <= 128):
            raise CommandError("invalid_native_result")
        values = utility.GetAvatarMeasurements(index)
        if type(values) is not list or len(values) > 512:
            raise CommandError("invalid_native_result")
        measurements = []
        for value in values:
            measure_name = self._field(value, "measurementName")
            measure_type = self._field(value, "measurementType")
            unit = self._field(value, "unit")
            if (type(measure_name) is not str or not 1 <= len(measure_name) <= 256
                    or type(measure_type) is not str or not 1 <= len(measure_type) <= 32
                    or type(unit) is not str or not 1 <= len(unit) <= 8):
                raise CommandError("invalid_native_result")
            numbers = [self._field(value, key) for key in
                       ("value", "basicLength", "surfaceLength")]
            if not all(number(v) for v in numbers):
                raise CommandError("invalid_native_result")
            measurements.append({"name": measure_name, "type": measure_type,
                                 "value": float(numbers[0]),
                                 "basic_length": float(numbers[1]),
                                 "surface_length": float(numbers[2]),
                                 "unit": unit})
        return {"avatar_index": index, "avatar_name": avatar_name,
                "measurement_count": len(measurements),
                "measurements": measurements, "units": "native_display_unit"}

    def _attachments(self):
        """Read every pattern-to-avatar-measure attachment and the pin count."""
        self._require("GetAllPatternToAvatarMeasures", "GetPinListSize")
        values = self.pattern.GetAllPatternToAvatarMeasures()
        pin_count = self.pattern.GetPinListSize()
        if type(values) is not list or len(values) > 1024:
            raise CommandError("invalid_native_result")
        if type(pin_count) is not int or not 0 <= pin_count <= 65536:
            raise CommandError("invalid_native_result")
        pairs = []
        for item in values:
            if type(item) not in (tuple, list) or len(item) != 2:
                raise CommandError("invalid_native_result")
            pattern_name, avatar_measure = item
            if (type(pattern_name) is not str or not 1 <= len(pattern_name) <= 256
                    or type(avatar_measure) is not str
                    or not 1 <= len(avatar_measure) <= 256):
                raise CommandError("invalid_native_result")
            pairs.append({"pattern_name": pattern_name,
                          "avatar_measure": avatar_measure})
        return {"pair_count": len(pairs), "pin_count": pin_count, "pairs": pairs}

    def _set_arrangement_shape_style(self, p):
        """Set Flat/Curved arrangement style and verify the readback type."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "SetArrangementShapeStyle", "GetArrangementOfPattern")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        baseline = self._arrangement_record(self.pattern.GetArrangementOfPattern(i))
        style = p["style"]
        try:
            self.pattern.SetArrangementShapeStyle(i, style)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        value = self._arrangement_record(self.pattern.GetArrangementOfPattern(i))
        if value["ArrangementType"] != style:
            raise CommandError("scene_change_unverified")
        if any(value[key] != baseline[key] for key in
               ("ArrangementName", "ArrangementOffsetX", "ArrangementOffsetY",
                "ArrangementOffsetZ", "ArrangementOrientation")):
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "arrangement_name": baseline["ArrangementName"],
                "offset": {"x": self._numeric_text(baseline["ArrangementOffsetX"]),
                           "y": self._numeric_text(baseline["ArrangementOffsetY"]),
                           "z": self._numeric_text(baseline["ArrangementOffsetZ"])},
                "orientation": self._numeric_text(baseline["ArrangementOrientation"]),
                "type": value["ArrangementType"], "units": "native_unspecified"}

    def _set_edge_to_avatar_measure(self, p):
        """Attach/detach one pattern edge to an avatar measure and read back."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "SetPatternEdgeToAvatarMeasure",
                      "GetPatternEdgeToAvatarMeasureAttachment")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        lines = self._lines({"pattern_index": i, "expected_name": expected})
        line_index = p["line_index"]
        if line_index >= lines["line_count"]:
            raise CommandError("invalid_parameters")
        measure = p["avatar_measure"]
        attach = p["attach"]
        try:
            result = self.pattern.SetPatternEdgeToAvatarMeasure(
                i, line_index, measure, attach)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if type(result) is not bool:
            raise CommandError("invalid_native_result")
        if result is not True:
            raise CommandError("scene_change_unverified")
        raw = self.pattern.GetPatternEdgeToAvatarMeasureAttachment(i, measure)
        value = _line_json(raw)
        if set(value) != {"is_attached", "line_index"}:
            raise CommandError("invalid_native_result")
        attached, index_after = value["is_attached"], value["line_index"]
        if type(attached) is not bool or type(index_after) is not int:
            raise CommandError("invalid_native_result")
        if attach:
            if attached is not True or index_after != line_index:
                raise CommandError("scene_change_unverified")
        elif attached is not False or index_after != -1:
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "line_index": line_index, "avatar_measure": measure,
                "attached": attach}

    def _simulate(self, p):
        """Run one bounded cloth simulation and verify the scene list."""
        self._require("GetPatternCount", "GetPatternPieceName")
        export = self.modules.get("export_api")
        utility = self.modules.get("utility_api")
        if not callable(getattr(export, "GetAvatarCount", None)):
            raise CommandError("api_unavailable")
        if not callable(getattr(utility, "Simulate", None)):
            raise CommandError("api_unavailable")
        before = self._list()
        avatars = export.GetAvatarCount()
        if type(avatars) is not int or not 0 <= avatars <= MAX_AVATARS:
            raise CommandError("invalid_native_result")
        if avatars < 1:
            raise CommandError("invalid_parameters")
        steps = p["steps"]
        started = time.monotonic()
        try:
            result = utility.Simulate(steps)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        elapsed = round((time.monotonic() - started) * 1000, 3)
        if type(result) is not bool:
            raise CommandError("invalid_native_result")
        if result is not True:
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "steps": steps,
                "pattern_count": before["pattern_count"],
                "avatar_count": avatars, "elapsed_ms": elapsed}

    @staticmethod
    def _image_file_result(requested, native):
        """Validate an image in the requested directory; native text may be descriptive."""
        candidates = []
        if type(native) is str and native:
            candidates.append(native)
        candidates.append(requested)
        for candidate in candidates:
            try:
                same_dir = (os.path.normcase(os.path.dirname(os.path.abspath(candidate)))
                            == os.path.normcase(os.path.dirname(os.path.abspath(requested))))
                size = os.path.getsize(candidate) if os.path.isfile(candidate) else 0
            except OSError:
                continue
            file_name = os.path.basename(candidate)
            if (same_dir and 0 < size <= 16777216
                    and 1 <= len(file_name) <= 128
                    and "/" not in file_name and "\\" not in file_name):
                return {"file_name": file_name, "bytes": size}
        raise CommandError("invalid_native_result")

    def _export_view_image(self, p):
        """Render one standard 3D view to a caller-generated image path."""
        export = self.modules.get("export_api")
        for name in ("ExportStdViewImage", "GetCurrentColorwayIndex"):
            if not callable(getattr(export, name, None)):
                raise CommandError("api_unavailable")
        colorway = export.GetCurrentColorwayIndex()
        if type(colorway) is not int or colorway < 0:
            colorway = 0
        view, width, height = p["view"], p["width"], p["height"]
        path = p["output_path"]
        try:
            native = export.ExportStdViewImage(
                view, path, colorway, width, height, p["fit_all_objects"])
        except TypeError:
            # The 5-argument overload frames the garment only and is the donor-tested form.
            try:
                native = export.ExportStdViewImage(
                    view, path, colorway, width, height)
            except Exception:
                raise CommandError("scene_change_unverified") from None
        except Exception:
            raise CommandError("scene_change_unverified") from None
        result = self._image_file_result(path, native)
        return {"verified": True, "view": view, "width": width,
                "height": height, **result}

    def _export_snapshot_2d(self, p):
        """Capture the current 2D window to a caller-generated image path."""
        export = self.modules.get("export_api")
        if not callable(getattr(export, "ExportThumbnail2D", None)):
            raise CommandError("api_unavailable")
        path = p["output_path"]
        try:
            native = export.ExportThumbnail2D(path)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        result = self._image_file_result(path, native)
        return {"verified": True, **result}

    def _set_camera_view(self, p):
        """Set one standard 3D camera view, optionally zoom-to-fit."""
        utility = self.modules.get("utility_api")
        for name in ("SetCamViewPoint", "Refresh3DWindow"):
            if not callable(getattr(utility, name, None)):
                raise CommandError("api_unavailable")
        if p["zoom_to_fit"] and not callable(getattr(utility, "SetZoomView", None)):
            raise CommandError("api_unavailable")
        try:
            utility.SetCamViewPoint(p["view"])
            if p["zoom_to_fit"]:
                utility.SetZoomView()
            utility.Refresh3DWindow()
        except Exception:
            raise CommandError("command_error") from None
        return {"verified": True, "view": p["view"],
                "zoom_to_fit": p["zoom_to_fit"]}

    def _reset_cloth_arrangement(self):
        """Restore the cloth shape to its loaded state."""
        utility = self.modules.get("utility_api")
        if not callable(getattr(utility, "ResetClothArrangement", None)):
            raise CommandError("api_unavailable")
        before = self._list()
        try:
            utility.ResetClothArrangement()
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_count": before["pattern_count"]}

    def _import_avatar_measurements(self, p):
        """Apply a measurement CSV to the single current avatar and verify count growth."""
        export = self.modules.get("export_api")
        importer = self.modules.get("import_api")
        utility = self.modules.get("utility_api")
        for name in ("GetAvatarCount",):
            if not callable(getattr(export, name, None)):
                raise CommandError("api_unavailable")
        if not callable(getattr(importer, "ImportMeasurement", None)):
            raise CommandError("api_unavailable")
        if not callable(getattr(utility, "GetAvatarMeasurements", None)):
            raise CommandError("api_unavailable")
        count = export.GetAvatarCount()
        if type(count) is not int or count != 1:
            raise CommandError("invalid_parameters")
        path = p["csv_path"]
        try:
            if not os.path.isfile(path) or not 0 < os.path.getsize(path) <= 16777216:
                raise CommandError("invalid_parameters")
        except OSError:
            raise CommandError("invalid_parameters") from None
        before_values = utility.GetAvatarMeasurements(0)
        if type(before_values) is not list or len(before_values) > 512:
            raise CommandError("invalid_native_result")
        before = len(before_values)
        try:
            imported = importer.ImportMeasurement(path)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        if type(imported) is not bool:
            raise CommandError("invalid_native_result")
        if imported is not True:
            raise CommandError("scene_change_unverified")
        after_values = utility.GetAvatarMeasurements(0)
        if type(after_values) is not list or len(after_values) > 512:
            raise CommandError("scene_change_unverified")
        after = len(after_values)
        if after <= before:
            raise CommandError("scene_change_unverified")
        return {"verified": True, "avatar_index": 0, "before_count": before,
                "after_count": after, "added": after - before}

    def _pattern_body_details(self):
        """Read the native body-region/semantic JSON document."""
        self._require("GetPatternOnBodyDetails")
        data = _line_json(self.pattern.GetPatternOnBodyDetails())
        if set(data) != {"upperBody", "lowerBody"}:
            raise CommandError("invalid_native_result")
        if type(data["upperBody"]) is not list or type(data["lowerBody"]) is not list:
            raise CommandError("invalid_native_result")
        return data

    def _pattern_details(self, p):
        """Read grain direction, category and classification for one piece."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetPatternPieceGrainDirection", "GetPatternPieceCategory",
                      "GetPatternPieceClassification")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        grain = self.pattern.GetPatternPieceGrainDirection(i)
        category = self.pattern.GetPatternPieceCategory(i)
        classification = self.pattern.GetPatternPieceClassification(i)
        if (not number(grain) or type(category) is not int
                or not -1 <= category <= 999
                or type(classification) is not str or not 0 <= len(classification) <= 256):
            raise CommandError("invalid_native_result")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"pattern_index": i, "pattern_name": expected,
                "grain_direction": float(grain), "category": category,
                "classification": classification}

    def _set_pattern_grain_direction(self, p):
        """Set one piece's grain direction and verify readback plus geometry."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetPatternPieceGrainDirection",
                      "SetPatternPieceGrainDirection")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        geometry_before = self._geometry(i)
        degrees = p["degrees"]
        try:
            self.pattern.SetPatternPieceGrainDirection(i, degrees)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        value = self.pattern.GetPatternPieceGrainDirection(i)
        if not number(value):
            raise CommandError("invalid_native_result")
        if not math.isclose((float(value) - degrees) % 360, 0.0,
                            rel_tol=0, abs_tol=1e-3):
            raise CommandError("scene_change_unverified")
        geometry_after = self._geometry(i)
        if (not math.isclose(geometry_before["area_mm2"], geometry_after["area_mm2"],
                             rel_tol=1e-5, abs_tol=0.05)
                or any(not math.isclose(a, b, rel_tol=1e-5, abs_tol=0.05)
                       for a, b in zip(geometry_before["position_mm"],
                                       geometry_after["position_mm"]))):
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "grain_direction": float(value)}

    def _mesh_counts(self, p):
        """Read native mesh face/vertex text by mesh type."""
        self._require("GetPatternCount", "GetPatternPieceName", "GetMeshCountByType")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        value = self.pattern.GetMeshCountByType(i)
        if type(value) is not dict or len(value) > 16:
            raise CommandError("invalid_native_result")
        meshes = []
        for mesh_type, raw in value.items():
            if (type(mesh_type) is not str or not 1 <= len(mesh_type) <= 64
                    or type(raw) is not str or not 1 <= len(raw) <= 64):
                raise CommandError("invalid_native_result")
            meshes.append({"type": mesh_type, "value": raw})
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"pattern_index": i, "pattern_name": expected, "meshes": meshes}

    def _set_particle_distance(self, p):
        """Set one piece's simulation mesh size and verify readback."""
        self._require("GetPatternCount", "GetPatternPieceName",
                      "GetParticleDistanceOfPattern", "SetParticleDistanceOfPattern")
        before = self._list()
        i, expected = p["pattern_index"], p["expected_name"]
        items = before["patterns"]
        if (i >= len(items) or items[i]["name"] != expected
                or sum(v["name"] == expected for v in items) != 1):
            raise CommandError("stale_pattern")
        geometry_before = self._geometry(i)
        distance = p["distance"]
        try:
            self.pattern.SetParticleDistanceOfPattern(i, distance)
        except Exception:
            raise CommandError("scene_change_unverified") from None
        value = self.pattern.GetParticleDistanceOfPattern(i)
        if not number(value):
            raise CommandError("invalid_native_result")
        if not math.isclose(float(value), distance, rel_tol=1e-5, abs_tol=1e-3):
            raise CommandError("scene_change_unverified")
        geometry_after = self._geometry(i)
        if (not math.isclose(geometry_before["area_mm2"], geometry_after["area_mm2"],
                             rel_tol=1e-5, abs_tol=0.05)
                or any(not math.isclose(a, b, rel_tol=1e-5, abs_tol=0.05)
                       for a, b in zip(geometry_before["position_mm"],
                                       geometry_after["position_mm"]))):
            raise CommandError("scene_change_unverified")
        if self._list() != before:
            raise CommandError("inventory_changed")
        return {"verified": True, "pattern_index": i, "pattern_name": expected,
                "distance": float(value)}

    @staticmethod
    def _near(a, b):
        return math.isclose(a, b, rel_tol=1e-5, abs_tol=0.05)

    def __call__(self, command, params):
        validate_params(command, params)
        if command in ("get_fabric_list", "get_avatars"):
            return self.inventory(command, params)
        if command in ("get_pattern_fabric", "assign_pattern_fabric"):
            return self.fabric_assignment(command, params)
        started = time.monotonic()
        if command == "list_clo_api":
            result = {"modules": {n: sorted(k for k in dir(self.modules.get(n))
                       if k.isascii() and not k.startswith("_")
                       and callable(getattr(self.modules[n], k, None)))[:512]
                       if self.modules.get(n) is not None else [] for n in API_MODULES}}
        elif command == "describe_clo_api":
            module = self.modules.get(params["module"])
            result = {"module": params["module"], "functions": {}}
            for key in params["functions"]:
                function = getattr(module, key, None)
                doc = (getattr(function, "__doc__", None) or "")[:8192] if callable(function) else ""
                result["functions"][key] = {"available": callable(function), "doc": doc}
        elif command == "get_pattern_list":
            result = self._list()
        elif command == "get_pattern_geometry":
            result = {"pattern": self._geometry(params["pattern_index"])}
        elif command == "get_pattern_outline":
            result = self._outline(params)
        elif command == "get_pattern_lines":
            result = self._lines(params)
        elif command == "add_seamline_pair":
            result = self._seam(params)
        elif command == "import_avatar":
            result = self._import_avatar(params)
        elif command == "get_arrangement":
            result = self._arrangements()
        elif command == "set_arrangement":
            result = self._set_arrangement(params)
        elif command == "set_arrangement_orientation":
            result = self._set_arrangement_orientation(params)
        elif command == "set_arrangement_position":
            result = self._set_arrangement_position(params)
        elif command == "get_3d_screenshot":
            result = self._screenshot(params)
        elif command == "get_arrangement_list":
            result = self._arrangement_library()
        elif command == "get_seamline_pairs":
            result = self._seamlines()
        elif command == "get_avatar_measurements":
            result = self._avatar_measurements(params)
        elif command == "get_pattern_avatar_attachments":
            result = self._attachments()
        elif command == "set_arrangement_shape_style":
            result = self._set_arrangement_shape_style(params)
        elif command == "set_pattern_edge_to_avatar_measure":
            result = self._set_edge_to_avatar_measure(params)
        elif command == "simulate":
            result = self._simulate(params)
        elif command == "export_view_image":
            result = self._export_view_image(params)
        elif command == "export_snapshot_2d":
            result = self._export_snapshot_2d(params)
        elif command == "set_camera_view":
            result = self._set_camera_view(params)
        elif command == "reset_cloth_arrangement":
            result = self._reset_cloth_arrangement()
        elif command == "import_avatar_measurements":
            result = self._import_avatar_measurements(params)
        elif command == "get_pattern_body_details":
            result = self._pattern_body_details()
        elif command == "get_pattern_details":
            result = self._pattern_details(params)
        elif command == "set_pattern_grain_direction":
            result = self._set_pattern_grain_direction(params)
        elif command == "get_mesh_counts":
            result = self._mesh_counts(params)
        elif command == "set_particle_distance":
            result = self._set_particle_distance(params)
        else:
            result = self._mutate(command, params)
            # Includes preflight, native setter(s) AND verification reads, not
            # pure native API duration. End-to-end client latency is separate.
            result["executor_ms"] = round((time.monotonic() - started) * 1000, 3)
        validate_result(command, result)
        return result

    def _mutate(self, command, p):
        # Probe required readback methods BEFORE making any change.
        self._require("GetPatternPieceName", "GetPatternPiecePos", "GetPatternPieceArea",
                      "GetBoundingBoxOfPattern")
        before = self._list()
        if command == "create_pattern":
            self._require("CreatePatternWithPoints", "SetPatternPieceName")
            self._new_name(p["name"])
            if before["pattern_count"] >= MAX_PATTERNS:
                raise CommandError("stale_pattern")
            # Read one existing piece to verify conversion of this build's
            # geometry records before mutating, when the scene isn't empty.
            if before["patterns"]:
                self._geometry(0)
            types = p.get("vertex_types")
            if types is None:
                types = [0] * len(p["points"])
            mutate = lambda: self.pattern.CreatePatternWithPoints(
                [(float(x), float(y), int(t))
                 for (x, y), t in zip(p["points"], types)])
        else:
            i = self._target(p)
            old = self._geometry(i)
            if command == "set_pattern_name":
                self._require("SetPatternPieceName")
                self._new_name(p["name"], i)
                mutate = lambda: self.pattern.SetPatternPieceName(i, p["name"])
            elif command == "move_pattern_relative":
                self._require("SetPatternPieceMove")
                if not all(number(a + b) for a, b in zip(old["position_mm"], (p["dx"], p["dy"]))):
                    raise CommandError("invalid_parameters")
                mutate = lambda: self.pattern.SetPatternPieceMove(i, float(p["dx"]), float(p["dy"]))
            elif command == "copy_pattern_with_offset":
                self._require("CopyPatternPieceMove", "SetPatternPieceName")
                self._new_name(p["name"])
                if before["pattern_count"] >= MAX_PATTERNS:
                    raise CommandError("stale_pattern")
                if not all(number(a + b) for a, b in zip(old["position_mm"], (p["dx"], p["dy"]))):
                    raise CommandError("invalid_parameters")
                mutate = lambda: self.pattern.CopyPatternPieceMove(i, float(p["dx"]), float(p["dy"]))
            else:
                self._require("DeletePatternPiece")
                mutate = lambda: self.pattern.DeletePatternPiece(i)
        # Once a native setter is entered, every exception may be post-change.
        # Never roll back or repeat it automatically.
        try:
            native_result = mutate()
            after = self._list()
            if command in ("create_pattern", "copy_pattern_with_offset"):
                if after["pattern_count"] != before["pattern_count"] + 1:
                    raise ValueError()
                if command == "copy_pattern_with_offset":
                    if type(native_result) is not int or not 0 <= native_result < after["pattern_count"]:
                        raise ValueError()
                    i = native_result
                else:
                    i = before["pattern_count"]
                # Verify insertion preserved other pieces' order/names.
                names_after = [v["name"] for v in after["patterns"]]
                if names_after[:i] + names_after[i + 1:] != [v["name"] for v in before["patterns"]]:
                    raise ValueError()
                self.pattern.SetPatternPieceName(i, p["name"])
            elif command == "delete_pattern":
                expected = [v["name"] for v in before["patterns"]]
                del expected[i]
                if [v["name"] for v in after["patterns"]] != expected:
                    raise ValueError()
                return {"verified": True, "pattern_count": after["pattern_count"],
                        "deleted_name": p["expected_name"]}
            elif after["pattern_count"] != before["pattern_count"]:
                raise ValueError()
            new = self._geometry(i)
            final_list = self._list()
            expected_names = [v["name"] for v in before["patterns"]]
            if command in ("create_pattern", "copy_pattern_with_offset"):
                expected_names.insert(i, p["name"])
            elif command == "set_pattern_name":
                expected_names[i] = p["name"]
            if [v["name"] for v in final_list["patterns"]] != expected_names:
                raise ValueError()
            if command in ("create_pattern", "copy_pattern_with_offset", "set_pattern_name"):
                if new["name"] != p["name"]:
                    raise ValueError()
            if command in ("move_pattern_relative", "copy_pattern_with_offset"):
                if (not all(self._near(a + b, c) for a, b, c in zip(
                        old["position_mm"], (p["dx"], p["dy"]), new["position_mm"]))
                        or not self._near(old["area_mm2"], new["area_mm2"])):
                    raise ValueError()
            if command == "set_pattern_name" and (new["position_mm"] != old["position_mm"]
                    or not self._near(old["area_mm2"], new["area_mm2"])):
                raise ValueError()
            if command == "create_pattern":
                types = p.get("vertex_types")
                straight = types is None or all(t == 0 for t in types)
                if straight:
                    points = p["points"]
                    area = abs(sum(a[0] * b[1] - b[0] * a[1]
                                   for a, b in zip(points, points[1:] + points[:1]))) / 2
                    if not self._near(area, new["area_mm2"]):
                        raise ValueError()
            return {"verified": True, "pattern_count": final_list["pattern_count"], "pattern": new}
        except Exception:
            raise CommandError("scene_change_unverified") from None
