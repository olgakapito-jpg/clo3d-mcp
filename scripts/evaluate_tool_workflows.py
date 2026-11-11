"""Offline selection contracts and synthetic traces; never import/start a server.

This is not an LLM benchmark, live inventory probe or domain acceptance runner.
Only pattern_contract.py (stdlib-only validators) is loaded as an isolated module.
"""

import argparse
import ast
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "tests/evals/clo_tool_selection.json"
MAX_BYTES = 200000
EXTERNAL = {"get_session_info", "transport_status", "lesson"}
MUTATIONS = {"create_pattern", "set_pattern_name", "copy_pattern_with_offset",
             "move_pattern_relative", "delete_pattern", "assign_pattern_fabric",
             "add_seamline_pair", "add_seamline_pair_partial", "import_avatar", "set_arrangement",
             "set_arrangement_orientation", "set_arrangement_position",
             "set_arrangement_shape_style", "set_pattern_edge_to_avatar_measure",
             "simulate", "set_camera_view", "reset_cloth_arrangement",
             "import_avatar_measurements", "set_pattern_grain_direction",
             "set_particle_distance", "import_dxf", "import_pattern_json",
             "import_avatar_size"}
ARTIFACTS = {"get_3d_screenshot", "export_view_image", "export_snapshot_2d",
             "export_pattern_json"}
SERVER_GENERATED = ARTIFACTS
DIAGNOSTIC = "create_test_rectangle"
CURRENT = EXTERNAL | MUTATIONS | ARTIFACTS | {DIAGNOSTIC, "ping", "get_pattern_count",
                                 "list_clo_api", "describe_clo_api", "get_pattern_list",
                                 "get_pattern_geometry", "get_fabric_list", "get_avatars",
                                 "get_pattern_fabric", "get_pattern_outline",
                                 "get_pattern_lines", "get_arrangement",
                                 "get_arrangement_list", "get_seamline_pairs",
                                 "get_avatar_measurements", "get_pattern_avatar_attachments",
                                 "get_pattern_body_details", "get_pattern_details",
                                 "get_mesh_counts"}
EFFECTS = {"read", "scene_mutation", "diagnostic_mutation", "filesystem_write",
           "external_effect", "global_mutation", "unknown"}
BLOCKERS = {"tool_unavailable", "capability_missing", "not_ready", "unsupported_geometry",
            "stale_target", "session_changed", "outcome_unknown", "scope_missing",
            "privacy", "unknown_effect", "not_production_evidence", "ambiguous_target"}
STOPS = {"error", "outcome_unknown", "schema_mismatch", "session_change", "stale_target"}
DECISIONS = {"complete", "blocked", "clarify", "stopped"}
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
PRIVATE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|/(?:home|Users|tmp)/|https?://|sk-[A-Za-z0-9]{12,})")


class EvaluationError(ValueError):
    """Fixed diagnostics only: never include submitted values, paths or secrets."""


def require(condition, code):
    if not condition:
        raise EvaluationError(code)


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value)
            and set(value) <= set(required) | set(optional), "invalid_fields")


def strings(value, allowed=None, minimum=0, maximum=64):
    require(type(value) is list and minimum <= len(value) <= maximum
            and all(type(v) is str for v in value) and len(set(value)) == len(value), "invalid_list")
    if allowed is not None:
        require(set(value) <= set(allowed), "unknown_value")


def bounded(value, depth=0, budget=None):
    if budget is None:
        budget = [20000]
    budget[0] -= 1
    require(depth <= 12 and budget[0] >= 0, "input_bound")
    if type(value) is dict:
        require(len(value) <= 128, "input_bound")
        for key, item in value.items():
            require(type(key) is str and len(key) <= 128, "invalid_key")
            require(key.lower() not in {"token", "secret", "password", "api_key", "path", "endpoint"},
                    "private_input")
            bounded(item, depth + 1, budget)
    elif type(value) is list:
        require(len(value) <= 512, "input_bound")
        for item in value:
            bounded(item, depth + 1, budget)
    elif type(value) is str:
        require(len(value) <= 8192 and not PRIVATE.search(value)
                and not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "private_or_invalid_text")
    else:
        require(value is None or type(value) is bool or
                (type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e16), "invalid_scalar")


