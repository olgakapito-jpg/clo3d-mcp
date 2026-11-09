"""Explicit one-shot B06 read diagnostic in CLO Script Editor, not an MCP tool.

Only the named own fixture; one native outline call, no retry/fallback or edits.
No imports of listener/runtime, threads, timers, network or arbitrary exec; the
only file written is one sanitized report under the project's gitignored
acceptance-output.
Requires the existing verified idle service on its owner UI thread. Temporarily
uses its busy guard to prevent callback reentrancy while the diagnostic runs.
See docs/CLO_OUTLINE_CHECK.md. Importing this file does not execute the probe.
"""

import json
import math
from pathlib import Path


EXPECTED_NAME = "MCP_B06_outline_03cc0407"
ROOT = None  # local override if Script Editor omits __file__ and the fallback fails
LOG_DIRNAME = "acceptance-output"
LOG_FILENAME = "clo_outline_probe_v1.json"


def log_folder():
    """Resolve the project folder; None when no candidate looks like this repo."""
    candidates = []
    if ROOT:
        candidates.append(Path(ROOT))
    if globals().get("__file__"):
        candidates.append(Path(__file__).resolve().parent.parent)
    candidates.append(Path.home() / "Documents" / "clo3d_mcp")
    for root in candidates:
        if (root / "pyproject.toml").is_file() and (root / "src" / "clo3d_mcp").is_dir():
            return root / LOG_DIRNAME
    return None


def write_report(report, filename):
    """Write the sanitized report of this run; never raises or hides console output."""
    folder = log_folder()
    if folder is None:
        return None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / filename
        path.write_text(json.dumps(report, ensure_ascii=True, allow_nan=False,
                                   sort_keys=True) + "\n", encoding="utf-8")
        return path
    except (OSError, ValueError):
        return None


def kind(value):
    for cls, label in ((list, "list"), (tuple, "tuple"), (dict, "dict"),
                       (str, "str"), (bool, "bool"), (int, "int"),
                       (float, "float"), (type(None), "null")):
        if type(value) is cls:
            return label
    return "other"


def structure(value):
    """Only exact builtin containers, bounded numeric sample; no repr/properties."""
    report = {"type": kind(value)}
    if type(value) not in (list, tuple, dict, str):
        return report
    report["length"] = len(value)
    if type(value) not in (list, tuple):
        return report
    rows = []
    for row in value[:4]:
        item = {"type": kind(row)}
        if type(row) in (list, tuple):
            item["length"] = len(row)
            sample = []
            for v in row[:4]:
                cell = {"type": kind(v)}
                if type(v) in (int, float):
                    try:
                        finite = math.isfinite(v)
                        bounded = finite and abs(v) <= 1e16
                    except (ValueError, OverflowError):
                        finite, bounded = False, False
                    cell.update(finite=finite, within_sample_bound=bounded)
                    if bounded:
                        cell["value"] = v
                sample.append(cell)
            item["sample"] = sample
        rows.append(item)
    report["rows"] = rows
    return report


def collect(pattern):
    """Called only after run_probe establishes runtime/thread/one-shot guards."""
    report = {"schema": "clo_outline_probe_v1", "status": "blocked",
              "evidence": "single_native_structure_not_acceptance", "outline_calls": 0}
    try:
        count = pattern.GetPatternCount()
        if type(count) is not int or not 1 <= count <= 256:
            report["stop_reason"] = "invalid_count"
            return report
        names = [pattern.GetPatternPieceName(i) for i in range(count)]
        if any(type(n) is not str or len(n) > 128 for n in names):
            report["stop_reason"] = "invalid_names"
            return report
        if names.count(EXPECTED_NAME) != 1:
            report["stop_reason"] = "own_fixture_missing_or_ambiguous"
            return report
        i = names.index(EXPECTED_NAME)
        if pattern.GetPatternCount() != count or pattern.GetPatternPieceName(i) != EXPECTED_NAME:
            report["stop_reason"] = "stale_fixture"
            return report
        report.update(pattern_index=i, outline_calls=1)
        value = pattern.GetPatternOutlinePoints(i)
        report["native"] = structure(value)
        after_count = pattern.GetPatternCount()
        if type(after_count) is not int or after_count != count:
            report["stop_reason"] = "inventory_changed"
            return report
        after = [pattern.GetPatternPieceName(j) for j in range(count)]
        if names != after:
            report["stop_reason"] = "inventory_changed"
            return report
        report.update(status="observed", stop_reason="stop_no_retry")
    except Exception:
        report.update(status="command_error", stop_reason="stop_no_retry")
    return report


def run_probe():
    import builtins
    blocked = {"schema": "clo_outline_probe_v1", "status": "blocked", "outline_calls": 0}
    registry = getattr(builtins, "_clo3d_mcp_service", None)
    if type(registry) is not dict or registry.get("version") != 1:
        return dict(blocked, stop_reason="verified_service_required")
    runtime = registry.get("current")
    if runtime is None:
        return dict(blocked, stop_reason="verified_service_required")
    try:
        if (runtime.profile != "service" or runtime.state != "active"
                or not runtime.service_ready or runtime.busy
                or runtime.executor is None or runtime.executor.state != "ready"):
            return dict(blocked, stop_reason="idle_service_required")
        if (runtime.timer.thread_id() != runtime.owner_thread
                or runtime.callback_thread != runtime.owner_thread
                or runtime.timer.visible_window_threads() != {runtime.owner_thread}):
            return dict(blocked, stop_reason="verified_ui_thread_required")
        runs = getattr(builtins, "_clo3d_mcp_outline_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_outline_probe_runs = runs
        if type(runs) is not set or runtime.session_id in runs or len(runs) >= 16:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        # Mark BEFORE import/native entry. Never reset on exception, never retry.
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
    report = run_probe()
    path = write_report(report, LOG_FILENAME)
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True))
    print("[LOG] " + (str(path) if path is not None else
                      "unavailable: project root not found; set ROOT in this probe"))
