"""Manual one-shot short simulation probe; NOT an MCP tool.

Calls utility_api.Simulate(STEPS) once on the verified idle service, then reads
back counts/names only. Visual drape evidence; one-shot, no retry. Run once with
a verified idle service and an explicit user simulation permission.
"""

import json
import time


STEPS = 60
SCHEMA = "clo_simulate_probe_v1"


def collect(pattern, export_api, utility):
    report = {"schema": SCHEMA, "status": "blocked",
              "evidence": "single_simulate_visual_only", "stage": "preflight"}
    try:
        count = pattern.GetPatternCount()
        if type(count) is not int or not 1 <= count <= 256:
            return dict(report, stop_reason="unexpected_pattern_count")
        names = [pattern.GetPatternPieceName(i) for i in range(count)]
        if any(type(name) is not str for name in names):
            return dict(report, stop_reason="invalid_pattern_names")
        avatars = export_api.GetAvatarCount()
        if type(avatars) is not int or avatars < 1:
            return dict(report, stop_reason="avatar_required")
        report.update(pattern_count=count, avatar_count=avatars, steps=STEPS,
                      stage="simulate")
        started = time.monotonic()
        try:
            result = utility.Simulate(STEPS)
        except Exception as exc:
            return dict(report, status="command_error",
                        stop_reason="simulate_no_retry",
                        error_type=type(exc).__name__,
                        elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        elapsed_ms = round((time.monotonic() - started) * 1000, 3)
        if type(result) is not bool:
            return dict(report, status="command_error",
                        stop_reason="invalid_native_result",
                        native_return_type=type(result).__name__,
                        elapsed_ms=elapsed_ms)
        after_count = pattern.GetPatternCount()
        after_names = [pattern.GetPatternPieceName(i) for i in range(after_count)] \
            if type(after_count) is int and 0 <= after_count <= 256 else None
        report.update(status="observed", native_return_type="bool",
                      native_return=result, elapsed_ms=elapsed_ms,
                      pattern_count_after=after_count,
                      names_unchanged=(after_names == names),
                      stop_reason="stop_no_retry")
        return report
    except Exception as exc:
        return dict(report, status="command_error",
                    stop_reason="native_exception_no_retry",
                    error_type=type(exc).__name__)


def run_probe():
    import builtins
    blocked = {"schema": SCHEMA, "status": "blocked"}
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
        runs = getattr(builtins, "_clo3d_mcp_simulate_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_simulate_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16 or runtime.session_id in runs:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            import export_api
            import utility_api
            return collect(pattern_api, export_api, utility_api)
        finally:
            runtime.busy = False
    except Exception:
        return dict(blocked, stop_reason="runtime_guard_error_no_retry")


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