def load_json(path):
    require(path.stat().st_size <= MAX_BYTES, "file_bound")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_):
        raise EvaluationError("nonfinite_json")

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                           parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError):
        raise EvaluationError("invalid_json") from None
    bounded(value)
    return value


def contract_module():
    spec = importlib.util.spec_from_file_location("offline_pattern_contract", ROOT / "src/clo3d_mcp/pattern_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONTRACT = contract_module()


def inventory(root=ROOT):
    """AST only: decorators, public args, literal command mapping and capabilities.

    Deliberately fails closed when the current50 registration shape changes.
    Does not inspect legacy server.py or claim a currently running profile.
    """
    tree = ast.parse((root / "src/clo3d_mcp/transport_server.py").read_text(encoding="utf-8"))
    tools = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorated = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and isinstance(d.func.value, ast.Name) and d.func.value.id == "mcp"
                        and d.func.attr == "tool" for d in node.decorator_list)
        if not decorated:
            continue
        require(node.name not in tools, "duplicate_registration")
        require(not node.args.kwonlyargs and not node.args.vararg
                and not node.args.kwarg, "unsupported_signature")
        defaults = len(node.args.defaults)
        require(all(isinstance(d, ast.Constant) and d.value is None for d in node.args.defaults),
                "unsupported_default")
        names = [a.arg for a in node.args.args]
        required = names[:len(names) - defaults] if defaults else names
        optional = names[len(required):]
        commands = [n.args[0].value for n in ast.walk(node)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "service"
                    and n.func.attr == "call" and n.args and isinstance(n.args[0], ast.Constant)]
        require(commands == ([] if node.name in EXTERNAL else [node.name]), "command_mapping_drift")
        tools[node.name] = {"args": required, "optional_args": optional,
                            "effect": "filesystem_write" if node.name in ARTIFACTS else
                            "scene_mutation" if node.name in MUTATIONS else
                            "diagnostic_mutation" if node.name == DIAGNOSTIC else "read"}
    require(set(tools) == CURRENT, "current_inventory_drift")
    # Evaluate only a tiny AST list-expression grammar, never source execution.
    constants = {"PATTERN_COMMANDS": list(CONTRACT.PATTERN_COMMANDS)}

    def literal(node):
        if isinstance(node, ast.List):
            require(all(isinstance(n, ast.Constant) and type(n.value) is str for n in node.elts), "capability_ast")
            return [n.value for n in node.elts]
        if isinstance(node, ast.Name):
            require(node.id in constants, "capability_ast")
            return constants[node.id]
        require(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add), "capability_ast")
        return literal(node.left) + literal(node.right)

    protocol = ast.parse((root / "src/clo3d_mcp/protocol.py").read_text(encoding="utf-8"))
    for node in protocol.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in {"CAPABILITIES", "SERVICE_CAPABILITIES", "PATTERN_CAPABILITIES"}:
                constants[name] = literal(node.value)
    require(set(constants.get("PATTERN_CAPABILITIES", [])) == CURRENT - EXTERNAL, "capability_inventory_drift")
    def profile(removed):
        return {"tools": sorted(CURRENT - removed),
                "capabilities": [c for c in constants["PATTERN_CAPABILITIES"] if c not in removed]}

    newest = {"export_view_image", "export_snapshot_2d", "set_camera_view",
              "reset_cloth_arrangement", "import_avatar_measurements",
              "get_pattern_body_details", "get_pattern_details",
              "set_pattern_grain_direction", "get_mesh_counts",
              "set_particle_distance"}
    previous = {"get_3d_screenshot", "get_arrangement_list", "get_seamline_pairs",
                "get_avatar_measurements", "get_pattern_avatar_attachments",
                "set_arrangement_shape_style", "set_pattern_edge_to_avatar_measure",
                "simulate"}
    base = newest | previous
    newer = {"lesson", "import_dxf", "export_pattern_json", "import_pattern_json",
             "add_seamline_pair_partial", "import_avatar_size"}
    profiles = {
        "current50": profile(set()),
        "current34": profile(newest | newer),
        "current26": profile(base | newer),
        "current25": profile(base | newer | {"set_arrangement_position"}),
        "current24": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation"}),
        "current23": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement"}),
        "current22": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement"}),
        "current21": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar"}),
        "current20": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar",
                                               "add_seamline_pair"}),
        "current19": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar",
                                               "add_seamline_pair", "get_pattern_lines"}),
        "current18": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar",
                                               "add_seamline_pair", "get_pattern_lines",
                                               "get_pattern_outline"}),
        "current16": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar",
                                               "add_seamline_pair", "get_pattern_lines",
                                               "get_pattern_fabric", "assign_pattern_fabric",
                                               "get_pattern_outline"}),
        # Historical selection fixtures keep their exact old capabilities.
        "current14": profile(base | newer | {"set_arrangement_position",
                                               "set_arrangement_orientation", "set_arrangement",
                                               "get_arrangement", "import_avatar",
                                               "add_seamline_pair", "get_pattern_lines",
                                               "get_fabric_list", "get_avatars",
                                               "get_pattern_fabric", "assign_pattern_fabric",
                                               "get_pattern_outline"}),
        "diagnostic5": {"tools": sorted((EXTERNAL - newer) | set(constants["SERVICE_CAPABILITIES"])),
                        "capabilities": constants["SERVICE_CAPABILITIES"]},
    }
    return {"tools": tools, "profiles": profiles}


