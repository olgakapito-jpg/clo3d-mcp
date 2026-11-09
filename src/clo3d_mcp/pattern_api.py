"""Explicit CLO pattern adapter; never imports CLO modules or legacy listener.

Constructed by launcher with existing embedded modules. Invoked ONLY by the
verified UI executor. A setter plus readback is not an atomic transaction.
"""

import math
import time

from clo3d_mcp.pattern_contract import (
    API_MODULES, MAX_PATTERNS, CommandError, number,
    validate_params, validate_result,
)
from clo3d_mcp.inventory_api import InventoryAPI
from clo3d_mcp.fabric_assignment_api import FabricAssignmentAPI


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
