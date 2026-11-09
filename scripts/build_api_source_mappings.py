"""Reproducible source-only CLO inventories; never import inspected modules.

Default: validate the normalized donor snapshot and rebuild/check local facts.
Network access is opt-in, pinned, bounded, read-only and never retries. Downloaded
Python is parsed as AST only. No CLO, MCP, git or third-party Python dependency.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path("docs/api/clo_source_mappings.json")
REPORT = Path("docs/api/CLO_SOURCE_MAPPINGS.md")
REVISION = "df150d95db604e4651bbbdfb151b8204209a7d12"
REPOSITORY = "adriendelmas/clo3d-mcp-extended"
RAW_BASE = f"https://raw.githubusercontent.com/{REPOSITORY}/{REVISION}/"
TREE_URL = f"https://api.github.com/repos/{REPOSITORY}/git/trees/{REVISION}?recursive=1"
NATIVE_MODULES = frozenset(("pattern_api", "fabric_api", "utility_api", "export_api",
                            "import_api", "rest_api", "gui_api"))
DONOR_FILES = (
    "LICENSE", "NOTICE", "plugin/clo3d_mcp_plugin.py", "src/clo3d_mcp/server.py",
    *(f"src/clo3d_mcp/extended/{name}.py" for name in (
        "__init__", "avatar", "docs", "files", "geometry", "materials", "nesting",
        "sewing", "simulation", "visuals")),
)
LOCAL_INPUTS = (
    "src/clo3d_mcp/server.py", "plugin/clo3d_mcp_plugin.py",
    "src/clo3d_mcp/transport_server.py", "src/clo3d_mcp/pattern_api.py",
    "src/clo3d_mcp/pattern_contract.py", "plugin/clo3d_mcp_start.py",
    "src/clo3d_mcp/pipe_runtime.py", "src/clo3d_mcp/pipe_session.py", "src/clo3d_mcp/protocol.py", "docs/PATTERN_API_CHECK.md",
    "docs/P3_MCP_CHECK.md", "tests/test_pattern_api.py", "tests/test_verify_patterns.py",
    "tests/test_transport_server.py", "tests/test_service_executor.py",
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def location(path, node):
    return {"path": path, "lines": [node.lineno, node.end_lineno]}


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else ""
    return ""


class Source:
    """Small conservative syntactic graph, not execution/dataflow simulation."""

    def __init__(self, path, data):
        self.path = path
        self.data = data
        self.text = data.decode("utf-8-sig")
        self.tree = ast.parse(self.text, filename=path)
        self.functions = {}
        self.parents = {}
        self.aliases = {name: name for name in NATIVE_MODULES}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in NATIVE_MODULES:
                        self.aliases[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module in NATIVE_MODULES:
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        self._collect(self.tree.body)

    def _collect(self, body, prefix=""):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[prefix + node.name] = node
                self._collect(node.body, prefix + node.name + ".")
            elif isinstance(node, ast.ClassDef):
                self._collect(node.body, prefix + node.name + ".")
            else:
                # Tools can be nested in an if/try registration branch.
                for field in ("body", "orelse", "finalbody"):
                    nested = getattr(node, field, None)
                    if isinstance(nested, list):
                        self._collect(nested, prefix)

    def nodes(self, function):
        """Walk one body without incorrectly including a nested function's body."""
        pending = list(ast.iter_child_nodes(function))
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            yield node
            pending.extend(ast.iter_child_nodes(node))

    def native_name(self, node):
        name = dotted(node)
        first, _, rest = name.partition(".")
        name = self.aliases.get(first, first) + ("." + rest if rest else "")
        parts = name.split(".")
        if len(parts) == 2 and parts[0] in NATIVE_MODULES:
            return name
        # Explicit adapter injection in PatternAPI.__init__, not generic self.*.
        if name.startswith("self.pattern.") and self.path.endswith("pattern_api.py"):
            return "pattern_api." + name.removeprefix("self.pattern.")
        return None

    def resolve_helper(self, node, owner):
        name = dotted(node)
        if name in self.functions:
            return name
        if name.startswith("self."):
            candidate = owner.rsplit(".", 1)[0] + "." + name[5:]
            if candidate in self.functions:
                return candidate
        prefix = owner.rsplit(".", 1)[0] if "." in owner else ""
        candidate = prefix + "." + name
        return candidate if candidate in self.functions else None

    def facts(self, name):
        function = self.functions[name]
        refs, helpers, dynamic = [], [], []
        for node in sorted(self.nodes(function), key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
            native = self.native_name(node)
            if native:
                parent = self.parents.get(node)
                kind = "direct_call" if isinstance(parent, ast.Call) and parent.func is node else "callable_reference"
                ref = {"id": native, "kind": kind,
                       "expression": ast.unparse(parent if kind == "direct_call" else node),
                       **location(self.path, node)}
                if kind == "callable_reference" and isinstance(parent, ast.Call):
                    helper = self.resolve_helper(parent.func, name)
                    if helper and node in parent.args:
                        position = parent.args.index(node)
                        target = self.functions[helper]
                        parameters = target.args.posonlyargs + target.args.args
                        if position < len(parameters):
                            parameter = parameters[position].arg
                            calls = [c for c in self.nodes(target) if isinstance(c, ast.Call)
                                     and dotted(c.func) == parameter]
                            if calls:
                                ref["invoked_via"] = {
                                    "helper": helper, "parameter": parameter,
                                    "call_sites": [location(self.path, c) for c in sorted(calls, key=lambda c: c.lineno)],
                                }
                refs.append(ref)
            if isinstance(node, ast.Call):
                helper = self.resolve_helper(node.func, name)
                if helper:
                    helpers.append({"function": helper, **location(self.path, node)})
                if dotted(node.func) in ("getattr", "eval", "exec"):
                    dynamic.append({"expression": ast.unparse(node), **location(self.path, node)})
        return {"function": name, **location(self.path, function), "native_references": refs,
                "helper_calls": helpers, "dynamic_expressions": dynamic}

    def reachable(self, name):
        """Keep a shortest syntactic evidence chain for each reachable reference."""
        pending, seen, refs, dynamic = [(name, [])], set(), [], []
        while pending:
            current, chain = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            facts = self.facts(current)
            for ref in facts["native_references"]:
                refs.append({**ref, "via": chain,
                             "confidence": "syntactic_direct" if not chain and ref["kind"] == "direct_call"
                             else "syntactic_indirect"})
            dynamic.extend({**item, "via": chain} for item in facts["dynamic_expressions"])
            for call in facts["helper_calls"]:
                pending.append((call["function"], chain + [call]))
        return {"native_ids": sorted({r["id"] for r in refs}), "references": refs,
                "dynamic_expressions": dynamic, "reachable_functions": sorted(seen)}

    def tools(self):
        result = []
        for name, node in self.functions.items():
            decorators = [d for d in node.decorator_list if isinstance(d, ast.Call)
                          and dotted(d.func).endswith(".tool")]
            if not decorators:
                continue
            tool_name = node.name
            for keyword in decorators[0].keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    tool_name = keyword.value.value
            routes = []
            for call in self.nodes(node):
                if not isinstance(call, ast.Call) or not call.args:
                    continue
                if dotted(call.func) not in ("_send", "service.call"):
                    continue
                if isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                    routes.append({"command": call.args[0].value, **location(self.path, call)})
            arguments = node.args
            positional = arguments.posonlyargs + arguments.args
            defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
            params = []
            for i, (arg, default) in enumerate(zip(positional, defaults)):
                params.append({"name": arg.arg, "kind": "positional_only" if i < len(arguments.posonlyargs)
                               else "positional_or_keyword", "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                               "required": default is None, "default": ast.unparse(default) if default is not None else None})
            for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
                params.append({"name": arg.arg, "kind": "keyword_only", "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                               "required": default is None, "default": ast.unparse(default) if default is not None else None})
            for arg, kind in ((arguments.vararg, "var_positional"), (arguments.kwarg, "var_keyword")):
                if arg:
                    params.append({"name": arg.arg, "kind": kind, "annotation": ast.unparse(arg.annotation) if arg.annotation else None,
                                   "required": False, "default": None})
            result.append({"name": tool_name, "function": name, **location(self.path, node),
                           "signature": f"{node.name}({ast.unparse(arguments)})" + (" -> " + ast.unparse(node.returns) if node.returns else ""),
                           "signature_source": "ast_normalized_python_declaration_not_MCP_JSON_schema",
                           "parameters": params, "description": ast.get_docstring(node, clean=True) or "",
                           "routes": sorted(routes, key=lambda r: r["lines"]),
                           "contract_acceptance": "not_established_by_static_mapping"})
        return sorted(result, key=lambda item: item["name"])

    def registry(self):
        result = []
        for node in self.tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "HANDLERS" for target in node.targets):
                continue
            for key, value in zip(node.value.keys, node.value.values):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    raise ValueError("Non-literal HANDLERS key")
                function = dotted(value)
                if function not in self.functions:
                    raise ValueError(f"Missing handler {function}")
                result.append({"command": key.value, "function": function,
                               "registry_evidence": location(self.path, value),
                               "handler_evidence": location(self.path, self.functions[function]),
                               **self.reachable(function)})
        return sorted(result, key=lambda item: item["command"])


def source_record(path, data, donor=False):
    return {"path": path, "sha256": digest(data), "bytes": len(data),
            "lines": len(data.decode("utf-8-sig").splitlines()),
            **({"url": RAW_BASE + path,
                "browse_url": f"https://github.com/{REPOSITORY}/blob/{REVISION}/{path}"} if donor else {})}


def attach_handlers(tools, handlers):
    index = {item["command"]: item for item in handlers}
    for tool in tools:
        tool["handler_commands"] = [route["command"] for route in tool["routes"] if route["command"] in index]
        tool["unresolved_commands"] = [route["command"] for route in tool["routes"] if route["command"] not in index]
        tool["native_ids"] = sorted({native for command in tool["handler_commands"] for native in index[command]["native_ids"]})
        tool["route_status"] = "literal_handler_route" if tool["handler_commands"] else "no_native_handler_route"
        tool["name_aliases"] = [{"tool_name": tool["name"], "wire_command": command,
                                 "handler_function": index[command]["function"], "equivalence": "routing_only_not_contract"}
                                for command in tool["handler_commands"] if command != tool["name"]]


def inventory(files):
    plugin = Source("plugin/clo3d_mcp_plugin.py", files["plugin/clo3d_mcp_plugin.py"])
    handlers = plugin.registry()
    tools = []
    for path, data in sorted(files.items()):
        if path.startswith("src/") and path.endswith(".py"):
            tools.extend(Source(path, data).tools())
    tools.sort(key=lambda item: item["name"])
    attach_handlers(tools, handlers)
    return {"tools": tools, "handlers": handlers,
            "handler_functions_outside_registry": [plugin.facts(name) for name in sorted(plugin.functions)
                if name.startswith("handle_") and name not in {h["function"] for h in handlers}]}


def donor_inventory(files, tree_bytes):
    tree = json.loads(tree_bytes)
    if tree.get("sha") != REVISION or tree.get("truncated"):
        raise ValueError("Unexpected/truncated pinned donor tree")
    paths = {entry["path"] for entry in tree["tree"] if entry["type"] == "blob"}
    if not set(DONOR_FILES) <= paths:
        raise ValueError("Pinned donor tree missing required sources")
    discovered = {p for p in paths if p.startswith("src/clo3d_mcp/extended/") and p.endswith(".py")}
    if discovered != {p for p in DONOR_FILES if "/extended/" in p}:
        raise ValueError("Unexpected donor extended module inventory")
    blobs = {entry["path"]: entry["sha"] for entry in tree["tree"] if entry["type"] == "blob"}
    for path, data in files.items():
        blob_sha = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        if blob_sha != blobs.get(path):
            raise ValueError(f"Source bytes disagree with pinned Git tree blob: {path}")
    result = inventory(files)
    result.update({"repository": REPOSITORY, "revision": REVISION,
                   "tree": {"url": TREE_URL, "sha256": digest(tree_bytes),
                            "response_sha": tree["sha"], "truncated": False},
                   "sources": [{**source_record(path, files[path], True), "git_blob_sha1": blobs[path]} for path in sorted(files)],
                   "license": {"identifier": "MIT", "copyright": [
                       "Copyright (c) 2026 Violet Sphinx (original clo3d-mcp)",
                       "Copyright (c) 2026 adriendelmas (clo3d-mcp-extended)"],
                       "license_url": RAW_BASE + "LICENSE", "notice_url": RAW_BASE + "NOTICE",
                       "notice_summary": "Derived from Ubani-Studio/clo3d-mcp (MIT); no CLO SDK sources included; not affiliated with CLO Virtual Fashion Inc.",
                       "reuse": "Normalized source facts, signatures and tool descriptions only; no donor executable implementation copied or executed. Retain donor LICENSE/NOTICE if later copying code or substantial fragments."}})
    if len(result["tools"]) != 170 or len(result["handlers"]) != 172:
        raise ValueError("Donor inventory must be exactly 170 tools / 172 registry commands")
    result["normalized_sha256"] = digest(canonical(result).encode("utf-8"))
    return result


CURRENT_PRIMARY = {
    "get_pattern_count": ["GetPatternCount"],
    "create_test_rectangle": ["GetPatternCount", "CreatePatternWithPoints"],
    "get_pattern_list": ["GetPatternCount", "GetPatternPieceName"],
    "get_pattern_geometry": ["GetPatternPieceName", "GetPatternPiecePos", "GetPatternPieceArea", "GetBoundingBoxOfPattern"],
    "create_pattern": ["CreatePatternWithPoints", "SetPatternPieceName"],
    "set_pattern_name": ["SetPatternPieceName"],
    "copy_pattern_with_offset": ["CopyPatternPieceMove", "SetPatternPieceName"],
    "move_pattern_relative": ["SetPatternPieceMove"],
    "delete_pattern": ["DeletePatternPiece"],
}
PATTERN_TOOLS = frozenset(("list_clo_api", "describe_clo_api", "get_pattern_list", "get_pattern_geometry",
                           "create_pattern", "set_pattern_name", "copy_pattern_with_offset", "move_pattern_relative", "delete_pattern"))
GEOMETRY_IDS = ["GetPatternCount", "GetPatternPieceName", "GetPatternPiecePos", "GetPatternPieceArea", "GetBoundingBoxOfPattern"]


def evidence_functions(source, names):
    return [{"function": name, **location(source.path, source.functions[name])} for name in names]


def current_inventory(files):
    server = Source("src/clo3d_mcp/transport_server.py", files["src/clo3d_mcp/transport_server.py"])
    adapter = Source("src/clo3d_mcp/pattern_api.py", files["src/clo3d_mcp/pattern_api.py"])
    launcher = Source("plugin/clo3d_mcp_start.py", files["plugin/clo3d_mcp_start.py"])
    contract = Source("src/clo3d_mcp/pattern_contract.py", files["src/clo3d_mcp/pattern_contract.py"])
    protocol = Source("src/clo3d_mcp/protocol.py", files["src/clo3d_mcp/protocol.py"])
    executor = Source("src/clo3d_mcp/pipe_session.py", files["src/clo3d_mcp/pipe_session.py"])
    tools = server.tools()
    all_refs = [ref for source in (adapter, launcher) for name in source.functions
                for ref in source.facts(name)["native_references"]]
    for tool in tools:
        name = tool["name"]
        primary = ["pattern_api." + n for n in CURRENT_PRIMARY.get(name, [])]
        if name == "create_test_rectangle":
            primary = ["pattern_api.CreatePatternWithPoints"]
        supporting = ["pattern_api." + n for n in GEOMETRY_IDS] if name in PATTERN_TOOLS and name not in ("list_clo_api", "describe_clo_api", "get_pattern_list") else []
        if name == "create_test_rectangle":
            supporting = ["pattern_api.GetPatternCount"]
        tool["primary_native_ids"] = primary
        tool["primary_native_role"] = "effect" if name in ("create_pattern", "set_pattern_name", "copy_pattern_with_offset", "move_pattern_relative", "delete_pattern", "create_test_rectangle") else "read_or_introspection"
        tool["supporting_native_ids"] = sorted(set(supporting) - set(primary))
        tool["native_ids"] = sorted(set(primary + supporting))
        tool["native_reference_evidence"] = [{**ref, "role": "primary_effect_or_read" if ref["id"] in primary else "preflight_or_readback"} for ref in all_refs if ref["id"] in tool["native_ids"]]
        tool["mapping_method"] = "reviewed_command_branch_selection_plus_AST_reference_locations; not_execution_trace"
        tool["profile"] = "pattern_package" if name in PATTERN_TOOLS else "base_service"
        tool["contract_evidence"] = evidence_functions(contract, [n for n in ("validate_params", "validate_result") if n in contract.functions]) if name in PATTERN_TOOLS else evidence_functions(server, ["build_mcp"])
        if name not in ("transport_status", "get_session_info") and name not in PATTERN_TOOLS:
            tool["contract_evidence"] += evidence_functions(protocol, ["validate"]) + evidence_functions(executor, ["Executor.receive"])
        tool["contract_scope"] = "strict raw command params/results via pattern_contract" if name in PATTERN_TOOLS else "base tool declaration/protocol/executor result checks; not pattern-command raw exact-key parity"
        if name in PATTERN_TOOLS:
            selected = ["PatternAPI.__call__"]
            if name in ("get_pattern_list", "get_pattern_geometry"):
                selected += ["PatternAPI._list" if name == "get_pattern_list" else "PatternAPI._geometry"]
            elif name not in ("list_clo_api", "describe_clo_api"):
                selected += ["PatternAPI._mutate", "PatternAPI._target", "PatternAPI._list", "PatternAPI._geometry"]
            tool["adapter_evidence"] = evidence_functions(adapter, selected)
        else:
            tool["adapter_evidence"] = evidence_functions(server, ["Service.status"] if name in ("transport_status", "get_session_info") else ["Service.call"])
            if name not in ("transport_status", "get_session_info"):
                tool["adapter_evidence"] += evidence_functions(executor, ["Executor.receive"])
            if name == "create_test_rectangle":
                tool["adapter_evidence"] += evidence_functions(launcher, ["main.create_rectangle"])
            if name == "get_pattern_count":
                tool["adapter_evidence"] += evidence_functions(launcher, ["main"])
        tests = []
        for path, data in sorted(files.items()):
            if not path.startswith("tests/") or not path.endswith(".py"):
                continue
            source = Source(path, data)
            for fname, node in source.functions.items():
                if not fname.split(".")[-1].startswith("test_"):
                    continue
                # Async scenarios are nested in many synchronous pytest tests.
                literals = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
                if name in literals or name in fname:
                    tests.append({"function": fname, **location(path, node), "kind": "syntactic_test_reference_not_test_result"})
        tool["test_evidence"] = tests
        tool["acceptance"] = {
            "status": "historical_limited_pattern_acceptance" if name in PATTERN_TOOLS else "historical_transport_diagnostic_evidence",
            "reference": "docs/PATTERN_API_CHECK.md" if name in PATTERN_TOOLS else "docs/P3_MCP_CHECK.md",
            "scope": "CLO 2026.1; simple straight polygons; count/name/position/area/bbox and load10 <=2 test pieces, <=256 total; introspection presence/docstrings only. Not curves/holes/avatar/sewing/simulation/import/export/point editing; exact patch build not recorded." if name in PATTERN_TOOLS else "Existing P0-P3 transport/base diagnostic scope only; not full native API or full tool-authoring DoD.",
            "performed_by_this_builder": False,
        }
        tool["contract_acceptance"] = "existing_limited_evidence_not_full_official_overload_or_build_acceptance"
    if len(tools) != 14:
        raise ValueError("Expected 14 current tools with pattern profile")
    return {"tools": tools, "profile_note": "14 only with pattern_package enabled; 5 base tools otherwise. Static declarations, not a live tools/list response."}


def local_inventory(root):
    files = {path: (root / path).read_bytes() for path in LOCAL_INPUTS}
    legacy = inventory({p: files[p] for p in ("src/clo3d_mcp/server.py", "plugin/clo3d_mcp_plugin.py")})
    if len(legacy["tools"]) != 47 or len(legacy["handlers"]) != 47:
        raise ValueError("Expected local legacy 47 tools / 47 registry commands")
    legacy["shared_native_alias_candidates"] = [
        {"tools": ["open_file", "import_file"], "shared_native_id": "import_api.ImportFile",
         "status": "shared_native_name_only_not_contract_equivalence"},
        {"tools": ["add_fabric", "import_fabric"], "shared_native_id": "fabric_api.AddFabric",
         "status": "shared_native_name_only_not_contract_equivalence"},
    ]
    legacy["current_replacement_limits"] = [
        {"legacy_tool": "get_pattern_bounding_box", "current_tool": "get_pattern_geometry",
         "scope": "bbox field only; get_pattern_info/GetPatternInformation not fully covered"},
        {"legacy_tool": "copy_pattern", "current_tool": "copy_pattern_with_offset",
         "scope": "relative offset only; CopyPatternPiecePos != CopyPatternPieceMove positional semantics"},
        {"legacy_tool": "create_pattern", "current_tool": "create_pattern",
         "scope": "simple straight 3-64 pair polygon only, not legacy triplets/curves"},
    ]
    return {"sources": [source_record(path, files[path]) for path in sorted(files)],
            "legacy": legacy, "current": current_inventory(files)}


def counts(donor, local):
    donor_names = {t["name"] for t in donor["tools"]}
    legacy_names = {t["name"] for t in local["legacy"]["tools"]}
    donor_native = {r["id"] for h in donor["handlers"] for r in h["references"]}
    return {"donor_tools": len(donor_names), "donor_handlers": len(donor["handlers"]),
            "donor_server_tools": sum(t["path"] == "src/clo3d_mcp/server.py" for t in donor["tools"]),
            "donor_extended_tools": sum("/extended/" in t["path"] for t in donor["tools"]),
            "donor_reachable_native_ids": len(donor_native),
            "donor_tools_without_native_references": sum(not t["native_ids"] for t in donor["tools"]),
            "legacy_tools": len(legacy_names), "legacy_handlers": len(local["legacy"]["handlers"]),
            "legacy_handler_functions_outside_registry": len(local["legacy"]["handler_functions_outside_registry"]),
            "shared_donor_legacy_tool_names": len(donor_names & legacy_names),
            "donor_only_tool_names": len(donor_names - legacy_names),
            "legacy_only_tool_names": sorted(legacy_names - donor_names),
            "current_tools": len(local["current"]["tools"])}


LIMITATIONS = [
    "Static AST evidence only. No donor/local inspected module import, no CLO call, restart, mutation or SDK execution.",
    "Native ids are module.symbol. No inferred official overload, binding/type availability, error semantics, units or contract acceptance.",
    "Helper reachability is a conservative syntactic graph including conditional/fallback paths, not proof that a call occurs. One shortest evidence path per helper; callable references remain distinct from direct calls.",
    "getattr/dynamic module/type lookup and strings are reported as unresolved expressions, never expanded into guessed native calls. Arbitrary alias/dataflow, closures, decorators and reflection are not evaluated.",
    "Current14 command-to-native selection is explicitly reviewed metadata tied to AST callsite evidence; references may be shared preflight/readback/conditional sites and are not an execution trace.",
    "Exact descriptions are source docstrings (ast.get_docstring clean=True), signatures are ast.unparse-normalized Python declarations, not generated MCP JSON schemas or live tools/list.",
    "Test function references establish traceability only, not execution/pass status or complete scenario coverage. Historical acceptance remains limited to cited documents and no new real CLO gate is closed.",
    "Official coverage join and reconciliation of removed names/types are separate; raw donor symbol matches are not coverage percentages.",
]


def build(root, donor):
    local = local_inventory(root)
    return {"schema_version": 1, "kind": "static_source_mappings", "checked_on": "2026-11-09",
            "generator": "scripts/build_api_source_mappings.py", "native_id_format": "module.symbol",
            "donor": donor, "local": local, "counts": counts(donor, local), "limitations": LIMITATIONS}


def validate_snapshot(snapshot):
    if snapshot.get("schema_version") != 1:
        raise ValueError("Unsupported mapping schema")
    donor = snapshot["donor"]
    if donor["revision"] != REVISION or donor["repository"] != REPOSITORY:
        raise ValueError("Wrong donor pin")
    expected = donor["normalized_sha256"]
    if digest(canonical({k: v for k, v in donor.items() if k != "normalized_sha256"}).encode("utf-8")) != expected:
        raise ValueError("Donor normalized snapshot hash mismatch")
    for section, ntools, nhandlers in ((donor, 170, 172), (snapshot["local"]["legacy"], 47, 47)):
        if len(section["tools"]) != ntools or len(section["handlers"]) != nhandlers:
            raise ValueError("Wrong tool/handler inventory")
        if len({t["name"] for t in section["tools"]}) != ntools:
            raise ValueError("Duplicate tool names")
        handlers = {h["command"]: h for h in section["handlers"]}
        if len(handlers) != nhandlers:
            raise ValueError("Duplicate handler commands")
        for tool in section["tools"]:
            if tool["unresolved_commands"]:
                raise ValueError("Unresolved literal command")
            native = sorted({n for command in tool["handler_commands"] for n in handlers[command]["native_ids"]})
            if native != tool["native_ids"]:
                raise ValueError("Inconsistent handler/native join")
    if len(snapshot["local"]["current"]["tools"]) != 14:
        raise ValueError("Wrong current tool count")
    sources = {s["path"]: s for s in donor["sources"]}
    if set(sources) != set(DONOR_FILES):
        raise ValueError("Wrong donor source inventory")
    for source in sources.values():
        if source["url"] != RAW_BASE + source["path"] or len(source["sha256"]) != 64:
            raise ValueError("Invalid donor provenance")
    for handler in donor["handlers"]:
        if handler["native_ids"] != sorted({r["id"] for r in handler["references"]}):
            raise ValueError("Inconsistent reference index")
        for ref in handler["references"]:
            start, end = ref["lines"]
            if not 1 <= start <= end <= sources[ref["path"]]["lines"]:
                raise ValueError("Invalid reference line range")
            if ref["id"].split(".")[0] not in NATIVE_MODULES:
                raise ValueError("Invalid qualified native id")
    if snapshot["counts"] != counts(donor, snapshot["local"]):
        raise ValueError("Incorrect counts")


def artifact_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def artifacts(snapshot):
    """Index plus deterministic <=180000-byte shards (repository cap 200000)."""
    index = json.loads(json.dumps(snapshot))
    result = {}
    sections = (("donor_tools", index["donor"], "tools"),
                ("donor_handlers", index["donor"], "handlers"),
                ("donor_extras", index["donor"], "handler_functions_outside_registry"),
                ("legacy_tools", index["local"]["legacy"], "tools"),
                ("legacy_handlers", index["local"]["legacy"], "handlers"),
                ("legacy_extras", index["local"]["legacy"], "handler_functions_outside_registry"),
                ("current_tools", index["local"]["current"], "tools"))
    for label, owner, key in sections:
        rows = owner.pop(key)
        groups, pending = [], []
        for row in rows:
            if pending and len(artifact_text(pending + [row]).encode("utf-8")) > 180000:
                groups.append(pending)
                pending = []
            pending.append(row)
        if pending or not groups:
            groups.append(pending)
        refs = []
        for number, group in enumerate(groups, 1):
            path = Path(f"docs/api/mappings/{label}_{number:02}.json")
            text = artifact_text(group)
            if len(text.encode("utf-8")) > 180000:
                raise ValueError(f"Oversized individual mapping shard: {path}")
            result[path] = text
            refs.append({"path": path.relative_to(SNAPSHOT.parent).as_posix(),
                         "sha256": digest(text.encode("utf-8")), "entries": len(group)})
        owner[key + "_shards"] = refs
    result[SNAPSHOT] = artifact_text(index)
    result[REPORT] = render_report(snapshot)
    return result


def load_snapshot(path):
    """Load indexed facts, verifying each shard hash and containment first."""
    path = Path(path)
    index = json.loads(path.read_text(encoding="utf-8"))
    for owner in (index["donor"], index["local"]["legacy"], index["local"]["current"]):
        for key in list(owner):
            if not key.endswith("_shards"):
                continue
            rows = []
            for reference in owner.pop(key):
                target = (path.parent / reference["path"]).resolve()
                if path.parent.resolve() not in target.parents:
                    raise ValueError("Shard path escapes mapping directory")
                data = target.read_bytes()
                if digest(data) != reference["sha256"]:
                    raise ValueError("Mapping shard hash mismatch")
                group = json.loads(data)
                if not isinstance(group, list) or len(group) != reference["entries"]:
                    raise ValueError("Mapping shard entry count mismatch")
                rows.extend(group)
            owner[key.removesuffix("_shards")] = rows
    validate_snapshot(index)
    return index


def load_mappings(path=ROOT / SNAPSHOT):
    """Coordinator join interface, with flat aliases and full structured facts.

    donor_tools/local_legacy_tools/current_tools: complete inventories.
    source_refs: separate donor/local provenance lists (paths collide across
    repositories intentionally). native_ids is mapping, never per-overload
    implementation or acceptance evidence.
    """
    snapshot = load_snapshot(path)
    return {**snapshot, "donor_tools": snapshot["donor"]["tools"],
            "local_legacy_tools": snapshot["local"]["legacy"]["tools"],
            "current_tools": snapshot["local"]["current"]["tools"],
            "source_refs": {"donor": snapshot["donor"]["sources"], "local": snapshot["local"]["sources"]}}


def fetch_donor():
    # At most 15 requests, 2 MiB each, 20 s socket timeout, 90 s budget checked
    # around downloads (not a hard wall-clock process kill); no retries.
    started = time.monotonic()
    def get(url):
        remaining = 90 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("Donor refresh total deadline exceeded")
        request = urllib.request.Request(url, headers={"User-Agent": "clo-source-static-audit/1"})
        with urllib.request.urlopen(request, timeout=min(20, remaining)) as response:
            if response.geturl() != url:
                raise ValueError("Unexpected donor URL redirect")
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Donor source exceeds 2 MiB bound")
        if time.monotonic() - started > 90:
            raise TimeoutError("Donor refresh download budget exceeded")
        return data
    tree = get(TREE_URL)
    files = {path: get(RAW_BASE + path) for path in DONOR_FILES}
    return donor_inventory(files, tree)


def render_report(snapshot):
    c = snapshot["counts"]
    lines = ["# Статические source mappings CLO API", "", "Сгенерировано `scripts/build_api_source_mappings.py`; дата проверки 2026-11-09.",
             "Ни один исследуемый модуль не импортируется. Это A0-факты, **не native/contract acceptance**.", "",
             f"Донор: [`{REVISION}`](https://github.com/{REPOSITORY}/tree/{REVISION}), MIT.",
             "Attribution: Copyright (c) 2026 Violet Sphinx (original clo3d-mcp); Copyright (c) 2026 adriendelmas (clo3d-mcp-extended).",
             "LICENSE/NOTICE: pinned URLs и SHA-256 в JSON; NOTICE указывает upstream Ubani-Studio/clo3d-mcp и отсутствие SDK/аффилиации CLO.",
             "Сохранены нормализованные факты, сигнатуры и описания; production-код донора не копируется/не выполняется.", "", "## Полнота инвентаря", ""]
    lines += [f"- `{key}`: `{value}`" for key, value in c.items()]
    lines += ["", "## Схема и доказательства", "",
              "Основной JSON — индекс; списки хранятся в `mappings/*.json` shards <=180000 bytes, каждый с SHA-256/count. `load_mappings(path)` возвращает full structure и flat aliases `donor_tools`, `local_legacy_tools`, `current_tools`, `source_refs` для coordinator join.",
              "`donor.tools` содержит все170 имён, exact source descriptions, нормализованные Python signatures/parameters, literal routes, handler_commands, native_ids и явные name_aliases.",
              "`donor.handlers` содержит все172 registry commands, handler/registry line ranges, qualified references и helper chains. `local.legacy` — отдельные47 tools/47 registry commands и DEV extras вне registry.",
              "`local.current.tools` — отдельные14 tools: profile, contract/adapter/test evidence, primary/supporting native ids и ограниченная historical acceptance. `shared_native_alias_candidates`/`current_replacement_limits` явно отделяют aliases от ограниченных замен.",
              "`sources` содержит SHA-256 исходных bytes, lengths, pinned raw/browse URLs (донор), Git blob SHA-1 и local relative paths. При donor rebuild bytes сверяются с blob IDs pinned tree; local bytes не нормализуются по CRLF, при смене line endings пересобрать.",
              "`normalized_sha256` защищает целостность нормализованных donor facts (не криптографическая подпись). Offline-проверка не доказывает соответствие недоступному raw source: для этого нужен pinned refresh/cache rebuild.",
              "`references.kind=direct_call` означает AST Call.func; `callable_reference` — ссылка на функцию/тип, не direct invocation. `invoked_via` фиксирует передачу callable аргумента helper-параметру и место его вызова.",
              "`via` — кратчайшая синтаксическая цепочка helper calls; confidence syntactic_direct/indirect не означает контрактную корректность/реальное исполнение. Dynamic getattr остаются отдельными unresolved expressions.",
              "Join с official manifest выполняется по `module.symbol`; overload/type/units/return semantics автоматически не назначаются.", "", "## Воспроизводимость", "", "```powershell",
              "python scripts/build_api_source_mappings.py --check",
              "python scripts/build_api_source_mappings.py --refresh-donor --write",
              "# Offline rebuild donor facts from a previously downloaded research cache:",
              "python scripts/build_api_source_mappings.py --donor-cache <cache-folder> --check", "```", "",
              "По умолчанию сеть выключена; --check валидирует сохранённый donor snapshot и заново строит local facts AST. --write обновляет только index/report/mapping shards; refresh bounded, pinned, без retries.",
              "Cache содержит tree.json и выбранные source paths; это исследовательский ввод, не IPC и не production dependency. Скрипт cache не исполняет и не сохраняет donor source в checkout.",
              "Unit tests: `uv run --frozen --with pytest pytest -q tests/test_api_source_mappings.py`. Они не вызывают CLO и не являются real-CLO evidence.", "", "## Явные local legacy aliases", ""]
    for tool in snapshot["local"]["legacy"]["tools"]:
        for alias in tool["name_aliases"]:
            lines.append(f"- `{alias['tool_name']}` → wire `{alias['wire_command']}` → `{alias['handler_function']}` (routing only).")
    lines += ["", "`open_file` / `import_file` и `add_fabric` / `import_fabric` имеют общие native names, но это не автоматически эквивалентные контракты. `list_extensions` не имеет native handler.",
              "Legacy copy_pattern/CopyPatternPiecePos не объявлен эквивалентом current copy_pattern_with_offset/CopyPatternPieceMove; create_pattern current покрывает только simple straight polygons.",
              "", "## Current14 и граница приёмки", ""]
    for tool in snapshot["local"]["current"]["tools"]:
        lines.append(f"- `{tool['name']}` ({tool['profile']}): " + (", ".join(f"`{n}`" for n in tool["primary_native_ids"]) or "нет фиксированного native вызова") + f"; evidence `{tool['acceptance']['reference']}`.")
    lines += ["", "PATTERN_API_CHECK.md: исторический CLO2026.1, simple polygon и load10, <=2 тестовых деталей, <=256 всего; count/name/position/area/bbox и пользовательское visual/UI подтверждение. Точный patch build не зафиксирован.",
              "Introspection доказывает presence/docstrings, не исполнение найденных функций. Транспортные status/ping/diagnostic evidence не расширяют pattern gate. Не покрыты curves/holes/avatar/sewing/simulation/import/export/point editing/большие сцены.",
              "Тестовые ссылки — traceability, не новые результаты тестов. Full official overload/build traceability и весь tool-authoring DoD не заявлены.", "", "## Ограничения", ""]
    lines += ["- " + limitation for limitation in snapshot["limitations"]]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--refresh-donor", action="store_true")
    source.add_argument("--donor-cache", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    path = ROOT / SNAPSHOT
    if args.refresh_donor:
        donor = fetch_donor()
    elif args.donor_cache:
        donor = donor_inventory({p: (args.donor_cache / p).read_bytes() for p in DONOR_FILES},
                                (args.donor_cache / "tree.json").read_bytes())
    else:
        saved = load_snapshot(path)
        donor = saved["donor"]
    snapshot = build(ROOT, donor)
    validate_snapshot(snapshot)
    outputs = artifacts(snapshot)
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        for relative, text in outputs.items():
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
    else:
        for relative, text in outputs.items():
            target = ROOT / relative
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                raise ValueError(f"Source mappings stale: {relative}; review source diff and rebuild with --write")
    print(canonical(snapshot["counts"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"source mappings: {exc}", file=sys.stderr)
        raise SystemExit(1)