def validate_args(tool, args, inv):
    require(tool in inv["tools"], "unknown_tool")
    spec = inv["tools"][tool]
    require(set(spec["args"]) <= set(args) <= set(spec["args"]) | set(spec.get("optional_args", [])),
            "invalid_fields")
    if tool in CONTRACT.PATTERN_COMMANDS and tool not in SERVER_GENERATED:
        try:
            CONTRACT.validate_params(tool, args)
        except CONTRACT.CommandError:
            raise EvaluationError("invalid_arguments") from None


def validate_dataset(data, inv):
    bounded(data)
    fields(data, {"schema_version", "evidence", "unavailable_tools", "cases"})
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "dataset_version")
    require(data["evidence"] == "synthetic_contract_not_llm_or_live", "evidence_level")
    unavailable = data["unavailable_tools"]
    strings(unavailable, minimum=1)
    require(all(IDENTIFIER.fullmatch(n) for n in unavailable) and not set(unavailable) & CURRENT,
            "unavailable_inventory_overlap")
    require(type(data["cases"]) is list and 20 <= len(data["cases"]) <= 128, "case_bound")
    ids = set()
    for case in data["cases"]:
        fields(case, {"id", "intent", "profile", "scope", "fixture", "expected_tools", "forbidden_tools",
                      "forbidden_effects", "required_args", "decision", "blockers", "stop_conditions"})
        require(type(case["id"]) is str and IDENTIFIER.fullmatch(case["id"]), "case_id")
        require(case["id"] not in ids, "duplicate_case_id")
        ids.add(case["id"])
        require(type(case["intent"]) is str and 10 <= len(case["intent"]) <= 2000
                and re.search(r"[А-Яа-яЁё]", case["intent"]), "russian_intent")
        require(case["profile"] in inv["profiles"] and case["scope"] in {"read_only", "scene", "diagnostic"},
                "profile_or_scope")
        fields(case["fixture"], {"ready", "patterns"})
        require(type(case["fixture"]["ready"]) is bool, "fixture_ready")
        strings(case["fixture"]["patterns"], maximum=256)
        require(all(CONTRACT.name(n) for n in case["fixture"]["patterns"]), "fixture_names")
        strings(case["expected_tools"], inv["profiles"][case["profile"]]["tools"])
        strings(case["forbidden_tools"], CURRENT | set(unavailable))
        require(not set(case["expected_tools"]) & set(case["forbidden_tools"]), "conflicting_tools")
        strings(case["forbidden_effects"], EFFECTS)
        require(type(case["required_args"]) is dict, "required_arguments")
        for tool, args in case["required_args"].items():
            require(tool in case["expected_tools"], "argument_tool_not_expected")
            validate_args(tool, args, inv)
        require(case["decision"] in DECISIONS, "invalid_decision")
        strings(case["blockers"], BLOCKERS)
        strings(case["stop_conditions"], STOPS)
        require(set(case["stop_conditions"]) == STOPS, "missing_stop_condition")
        require((case["decision"] == "complete") == (not case["blockers"]), "blocker_decision")
        for tool in case["expected_tools"]:
            require(inv["tools"][tool]["effect"] not in case["forbidden_effects"], "conflicting_effect")
            require(case["scope"] != "read_only" or tool not in MUTATIONS | {DIAGNOSTIC}, "scope_conflict")
        if not case["fixture"]["ready"]:
            require(set(case["expected_tools"]) <= EXTERNAL, "not_ready_native_selection")
    return data


