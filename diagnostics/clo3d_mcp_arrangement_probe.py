"""Manual one-shot arrangement read probe; NOT an MCP tool.

Reads GetArrangementList and GetArrangementOfPattern for every current piece
(up to 32), reporting only keys and value types/numbers, never pattern names or
free strings. Run once in Script Editor with the verified service idle.
See docs/CLO_FIT_CHECK.md.
"""

import json


MAX_PIECES = 32


def kind(value):
    for cls, label in ((dict, "dict"), (list, "list"), (str, "str"),
                       (bool, "bool"), (int, "int"), (float, "float"),
                       (type(None), "null")):
        if type(value) is cls:
            return label
    return "other"


def sanitize(value):
    """Field-name keys plus numeric/bool values; strings only as type/len."""
    if type(value) is not dict:
        return {"type": kind(value)}
    report = {"keys": sorted(value), "fields": {}}
    for key, item in value.items():
        entry = {"type": kind(item)}
        if type(item) in (int, float, bool):
            entry["value"] = item
        elif type(item) is str:
            entry["length"] = len(item)
        elif type(item) in (list, dict):
            entry["length"] = len(item)
        report["fields"][key] = entry
    return report


def collect(pattern):
    report = {"schema": "clo_arrangement_probe_v1", "status": "blocked",
              "evidence": "single_read_not_fit_acceptance"}
    try:
        count = pattern.GetPatternCount()
        if type(count) is not int or not 0 <= count <= MAX_PIECES:
            return dict(report, stop_reason="unexpected_count")
        report["count"] = count
        listing = pattern.GetArrangementList()
        report["list_type"] = kind(listing)
        report["list_length"] = len(listing) if type(listing) is list else None
        pieces = []
        for index in range(count):
            value = pattern.GetArrangementOfPattern(index)
            pieces.append({"index": index, "arrangement": sanitize(value)})
        report["pieces"] = pieces
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_arrangement_probe_v1", "status": "blocked"}
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
        runs = getattr(builtins, "_clo3d_mcp_arrangement_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_arrangement_probe_runs = runs
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
