"""Offline-only synthetic selection and trace contracts; no server/native imports."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate_tool_workflows", ROOT / "scripts/evaluate_tool_workflows.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


@pytest.fixture
def inv():
    return evaluation.inventory()


@pytest.fixture
def data():
    return evaluation.load_json(evaluation.DATASET)


@pytest.fixture
def trace(inv):
    return evaluation.synthetic_examples(inv)[0]


def test_current24_inventory_ast_without_server_imports(inv):
    assert len(inv["tools"]) == 24
    assert set(inv["profiles"]["current24"]["capabilities"]) == evaluation.CURRENT - evaluation.EXTERNAL
    for size in (14, 16, 18):
        assert len(inv["profiles"]["current" + str(size)]["tools"]) == size
        assert "get_pattern_outline" not in inv["profiles"]["current" + str(size)]["tools"]
        assert "get_pattern_lines" not in inv["profiles"]["current" + str(size)]["tools"]
        assert "add_seamline_pair" not in inv["profiles"]["current" + str(size)]["tools"]
        assert "import_avatar" not in inv["profiles"]["current" + str(size)]["tools"]
        assert "get_arrangement" not in inv["profiles"]["current" + str(size)]["tools"]
        assert "set_arrangement" not in inv["profiles"]["current" + str(size)]["tools"]
    assert len(inv["profiles"]["current23"]["tools"]) == 23
    assert "set_arrangement" not in inv["profiles"]["current23"]["tools"]
    assert len(inv["profiles"]["current22"]["tools"]) == 22
    assert "get_arrangement" not in inv["profiles"]["current22"]["tools"]
    assert len(inv["profiles"]["current21"]["tools"]) == 21
    assert "import_avatar" not in inv["profiles"]["current21"]["tools"]
    assert len(inv["profiles"]["current20"]["tools"]) == 20
    assert "add_seamline_pair" not in inv["profiles"]["current20"]["tools"]
    assert len(inv["profiles"]["current19"]["tools"]) == 19
    assert "get_pattern_outline" in inv["profiles"]["current19"]["tools"]
    assert "get_pattern_lines" not in inv["profiles"]["current19"]["tools"]
    assert len(inv["profiles"]["diagnostic5"]["tools"]) == 5
    assert evaluation.EXTERNAL.isdisjoint(inv["profiles"]["current16"]["capabilities"])
    assert inv["tools"]["copy_pattern_with_offset"]["args"] == ["pattern_index", "expected_name", "name", "dx", "dy"]
    code = """
import runpy, sys
runpy.run_path('scripts/evaluate_tool_workflows.py', run_name='offline_check')
assert not any(n.startswith(('mcp', 'uvicorn', 'clo3d_mcp.transport_server',
    'clo3d_mcp.server', 'clo3d_mcp.pipe_runtime')) for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True, timeout=20)


def outline_trace(inv):
    sid = "synthetic-outline"
    def step(tool, args, result):
        return {"tool": tool, "args": args, "result": result, "session": sid}
    return {"kind": "trace", "execution": "serial", "decision": "complete", "blockers": [],
            "steps": [
                step("get_session_info", {}, {"session_id": sid, "ready": True, "connected": True,
                     "quarantined": False, "error": None,
                     "capabilities": list(inv["profiles"]["current19"]["capabilities"])}),
                step("get_pattern_list", {}, {"ok": True, "pattern_count": 1,
                     "patterns": [{"index": 0, "name": "panel"}]}),
                step("get_pattern_outline", {"pattern_index": 0, "expected_name": "panel"},
                     {"ok": True, "pattern_index": 0, "pattern_name": "panel", "point_count": 4,
                      "points_mm": [[0, 0], [120, 0], [120, 80], [0, 80]], "units": "mm",
                      "coordinate_frame": "bbox_top_left_y_down"})]}


def test_outline_workflow_read_only_selection_and_cross_domain(inv, data):
    case = next(c for c in data["cases"] if c["id"] == "outline_endpoints")
    trace = outline_trace(inv)
    evaluation.validate_submission(trace, inv, case)
    trace["steps"].append({"tool": "get_pattern_fabric",
        "args": {"pattern_index": 0, "expected_name": "panel"}, "session": "synthetic-outline",
        "result": {"ok": True, "pattern_index": 0, "pattern_name": "panel",
                   "fabric_index": 0, "fabric_name": "cotton"}})
    evaluation.validate_submission(trace, inv, profile="current19", scope="read_only")


