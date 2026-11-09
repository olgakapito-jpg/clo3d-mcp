"""Manual one-shot arrangement assignment + ReDrape probe; NOT an MCP tool.

Assigns fixed avatar arrangement points to the five own pieces via
SetArrangement, then calls ReDrape3DArrangement once with ApiTypes option.
Visual-only evidence; one-shot, no retry. Run once with verified idle service.
"""

import json


ASSIGNMENT = {
    "MCP_3D_TEST": 59,
    "MCP_SEAM_A": 60,
    "MCP_SEAM_B": 43,
    "MCP_SEAM_C": 6,
    "MCP_SEAM_D": 0,
}
MAX_ENTRIES = 110


def collect(pattern, export_api, utility, api_types):
    report = {"schema": "clo_arrange_probe_v1", "status": "blocked",
              "evidence": "single_assignment_sequence_visual_only", "stage": "preflight"}
    try:
        count = pattern.GetPatternCount()
        if type(count) is not int or not 1 <= count <= 256:
            return dict(report, stop_reason="unexpected_pattern_count")
        names = [pattern.GetPatternPieceName(i) for i in range(count)]
        library = pattern.GetArrangementList()
        if type(library) is not list or not 0 < len(library) <= MAX_ENTRIES:
            return dict(report, stop_reason="unexpected_arrangement_list")
        targets = []
        for name, arrangement_index in ASSIGNMENT.items():
            if names.count(name) != 1:
                return dict(report, stop_reason="own_fixture_missing_or_ambiguous")
            if not 0 <= arrangement_index < len(library):
                return dict(report, stop_reason="arrangement_index_out_of_range")
            targets.append((names.index(name), name, arrangement_index))
        avatars = export_api.GetAvatarCount()
        if type(avatars) is not int or avatars < 1:
            return dict(report, stop_reason="avatar_required")
        report.update(avatar_count=avatars, pattern_count=count, stage="assign")
        applied = []
        for index, name, arrangement_index in targets:
            try:
                pattern.SetArrangement(index, arrangement_index)
            except Exception as exc:
                return dict(report, status="command_error", stop_reason="set_arrangement_no_retry",
                            stage="assign", applied=applied, error_type=type(exc).__name__)
            value = pattern.GetArrangementOfPattern(index)
            if type(value) is not dict:
                return dict(report, status="command_error", stop_reason="arrangement_readback_failed",
                            stage="assign", applied=applied)
            applied.append({"name": name, "index": index,
                            "arrangement_index": arrangement_index,
                            "assigned_name": value.get("ArrangementName")
                            if type(value.get("ArrangementName")) is str else None})
        report.update(applied=applied, stage="redrape")
        try:
            option = api_types.ImportExportOption()
        except Exception:
            return dict(report, status="observed", stop_reason="option_construct_failed")
        flags = []
        for flag in ("bAddArrangementPoints", "bAutoCreateFittingSuit", "bMoveGarment"):
            if hasattr(option, flag):
                try:
                    setattr(option, flag, True)
                    flags.append(flag)
                except Exception:
                    pass
        try:
            utility.ReDrape3DArrangement(option)
        except Exception as exc:
            return dict(report, status="command_error", stop_reason="redrape_no_retry",
                        stage="redrape", flags=flags, error_type=type(exc).__name__)
        report.update(flags=flags, native_return_type="NoneType")
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception as exc:
        return dict(report, status="command_error", stop_reason="native_exception_no_retry",
                    error_type=type(exc).__name__)


def run_probe():
    import builtins
    blocked = {"schema": "clo_arrange_probe_v1", "status": "blocked"}
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
        runs = getattr(builtins, "_clo3d_mcp_arrange_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_arrange_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16 or runtime.session_id in runs:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            import export_api
            import utility_api
            import ApiTypes
            return collect(pattern_api, export_api, utility_api, ApiTypes)
        finally:
            runtime.busy = False
    except Exception:
        return dict(blocked, stop_reason="runtime_guard_error_no_retry")


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=True, allow_nan=False, sort_keys=True))
