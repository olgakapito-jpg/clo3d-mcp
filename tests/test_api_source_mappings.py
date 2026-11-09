"""AST-only source inventory tests: no CLO/MCP imports or network requests."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_mappings", ROOT / "scripts/build_api_source_mappings.py")
mapping = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mapping)


def source(text):
    return mapping.Source("fixture.py", text.encode())


def test_helper_propagation_keeps_callable_and_indirect_evidence():
    parsed = source('''
import pattern_api as p
def invoke(function, *args):
    return function(*args)
def helper():
    return p.GetPatternCount()
def handle_info(params):
    return [invoke(p.GetPatternPieceName, 0), helper()]
HANDLERS = {"info": handle_info}
''')
    handler = parsed.registry()[0]
    assert handler["native_ids"] == ["pattern_api.GetPatternCount", "pattern_api.GetPatternPieceName"]
    refs = {r["id"]: r for r in handler["references"]}
    assert refs["pattern_api.GetPatternPieceName"]["kind"] == "callable_reference"
    assert refs["pattern_api.GetPatternPieceName"]["invoked_via"]["parameter"] == "function"
    assert refs["pattern_api.GetPatternCount"]["via"][0]["function"] == "helper"
    assert refs["pattern_api.GetPatternCount"]["confidence"] == "syntactic_indirect"


def test_helper_cycles_terminate_without_inventing_native_calls():
    parsed = source('''
def a(): return b()
def b(): return [a(), getattr(pattern_api, "Unknown")]
''')
    facts = parsed.reachable("a")
    assert facts["native_ids"] == []
    assert facts["reachable_functions"] == ["a", "b"]
    assert len(facts["dynamic_expressions"]) == 1


def test_aliases_parameters_and_nested_registration():
    parsed = source('''
from fabric_api import AddFabric as add
def handle_add(params): return add(params["path"])
HANDLERS = {"wire_add": handle_add}
def register(mcp):
    @mcp.tool(name="import_fabric")
    def tool(path: str, enabled: bool = False, *, count: int = 1) -> dict:
        """Exact description."""
        return _send("wire_add", {"path": path})
''')
    tools, handlers = parsed.tools(), parsed.registry()
    mapping.attach_handlers(tools, handlers)
    assert tools[0]["name"] == "import_fabric"
    assert tools[0]["description"] == "Exact description."
    assert tools[0]["native_ids"] == ["fabric_api.AddFabric"]
    assert tools[0]["name_aliases"][0]["wire_command"] == "wire_add"
    assert tools[0]["parameters"][0]["required"] is True
    assert tools[0]["parameters"][1]["default"] == "False"
    assert tools[0]["parameters"][2]["kind"] == "keyword_only"


def test_nested_tool_bodies_are_not_included_in_outer_helpers():
    parsed = source('''
def register(mcp):
    @mcp.tool()
    def nested(): return pattern_api.GetPatternCount()
    return None
''')
    assert parsed.facts("register")["native_references"] == []
    assert parsed.facts("register.nested")["native_references"][0]["id"] == "pattern_api.GetPatternCount"


def test_tools_without_native_references_are_retained():
    parsed = source('''
@mcp.tool()
def ping(): return _send("ping")
def handle_ping(params): return {"pong": True}
HANDLERS = {"ping": handle_ping}
''')
    tools = parsed.tools()
    mapping.attach_handlers(tools, parsed.registry())
    assert len(tools) == 1 and tools[0]["native_ids"] == []
    assert tools[0]["handler_commands"] == ["ping"]


@pytest.fixture
def snapshot():
    return mapping.load_snapshot(ROOT / mapping.SNAPSHOT)


def test_snapshot_normalized_integrity_inventory_and_local_rebuild(snapshot):
    mapping.validate_snapshot(snapshot)
    assert mapping.build(ROOT, snapshot["donor"]) == snapshot
    assert mapping.render_report(snapshot) == (ROOT / mapping.REPORT).read_text(encoding="utf-8")
    assert snapshot["counts"]["donor_tools"] == 170
    assert snapshot["counts"]["donor_handlers"] == 172
    assert snapshot["counts"]["donor_server_tools"] == 33
    assert snapshot["counts"]["donor_extended_tools"] == 137
    assert snapshot["counts"]["donor_reachable_native_ids"] == 336
    assert snapshot["counts"]["shared_donor_legacy_tool_names"] == 44
    assert snapshot["counts"]["legacy_tools"] == 47
    assert snapshot["counts"]["legacy_handlers"] == 47
    assert snapshot["counts"]["current_tools"] == 24
    assert {t["name"] for t in snapshot["donor"]["tools"] if not t["native_ids"]} == {
        "list_clo_api", "describe_clo_api", "find_api_types"}


def test_snapshot_detects_donor_tampering(snapshot):
    snapshot["donor"]["tools"][0]["description"] += "tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        mapping.validate_snapshot(snapshot)


def test_local_aliases_and_dev_extras_are_explicit(snapshot):
    tools = {t["name"]: t for t in snapshot["local"]["legacy"]["tools"]}
    for tool, command in (("save_project", "save_file"), ("get_pattern_bounding_box", "get_bounding_box"),
                          ("assign_fabric_to_pattern", "assign_fabric")):
        assert tools[tool]["name_aliases"][0]["wire_command"] == command
    assert tools["list_extensions"]["handler_commands"] == []
    extras = snapshot["local"]["legacy"]["handler_functions_outside_registry"]
    assert {e["function"] for e in extras} == {"handle_run_script", "handle_reload_plugin"}
    assert len(snapshot["local"]["legacy"]["shared_native_alias_candidates"]) == 2


def test_current_inventory_is_separate_and_acceptance_is_limited(snapshot):
    tools = {t["name"]: t for t in snapshot["local"]["current"]["tools"]}
    assert len(tools) == 24
    assert tools["get_pattern_outline"]["primary_native_ids"] == ["pattern_api.GetPatternOutlinePoints"]
    assert tools["get_pattern_outline"]["supporting_native_ids"] == ["pattern_api.GetPatternCount", "pattern_api.GetPatternPieceName"]
    assert tools["get_pattern_outline"]["acceptance"]["status"] == "blocked_real_outline_invalid_native_result"
    assert tools["copy_pattern_with_offset"]["primary_native_ids"] == [
        "pattern_api.CopyPatternPieceMove", "pattern_api.SetPatternPieceName"]
    assert "pattern_api.CopyPatternPiecePos" not in tools["copy_pattern_with_offset"]["native_ids"]
    for tool in tools.values():
        assert tool["acceptance"]["performed_by_this_builder"] is False
        assert tool["contract_acceptance"] != "accepted"
    assert tools["list_clo_api"]["native_ids"] == []
    assert tools["create_pattern"]["contract_evidence"]
    assert tools["create_pattern"]["test_evidence"]
    for tool in tools.values():
        assert tool["contract_evidence"]
        assert tool["adapter_evidence"]
        assert tool["test_evidence"]
    assert tools["create_test_rectangle"]["primary_native_ids"] == ["pattern_api.CreatePatternWithPoints"]
    assert tools["create_test_rectangle"]["supporting_native_ids"] == ["pattern_api.GetPatternCount"]
    for name in ("get_pattern_fabric", "assign_pattern_fabric"):
        assert tools[name]["acceptance"]["status"] == "limited_real_assignment_readback_ui_confirmed"
        assert "user confirmed normal UI" in tools[name]["acceptance"]["scope"]
        assert tools[name]["acceptance"]["reference"] == "docs/CLO_FABRIC_ASSIGNMENT_CHECK.md"


def test_offline_default_does_not_fetch(monkeypatch):
    def forbidden():
        raise AssertionError("Network must not be used in offline check")
    monkeypatch.setattr(mapping, "fetch_donor", forbidden)
    assert mapping.main(["--check"]) == 0


def test_loader_interface_and_small_artifacts(snapshot):
    loaded = mapping.load_mappings(ROOT / mapping.SNAPSHOT)
    assert len(loaded["donor_tools"]) == 170
    assert len(loaded["local_legacy_tools"]) == 47
    assert len(loaded["current_tools"]) == 24
    assert loaded["source_refs"]["donor"]
    for path, text in mapping.artifacts(snapshot).items():
        assert len(text.encode("utf-8")) <= 200000, path


def test_all_generated_files_pass_repository_asset_guard(snapshot):
    guard_spec = importlib.util.spec_from_file_location("asset_guard", ROOT / "tests/test_no_assets.py")
    guard = importlib.util.module_from_spec(guard_spec)
    guard_spec.loader.exec_module(guard)
    outputs = {p.as_posix(): text.encode("utf-8") for p, text in mapping.artifacts(snapshot).items()}
    assert guard.faults(list(outputs), read=outputs.__getitem__) == []


def test_donor_rebuild_rejects_bytes_not_matching_pinned_tree():
    files = {p: b"source facts only\n" for p in mapping.DONOR_FILES}
    tree = {"sha": mapping.REVISION, "truncated": False, "tree": [
        {"path": p, "type": "blob", "sha": "0" * 40} for p in mapping.DONOR_FILES]}
    with pytest.raises(ValueError, match="disagree with pinned Git tree blob"):
        mapping.donor_inventory(files, json.dumps(tree).encode())


def test_loader_rejects_shard_tampering_before_parsing(tmp_path):
    snapshot = mapping.load_snapshot(ROOT / mapping.SNAPSHOT)
    for path, text in mapping.artifacts(snapshot).items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    target = tmp_path / "docs/api/mappings/donor_tools_01.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="shard hash mismatch"):
        mapping.load_mappings(tmp_path / mapping.SNAPSHOT)