def status_result(result, info=False):
    # Sanitized synthetic snapshots, intentionally not raw live status captures.
    fields(result, {"session_id", "ready", "connected", "quarantined", "error"},
           {"capabilities"} if info else ())
    require(type(result["session_id"]) is str and re.fullmatch(r"synthetic-[a-z0-9_-]{1,32}", result["session_id"]),
            "synthetic_session_required")
    require(all(type(result[k]) is bool for k in ("ready", "connected", "quarantined")), "status_boolean")
    require(result["error"] is None or result["error"] in {"http_bind_failed", "executor_unavailable"}, "status_error")
    if info:
        require("capabilities" in result, "missing_capabilities")
        strings(result["capabilities"], CURRENT - EXTERNAL)


def validate_success(tool, result):
    if tool in EXTERNAL:
        status_result(result, tool == "get_session_info")
    elif tool in CONTRACT.PATTERN_COMMANDS:
        require(result.get("ok") is True, "success_flag")
        try:
            CONTRACT.validate_result(tool, {k: v for k, v in result.items() if k != "ok"})
        except CONTRACT.CommandError:
            raise EvaluationError("result_schema") from None
    elif tool == "ping":
        require(set(result) == {"ok", "pong"} and result["ok"] is True and result["pong"] is True, "ping_schema")
    else:
        fields(result, {"ok", "pattern_count"} | ({"created"} if tool == DIAGNOSTIC else set()))
        require(result["ok"] is True and type(result["pattern_count"]) is int
                and result["pattern_count"] >= 0, "count_schema")
        if tool == DIAGNOSTIC:
            require(result["created"] is True, "diagnostic_schema")


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-5, abs_tol=0.05)


def same_geometry(a, b):
    return (a["index"] == b["index"] and a["name"] == b["name"]
            and close(a["area_mm2"], b["area_mm2"])
            and all(close(x, y) for x, y in zip(a["position_mm"], b["position_mm"])))


