"""Manual one-shot ReDrape probe using ApiTypes.ImportExportOption; NOT an MCP tool.

Builds the option via the documented ApiTypes type (export_api factories are
unavailable), enables arrangement/fitting-suit flags, calls
ReDrape3DArrangement once, then reports counts. The user checks 3D; simulation/
fit has no objective MCP getter. Run once in Script Editor with the service idle.
"""

import json


def collect(pattern, utility, api_types):
    report = {"schema": "clo_redrape_probe_v1", "status": "blocked",
              "evidence": "single_redrape_call_visual_only"}
    try:
        if not hasattr(api_types, "ImportExportOption"):
            return dict(report, stop_reason="api_types_option_unavailable")
        avatars = utility.GetAvatarCount()
        count = pattern.GetPatternCount()
        if type(avatars) is not int or avatars < 1:
            return dict(report, stop_reason="avatar_required")
        if type(count) is not int or not 1 <= count <= 256:
            return dict(report, stop_reason="unexpected_pattern_count")
        try:
            option = api_types.ImportExportOption()
        except Exception:
            return dict(report, stop_reason="option_construct_failed")
        flags = []
        for name, value in (("bAddArrangementPoints", True),
                            ("bAutoCreateFittingSuit", True),
                            ("bMoveGarment", True)):
            if hasattr(option, name):
                try:
                    setattr(option, name, value)
                    flags.append(name)
                except Exception:
                    pass
        report.update(avatar_count=avatars, pattern_count=count, flags=flags)
        try:
            result = utility.ReDrape3DArrangement(option)
        except Exception:
            return dict(report, status="command_error", stop_reason="native_exception_no_retry")
        report["native_return_type"] = type(result).__name__
        report["pattern_count_after"] = pattern.GetPatternCount()
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_redrape_probe_v1", "status": "blocked"}
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
        runs = getattr(builtins, "_clo3d_mcp_redrape_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_redrape_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16 or runtime.session_id in runs:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            import utility_api
            import ApiTypes
            return collect(pattern_api, utility_api, ApiTypes)
        finally:
            runtime.busy = False
    except Exception:
        return dict(blocked, stop_reason="runtime_guard_error_no_retry")


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