@pytest.mark.parametrize("fault", ["missing_list", "stale_name", "identity", "frame", "after_error", "capability"])
def test_outline_workflow_stops_missing_stale_schema_or_error(inv, data, fault):
    case = next(c for c in data["cases"] if c["id"] == "outline_endpoints")
    trace = outline_trace(inv)
    if fault == "missing_list":
        del trace["steps"][1]
    elif fault == "stale_name":
        trace["steps"][2]["args"]["expected_name"] = "old"
    elif fault == "identity":
        trace["steps"][2]["result"]["pattern_name"] = "other"
    elif fault == "capability":
        trace["steps"][0]["result"]["capabilities"].remove("get_pattern_outline")
    else:
        next_step = deepcopy(trace["steps"][2])
        if fault == "frame":
            trace["steps"][2]["result"]["coordinate_frame"] = "global2D"
        else:
            trace["steps"][2]["result"] = {"ok": False, "error": "inventory_changed"}
        trace["steps"].append(next_step)
    with pytest.raises(evaluation.EvaluationError):
        evaluation.validate_submission(trace, inv, case)


def fabric_trace(inv):
    sid = "synthetic-fabric"
    def step(tool, args, result):
        return {"tool": tool, "args": args, "session": sid, "result": result}
    mapping = {"ok": True, "pattern_index": 0, "pattern_name": "front",
               "fabric_index": 0, "fabric_name": "cotton"}
    assign_args = {"pattern_index": 0, "expected_name": "front", "fabric_index": 1,
                   "expected_fabric_name": "jersey", "expected_current_fabric_index": 0}
    assigned = {**mapping, "fabric_index": 1, "fabric_name": "jersey",
                "verified": True, "previous_fabric_index": 0, "executor_ms": 1.0}
    return {"kind": "trace", "execution": "serial", "decision": "complete", "blockers": [],
            "steps": [
                step("get_session_info", {}, {"session_id": sid, "ready": True,
                     "connected": True, "quarantined": False, "error": None,
                     "capabilities": inv["profiles"]["current18"]["capabilities"]}),
                step("get_pattern_list", {}, {"ok": True, "pattern_count": 1,
                     "patterns": [{"index": 0, "name": "front"}]}),
                step("get_fabric_list", {}, {"ok": True, "fabric_count": 2,
                     "fabrics": [{"index": 0, "name": "cotton"}, {"index": 1, "name": "jersey"}]}),
                step("get_pattern_fabric", {"pattern_index": 0, "expected_name": "front"}, mapping),
                step("assign_pattern_fabric", assign_args, assigned),
                step("get_pattern_fabric", {"pattern_index": 0, "expected_name": "front"},
                     {**mapping, "fabric_index": 1, "fabric_name": "jersey"}),
                step("transport_status", {}, {"session_id": sid, "ready": True,
                     "connected": True, "quarantined": False, "error": None})]}


def test_fabric_assignment_trace_requires_independent_mapping_readback(inv, data):
    case = next(c for c in data["cases"] if c["id"] == "pattern_fabric_assign")
    trace = fabric_trace(inv)
    evaluation.validate_submission(trace, inv, case)
    del trace["steps"][5]
    with pytest.raises(evaluation.EvaluationError, match="unfinished_readback"):
        evaluation.validate_submission(trace, inv, case)


@pytest.mark.parametrize("fault", ["mapping", "target", "readback", "missing_fabrics", "after_error"])
def test_fabric_trace_rejects_stale_missing_and_post_error_calls(inv, data, fault):
    case = next(c for c in data["cases"] if c["id"] == "pattern_fabric_assign")
    trace = fabric_trace(inv)
    if fault == "mapping":
        trace["steps"][4]["args"]["expected_current_fabric_index"] = 1
    elif fault == "target":
        trace["steps"][4]["args"]["expected_fabric_name"] = "other"
    elif fault == "readback":
        trace["steps"][5]["result"]["fabric_index"] = 0
    elif fault == "missing_fabrics":
        del trace["steps"][2]
    else:
        trace["steps"][4]["result"] = {"ok": False, "error": "scene_change_unverified",
                                               "scene_may_have_changed": True}
    with pytest.raises(evaluation.EvaluationError):
        evaluation.validate_submission(trace, inv, case)