def validate_submission(submission, inv, case=None, profile="current16", scope="scene"):
    """Check supplied static plan or serial synthetic observations, never execute.

    Plan checks cannot establish result schemas, identity or real-world effects.
    A stopped trace may contain one malformed/error result, but nothing after it.
    """
    bounded(submission)
    fields(submission, {"kind", "execution", "steps", "decision", "blockers"})
    require(submission["kind"] in {"plan", "trace"} and submission["execution"] == "serial", "submission_kind")
    require(submission["decision"] in DECISIONS, "invalid_decision")
    strings(submission["blockers"], BLOCKERS)
    require(type(submission["steps"]) is list and len(submission["steps"]) <= 128, "step_bound")
    if case:
        profile, scope = case["profile"], case["scope"]
    require(profile in inv["profiles"] and scope in {"read_only", "scene", "diagnostic"}, "profile_or_scope")
    is_trace = submission["kind"] == "trace"
    tools, capabilities = set(inv["profiles"][profile]["tools"]), set()
    session = None
    ready = False
    session_seen = preflight = listed = counted = False
    names, geometries = None, {}
    fabrics, mappings = None, {}
    fabric_list_seen = False
    count = None
    fixture_list_seen = fixture_status_seen = False
    pending = None
    stopped = None
    called = []
    for step in submission["steps"]:
        require(stopped is None, "call_after_stop")
        fields(step, {"tool", "args", "session", "result"} if is_trace else {"tool", "args"})
        tool, args = step["tool"], step["args"]
        require(type(tool) is str and tool in tools, "unavailable_tool")
        validate_args(tool, args, inv)
        effect = inv["tools"][tool]["effect"]
        require(scope != "read_only" or effect == "read", "scope_violation")
        require(tool != DIAGNOSTIC or scope == "diagnostic", "diagnostic_not_production")
        if case:
            require(tool not in case["forbidden_tools"] and effect not in case["forbidden_effects"], "forbidden_selection")
        called.append(tool)
        if is_trace:
            require(type(step["session"]) is str and re.fullmatch(r"synthetic-[a-z0-9_-]{1,32}", step["session"]),
                    "synthetic_session_required")
            if session is not None and step["session"] != session:
                stopped = "session_change"
                continue
        if tool not in EXTERNAL:
            require(session_seen, "missing_session_preflight")
            if is_trace:
                require(ready and tool in capabilities, "not_ready_or_capability_missing")
        mutation = tool in MUTATIONS or tool == DIAGNOSTIC
        if pending and tool not in EXTERNAL:
            require(tool == pending["tool"], "missing_independent_readback")
        if tool == "get_pattern_geometry":
            require(listed, "missing_fresh_list")
            if is_trace:
                require(args["pattern_index"] < len(names), "stale_target")
        if tool in ("get_pattern_fabric", "get_pattern_outline"):
            require(listed, "missing_fresh_list")
            if is_trace:
                idx = args["pattern_index"]
                require(idx < len(names) and names[idx] == args["expected_name"]
                        and names.count(args["expected_name"]) == 1, "stale_target")
        if tool == "assign_pattern_fabric":
            require(fabric_list_seen, "missing_fabric_list")
            if is_trace:
                idx, f = args["pattern_index"], args["fabric_index"]
                require(idx in mappings and mappings[idx]["fabric_index"] == args["expected_current_fabric_index"],
                        "missing_or_stale_fabric_mapping")
                require(f < len(fabrics) and fabrics[f]["name"] == args["expected_fabric_name"]
                        and sum(v["name"] == args["expected_fabric_name"] for v in fabrics) == 1,
                        "stale_fabric_target")
        if mutation:
            require(preflight and (counted if tool == DIAGNOSTIC else listed), "missing_mutation_preflight")
            if is_trace and tool != DIAGNOSTIC:
                if tool != "create_pattern":
                    idx = args["pattern_index"]
                    require(idx < len(names) and names[idx] == args["expected_name"]
                            and names.count(args["expected_name"]) == 1, "stale_target")
                    if tool not in {"delete_pattern", "assign_pattern_fabric"}:
                        require(idx in geometries, "missing_pre_geometry")
                if "name" in args:
                    require(args["name"] not in names or (tool == "set_pattern_name"
                            and args["name"] == args["expected_name"]), "name_conflict")
                require(tool not in {"create_pattern", "copy_pattern_with_offset"} or len(names) < 256, "pattern_capacity")
        if not is_trace:
            if tool in EXTERNAL:
                session_seen = session_seen or tool == "get_session_info"
                preflight = True
            if tool == "get_pattern_list":
                listed = True
            if tool == "get_fabric_list":
                fabric_list_seen = True
            if tool == "get_pattern_count":
                counted = True
            if pending and tool == pending["tool"]:
                pending = None
            if mutation:
                pending = {"tool": "get_pattern_count" if tool == DIAGNOSTIC else
                           "get_pattern_list" if tool == "delete_pattern" else
                           "get_pattern_fabric" if tool == "assign_pattern_fabric" else "get_pattern_geometry"}
                preflight = False
                listed = tool not in {"delete_pattern", "create_pattern", "copy_pattern_with_offset"}
                # New indices cannot be proven in a static plan, but list/readback order can.
                if pending["tool"] == "get_pattern_geometry":
                    listed = True
            continue
        result = step["result"]
        require(type(result) is dict, "result_object")
        if result.get("isError") is True or result.get("ok") is False:
            fields(result, {"ok", "error"}, {"isError", "scene_may_have_changed"})
            require(result["ok"] is False and result["error"] in {
                "command_error", "invalid_parameters", "stale_pattern", "api_unavailable", "outcome_unknown",
                "scene_change_unverified", "queue_full", "queue_timeout", "executor_unavailable", "disconnect",
                "client_timeout", "waiter_limit", "inventory_limit", "inventory_changed",
                "invalid_native_result", "stale_fabric", "executor_release_timeout", "executor_release_unavailable"}, "error_schema")
            require("isError" not in result or result["isError"] is True, "error_schema")
            require("scene_may_have_changed" not in result or result["scene_may_have_changed"] is True, "error_schema")
            stopped = "outcome_unknown" if result["error"] in {"outcome_unknown", "disconnect", "client_timeout"} else "error"
            continue
        try:
            validate_success(tool, result)
        except EvaluationError:
            stopped = "schema_mismatch"
            continue
        if tool in EXTERNAL:
            if session is not None and result["session_id"] != session:
                stopped = "session_change"
                continue
            require(step["session"] == result["session_id"], "session_envelope_mismatch")
            session = result["session_id"]
            if case and not fixture_status_seen:
                require(result["ready"] == case["fixture"]["ready"], "fixture_ready_mismatch")
                fixture_status_seen = True
            ready = result["ready"] and result["connected"] and not result["quarantined"] and result["error"] is None
            if tool == "get_session_info":
                capabilities = set(result["capabilities"])
                require(capabilities <= set(inv["profiles"][profile]["capabilities"]), "profile_capability_mismatch")
            session_seen = session_seen or tool == "get_session_info"
            preflight = True
        elif tool == "get_pattern_list":
            observed = [p["name"] for p in result["patterns"]]
            if case and not fixture_list_seen:
                require(observed == case["fixture"]["patterns"], "fixture_patterns_mismatch")
                fixture_list_seen = True
            if pending:
                require(observed == pending["names"], "readback_mismatch")
                pending = None
            names, count, listed, geometries, mappings = observed, len(observed), True, {}, {}
        elif tool == "get_fabric_list":
            fabrics = result["fabrics"]
            fabric_list_seen = True
            mappings = {}
        elif tool == "get_pattern_outline":
            idx = args["pattern_index"]
            require(result["pattern_index"] == idx and result["pattern_name"] == names[idx],
                    "outline_identity_mismatch")
        elif tool == "get_pattern_fabric":
            idx = args["pattern_index"]
            require(result["pattern_index"] == idx and result["pattern_name"] == names[idx],
                    "fabric_mapping_identity")
            if fabrics is not None:
                f = result["fabric_index"]
                require(f < len(fabrics) and fabrics[f]["name"] == result["fabric_name"],
                        "fabric_mapping_identity")
            if pending:
                require(all(result[k] == pending["mapping"][k] for k in
                            ("pattern_index", "pattern_name", "fabric_index", "fabric_name")),
                        "readback_mismatch")
                pending = None
            mappings[idx] = result
        elif tool == "get_pattern_count":
            if pending:
                require(result["pattern_count"] == pending["count"], "readback_mismatch")
                pending = None
            count, counted = result["pattern_count"], True
        elif tool == "get_pattern_geometry":
            pattern = result["pattern"]
            idx = args["pattern_index"]
            require(pattern["index"] == idx and pattern["name"] == names[idx], "geometry_identity_mismatch")
            if pending:
                require(same_geometry(pattern, pending["pattern"]), "readback_mismatch")
                pending = None
            geometries[idx] = pattern
        elif mutation:
            before = list(names) if names is not None else None
            if tool == DIAGNOSTIC:
                require(result["pattern_count"] == count + 1, "mutation_invariant")
                pending = {"tool": "get_pattern_count", "count": count + 1}
            elif tool == "assign_pattern_fabric":
                require(result["pattern_index"] == args["pattern_index"]
                        and result["pattern_name"] == args["expected_name"]
                        and result["fabric_index"] == args["fabric_index"]
                        and result["fabric_name"] == args["expected_fabric_name"]
                        and result["previous_fabric_index"] == args["expected_current_fabric_index"],
                        "mutation_invariant")
                pending = {"tool": "get_pattern_fabric", "mapping": result}
            elif tool == "delete_pattern":
                require(result["deleted_name"] == args["expected_name"]
                        and result["pattern_count"] == len(names) - 1, "mutation_invariant")
                del before[args["pattern_index"]]
                pending = {"tool": "get_pattern_list", "names": before}
            else:
                pattern = result["pattern"]
                addition = tool in {"create_pattern", "copy_pattern_with_offset"}
                require(result["pattern_count"] == len(names) + int(addition), "mutation_invariant")
                expected_name = args.get("name", args.get("expected_name"))
                require(pattern["name"] == expected_name, "mutation_identity")
                if not addition:
                    require(pattern["index"] == args["pattern_index"], "mutation_identity")
                if tool != "create_pattern":
                    old = geometries[args["pattern_index"]]
                    require(close(old["area_mm2"], pattern["area_mm2"]), "mutation_area")
                    delta = [args.get("dx", 0), args.get("dy", 0)]
                    require(all(close(a + d, b) for a, d, b in zip(old["position_mm"], delta, pattern["position_mm"])),
                            "mutation_position")
                else:
                    pts = args["points"]
                    area = abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1]))) / 2
                    require(close(area, pattern["area_mm2"]), "mutation_area")
                idx = pattern["index"]
                if addition:
                    require(idx <= len(names), "mutation_identity")
                    before.insert(idx, pattern["name"])
                else:
                    before[idx] = pattern["name"]
                names = before
                pending = {"tool": "get_pattern_geometry", "pattern": pattern}
            preflight, listed, counted = False, True, False
    if stopped:
        require(submission["decision"] == "stopped", "must_stop")
    else:
        require(pending is None, "unfinished_readback")
        require(submission["decision"] != "stopped", "missing_stop_event")
    if case:
        require(bool(called) == bool(case["expected_tools"]), "no_call_required")
        require(set(case["expected_tools"]) <= set(called), "missing_expected_tool")
        require(submission["decision"] == case["decision"] and set(submission["blockers"]) == set(case["blockers"]),
                "decision_mismatch")
        for tool, args in case["required_args"].items():
            require(any(s["tool"] == tool and s["args"] == args for s in submission["steps"]), "required_args_mismatch")
    return {"accepted": True, "kind": submission["kind"], "stop_reason": stopped,
            "evidence": "synthetic_trace_contract" if is_trace else "static_plan_only"}


