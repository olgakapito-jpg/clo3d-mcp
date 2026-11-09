"""Conservative coverage semantics; no imports of native CLO or legacy code."""

import copy
import ast
import importlib.util
import json
import hashlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("coverage_builder", ROOT / "scripts/build_api_coverage.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def row():
    return builder.coverage_row({"qualified_name": "pattern_api.MovePatternPoint", "signature": "MovePatternPoint(int, int, float, float)", "evidence": [{"url": "https://developer.clo3d.com/list.html#move"}]})


def test_reference_does_not_mean_overload_implementation():
    value = builder.coverage_row({"qualified_name": "fabric_api.AddFabric", "signature": "AddFabric(str)", "evidence": ["official"]}, {"presence": "present", "binding": "callable", "evidence": "docstring"}, {"tools": ["some_current_operation"], "call_arity": 1}, ["add_fabric"], ["import_fabric"])
    assert value["runtime_presence"] == "present"
    assert value["implementation"] == "planned"
    assert value["verification"] == "not_tested"
    assert value["overload_coverage"] == "not_established"
    assert value["effect"] == "unknown"
    builder.validate_rows([value])


@pytest.mark.parametrize("field,value", [("owner_task", "A99"), ("domain", "made_up"), ("runtime_presence", "available"), ("binding_status", "present"), ("verification", "passed"), ("implementation", "done"), ("effect", "probably_read")])
def test_unknown_status_or_owner_rejected(field, value):
    item = row()
    item[field] = value
    with pytest.raises(ValueError):
        builder.validate_rows([item])


def test_duplicate_missing_evidence_and_false_implemented_rejected():
    item = row()
    with pytest.raises(ValueError):
        builder.validate_rows([item, copy.deepcopy(item)])
    for change in ({"docs_evidence": []}, {"verification": "real_pass"}, {"implementation": "implemented"}, {"runtime_presence": "present"}, {"binding_status": "callable"}, {"runtime_overload_presence": "present"}, {"runtime_overload_binding": "callable"}, {"runtime_evidence_scope": "exact_overload_verified"}):
        invalid = {**item, **change}
        with pytest.raises(ValueError):
            builder.validate_rows([invalid])


def test_runtime_only_code_fences_are_evidence():
    text = "## fabric_api\n\nGetMadeUp() in prose\n```text\nGetFabricName(int) -> str; GetFabricName(int,int) -> str\n```\n## Other notes\nAbsent()\n"
    result = builder.runtime_observations(text)
    assert set(result) == {"fabric_api.GetFabricName"}
    assert "overloads" not in result["fabric_api.GetFabricName"]


def test_historical_runtime_names_count_is_explicit_and_not_native_acceptance():
    result = builder.runtime_observations((ROOT / "docs/CLO_API_RUNTIME_EVIDENCE.md").read_text(encoding="utf-8"))
    assert len(result) == 43
    assert all(item["presence"] == "present" and "no native execution" in item["scope"] for item in result.values())


def test_qualified_module_is_part_of_identity():
    first = row()
    other = builder.coverage_row({"qualified_name": "utility_api.MovePatternPoint", "signature": first["signature"], "evidence": ["official"]})
    assert first["id"] != other["id"]


def test_prefix_does_not_prove_effect_or_units():
    value = builder.coverage_row({"qualified_name": "export_api.ExportTechPackToStream", "evidence": ["official"]})
    assert value["effect"] == "unknown"
    assert value["may_open_dialog"] == "not_checked"
    assert value["units"] == "not_checked"


def test_current_scope_has_real_tool_names_and_does_not_claim_overload_acceptance():
    data = json.loads((ROOT / "docs/api/current_operation_scope.json").read_text(encoding="utf-8"))
    tree = ast.parse((ROOT / "src/clo3d_mcp/transport_server.py").read_text(encoding="utf-8"))
    inventory = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
                 and any(isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                         and dec.func.attr == "tool" for dec in node.decorator_list)}
    assert len(inventory) == 24
    symbols = set()
    for operation in data["operations"]:
        assert operation["symbol"] not in symbols
        symbols.add(operation["symbol"])
        assert set(operation["tools"]) <= inventory
        assert type(operation["call_arity"]) is int
        assert 0 <= operation["call_arity"] <= 8
        assert operation["scope"] and operation["role"] in ("read", "mutation")
    assert set(data["infrastructure_tools"]) <= inventory
    assert "not_established" in data["overload_policy"]
    evidence = data["evidence"]
    for path in [value for value in evidence.values() if isinstance(value, str)] + evidence["tests"]:
        assert (ROOT / path).is_file(), path


def test_review_gates_have_unique_ids_evidence_and_unblocking_criteria():
    gates = json.loads((ROOT / "docs/api/review_gates.json").read_text(encoding="utf-8"))["gates"]
    assert len({gate["id"] for gate in gates}) == len(gates)
    for gate in gates:
        assert gate["reason"] and gate["required_evidence"] and gate["scope"]
        assert gate["acceptance_package"] in {"B%02d" % i for i in range(14)}
        for path in gate["references"]:
            assert (ROOT / path).is_file(), path
        for symbol in gate["symbols"]:
            assert symbol.count(".") == 1


