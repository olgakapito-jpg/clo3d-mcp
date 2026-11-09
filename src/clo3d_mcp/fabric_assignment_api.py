"""Explicit Object Browser fabric relationships; verified UI executor only.

No imports of native modules, fallback, retry or rollback. Assign option is fixed
to 1; no cross-colorway/material-link management. Indices/names are stale guards,
not persistent identities. Multiple native reads are not an atomic snapshot.
"""

import time

from clo3d_mcp.pattern_contract import CommandError, MAX_FABRICS, validate_result


class FabricAssignmentAPI:
    def __init__(self, patterns):
        self.patterns = patterns

    def _require(self, mutation):
        self.patterns._require("GetPatternCount", "GetPatternPieceName")
        names = ["GetFabricCount", "GetFabricName", "GetFabricIndexForPattern"]
        if mutation:
            names.append("AssignFabricToPattern")
            self.patterns._require("GetPatternPiecePos", "GetPatternPieceArea",
                                   "GetBoundingBoxOfPattern")
        return self.patterns.inventory._require("fabric_api", names)

    @staticmethod
    def _index(value, count):
        # No undocumented -1/unassigned sentinel or bool/int conversion.
        if type(value) is not int or not 0 <= value < count <= MAX_FABRICS:
            raise CommandError("invalid_native_result")
        return value

    def _snapshot(self):
        return (self.patterns._list(), self.patterns.inventory._fabrics())

    @staticmethod
    def _target(p, patterns):
        items = patterns["patterns"]
        i = p["pattern_index"]
        if (i >= len(items) or items[i]["name"] != p["expected_name"]
                or sum(v["name"] == p["expected_name"] for v in items) != 1):
            raise CommandError("stale_pattern")
        return i

    def read(self, p):
        fabric_api = self._require(False)
        patterns, fabrics = self._snapshot()
        i = self._target(p, patterns)
        f = self._index(fabric_api.GetFabricIndexForPattern(i), fabrics["fabric_count"])
        if self._index(fabric_api.GetFabricIndexForPattern(i), fabrics["fabric_count"]) != f:
            raise CommandError("inventory_changed")
        if self._snapshot() != (patterns, fabrics):
            raise CommandError("inventory_changed")
        return {"pattern_index": i, "pattern_name": p["expected_name"],
                "fabric_index": f, "fabric_name": fabrics["fabrics"][f]["name"]}

    def assign(self, p):
        started = time.monotonic()
        fabric_api = self._require(True)
        patterns, fabrics = self._snapshot()
        i = self._target(p, patterns)
        f = p["fabric_index"]
        if (f >= fabrics["fabric_count"]
                or fabrics["fabrics"][f]["name"] != p["expected_fabric_name"]
                or sum(v["name"] == p["expected_fabric_name"]
                       for v in fabrics["fabrics"]) != 1):
            raise CommandError("stale_fabric")
        count = fabrics["fabric_count"]
        before = [self._index(fabric_api.GetFabricIndexForPattern(j), count)
                  for j in range(patterns["pattern_count"])]
        if before[i] != p["expected_current_fabric_index"]:
            raise CommandError("stale_fabric")
        old = self.patterns._geometry(i)
        if self._snapshot() != (patterns, fabrics):
            raise CommandError("inventory_changed")
        # Recheck every mapping before entry; no hidden setters in preflight.
        if [self._index(fabric_api.GetFabricIndexForPattern(j), count)
                for j in range(patterns["pattern_count"])] != before:
            raise CommandError("inventory_changed")
        try:
            # Explicit 3-arg overload: Object Browser fabric, pattern, option1.
            # Even False/exception can be post-effect: no retry or cleanup.
            if fabric_api.AssignFabricToPattern(f, i, 1) is not True:
                raise ValueError()
            expected = list(before)
            expected[i] = f
            for _ in range(2):
                observed = [self._index(fabric_api.GetFabricIndexForPattern(j), count)
                            for j in range(patterns["pattern_count"])]
                if observed != expected or self._snapshot() != (patterns, fabrics):
                    raise ValueError()
            new = self.patterns._geometry(i)
            if (new["name"] != old["name"] or new["position_mm"] != old["position_mm"]
                    or not self.patterns._near(new["area_mm2"], old["area_mm2"])
                    or new["bounding_box"] != old["bounding_box"]):
                raise ValueError()
            result = {"verified": True, "pattern_index": i,
                      "pattern_name": p["expected_name"], "fabric_index": f,
                      "fabric_name": p["expected_fabric_name"],
                      "previous_fabric_index": before[i],
                      "executor_ms": round((time.monotonic() - started) * 1000, 3)}
            validate_result("assign_pattern_fabric", result)
            return result
        except Exception:
            raise CommandError("scene_change_unverified") from None

    def __call__(self, command, params):
        try:
            result = self.read(params) if command == "get_pattern_fabric" else self.assign(params)
        except CommandError:
            raise
        except Exception:
            raise CommandError("command_error") from None
        validate_result(command, result)
        return result
