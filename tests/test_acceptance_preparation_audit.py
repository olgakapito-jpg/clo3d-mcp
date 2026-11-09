"""Offline audit includes untracked source, not just the historical git guard."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prep_audit", ROOT / "scripts/check_acceptance_preparation.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_inventory_is_ast_only():
    assert audit.inventory("raise RuntimeError('must not execute')\n@mcp.tool()\nasync def sample(): pass\n") == ["sample"]


def test_valid_source_and_relative_link(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\n[B](b.md)\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    assert audit.audit(tmp_path, ["a.md", "b.md"]) == []


@pytest.mark.parametrize("name,body", [("asset.avac", "opaque"), ("big.json", "x" * 200001), ("bad.json", '{"x":NaN}'), ("duplicate.json", '{"x":1,"x":2}'), ("bad.md", "[gone](missing.md)\n"), ("escape.md", "[bad](../outside.md)\n"), ("space.md", "bad \n"), ("fence.md", "```py\nmissing\n"), ("merge.py", "<<<<<<< branch\n"), ("machine.md", "C:/Users/" + "PrivateUser/Documents/project")])
def test_faults_are_bounded_and_portable(tmp_path, name, body):
    (tmp_path / name).write_text(body, encoding="utf-8")
    faults = audit.audit(tmp_path, [name])
    assert faults and all(str(tmp_path) not in fault for fault in faults)


def test_unsafe_paths_and_unbounded_inventory_rejected(tmp_path):
    assert audit.audit(tmp_path, ["../outside.py"]) == ["Unsafe source-relative path"]
    assert audit.audit(tmp_path, ["a"] * 4001) == ["Too many source files; stop instead of unbounded scan"]


def test_unknown_deleted_path_is_not_a_binary_false_positive(tmp_path):
    assert audit.audit(tmp_path, ["removed.avac"]) == []


def test_private_asset_report_is_not_portable_source(tmp_path):
    (tmp_path / "acceptance-assets.json").write_text('{"candidates":[]}', encoding="utf-8")
    assert audit.audit(tmp_path, ["acceptance-assets.json"])
    output = tmp_path / "acceptance-output"
    output.mkdir()
    (output / "report.json").write_text("{}", encoding="utf-8")
    assert audit.audit(tmp_path, ["acceptance-output/report.json"])
