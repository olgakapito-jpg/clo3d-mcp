"""Manual one-shot line-info schema observation; NOT an MCP tool/outline fallback.

Run once in the existing CLO Script Editor with the verified service idle.
Only the uniquely named own fixture, one GetPatternLineInfo call. No setters,
outline/length calls, network, callbacks, listener or runtime imports. The only
file written is one sanitized report under the project's gitignored
acceptance-output. Importing this script does not execute it. See
docs/CLO_LINE_API_CONTRACT_REVIEW.md.
"""

import json
import math
import re
from pathlib import Path


EXPECTED_NAME = "MCP_B06_outline_03cc0407"
# Explicit manual second attempt after the first stopped BEFORE the line getter:
# fixture recreated and independently checked in this exact session. Not a retry
# loop, not a marker reset, not permission for a third attempt or another session.
FIXTURE_RECREATED_SESSION = "7913b43474cd6cd337318631692c245d"
MAX_BYTES = 65536
MAX_DEPTH = 16
FIELDS = ("status", "patternIndex", "patternName", "lineCount", "boundingBox", "lines", "message")
LINE_FIELDS = ("lineIndex", "length", "orientation", "location", "start", "end", "mid", "midNorm")
ROOT = None  # local override if Script Editor omits __file__ and the fallback fails
LOG_DIRNAME = "acceptance-output"
LOG_FILENAME = "clo_line_info_probe_v1.json"


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


def field_types(value, fields):
    return {key: kind(value[key]) for key in fields if key in value}


def numeric_fields(value, fields):
    if type(value) is not dict:
        return {"type": kind(value)}
    return {key: {"type": kind(value[key]), **(
        {"value": value[key]} if type(value[key]) in (int, float) else {})}
        for key in fields if key in value}


def observe(value, index):
    """Bounded, allowlisted projection, not acceptance of a production schema."""
    report = {"type": kind(value)}
    if type(value) is not str:
        report["json_observation"] = "not_string"
        return report
    report["chars"] = len(value)
    if len(value) > MAX_BYTES:
        report["json_observation"] = "size_limit"
        return report
    try:
        raw = value.encode("utf-8", errors="strict")
        report["bytes"] = len(raw)
        if len(raw) > MAX_BYTES:
            report["json_observation"] = "size_limit"
            return report
        check_depth(value)
        data = json.loads(value, object_pairs_hook=unique_object,
                          parse_int=number, parse_float=number,
                          parse_constant=reject_constant)
        # Reject escaped lone surrogates too; no raw strings are emitted below.
        json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        report["json_observation"] = "rejected_json_or_limits"
        return report
    report["root_type"] = kind(data)
    if type(data) is not dict:
        report["json_observation"] = "not_object"
        return report
    report.update(json_observation="object_observed", field_types=field_types(data, FIELDS),
                  extra_field_count=sum(key not in FIELDS for key in data))
    status = data.get("status")
    # Only the status token; never native message, arbitrary keys or scene names.
    if type(status) is str and re.fullmatch(r"[a-zA-Z_]{1,32}", status):
        report["status_token"] = status
    report["pattern_index_matches"] = type(data.get("patternIndex")) is int and data["patternIndex"] == index
    report["pattern_name_matches"] = type(data.get("patternName")) is str and data["patternName"] == EXPECTED_NAME
    if type(data.get("lineCount")) is int:
        report["line_count"] = data["lineCount"]
    if "boundingBox" in data:
        report["bounding_box"] = numeric_fields(data["boundingBox"],
            ("minX", "minY", "maxX", "maxY", "width", "height"))
    lines = data.get("lines")
    if type(lines) is list:
        report["lines_length"] = len(lines)
        sample = []
        for line in lines[:4]:
            item = {"type": kind(line)}
            if type(line) is dict:
                item.update(field_types=field_types(line, LINE_FIELDS),
                            extra_field_count=sum(key not in LINE_FIELDS for key in line),
                            numbers=numeric_fields(line, ("lineIndex", "length")))
                for key in ("start", "end", "mid", "midNorm"):
                    if key in line:
                        item[key] = numeric_fields(line[key], ("x", "y"))
                for key, allowed in (("orientation", ("horizontal", "vertical", "diagonal")),
                    ("location", ("top", "bottom", "left", "right", "top-left",
                                  "top-right", "bottom-left", "bottom-right", "center"))):
                    if key in line:
                        item[key] = line[key] if type(line[key]) is str and line[key] in allowed else "unlisted_or_nonstring"
            sample.append(item)
        report["line_sample"] = sample
    return report


def inventory(pattern):
    count = pattern.GetPatternCount()
    if type(count) is not int or not 1 <= count <= 256:
        raise ValueError("invalid_inventory")
    names = [pattern.GetPatternPieceName(i) for i in range(count)]
    if any(type(n) is not str or len(n) > 128 for n in names):
        raise ValueError("invalid_inventory")
    return count, names


def collect(pattern):
    report = {"schema": "clo_line_info_probe_v1", "status": "blocked",
              "evidence": "single_native_schema_not_acceptance", "line_info_calls": 0}
    try:
        count, names = inventory(pattern)
        if names.count(EXPECTED_NAME) != 1:
            return dict(report, stop_reason="own_fixture_missing_or_ambiguous")
        index = names.index(EXPECTED_NAME)
        current_count = pattern.GetPatternCount()
        if (type(current_count) is not int or current_count != count
                or pattern.GetPatternPieceName(index) != EXPECTED_NAME):
            return dict(report, stop_reason="stale_fixture")
        report.update(pattern_index=index, line_info_calls=1)
        value = pattern.GetPatternLineInfo(index)
        report["native"] = observe(value, index)
        # Failure/unknown JSON stops ALL subsequent native reads, including inventory.
        native = report["native"]
        if (native.get("json_observation") != "object_observed"
                or native.get("status_token") == "failed"
                or not native.get("pattern_index_matches")
                or not native.get("pattern_name_matches")):
            return dict(report, status="observed", stop_reason="native_result_stop_no_more_reads")
        # Even a new success token is only observed, never used to authorize another API.
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="stop_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_line_info_probe_v1", "status": "blocked", "line_info_calls": 0}
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
        runs = getattr(builtins, "_clo3d_mcp_line_info_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_line_info_probe_runs = runs
        if type(runs) is not set or len(runs) >= 16:
            return dict(blocked, stop_reason="one_shot_already_used_or_limit")
        attempt = "initial"
        if runtime.session_id in runs:
            if runtime.session_id != FIXTURE_RECREATED_SESSION:
                return dict(blocked, stop_reason="one_shot_already_used_or_limit")
            second = getattr(builtins, "_clo3d_mcp_line_info_fixture_recreated_runs", None)
            if second is None:
                second = set()
                builtins._clo3d_mcp_line_info_fixture_recreated_runs = second
            if type(second) is not set or second:
                return dict(blocked, stop_reason="one_shot_already_used_or_limit")
            second.add(runtime.session_id)
            attempt = "fixture_recreated_2"
        else:
            runs.add(runtime.session_id)
        runtime.busy = True
        try:
            import pattern_api
            return dict(collect(pattern_api), attempt=attempt)
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