def test_line_review_keeps_both_length_overloads_unimplemented_and_not_outline_fallback():
    gates = json.loads((ROOT / "docs/api/review_gates.json").read_text(encoding="utf-8"))["gates"]
    gate = next(g for g in gates if g["id"] == "line-read-contract")
    assert set(gate["symbols"]) == {"pattern_api.GetPatternLineInfo", "pattern_api.GetLineLength"}
    assert "docs/CLO_LINE_API_CONTRACT_REVIEW.md" in gate["references"]
    _, rows = builder.load_coverage(ROOT / "docs/api/clo_api_coverage.json")
    selected = [r for r in rows if r["qualified_name"] in gate["symbols"]]
    assert {r["id"] for r in selected} == {
        "pattern_api.GetPatternLineInfo#45ddc71808d7eb67",
        "pattern_api.GetLineLength#1ae661ba75ad2f5a",
        "pattern_api.GetLineLength#3bc2ab838bd1591f",
    }
    for item in selected:
        assert "line-read-contract" in item["review_gates"]
        assert item["implementation"] == "planned"
        assert item["verification"] == "not_tested"
        assert item["overload_coverage"] == "not_established"
        if item["qualified_name"] == "pattern_api.GetPatternLineInfo":
            assert item["current_operation"]["tools"] == ["get_pattern_lines"]
        else:
            assert item["current_operation"] is None
    source = (ROOT / "src/clo3d_mcp/pattern_api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Attribute) and n.attr == "GetLineLength"
                   for n in ast.walk(tree))


def test_join_preserves_every_declaration_and_does_not_merge_same_symbol_overloads():
    declarations = [{"qualified_name": "fabric_api.GetFabricCount", "signature": signature, "evidence": ["official"]}
                    for signature in ("GetFabricCount(bool=True)", "GetFabricCount(int)")]
    rows = builder.build_rows(declarations, {}, [], {"fabric_api.GetFabricCount": {"donor_tools": ["get_fabric_count"]}})
    assert len(rows) == 2 and len({r["id"] for r in rows}) == 2
    assert all(r["donor_tools"] == ["get_fabric_count"] for r in rows)
    assert all(r["implementation"] == "planned" and r["binding_status"] == "not_checked" for r in rows)


def write_manifest(tmp_path, shard_path="chunk.json", digest=None):
    raw = json.dumps({"rows": [row()]}).encode()
    (tmp_path / "chunk.json").write_bytes(raw)
    manifest = {"schema_version": 1, "shards": [{"path": shard_path, "sha256": digest or hashlib.sha256(raw).hexdigest(), "count": 1}], "counts": {"declarations": 1}}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_loader_checks_hash_and_path(tmp_path):
    path = write_manifest(tmp_path)
    assert len(builder.load_coverage(path)[1]) == 1
    path = write_manifest(tmp_path, digest="0" * 64)
    with pytest.raises(ValueError, match="hash"):
        builder.load_coverage(path)
    path = write_manifest(tmp_path, shard_path="../outside.json")
    with pytest.raises(ValueError, match="Unsafe"):
        builder.load_coverage(path)


def historical_manifest(tmp_path):
    index_dir = tmp_path / "docs/api"
    index_dir.mkdir(parents=True)
    path = write_manifest(index_dir)
    evidence = tmp_path / "docs/historical.md"
    evidence.write_bytes(b"historical symbol observations\n")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["historical_runtime_source"] = {
        "path": "docs/historical.md",
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "hash_scope": "historical_document_bytes_not_exact_overload",
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path, evidence


def test_loader_detects_changed_historical_evidence(tmp_path):
    path, evidence = historical_manifest(tmp_path)
    assert len(builder.load_coverage(path)[1]) == 1
    evidence.write_bytes(b"changed observations\n")
    with pytest.raises(ValueError, match="Historical runtime evidence hash mismatch"):
        builder.load_coverage(path)


@pytest.mark.parametrize("change", [
    {"path": "../outside.md"},
    {"path": "C:/outside.md"},
    {"path": "//server/share/outside.md"},
    {"hash_scope": "exact_overload_verified"},
])
def test_loader_rejects_unsafe_historical_provenance_before_file_access(tmp_path, monkeypatch, change):
    path, _ = historical_manifest(tmp_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["historical_runtime_source"].update(change)
    path.write_text(json.dumps(manifest), encoding="utf-8")

    def forbidden_read(self):
        pytest.fail("Unsafe historical evidence must not be read")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read)
    with pytest.raises(ValueError, match="Unsafe historical runtime provenance"):
        builder.load_coverage(path)


def test_committed_full_join_reproduces_offline_and_preserves_inventory():
    official = builder.script_loader("official_coverage_test", "build_official_api_catalog.py").load_catalog(ROOT / "docs/api/clo_official_api.json")
    mappings = builder.script_loader("mapping_coverage_test", "build_api_source_mappings.py").load_mappings(ROOT / "docs/api/clo_source_mappings.json")
    generated = builder.generated_files(official, mappings)
    for path, raw in generated.items():
        assert len(raw) <= 200000
        assert (ROOT / "docs/api" / path).read_bytes() == raw, path
    manifest, rows = builder.load_coverage(ROOT / "docs/api/clo_api_coverage.json")
    assert len(rows) == 1134
    assert len({row["qualified_name"] for row in rows}) == 890
    assert manifest["counts"]["donor_tools"] == 170
    assert manifest["counts"]["local_legacy_tools"] == 47
    assert manifest["counts"]["current_tools"] == 24
    assert {row["id"] for row in rows} == {dec["id"] for method in official["methods"] for dec in method["declarations"]}
    assert all(row["verification"] == "not_tested" and row["implementation"] == "planned" for row in rows)
    extras = {entry["qualified_name"] for entry in manifest["nonofficial_entries"]}
    assert "utility_api.GetNestingBufferSpacing" in extras
    assert len({row["qualified_name"] for row in rows if row["runtime_presence"] == "present"}) == 43
