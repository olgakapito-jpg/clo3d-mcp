"""Offline, conservative join of official declarations and source mappings.

This is source documentation, not runtime dispatch, an API execution engine or
proof that an official overload has been exercised. No imports of CLO/legacy.
"""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRESENCE = {"present", "absent", "not_checked"}
BINDING = {"callable", "types_missing", "ambiguous", "not_checked"}
IMPLEMENTATION = {"planned", "implemented", "alias", "blocked", "excluded"}
VERIFICATION = {"not_tested", "local_pass", "real_pass", "real_fail"}
EFFECTS = {"read", "scene_mutation", "filesystem_write", "external_effect", "lifecycle", "unknown"}
DOMAINS = {"pattern", "fabric", "avatar", "colorway", "scene", "geometry", "sewing", "simulation", "io", "grading_nesting_uv", "display_render_animation", "rest", "gui", "service", "unknown"}
OWNERS = {"A0", "A1", "A2", "A3", "A4", "A5", "A6"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def runtime_observations(text):
    """Read historical, explicitly abbreviated docstrings. Never infer overloads.

    Only names inside module code fences count; prose mentions aren't evidence.
    Multiple signatures in a line stay as observation text, not parsed contracts.
    """
    result = {}
    module = None
    fenced = False
    for line in text.splitlines():
        match = re.fullmatch(r"## (\w+_api)", line)
        if match:
            module = match.group(1)
        if line.startswith("```"):
            fenced = not fenced
            continue
        if module and fenced:
            for name in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\(", line):
                key = module + "." + name
                record = result.setdefault(key, {"presence": "present", "binding": "callable", "observed_lines": [], "evidence": "docs/CLO_API_RUNTIME_EVIDENCE.md", "scope": "Historical abbreviated docstring; no native execution, no exact overload match established."})
                if line not in record["observed_lines"]:
                    record["observed_lines"].append(line)
    return result


def classify(module, symbol):
    """Planning buckets only. Effect cannot be trusted from an English prefix."""
    if module == "rest_api":
        return "rest", "A6"
    if module == "gui_api":
        return "gui", "A6"
    if module == "fabric_api":
        return "fabric", "A2"
    if module in ("import_api", "export_api"):
        return "io", "A6"
    terms = (
        (("Avatar", "Pose", "Measurement"), "avatar", "A3"),
        (("Colorway",), "colorway", "A4"),
        (("Seam", "Sew", "Topstitch", "Zipper", "Button", "Trim", "Graphic"), "sewing", "A6"),
        (("Grading", "Grade", "Nesting", "UV", "UDIM"), "grading_nesting_uv", "A6"),
        (("Simulat", "Mesh", "Cloth", "Wind", "Arrangement", "Particle", "Drap"), "simulation", "A6"),
        (("Render", "Animation", "Camera", "Display", "View", "Frame", "Light"), "display_render_animation", "A6"),
        (("Project", "Garment"), "scene", "A4"),
    )
    for needles, domain, owner in terms:
        if any(term in symbol for term in needles):
            return domain, owner
    return ("geometry", "A6") if module == "pattern_api" else ("service", "A6")


def coverage_row(declaration, observation=None, current_scope=None, donor_tools=(), legacy_tools=()):
    """Input is a normalized declaration supplied by the official loader."""
    qualified = declaration["qualified_name"]
    module, symbol = qualified.split(".", 1)
    domain, owner = classify(module, symbol)
    signature = declaration.get("signature", "")
    identity = declaration.get("id") or qualified + ":" + hashlib.sha256(signature.encode()).hexdigest()[:16]
    observed = observation or {}
    scope = current_scope or {}
    return {
        "id": identity, "module": module, "symbol": symbol,
        "qualified_name": qualified, "overload": declaration.get("overload", identity),
        "signature": signature, "domain": domain, "owner_task": owner,
        "planning_classification": "lexical_bucket_not_semantic_contract",
        "docs_evidence": declaration.get("evidence", []),
        "runtime_presence": observed.get("presence", "not_checked"),
        "binding_status": observed.get("binding", "not_checked"),
        "runtime_evidence_scope": "symbol_docstring_only_not_exact_overload",
        "runtime_overload_presence": "not_checked",
        "runtime_overload_binding": "not_checked",
        "runtime_evidence": observed.get("evidence"),
        "effect": "unknown", "may_open_dialog": "not_checked", "may_block_ui": "not_checked",
        "units": "not_checked", "implementation": "planned",
        "overload_coverage": "not_established",
        "current_operation": ({"symbol": qualified, "tools": scope["tools"], "call_arity": scope["call_arity"],
                               "scope_reference": "docs/api/current_operation_scope.json"} if scope else None),
        "donor_tools": sorted(set(donor_tools)), "legacy_tools": sorted(set(legacy_tools)),
        "verification": "not_tested", "verification_method": "unavailable",
        "acceptance_scope": "No per-overload real acceptance claimed. Current-operation evidence, if linked, has narrower scope.",
        "blocker_reason": "Native overload, units/options, effect and verification contract need explicit review before publication.",
        "dependencies": declaration.get("type_dependencies", []),
        "official_record_id": declaration.get("official_record_id", qualified),
        "documentation_issues": declaration.get("documentation_issues", []),
        "review_gates": declaration.get("review_gates", []),
    }


def validate_rows(rows):
    ids = set()
    for row in rows:
        if row.get("id") in ids or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("Duplicate or missing row id")
        ids.add(row["id"])
        for field, choices in (("runtime_presence", PRESENCE), ("binding_status", BINDING), ("implementation", IMPLEMENTATION), ("verification", VERIFICATION), ("effect", EFFECTS), ("domain", DOMAINS), ("owner_task", OWNERS)):
            if row.get(field) not in choices:
                raise ValueError("Unknown " + field)
        if not row.get("docs_evidence"):
            raise ValueError("Missing official evidence")
        if row["verification"] != "not_tested" and not row.get("verification_evidence"):
            raise ValueError("Verification without evidence")
        if row["implementation"] == "implemented" and row.get("overload_coverage") != "explicitly_reviewed":
            raise ValueError("Implementation must not be inferred from source references")
        if row["runtime_presence"] != "not_checked" and not row.get("runtime_evidence"):
            raise ValueError("Runtime presence without evidence")
        if row["binding_status"] != "not_checked" and not row.get("runtime_evidence"):
            raise ValueError("Runtime binding without evidence")
        if row.get("runtime_evidence_scope") != "symbol_docstring_only_not_exact_overload":
            raise ValueError("Unsupported runtime evidence scope")
        if (row.get("runtime_overload_presence") != "not_checked"
                or row.get("runtime_overload_binding") != "not_checked"):
            raise ValueError("Exact overload evidence is not established by this catalog")
        if row["implementation"] == "blocked" and not row.get("blocker_reason"):
            raise ValueError("Blocked without reason")
    return rows


def build_rows(declarations, observations, operations, source_links):
    """Join already-normalized facts without raising their evidence level.

    source_links: qualified name -> {donor_tools: [], legacy_tools: []}.
    Operations match a symbol, never every overload or raw English synonym.
    """
    current = {entry["symbol"]: entry for entry in operations}
    rows = []
    for declaration in sorted(declarations, key=lambda item: (item["qualified_name"], item.get("signature", ""), item.get("id", ""))):
        qualified = declaration["qualified_name"]
        link = source_links.get(qualified, {})
        rows.append(coverage_row(declaration, observations.get(qualified), current.get(qualified),
                                 link.get("donor_tools", ()), link.get("legacy_tools", ())))
    return validate_rows(rows)


def load_coverage(index_path):
    """Validate shard boundaries and hashes before trusting any row."""
    index_path = Path(index_path).resolve()
    manifest = read_json(index_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unknown coverage schema")
    for item in manifest.get("inputs", []):
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe input provenance path")
        path = index_path.parent / relative
        if path.is_symlink() or not path.resolve().is_relative_to(index_path.parent):
            raise ValueError("Unsafe input provenance target")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Input provenance hash mismatch")
    runtime = manifest.get("historical_runtime_source")
    if runtime is not None:
        relative = Path(runtime["path"])
        root = index_path.parent.parent.parent
        if (relative.is_absolute() or ".." in relative.parts
                or runtime.get("hash_scope") != "historical_document_bytes_not_exact_overload"):
            raise ValueError("Unsafe historical runtime provenance")
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("Unsafe historical runtime provenance target")
        if hashlib.sha256(path.read_bytes()).hexdigest() != runtime["sha256"]:
            raise ValueError("Historical runtime evidence hash mismatch")
    rows = []
    seen = set()
    for shard in manifest["shards"]:
        relative = Path(shard["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe shard path")
        path = index_path.parent / relative
        if path.is_symlink() or not path.resolve().is_relative_to(index_path.parent):
            raise ValueError("Unsafe shard target")
        if shard["path"] in seen:
            raise ValueError("Duplicate shard")
        seen.add(shard["path"])
        raw = path.read_bytes()
        if len(raw) > 200000:
            raise ValueError("Oversized shard")
        if hashlib.sha256(raw).hexdigest() != shard["sha256"]:
            raise ValueError("Coverage shard hash mismatch")
        items = json.loads(raw)["rows"]
        if len(items) != shard["count"]:
            raise ValueError("Shard count mismatch")
        rows.extend(items)
    validate_rows(rows)
    if len(rows) != manifest["counts"]["declarations"]:
        raise ValueError("Coverage count mismatch")
    return manifest, rows


def script_loader(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalized_inputs(official, mappings, gates):
    sources = {source["id"]: source for source in official["sources"]}
    declarations = []
    for method in official["methods"]:
        for declaration in method["declarations"]:
            evidence = []
            for occurrence in declaration["occurrences"]:
                for item in occurrence["sources"]:
                    source = sources[item["source_id"]]
                    entry = {"source_id": source["id"], "url": source["url"], "sha256": source["sha256"],
                             "line": item["line"], "block": item["block"]}
                    if item.get("anchor"):
                        entry["anchor"] = item["anchor"]
                    if entry not in evidence:
                        evidence.append(entry)
            selected = [gate["id"] for gate in gates if method["qualified_name"] in gate["symbols"]]
            if method["module"] in ("rest_api", "gui_api"):
                selected.append("external-global-lifecycle")
            dependencies = declaration.get("type_references", [])
            if dependencies:
                selected.append("binding-types")
            declarations.append({"id": declaration["id"], "qualified_name": method["qualified_name"],
                                 "signature": declaration["signature_raw"], "overload": declaration["id"],
                                 "evidence": evidence, "type_dependencies": dependencies,
                                 "official_record_id": method["id"],
                                 "documentation_issues": declaration.get("documentation_issues", []),
                                 "review_gates": sorted(set(selected))})
    links = {}
    for key, field in (("donor_tools", "donor_tools"), ("local_legacy_tools", "legacy_tools")):
        for tool in mappings[key]:
            for qualified in tool["native_ids"]:
                record = links.setdefault(qualified, {"donor_tools": [], "legacy_tools": []})
                record[field].append(tool["name"])
    return declarations, links


def make_catalog(official, mappings, observations, operations, gates):
    declarations, links = normalized_inputs(official, mappings, gates)
    rows = build_rows(declarations, observations, operations, links)
    official_names = {method["qualified_name"] for method in official["methods"]}
    extras = []
    for qualified in sorted((set(links) | set(observations) | {op["symbol"] for op in operations}) - official_names):
        extras.append({"qualified_name": qualified, "official_status": "not_in_documented_python_method_universe",
                       "mapping": links.get(qualified, {}), "runtime_observation": observations.get(qualified),
                       "implementation": "blocked", "verification": "not_tested",
                       "reason": "May be removed method, type/factory or runtime-only name. Not silently excluded or declared a callable method."})
    summary = {"declarations": len(rows), "official_names": len(official_names),
               "official_types": len(official["types"]), "additional_interfaces": len(official["interfaces"]),
               "donor_tools": len(mappings["donor_tools"]), "local_legacy_tools": len(mappings["local_legacy_tools"]),
               "current_tools": len(mappings["current_tools"]), "current_native_operations": len(operations),
               "historical_docstring_names": len(observations), "nonofficial_mapping_names": len(extras),
               "official_names_with_donor_reference": len(official_names & set(links)),
               "per_overload_implemented_claims": sum(row["implementation"] == "implemented" for row in rows),
               "per_overload_real_pass_claims": sum(row["verification"] == "real_pass" for row in rows)}
    summary["official_names_with_donor_reference"] = len({name for name in official_names if links.get(name, {}).get("donor_tools")})
    summary["official_names_with_legacy_reference"] = len({name for name in official_names if links.get(name, {}).get("legacy_tools")})
    summary["declarations_by_module"] = dict(sorted(Counter(row["module"] for row in rows).items()))
    return rows, extras, summary


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def generated_files(official, mappings):
    operations = read_json(ROOT / "docs/api/current_operation_scope.json")["operations"]
    gates = read_json(ROOT / "docs/api/review_gates.json")["gates"]
    observations = runtime_observations((ROOT / "docs/CLO_API_RUNTIME_EVIDENCE.md").read_text(encoding="utf-8"))
    rows, extras, counts = make_catalog(official, mappings, observations, operations, gates)
    files = {}
    shards = []
    for module in sorted({row["module"] for row in rows}):
        chunks, chunk = [], []
        for row in [item for item in rows if item["module"] == module]:
            if chunk and len(json_bytes({"rows": chunk + [row]})) > 150000:
                chunks.append(chunk)
                chunk = []
            chunk.append(row)
        if chunk:
            chunks.append(chunk)
        for number, items in enumerate(chunks, 1):
            path = "coverage/%s-%02d.json" % (module, number)
            raw = json_bytes({"rows": items})
            if len(raw) > 180000:
                raise ValueError("Single coverage row too large")
            files[path] = raw
            shards.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "count": len(items)})
    inputs = ["clo_official_api.json", "clo_source_mappings.json", "current_operation_scope.json", "review_gates.json"]
    manifest = {"schema_version": 1, "target": "CLO2026.1.336", "checked_on": "2026-11-09",
                "scope": "offline_join_not_native_execution_or_full_overload_acceptance",
                "inputs": [{"path": path, "sha256": hashlib.sha256((ROOT / "docs/api" / path).read_bytes()).hexdigest()} for path in inputs],
                "runtime_evidence": "docs/CLO_API_RUNTIME_EVIDENCE.md", "counts": counts,
                "historical_runtime_source": {"path": "docs/CLO_API_RUNTIME_EVIDENCE.md",
                    "sha256": hashlib.sha256((ROOT / "docs/CLO_API_RUNTIME_EVIDENCE.md").read_bytes()).hexdigest(),
                    "hash_scope": "historical_document_bytes_not_exact_overload"},
                "status_policy": "Every official declaration accounted for; source reference never elevates per-overload implementation/real status. Current limited operations recorded separately. runtime_presence/binding_status are historical symbol-level docstring observations, not exact-overload evidence or confirmation of the installed target build.",
                "shards": shards, "nonofficial_entries": extras,
                "type_closure_reference": "clo_official_api.json", "mapping_reference": "clo_source_mappings.json",
                "current_scope_reference": "current_operation_scope.json", "review_gate_reference": "review_gates.json"}
    files["clo_api_coverage.json"] = json_bytes(manifest)
    module_lines = "\n".join("| `%s` | %s |" % pair for pair in counts["declarations_by_module"].items())
    extra_lines = "\n".join("- `%s`: %s" % (entry["qualified_name"], entry["reason"]) for entry in extras) or "- Нет."
    report = """# A0: общий реестр official / runtime / donor / local / current

Target только **CLO2026.1.336**, SDK11.0.1. Это offline source specification,
не исполнение native API и не публикация новых tools. Обновляется командой
`uv run --frozen python scripts/build_api_coverage.py`; проверка без записи:
`uv run --frozen python scripts/build_api_coverage.py --check`.

## Denominator и точность

- Official qualified Python names: **%(official_names)s** (включая GUI).
- Уникальные нормализованные объявления/overloads: **%(declarations)s**.
- Отдельные документированные types/options: **%(official_types)s**; дополнительные
  interfaces: **%(additional_interfaces)s**. Не прибавляются к implemented tools.
- Donor tools: **%(donor_tools)s**, local legacy: **%(local_legacy_tools)s**,
  current enabled tools: **%(current_tools)s**, current native-operation scopes: **%(current_native_operations)s**.
- Исторические docstring observations: **%(historical_docstring_names)s** names;
  это presence/callability на уровне symbol, не точная проверка overload.
- Official names со static donor mapping: **%(official_names_with_donor_reference)s**;
  с legacy mapping: **%(official_names_with_legacy_reference)s**. Это не coverage реализации.

| Module | Unique declarations |
|---|---:|
%(module_lines)s

`clo_api_coverage.json` содержит index/counts/input hashes и coverage shards с
hash/count; все строки включают id/symbol/signature/docs evidence, runtime/binding,
owner/domain, donor/legacy links, current-operation reference, dependencies и gates.
Полные parameters/returns/docs prose/C++ pair/type-member details — в official
record по `official_record_id` через `clo_official_api.json`. Tool/handler/helper
locations и provenance — в `clo_source_mappings.json`. Это ссылки на канонические
данные, не потеря сведений и не раздувание одинаковых текстов в каждом слое.

## Чего реестр НЕ утверждает

Каждая строка классифицирована, но semantic contract (effect/units/dialogs,
индексный namespace/options/readback) остаётся **not_checked** до review данного
пакета. Лексический domain/owner — только planning bucket, не semantic evidence.
Даже `Get*`/`*Stream` не означает безопасный read. Все официальные per-overload
implementation пока planned, verification not_tested; это намеренно не выводится
из количества refs. Уже принятые ограниченные10 native operations и14 tools
не потеряны: их actual scope/evidence живёт в `current_operation_scope.json` и
source mappings, не объявляется полным покрытием официальных перегрузок.

Наличие docstring поднимает только symbol-level runtime presence/callability;
типы и конкретная overload semantics остаются отдельным gate. Type reference
resolved в official manifest означает documentation link, не Python binding.
Unresolved tokens/необычные annotations сохранены для review, не угадываются.

## Nonofficial / removed / factory references

%(extra_lines)s

Их не теряем и не считаем автоматически доступными методами. Removed nesting
getter отдельно связан с review gate; factory references требуют type review.

## Приёмка и дальнейшие пакеты

`review_gates.json` задаёт явные условия разблокирования, а
`../CLO_ACCEPTANCE_PACKAGES.md` — B00–B13 с bounded критериями. Общий порядок:
`../CLO_COMPREHENSIVE_CHECK.md`. REST/GUI/global/lifecycle не включаются в
автоматический run. Полный manifest — подготовка denominator, не обещание
проверить весь API за один запуск или реализовать его generic dispatcher.

Источники/точные counts/anomalies: `CLO_OFFICIAL_API.md` и `CLO_SOURCE_MAPPINGS.md`.
Реальные новые CLO calls при генерации реестра не выполняются.
""" % {**counts, "module_lines": module_lines, "extra_lines": extra_lines}
    files["CLO_API_CATALOG.md"] = report.encode("utf-8")
    return files


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate existing coverage index and shard hashes, offline")
    args = parser.parse_args(argv)
    index = ROOT / "docs/api/clo_api_coverage.json"
    official = script_loader("official_catalog_for_join", "build_official_api_catalog.py").load_catalog(ROOT / "docs/api/clo_official_api.json")
    mappings = script_loader("source_mappings_for_join", "build_api_source_mappings.py").load_mappings(ROOT / "docs/api/clo_source_mappings.json")
    files = generated_files(official, mappings)
    for relative, raw in files.items():
        path = index.parent / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                raise ValueError("Stale or missing generated coverage file: " + relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    manifest, rows = load_coverage(index)
    print("PASS: %d declarations, conservative per-overload statuses" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
