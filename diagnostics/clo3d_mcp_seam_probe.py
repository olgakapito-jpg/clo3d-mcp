"""Manual one-shot whole-line seam probe; NOT an MCP tool.

Uses own MCP_SEAM_A/MCP_SEAM_B rectangles, lineIndex 0 on each, one
AddSeamlinePairGroup call, then reads seam count/connectivity and verifies lines
and geometry are unchanged. Bounded, no retries. Run once in Script Editor with
the verified service idle. See docs/CLO_SEAMLINING_CHECK.md.
"""

import json


NAME_A = "MCP_SEAM_A"
NAME_B = "MCP_SEAM_B"
LINE = 0
MAX_BYTES = 65536


def finite(value):
    return type(value) in (int, float) and value == value and abs(value) <= 1e16


def line_snapshot(pattern, index):
    value = pattern.GetPatternLineInfo(index)
    if type(value) is not str or not 1 <= len(value) <= MAX_BYTES:
        return {"type": type(value).__name__}
    try:
        data = json.loads(value)
    except (ValueError, RecursionError):
        return {"json": "invalid"}
    if type(data) is not dict or data.get("status") != "success":
        return {"json": "not_success"}
    lines = data.get("lines")
    if type(lines) is not list:
        return {"json": "no_lines"}
    return {"line_count": len(lines),
            "lengths": [float(item["length"]) for item in lines
                        if type(item) is dict and finite(item.get("length"))]}


def geometry_snapshot(pattern, index):
    area = pattern.GetPatternPieceArea(index)
    box = pattern.GetBoundingBoxOfPattern(index)
    return {"area": float(area) if finite(area) else None,
            "bbox": box if isinstance(box, dict) else None}


def connectivity(pattern):
    value = pattern.GetPatternGroupsBySeamlineConnectivity(False, False)
    if type(value) is not str or len(value) > MAX_BYTES:
        return {"type": type(value).__name__}
    try:
        data = json.loads(value)
    except (ValueError, RecursionError):
        return {"json": "invalid"}
    if type(data) is not dict:
        return {"json": "not_object"}
    return {"status": data.get("status") if type(data.get("status")) is str else None,
            "group_count": data.get("groupCount") if type(data.get("groupCount")) is int else None}


def collect(pattern):
    report = {"schema": "clo_seam_probe_v1", "status": "blocked",
              "evidence": "single_whole_line_seam_not_acceptance", "calls": 0}
    try:
        count = pattern.GetPatternCount()
        names = [pattern.GetPatternPieceName(i) for i in range(count)]
        if names.count(NAME_A) != 1 or names.count(NAME_B) != 1:
            return dict(report, stop_reason="own_seam_fixtures_missing_or_ambiguous")
        a, b = names.index(NAME_A), names.index(NAME_B)
        before_a = line_snapshot(pattern, a)
        before_b = line_snapshot(pattern, b)
        if before_a.get("line_count", 0) <= LINE or before_b.get("line_count", 0) <= LINE:
            return dict(report, stop_reason="own_line_index_missing")
        seams_before = pattern.GetSeamlinePairGroupCount()
        if type(seams_before) is not int:
            return dict(report, stop_reason="unexpected_seam_count")
        report.update(index_a=a, index_b=b, line_a=LINE, line_b=LINE,
                      seams_before=seams_before,
                      geometry_before={"a": geometry_snapshot(pattern, a),
                                       "b": geometry_snapshot(pattern, b)},
                      lines_before={"a": before_a, "b": before_b})
        report["calls"] = 1
        result = pattern.AddSeamlinePairGroup(a, LINE, b, LINE, True, True)
        report["native_return_type"] = type(result).__name__
        if type(result) is bool:
            report["native_return"] = result
        elif type(result) is int:
            report["native_return_int"] = result
        seams_after = pattern.GetSeamlinePairGroupCount()
        report["seams_after"] = seams_after if type(seams_after) is int else None
        report["lines_after"] = {"a": line_snapshot(pattern, a), "b": line_snapshot(pattern, b)}
        report["geometry_after"] = {"a": geometry_snapshot(pattern, a),
                                    "b": geometry_snapshot(pattern, b)}
        report["connectivity_after"] = connectivity(pattern)
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_seam_probe_v1", "status": "blocked", "calls": 0}
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
        runs = getattr(builtins, "_clo3d_mcp_seam_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_seam_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16 or runtime.session_id in runs:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            return collect(pattern_api)
        finally:
            runtime.busy = False
    except Exception:
        return dict(blocked, stop_reason="runtime_guard_error_no_retry")


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
