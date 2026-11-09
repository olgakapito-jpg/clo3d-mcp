"""Manual one-shot arrangement-list read; NOT an MCP tool.

Prints the 110 library entries (arrangement preset names/type/offset/orientation)
so we can choose SetArrangement indices. Read-only, one-shot, no retry.
Run once in Script Editor with the verified service idle.
"""

import json


MAX_ENTRIES = 110


def kind(value):
    return type(value).__name__


def entry(value):
    if type(value) is not dict:
        return {"type": kind(value)}
    fields = {}
    for key, item in value.items():
        if type(item) is str:
            fields[key] = item if len(item) <= 64 and all(ord(c) >= 32 for c in item) else {
                "type": "str", "length": len(item)}
        elif type(item) in (int, float, bool):
            fields[key] = item
        else:
            fields[key] = {"type": kind(item)}
    return fields


def collect(pattern):
    report = {"schema": "clo_arrangement_list_probe_v1", "status": "blocked"}
    try:
        values = pattern.GetArrangementList()
        if type(values) is not list or len(values) > MAX_ENTRIES:
            return dict(report, stop_reason="unexpected_arrangement_list")
        report["entries"] = [entry(value) for value in values]
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_arrangement_list_probe_v1", "status": "blocked"}
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
        runs = getattr(builtins, "_clo3d_mcp_arrangement_list_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_arrangement_list_probe_runs = runs
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
