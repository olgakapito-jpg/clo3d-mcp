"""Manual one-shot base-shape curve probe; NOT an MCP tool or production adapter.

Creates ONE own rectangle, then applies CreateBaseShapeWithPoints variants with
straight/spline/Bezier vertex types and reads geometry/lines/internal-shape
count. Bounded, no retries. Run once in Script Editor with the verified service
idle. See docs/CLO_LINE_API_CONTRACT_REVIEW.md.
"""

import json


NAME = "MCP_BASESHAPE_PROBE"
POINTS = [[3000.0, 1000.0], [3120.0, 1000.0], [3120.0, 1080.0], [3000.0, 1080.0]]
MAX_BYTES = 65536


def finite(value):
    return type(value) in (int, float) and value == value and abs(value) <= 1e16


def line_summary(value):
    if type(value) is not str or not 1 <= len(value) <= MAX_BYTES:
        return {"type": type(value).__name__}
    try:
        data = json.loads(value)
    except (ValueError, RecursionError):
        return {"type": "str", "json": "invalid"}
    if type(data) is not dict:
        return {"type": "str", "json": "not_object"}
    lines = data.get("lines")
    summary = {"json": "object", "status": data.get("status") if type(data.get("status")) is str else None,
               "line_count": data.get("lineCount") if type(data.get("lineCount")) is int else None}
    if type(lines) is list:
        summary["lengths"] = [float(item["length"]) for item in lines
                              if type(item) is dict and finite(item.get("length"))][:64]
    return summary


def snapshot(pattern, utility, index):
    area = pattern.GetPatternPieceArea(index)
    box = pattern.GetBoundingBoxOfPattern(index)
    internal = utility.GetInternalShapeInformation(index)
    return {
        "area": float(area) if finite(area) else None,
        "bbox": box if isinstance(box, dict) else type(box).__name__,
        "internal_shapes": len(internal) if isinstance(internal, list) else None,
        "lines": line_summary(pattern.GetPatternLineInfo(index)),
    }


def typed(types):
    return [(float(x), float(y), int(t)) for (x, y), t in zip(POINTS, types)]


def collect(pattern, utility):
    report = {"schema": "clo_base_shape_probe_v1", "status": "blocked",
              "evidence": "single_sequence_not_acceptance", "steps": []}
    try:
        before = pattern.GetPatternCount()
        if type(before) is not int or not 0 <= before < 255:
            return dict(report, stop_reason="unexpected_count")
        names = [pattern.GetPatternPieceName(i) for i in range(before)]
        if NAME in names:
            return dict(report, stop_reason="own_fixture_already_exists")
        created = pattern.CreatePatternWithPoints([(x, y, 0) for x, y in POINTS])
        after = pattern.GetPatternCount()
        if type(after) is not int or after != before + 1:
            return dict(report, status="command_error", stop_reason="create_not_verified")
        index = before
        pattern.SetPatternPieceName(index, NAME)
        report["created_index"] = index
        report["steps"].append({"step": "created", **snapshot(pattern, utility, index)})
        variants = [
            ("same_straight", [0, 0, 0, 0]),
            ("one_spline", [0, 2, 0, 0]),
            ("two_spline", [0, 2, 0, 2]),
            ("one_bezier", [0, 3, 0, 0]),
            ("two_bezier", [0, 3, 0, 3]),
        ]
        for label, types in variants:
            result = pattern.CreateBaseShapeWithPoints(index, typed(types), True)
            report["steps"].append({
                "step": label, "return_type": type(result).__name__,
                "return": result if type(result) is int else None,
                **snapshot(pattern, utility, index),
            })
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_base_shape_probe_v1", "status": "blocked", "steps": []}
    registry = getattr(builtins, "_clo3d_mcp_service", None)
    if type(registry) is not dict or registry.get("version") != 1 or registry.get("current") is None:
        return dict(blocked, stop_reason="verified_service_required")
    runtime = registry["current"]
    try:
        if (runtime.profile != "service" or runtime.state != "active"
                or not runtime.service_ready or runtime.busy
                or runtime.executor is None or runtime.executor.state != "ready"):
            return dict(blocked, stop_reason="idle_service_required")
        if (runtime.timer.thread_id() != runtime.owner_thread
                or runtime.callback_thread != runtime.owner_thread
                or runtime.timer.visible_window_threads() != {runtime.owner_thread}):
            return dict(blocked, stop_reason="verified_ui_thread_required")
        runs = getattr(builtins, "_clo3d_mcp_base_shape_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_base_shape_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16 or runtime.session_id in runs:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            import utility_api
            return collect(pattern_api, utility_api)
        finally:
            runtime.busy = False
    except Exception:
        return dict(blocked, stop_reason="runtime_guard_error_no_retry")


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