def test_inventory_rejects_mapping_and_registration_drift(tmp_path):
    folder = tmp_path / "src/clo3d_mcp"
    folder.mkdir(parents=True)
    source = (ROOT / "src/clo3d_mcp/transport_server.py").read_text(encoding="utf-8")
    (folder / "transport_server.py").write_text(source.replace('service.call("ping")', 'service.call("bogus")'), encoding="utf-8")
    with pytest.raises(evaluation.EvaluationError, match="command_mapping_drift"):
        evaluation.inventory(tmp_path)


def test_dataset_valid_bounded_russian_and_all_tools_covered(inv, data):
    assert evaluation.validate_dataset(data, inv) is data
    assert len(data["cases"]) >= 20
    assert set().union(*(set(c["expected_tools"]) for c in data["cases"])) == evaluation.CURRENT
    assert evaluation.DATASET.stat().st_size <= 200000
    assert all(c["stop_conditions"] for c in data["cases"])


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(bogus=True),
    lambda d: d.update(schema_version=True),
    lambda d: d.update(schema_version=2),
    lambda d: d.update(evidence="real_pass"),
    lambda d: d.update(cases=d["cases"][:19]),
    lambda d: d["cases"].append(deepcopy(d["cases"][0])),
    lambda d: d["cases"][0].update(id=True),
    lambda d: d["cases"][0].update(intent="English only intent"),
    lambda d: d["cases"][0].update(bogus="field"),
    lambda d: d["cases"][0].update(expected_tools=["bogus_command"]),
    lambda d: d["cases"][0].update(expected_tools=["assign_fabric"]),
    lambda d: d["cases"][0].update(forbidden_tools=["bogus_command"]),
    lambda d: d["cases"][0].update(forbidden_effects=["magic"]),
    lambda d: d["cases"][0].update(stop_conditions=[]),
    lambda d: d["cases"][0].update(blockers=["magic"]),
    lambda d: d["cases"][0].update(decision=True),
    lambda d: d["cases"][0].update(expected_tools=["transport_status", "transport_status"]),
    lambda d: d["cases"][0]["fixture"].update(ready=1),
    lambda d: d["cases"][0]["fixture"].update(patterns=["panel", "panel"]),
    lambda d: d["cases"][0]["required_args"].update(transport_status={"extra": 1}),
    lambda d: next(c for c in d["cases"] if c["id"] == "list_area")["required_args"]["get_pattern_geometry"].update(pattern_index=True),
    lambda d: next(c for c in d["cases"] if c["id"] == "list_area")["required_args"]["get_pattern_geometry"].update(pattern_index=256),
    lambda d: d["unavailable_tools"].append("ping"),
    lambda d: d["cases"][0].update(profile="legacy47"),
    lambda d: d["cases"][0].update(required_args={"ping": {}}),
    lambda d: d["cases"][0].update(intent="Секретный файл C:\\private\\scene.zprj"),
    lambda d: d.update(secret="not-for-logging"),
])
def test_bad_dataset_rejected(inv, data, mutate):
    mutate(data)
    with pytest.raises(evaluation.EvaluationError):
        evaluation.validate_dataset(data, inv)


@pytest.mark.parametrize("contents", [
    '{"a": 1, "a": 2}', '{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', '{oops',
    '{"path": "private"}', '{"text": "https://private.example"}',
])
def test_json_loader_strict_and_private(tmp_path, contents):
    file = tmp_path / "input.json"
    file.write_text(contents, encoding="utf-8")
    with pytest.raises(evaluation.EvaluationError):
        evaluation.load_json(file)


def test_file_depth_and_count_bounds(tmp_path, inv, data):
    file = tmp_path / "oversized.json"
    file.write_bytes(b" " * 200001)
    with pytest.raises(evaluation.EvaluationError, match="file_bound"):
        evaluation.load_json(file)
    value = {}
    for _ in range(14):
        value = {"nested": value}
    with pytest.raises(evaluation.EvaluationError, match="input_bound"):
        evaluation.bounded(value)
    data["cases"] = data["cases"] * 5
    with pytest.raises(evaluation.EvaluationError, match="case_bound"):
        evaluation.validate_dataset(data, inv)


def test_valid_trace_and_refreshed_two_deletes(inv, data, trace):
    assert evaluation.validate_submission(trace, inv)["evidence"] == "synthetic_trace_contract"
    deletes = evaluation.synthetic_examples(inv)[1]
    case = next(c for c in data["cases"] if c["id"] == "two_delete_refresh")
    assert evaluation.validate_submission(deletes, inv, case)["accepted"]
    case = next(c for c in data["cases"] if c["id"] == "whole_piece_move")
    assert evaluation.validate_submission(trace, inv, case)["accepted"]


