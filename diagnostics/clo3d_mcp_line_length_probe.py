"""Manual one-shot outer line-length correspondence; NOT an MCP tool/outline fallback.

Run once in the existing CLO Script Editor with the verified service idle and the
own fixture present. One GetPatternLineInfo plus at most four 2-argument
GetLineLength calls on the returned lineIndex values. No setters, outline calls,
3-argument overload, network, callbacks, listener or runtime imports. The only
file written is one sanitized report under the project's gitignored
acceptance-output. Importing this script does not execute it. See
docs/CLO_LINE_API_CONTRACT_REVIEW.md.
"""

import json
import math
from pathlib import Path


EXPECTED_NAME = "MCP_B06_outline_03cc0407"
EXPECTED_INDICES = (0, 1, 2, 3)
EXPECTED_LENGTHS_MM = (120.0, 80.0, 120.0, 80.0)
TOLERANCE_MM = 0.01
MAX_BYTES = 65536
MAX_DEPTH = 16
ROOT = None  # local override if Script Editor omits __file__ and the fallback fails
LOG_DIRNAME = "acceptance-output"
LOG_FILENAME = "clo_line_length_probe_v1.json"


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
    for cls, label in ((dict, "dict"), (list, "list"), (str, "str"),
                       (bool, "bool"), (int, "int"), (float, "float"),
                       (type(None), "null")):
        if type(value) is cls:
            return label
    return "other"


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e16


def number(text):
    if len(text) > 64:
        raise ValueError("numeric_limit")
    value = float(text) if any(c in text for c in ".eE") else int(text)
    if not math.isfinite(value) or abs(value) > 1e16:
        raise ValueError("numeric_limit")
    return value


def reject_constant(text):
    raise ValueError("nonfinite")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def check_depth(text):
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError("depth_limit")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced")


def parse_line_info(value, index):
    """Return sorted [(lineIndex, length)] or raise ValueError; never echoes text."""
    if type(value) is not str:
        raise ValueError("not_string")
    if len(value) > MAX_BYTES:
        raise ValueError("size_limit")
    raw = value.encode("utf-8", errors="strict")
    if len(raw) > MAX_BYTES:
        raise ValueError("size_limit")
    if value == "":
        raise ValueError("empty")
    check_depth(value)
    data = json.loads(value, object_pairs_hook=unique_object,
                      parse_int=number, parse_float=number,
                      parse_constant=reject_constant)
    if type(data) is not dict:
        raise ValueError("not_object")
    if data.get("status") != "success":
        raise ValueError("status")
    if type(data.get("patternIndex")) is not int or data["patternIndex"] != index:
        raise ValueError("pattern_index")
    if type(data.get("patternName")) is not str or data["patternName"] != EXPECTED_NAME:
        raise ValueError("pattern_name")
    lines = data.get("lines")
    if type(data.get("lineCount")) is not int or type(lines) is not list:
        raise ValueError("line_count")
    if data["lineCount"] != len(lines) or len(lines) != len(EXPECTED_INDICES):
        raise ValueError("line_count")
    result = []
    for line in lines:
        if type(line) is not dict:
            raise ValueError("line_type")
        line_index, length = line.get("lineIndex"), line.get("length")
        if type(line_index) is not int or not finite_number(length):
            raise ValueError("line_fields")
        result.append((line_index, float(length)))
    indices = [item[0] for item in result]
    if len(set(indices)) != len(indices) or sorted(indices) != list(EXPECTED_INDICES):
        raise ValueError("line_layout")
    return sorted(result)


def inventory(pattern):
    count = pattern.GetPatternCount()
    if type(count) is not int or not 1 <= count <= 256:
        raise ValueError("invalid_inventory")
    names = [pattern.GetPatternPieceName(i) for i in range(count)]
    if any(type(n) is not str or len(n) > 128 for n in names):
        raise ValueError("invalid_inventory")
    return count, names


def collect(pattern):
    report = {"schema": "clo_line_length_probe_v1", "status": "blocked",
              "evidence": "single_session_length_correspondence_not_acceptance",
              "line_info_calls": 0, "line_length_calls": 0,
              "tolerance_mm": TOLERANCE_MM}
    try:
        count, names = inventory(pattern)
        if names.count(EXPECTED_NAME) != 1:
            return dict(report, stop_reason="own_fixture_missing_or_ambiguous")
        index = names.index(EXPECTED_NAME)
        current_count = pattern.GetPatternCount()
        if (type(current_count) is not int or current_count != count
                or pattern.GetPatternPieceName(index) != EXPECTED_NAME):
            return dict(report, stop_reason="stale_fixture")
        report["pattern_index"] = index
        report["line_info_calls"] = 1
        try:
            lines = parse_line_info(pattern.GetPatternLineInfo(index), index)
        except (ValueError, UnicodeError, RecursionError, OverflowError):
            # No line-length call after any unexpected line-info result.
            return dict(report, status="observed", stop_reason="line_info_stop_no_length_calls")
        info = dict(lines)
        report["line_indices"] = [item[0] for item in lines]
        report["info_lengths_mm"] = [item[1] for item in lines]
        observed = []
        for line_index in report["line_indices"]:
            try:
                value = pattern.GetLineLength(index, line_index)
            except Exception:
                return dict(report, status="command_error",
                            stop_reason="length_call_error_no_retry")
            report["line_length_calls"] += 1
            if not finite_number(value):
                return dict(report, status="observed", stop_reason="invalid_length_result")
            observed.append({"lineIndex": line_index, "type": kind(value),
                             "info_length": info[line_index], "call_length": float(value),
                             "abs_delta": abs(float(value) - info[line_index])})
        report["lengths"] = observed
        report["max_abs_delta_mm"] = max(item["abs_delta"] for item in observed)
        report["per_index_match"] = all(item["abs_delta"] <= TOLERANCE_MM for item in observed)
        # Multiset check against the known 120x80 rectangle, independent of index order.
        actual = sorted(item["call_length"] for item in observed)
        expected = sorted(EXPECTED_LENGTHS_MM)
        report["actual_multiset_mm"] = actual
        report["expected_multiset_mm"] = expected
        report["multiset_match"] = all(
            abs(left - right) <= TOLERANCE_MM for left, right in zip(actual, expected))
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="stop_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_line_length_probe_v1", "status": "blocked",
               "line_info_calls": 0, "line_length_calls": 0}
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
        runs = getattr(builtins, "_clo3d_mcp_line_length_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_line_length_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        if runtime.session_id in runs:
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
    report = run_probe()
    path = write_report(report, LOG_FILENAME)
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True))
    print("[LOG] " + (str(path) if path is not None else
                      "unavailable: project root not found; set ROOT in this probe"))