def synthetic_examples(inv):
    """Small public fixtures: not recorded traffic or a model-produced plan."""
    sid = "synthetic-a"
    status = {"session_id": sid, "ready": True, "connected": True, "quarantined": False,
              "error": None, "capabilities": inv["profiles"]["current14"]["capabilities"]}
    def step(tool, args, result):
        return {"tool": tool, "args": args, "session": sid, "result": result}
    def geo(index, name, x=0):
        return {"index": index, "name": name, "position_mm": [x, 0], "area_mm2": 100,
                "bounding_box": {"Width": "10", "Height": "10"}}
    def listing(names):
        return {"ok": True, "pattern_count": len(names),
                "patterns": [{"index": i, "name": name} for i, name in enumerate(names)]}
    steps = [step("get_session_info", {}, status), step("get_pattern_list", {}, listing(["panel"])),
             step("get_pattern_geometry", {"pattern_index": 0}, {"ok": True, "pattern": geo(0, "panel")}),
             step("move_pattern_relative", {"pattern_index": 0, "expected_name": "panel", "dx": 20, "dy": 0},
                  {"ok": True, "verified": True, "pattern_count": 1, "pattern": geo(0, "panel", 20), "executor_ms": 1}),
             step("get_pattern_geometry", {"pattern_index": 0}, {"ok": True, "pattern": geo(0, "panel", 20)})]
    valid = {"kind": "trace", "execution": "serial", "steps": steps, "decision": "complete", "blockers": []}
    deleted = deepcopy(valid)
    deleted["steps"] = [deepcopy(steps[0]), step("get_pattern_list", {}, listing(["panel", "copy"])),
        step("delete_pattern", {"pattern_index": 0, "expected_name": "panel"},
             {"ok": True, "verified": True, "pattern_count": 1, "deleted_name": "panel", "executor_ms": 1}),
        step("get_pattern_list", {}, listing(["copy"])), deepcopy(steps[0]),
        step("delete_pattern", {"pattern_index": 0, "expected_name": "copy"},
             {"ok": True, "verified": True, "pattern_count": 0, "deleted_name": "copy", "executor_ms": 1}),
        step("get_pattern_list", {}, listing([]))]
    return valid, deleted