@pytest.mark.parametrize("mutate", [
    lambda t: t.update(kind="live"),
    lambda t: t.update(execution="parallel"),
    lambda t: t.update(extra=True),
    lambda t: t["steps"].pop(),
    lambda t: t["steps"].pop(0),
    lambda t: t["steps"].pop(1),
    lambda t: t["steps"].pop(2),
    lambda t: t["steps"][3].update(tool="bogus"),
    lambda t: t["steps"][3].update(tool="assign_fabric"),
    lambda t: t["steps"][3]["args"].update(dx=True),
    lambda t: t["steps"][3]["args"].update(dx=float("nan")),
    lambda t: t["steps"][3]["args"].update(dx=float("inf")),
    lambda t: t["steps"][3]["args"].update(dx=100001),
    lambda t: t["steps"][3]["args"].update(expected_name="wrong"),
    lambda t: t["steps"][3]["args"].update(extra=1),
    lambda t: t["steps"][4]["result"]["pattern"].update(name="wrong"),
    lambda t: t["steps"][4]["result"]["pattern"].update(position_mm=[40, 0]),
    lambda t: t["steps"][3]["result"]["pattern"].update(area_mm2=200),
    lambda t: t["steps"][3]["result"].update(pattern_count=2),
    lambda t: t["steps"][3]["result"].update(verified="true"),
    lambda t: t["steps"][0]["result"].update(ready=False),
    lambda t: t["steps"][0]["result"].update(capabilities=["ping"]),
    lambda t: t["steps"][3].update(session="synthetic-new"),
    lambda t: t["steps"][3]["result"].update(ok=False, error="command_error"),
])
def test_unsafe_trace_rejected(inv, trace, mutate):
    mutate(trace)
    with pytest.raises(evaluation.EvaluationError):
        evaluation.validate_submission(trace, inv)


@pytest.mark.parametrize("error", ["command_error", "outcome_unknown", "scene_change_unverified", "disconnect", "client_timeout", "stale_pattern"])
def test_stop_on_error_no_retry_or_finally_cleanup(inv, trace, error):
    trace["steps"] = trace["steps"][:4]
    trace["steps"][-1]["result"] = {"ok": False, "error": error, "isError": True}
    trace["decision"] = "stopped"
    assert evaluation.validate_submission(trace, inv)["stop_reason"]
    for tool, args in [("transport_status", {}), ("move_pattern_relative", trace["steps"][-1]["args"]),
                       ("delete_pattern", {"pattern_index": 0, "expected_name": "panel"})]:
        continued = deepcopy(trace)
        continued["steps"].append({"tool": tool, "args": args, "session": "synthetic-a", "result": {}})
        with pytest.raises(evaluation.EvaluationError, match="call_after_stop"):
            evaluation.validate_submission(continued, inv)


@pytest.mark.parametrize("alter", [
    lambda t: t["steps"][-1]["result"].update(verified=False),
    lambda t: t["steps"][-1]["result"].update(pattern_count=True),
    lambda t: t["steps"][-1]["result"].update(unexpected=1),
    lambda t: t["steps"][-1].update(session="synthetic-b"),
])
def test_schema_or_session_change_can_only_stop(inv, trace, alter):
    trace["steps"] = trace["steps"][:4]
    trace["decision"] = "stopped"
    alter(trace)
    assert evaluation.validate_submission(trace, inv)["stop_reason"] in {"schema_mismatch", "session_change"}


def test_stale_second_delete_and_missing_refresh_rejected(inv):
    trace = evaluation.synthetic_examples(inv)[1]
    trace["steps"][5]["args"]["pattern_index"] = 1
    with pytest.raises(evaluation.EvaluationError, match="stale_target"):
        evaluation.validate_submission(trace, inv)
    trace = evaluation.synthetic_examples(inv)[1]
    trace["steps"].pop(3)
    with pytest.raises(evaluation.EvaluationError, match="missing_independent_readback"):
        evaluation.validate_submission(trace, inv)


def test_missing_fresh_session_preflight_between_mutations(inv):
    trace = evaluation.synthetic_examples(inv)[1]
    trace["steps"].pop(4)
    with pytest.raises(evaluation.EvaluationError, match="missing_mutation_preflight"):
        evaluation.validate_submission(trace, inv)


