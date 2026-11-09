"""Manual one-shot line-info failure observation; NOT an MCP tool/outline fallback.

Run once in the existing CLO Script Editor with the verified service idle and the
own fixture present. The public tool rejects invalid indices before the native
call, so this diagnostic calls GetPatternLineInfo once with the first
out-of-range index (count) to observe the native failure/empty shape. No setters,
outline/length calls, files, network, callbacks, listener or runtime imports.
Importing this script does not execute it. See docs/CLO_LINE_API_CONTRACT_REVIEW.md.
"""

import json
import re


EXPECTED_NAME = "MCP_B06_outline_03cc0407"
MAX_BYTES = 65536
MAX_DEPTH = 16
FIELDS = ("status", "patternIndex", "patternName", "lineCount", "boundingBox", "lines", "message")


def kind(value):
    for cls, label in ((dict, "dict"), (list, "list"), (str, "str"),
                       (bool, "bool"), (int, "int"), (float, "float"),
                       (type(None), "null")):
        if type(value) is cls:
            return label
    return "other"


def reject_constant(_text):
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


def observe(value):
    """Bounded projection; never echoes native message/name/raw JSON."""
    report = {"type": kind(value)}
    if type(value) is not str:
        report["json_observation"] = "not_string"
        return report
    report["chars"] = len(value)
    if not 1 <= len(value) <= MAX_BYTES:
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
                          parse_constant=reject_constant)
        json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        report["json_observation"] = "rejected_json_or_limits"
        return report
    report["root_type"] = kind(data)
    if type(data) is not dict:
        report["json_observation"] = "not_object"
        return report
    report.update(json_observation="object_observed",
                  field_types={key: kind(data[key]) for key in FIELDS if key in data},
                  field_count=len(data), message_present="message" in data)
    status = data.get("status")
    if type(status) is str and re.fullmatch(r"[a-zA-Z_]{1,32}", status):
        report["status_token"] = status
    if type(data.get("patternIndex")) is int:
        report["pattern_index"] = data["patternIndex"]
    for key in ("lineCount", "lines"):
        if type(data.get(key)) is int:
            report[key] = data[key]
        elif type(data.get(key)) is list:
            report["lines_length"] = len(data[key])
    return report


def collect(pattern):
    report = {"schema": "clo_line_failure_probe_v1", "status": "blocked",
              "calls": 0, "evidence": "single_invalid_index_native_observation_not_acceptance"}
    try:
        count = pattern.GetPatternCount()
        if type(count) is not int or not 1 <= count <= 255:
            return dict(report, stop_reason="unexpected_count_for_invalid_index")
        names = [pattern.GetPatternPieceName(i) for i in range(count)]
        if names.count(EXPECTED_NAME) != 1:
            return dict(report, stop_reason="own_fixture_missing_or_ambiguous")
        invalid = count
        report.update(fixture_count=count, invalid_index=invalid, calls=1)
        try:
            value = pattern.GetPatternLineInfo(invalid)
        except Exception:
            return dict(report, status="command_error", stop_reason="native_exception_no_retry")
        report["native"] = observe(value)
        return dict(report, status="observed", stop_reason="stop_no_retry")
    except Exception:
        return dict(report, status="command_error", stop_reason="stop_no_retry")


def run_probe():
    import builtins
    blocked = {"schema": "clo_line_failure_probe_v1", "status": "blocked", "calls": 0}
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
        runs = getattr(builtins, "_clo3d_mcp_line_failure_probe_runs", None)
        if runs is None:
            runs = set()
            builtins._clo3d_mcp_line_failure_probe_runs = runs
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
