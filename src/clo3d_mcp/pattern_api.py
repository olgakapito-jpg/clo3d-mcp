"""Explicit CLO pattern adapter; never imports CLO modules or legacy listener.

Constructed by launcher with existing embedded modules. Invoked ONLY by the
verified UI executor. A setter plus readback is not an atomic transaction.
"""

import json
import math
import time

from clo3d_mcp.pattern_contract import (
    API_MODULES, MAX_LINE_JSON_BYTES, MAX_LINES, MAX_PATTERNS, CommandError, number,
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
            mutate = lambda: self.pattern.CreatePatternWithPoints(
                [(float(x), float(y), 0) for x, y in p["points"]])
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
                points = p["points"]
                area = abs(sum(a[0] * b[1] - b[0] * a[1]
                               for a, b in zip(points, points[1:] + points[:1]))) / 2
                if not self._near(area, new["area_mm2"]):
                    raise ValueError()
            return {"verified": True, "pattern_count": final_list["pattern_count"], "pattern": new}
        except Exception:
            raise CommandError("scene_change_unverified") from None