def test_plan_is_not_trace_evidence(inv, trace):
    plan = {**trace, "kind": "plan", "steps": [{"tool": s["tool"], "args": s["args"]} for s in trace["steps"]]}
    assert evaluation.validate_submission(plan, inv)["evidence"] == "static_plan_only"
    plan["steps"].pop()
    with pytest.raises(evaluation.EvaluationError, match="unfinished_readback"):
        evaluation.validate_submission(plan, inv)


def test_no_call_case_and_decision_and_required_args(inv, data, trace):
    case = next(c for c in data["cases"] if c["id"] == "bezier_controls_no_call")
    no_call = {"kind": "plan", "execution": "serial", "steps": [], "decision": "blocked", "blockers": ["unsupported_geometry"]}
    assert evaluation.validate_submission(no_call, inv, case)["accepted"]
    no_call["steps"] = [{"tool": "transport_status", "args": {}}]
    with pytest.raises(evaluation.EvaluationError, match="no_call_required"):
        evaluation.validate_submission(no_call, inv, case)
    case = next(c for c in data["cases"] if c["id"] == "whole_piece_move")
    case["required_args"]["move_pattern_relative"]["dx"] = 30
    with pytest.raises(evaluation.EvaluationError, match="required_args_mismatch"):
        evaluation.validate_submission(trace, inv, case)


def test_fixture_and_scope_and_diagnostic_guards(inv, data, trace):
    case = next(c for c in data["cases"] if c["id"] == "whole_piece_move")
    case["fixture"]["patterns"] = ["other"]
    with pytest.raises(evaluation.EvaluationError, match="fixture_patterns_mismatch"):
        evaluation.validate_submission(trace, inv, case)
    with pytest.raises(evaluation.EvaluationError, match="scope_violation"):
        evaluation.validate_submission(trace, inv, scope="read_only")
    plan = {"kind": "plan", "execution": "serial", "steps": [{"tool": "create_test_rectangle", "args": {}}],
            "decision": "complete", "blockers": []}
    with pytest.raises(evaluation.EvaluationError, match="diagnostic_not_production"):
        evaluation.validate_submission(plan, inv)