def self_test(inv):
    valid, deleted = synthetic_examples(inv)
    for value in (valid, deleted):
        validate_submission(value, inv)
    invalid = []
    no_readback = deepcopy(valid)
    no_readback["steps"].pop()
    invalid.append(no_readback)
    boolean = deepcopy(valid)
    boolean["steps"][3]["args"]["dx"] = True
    invalid.append(boolean)
    retry = deepcopy(valid)
    retry["steps"][3]["result"] = {"ok": False, "error": "outcome_unknown"}
    retry["steps"].append(deepcopy(retry["steps"][3]))
    invalid.append(retry)
    stale = deepcopy(deleted)
    stale["steps"][5]["args"]["pattern_index"] = 1
    invalid.append(stale)
    schema = deepcopy(valid)
    schema["steps"][3]["result"]["verified"] = "true"
    invalid.append(schema)
    changed = deepcopy(valid)
    changed["steps"][3]["session"] = "synthetic-b"
    invalid.append(changed)
    for value in invalid:
        try:
            validate_submission(value, inv)
        except EvaluationError:
            continue
        raise EvaluationError("self_test_false_accept")
    return {"valid_accepted": 2, "invalid_rejected": len(invalid)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate dataset and AST current16 inventory")
    parser.add_argument("--self-test", action="store_true", help="Validate synthetic positive/negative traces")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--submission", type=Path, help="Supplied sanitized synthetic plan/trace JSON")
    parser.add_argument("--case", help="Dataset ID for the supplied plan/trace")
    args = parser.parse_args(argv)
    if not (args.check or args.self_test or args.submission):
        parser.error("choose --check, --self-test or --submission")
    try:
        inv = inventory()
        data = validate_dataset(load_json(args.dataset), inv)
        result = {"evidence": "offline_contract_not_llm_selection_or_real_clo", "tools": len(inv["tools"]),
                  "cases": len(data["cases"])}
        if args.self_test:
            result["self_test"] = self_test(inv)
        if args.submission:
            require(args.case is not None, "case_required")
            matches = [c for c in data["cases"] if c["id"] == args.case]
            require(len(matches) == 1, "unknown_case")
            result["submission"] = validate_submission(load_json(args.submission), inv, matches[0])
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (EvaluationError, OSError, ValueError, TypeError, KeyError, RecursionError):
        # No raw exception, input, session or machine-specific path in output.
        print(json.dumps({"accepted": False, "error": "offline_contract_validation_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