def test_cli_check_and_self_test(capsys):
    assert evaluation.main(["--check", "--self-test"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cases"] >= 20 and result["tools"] == 24
    assert result["self_test"] == {"valid_accepted": 2, "invalid_rejected": 6}
    assert "not_llm" in result["evidence"]


def test_cli_supplied_trace_and_private_failure(tmp_path, trace, capsys):
    file = tmp_path / "synthetic.json"
    file.write_text(json.dumps(trace), encoding="utf-8")
    assert evaluation.main(["--submission", str(file), "--case", "whole_piece_move"]) == 0
    assert json.loads(capsys.readouterr().out)["submission"]["accepted"]
    file.write_text('{"secret":"DO-NOT-PRINT"}', encoding="utf-8")
    assert evaluation.main(["--submission", str(file), "--case", "whole_piece_move"]) == 1
    output = capsys.readouterr().out
    assert "DO-NOT-PRINT" not in output and str(file) not in output
    assert json.loads(output)["error"] == "offline_contract_validation_failed"


def chain_trace(inv):
    """Every production mutation, with readback and refreshed session snapshots."""
    info = evaluation.synthetic_examples(inv)[0]["steps"][0]
    def step(tool, args, result):
        return {"tool": tool, "args": args, "session": "synthetic-a", "result": result}
    def geo(index, name, x=0):
        return {"index": index, "name": name, "position_mm": [x, 0], "area_mm2": 100,
                "bounding_box": {"Width": "10", "Height": "10"}}
    def mutation(pattern, count=2):
        return {"ok": True, "verified": True, "pattern_count": count, "pattern": pattern, "executor_ms": 1}
    def read(pattern):
        return step("get_pattern_geometry", {"pattern_index": pattern["index"]}, {"ok": True, "pattern": pattern})
    steps = [deepcopy(info), step("get_pattern_list", {}, {"ok": True, "pattern_count": 0, "patterns": []}),
             step("create_pattern", {"points": [[0, 0], [10, 0], [10, 10], [0, 10]], "name": "panel"},
                  mutation(geo(0, "panel"), 1)), read(geo(0, "panel")), deepcopy(info),
             step("copy_pattern_with_offset", {"pattern_index": 0, "expected_name": "panel", "name": "copy", "dx": 20, "dy": 0},
                  mutation(geo(1, "copy", 20))), read(geo(1, "copy", 20)), deepcopy(info),
             step("move_pattern_relative", {"pattern_index": 1, "expected_name": "copy", "dx": 20, "dy": 0},
                  mutation(geo(1, "copy", 40))), read(geo(1, "copy", 40)), deepcopy(info),
             step("set_pattern_name", {"pattern_index": 1, "expected_name": "copy", "name": "front"},
                  mutation(geo(1, "front", 40))), read(geo(1, "front", 40)), deepcopy(info),
             step("delete_pattern", {"pattern_index": 1, "expected_name": "front"},
                  {"ok": True, "verified": True, "pattern_count": 1, "deleted_name": "front", "executor_ms": 1}),
             step("get_pattern_list", {}, {"ok": True, "pattern_count": 1, "patterns": [{"index": 0, "name": "panel"}]})]
    return {"kind": "trace", "execution": "serial", "steps": steps, "decision": "complete", "blockers": []}


def test_complete_production_chain(inv):
    assert evaluation.validate_submission(chain_trace(inv), inv)["accepted"]


@pytest.mark.parametrize("position", [2, 5, 8, 11, 14])
@pytest.mark.parametrize("fault", ["command_error", "outcome_unknown", "schema_mismatch", "session_change"])
def test_each_mutating_stage_stops_on_injected_fault(inv, position, fault):
    trace = chain_trace(inv)
    if fault == "schema_mismatch":
        trace["steps"][position]["result"]["verified"] = "true"
    elif fault == "session_change":
        trace["steps"][position]["session"] = "synthetic-b"
    else:
        trace["steps"][position]["result"] = {"ok": False, "error": fault}
    trace["decision"] = "stopped"
    with pytest.raises(evaluation.EvaluationError, match="call_after_stop"):
        evaluation.validate_submission(trace, inv)
    trace["steps"] = trace["steps"][:position + 1]
    assert evaluation.validate_submission(trace, inv)["stop_reason"]


@pytest.mark.parametrize("points", [
    [[0, 0], [10, 10], [10, 0], [0, 10]],
    [[0, 0], [10, 0], [10, 10], [0, 0]],
    [[0, 0, 1], [10, 0, 1], [10, 10, 1]],
    [[0, 0], [5, 0], [10, 0], [10, 10]],
    [[False, 0], [10, 0], [10, 10]],
    [[0, 0]] * 65,
])
def test_invalid_shape_arguments_rejected(inv, points):
    with pytest.raises(evaluation.EvaluationError, match="invalid_arguments"):
        evaluation.validate_args("create_pattern", {"points": points, "name": "panel"}, inv)


def test_diagnostic_success_requires_count_and_independent_count(inv):
    trace = evaluation.synthetic_examples(inv)[0]
    trace["steps"] = trace["steps"][:1] + [
        {"tool": "get_pattern_count", "args": {}, "session": "synthetic-a", "result": {"ok": True, "pattern_count": 0}},
        {"tool": "create_test_rectangle", "args": {}, "session": "synthetic-a", "result": {"ok": True, "created": True, "pattern_count": 1}},
        {"tool": "get_pattern_count", "args": {}, "session": "synthetic-a", "result": {"ok": True, "pattern_count": 1}}]
    assert evaluation.validate_submission(trace, inv, scope="diagnostic")["accepted"]
    trace["steps"][-1]["result"]["pattern_count"] = 2
    with pytest.raises(evaluation.EvaluationError, match="readback_mismatch"):
        evaluation.validate_submission(trace, inv, scope="diagnostic")


def test_status_without_capabilities_cannot_preflight_static_native_plan(inv):
    plan = {"kind": "plan", "execution": "serial", "steps": [
        {"tool": "transport_status", "args": {}}, {"tool": "ping", "args": {}}],
        "decision": "complete", "blockers": []}
    with pytest.raises(evaluation.EvaluationError, match="missing_session_preflight"):
        evaluation.validate_submission(plan, inv)


def test_ping_boolean_result_is_strict():
    with pytest.raises(evaluation.EvaluationError, match="ping_schema"):
        evaluation.validate_success("ping", {"ok": 1, "pong": True})


def test_generated_files_are_bounded():
    for relative in ["scripts/evaluate_tool_workflows.py", "tests/evals/clo_tool_selection.json",
                     "tests/test_tool_workflow_evals.py", "docs/CLO_TOOL_EVALUATION.md"]:
        assert (ROOT / relative).stat().st_size <= 200000
