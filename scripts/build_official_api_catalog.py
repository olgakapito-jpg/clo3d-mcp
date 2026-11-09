"""Extract a documentation-only CLO API specification; never import/call CLO.

Only stdlib is used. HTML and RST are independently parsed and reconciled.
Raw declarations/documentation are data, never evaluated as Python or C++.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import textwrap
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "docs/api/clo_official_api.json"
PAGES = ("list", "optiontype", "gui_api_reference", "library", "eventplugin",
         "download", "changelog", "python")
BASE_URL = "https://developer.clo3d.com/"
MAX_SOURCE_BYTES = 4_000_000
MAX_SHARD_BYTES = 160_000
MAX_NOTES_CHARS = 16_000
TARGET = "CLO2026.1.336"
SCHEMA_VERSION = 1


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def normalized(text):
    """Only presentation whitespace is ignored; spelling/defaults stay intact."""
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def signature_key(text):
    # Do not collapse whitespace inside string literals/default values.
    parts = re.split(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''', text.strip())
    return "".join(part if i % 2 else re.sub(r"\s+", " ", part)
                   for i, part in enumerate(parts))


def rst_blocks(text):
    """Read directives by indentation, not blank lines (RST uses tabs too)."""
    lines = text.splitlines()
    section = None
    blocks = []
    for i, line in enumerate(lines):
        if i + 1 < len(lines) and re.fullmatch(r"[-*]{3,}\s*", lines[i + 1]):
            section = line.strip()
        match = re.match(r"^(\s*)\.\. code-(?:tab|block):: (\S+)\s*$", line)
        if not match:
            continue
        indent = len(match[1].expandtabs(8))
        body = []
        for following in lines[i + 1:]:
            expanded = following.expandtabs(8)
            if expanded.strip() and len(expanded) - len(expanded.lstrip()) <= indent:
                break
            body.append(expanded)
        blocks.append({"language": match[2], "section": section,
                       "line": i + 1, "ordinal": len(blocks) + 1,
                       "raw": textwrap.dedent("\n".join(body)).strip()})
    return blocks


class HTMLBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.sections = []
        self.language = None
        self.body = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section":
            self.sections.append(attrs.get("id"))
        if tag == "div" and attrs.get("class", "").startswith("highlight-"):
            self.language = attrs["class"].split()[0][len("highlight-"):]
        if tag == "pre":
            self.body = []
            self.location = {"language": self.language, "line": self.getpos()[0],
                             "anchor": self.sections[-1] if self.sections else None}

    def handle_data(self, data):
        if self.body is not None:
            self.body.append(data)

    def handle_endtag(self, tag):
        if tag == "pre" and self.body is not None:
            self.blocks.append({**self.location, "raw": "".join(self.body).strip(),
                                "ordinal": len(self.blocks) + 1})
            self.body = None
        if tag == "section":
            self.sections.pop()


def reconcile_blocks(page, sources):
    rst = rst_blocks(sources[page + ".rst.txt"].decode("utf-8-sig"))
    parser = HTMLBlocks()
    parser.feed(sources[page + ".html"].decode("utf-8-sig"))
    html = parser.blocks
    if len(rst) != len(html):
        raise ValueError(f"{page}: HTML/RST block count differs: {len(html)}/{len(rst)}")
    result = []
    for left, right in zip(rst, html):
        if left["language"] != right["language"] or normalized(left["raw"]) != normalized(right["raw"]):
            raise ValueError(f"{page}: HTML/RST disagree at block {left['ordinal']}")
        result.append({**left, "anchor": right["anchor"], "sources": [
            {"source_id": page + ".rst.txt", "line": left["line"], "block": left["ordinal"]},
            {"source_id": page + ".html", "line": right["line"], "block": right["ordinal"],
             "anchor": right["anchor"]}]})
    return result


def split_parameters(raw):
    parts, start, stack, quote, escaped = [], 0, [], None, False
    for i, char in enumerate(raw):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack:
                raise ValueError("Unbalanced parameter delimiters")
            stack.pop()
        elif char == "," and not stack:
            parts.append(raw[start:i].strip())
            start = i + 1
    if stack or quote:
        raise ValueError("Unbalanced parameter expression")
    if raw[start:].strip():
        parts.append(raw[start:].strip())
    return parts


def parse_signature(raw):
    match = re.fullmatch(r"(?:def\s+)?(?:(\w+)\.)?(\w+)\((.*)\)\s*->\s*(.+)", raw)
    if not match:
        raise ValueError(f"Unrecognized documented declaration: {raw}")
    params = []
    for part in split_parameters(match[3]):
        item = {"raw": part}
        # This is a text extractor, not an interpreter/type checker.
        field = re.fullmatch(r"(\w+)\s*:\s*(.*?)(?:\s*=\s*(.*))?", part)
        if field:
            item.update(name=field[1], annotation_raw=field[2].strip())
            if field[3] is not None:
                item["default_raw"] = field[3]
        else:
            item["parse_status"] = "ambiguous"
        params.append(item)
    return {"symbol": match[2], "parameters": params, "return_raw": match[4]}


BUILTINS = {"str", "int", "float", "bool", "None", "list", "dict", "tuple", "set",
            "map", "vector", "array", "std", "string", "wstring", "unsigned", "double",
            "char", "void", "const", "long", "short", "size_t", "Callable", "Any",
            "object", "Optional", "function", "uint32_t", "uint64_t"}


def type_references(annotations, documentation, known):
    refs = {}
    for raw in annotations:
        for token in re.findall(r"[A-Za-z_]\w*(?:(?:\.|::)[A-Za-z_]\w*)*", raw):
            name = token.removeprefix("ApiTypes.").removeprefix("Marvelous::")
            if name in BUILTINS:
                continue
            resolved = name in known
            refs[(name, "annotation")] = {
                "name": name, "basis": "annotation", "status": "resolved" if resolved else "unresolved",
                "type_id": "type:" + name if resolved else None,
            }
    # A mention is not claimed to be a parameter's binding type.
    for name in sorted(known):
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", documentation):
            refs[(name, "documentation_mention")] = {
                "name": name, "basis": "documentation_mention", "status": "resolved",
                "type_id": "type:" + name}
    return sorted(refs.values(), key=lambda item: (item["name"], item["basis"]))


def parse_type(block):
    members = []
    description = []
    in_doc = False
    for line in block["raw"].splitlines():
        if line.strip() == '"""':
            in_doc = not in_doc
            continue
        if in_doc:
            description.append(line)
            continue
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            if members:
                members[-1]["documentation_raw"] += "\n" + line.lstrip()[1:].strip()
                members[-1]["raw"] += "\n" + line
            else:
                description.append(line)
            continue
        declaration, _, comment = line.partition("#")
        member = {"raw": line, "documentation_raw": comment.strip()}
        field = re.fullmatch(r"(\w+)\s*:\s*(.+?)\s*", declaration)
        enum = re.fullmatch(r"(\w+)\s*=\s*(.+?)\s*", declaration)
        if field:
            member.update(name=field[1], kind="field", annotation_raw=field[2])
        elif enum:
            member.update(name=enum[1], kind="enum_value", value_raw=enum[2])
        elif "(" in declaration:
            parsed = parse_signature(declaration.strip())
            member.update(name=parsed.pop("symbol"), kind="method", **parsed)
        else:
            member.update(name=None, kind="ambiguous")
        members.append(member)
    return {"id": "type:" + block["section"], "name": block["section"],
            "documented_namespace": "ApiTypes", "binding_status": "not_checked",
            "classification": "documented_python_type", "raw": block["raw"],
            "description_raw": "\n".join(description), "members": members,
            "occurrences": [{"sources": block["sources"]}]}


def source_records(sources, checked_on):
    records = []
    for name, content in sorted(sources.items()):
        url = BASE_URL + ("_sources/" if name.endswith(".rst.txt") else "") + name
        records.append({"id": name, "url": url, "sha256": digest(content),
                        "hash_scope": "fetched_source_bytes_not_normalized",
                        "bytes": len(content), "checked_on": checked_on})
    return records


def build_catalog(sources, checked_on):
    date.fromisoformat(checked_on)
    for page in PAGES:
        for ext in (".html", ".rst.txt"):
            if page + ext not in sources:
                raise ValueError(f"Missing source {page + ext}")
    download = sources["download.rst.txt"].decode("utf-8-sig")
    changelog = sources["changelog.rst.txt"].decode("utf-8-sig")
    version = re.search(r"\*\*SDK v([\d.]+)\*\*[^\n]*CLO ([\d.]+) Official Release", download)
    if not version or version[1] != "11.0.1" or "CLO" + version[2] != TARGET:
        raise ValueError("Latest official SDK changed or version evidence missing; review target explicitly")
    release = re.search(r"(?m)^V11\.0\.1, (.+)$", changelog)
    update = re.search(r"(?m)^Documentation update, (.+)$", changelog)
    if not release or not update:
        raise ValueError("Changelog provenance missing")
    type_blocks = reconcile_blocks("optiontype", sources)
    if any(block["language"] != "python" for block in type_blocks):
        raise ValueError("Unclassified option/type language")
    types = [parse_type(block) for block in type_blocks]
    known = {record["name"] for record in types}
    if len(known) != len(types):
        raise ValueError("Duplicate type sections need explicit reconciliation")
    methods = {}
    for page in ("list", "gui_api_reference"):
        blocks = reconcile_blocks(page, sources)
        for pos, block in enumerate(blocks):
            if block["language"] != "python":
                if (page != "list" or block["language"] != "c++" or pos == 0
                        or blocks[pos - 1]["language"] != "python"):
                    raise ValueError(f"Unclassified reference block: {page}/{block['ordinal']}")
                continue
            signature = block["raw"].splitlines()[0].strip()
            parsed = parse_signature(signature)
            module = block["section"].lower() if page == "list" else "gui_api"
            qualified = module + "." + parsed.pop("symbol")
            method = methods.setdefault(qualified, {
                "id": qualified, "qualified_name": qualified, "module": module,
                "symbol": qualified.split(".")[1], "classification": "documented_python",
                "semantic_contract_status": "not_checked",
                "runtime_presence": "not_checked", "binding_status": "not_checked", "declarations": []})
            key = signature_key(signature)
            declaration = next((d for d in method["declarations"] if d["signature_normalized"] == key), None)
            if declaration is None:
                declaration = {"id": qualified + "#" + digest(key.encode())[:16],
                               "signature_normalized": key, "signature_raw": signature,
                               **parsed, "occurrences": []}
                method["declarations"].append(declaration)
            documentation = block["raw"].partition("\n")[2]
            occurrence = {"signature_raw": signature, "documentation_raw": documentation,
                          "section": block["section"], "sources": block["sources"]}
            if page == "list":
                if pos + 1 >= len(blocks) or blocks[pos + 1]["language"] != "c++":
                    raise ValueError("Unpaired Python/C++ tab")
                cpp = blocks[pos + 1]
                occurrence["cpp"] = {"signature_raw": cpp["raw"].splitlines()[0].strip(),
                                     "documentation_raw": cpp["raw"].partition("\n")[2],
                                     "sources": cpp["sources"],
                                     "classification": "paired_cpp_documentation_not_binding_evidence"}
            else:
                # GUI parameter/return descriptions are prose outside the code block.
                lines = sources[page + ".rst.txt"].decode("utf-8-sig").splitlines()
                stop = blocks[pos + 1]["line"] - 1 if pos + 1 < len(blocks) else len(lines)
                prose = lines[block["line"]:stop]
                occurrence["documentation_raw"] = textwrap.dedent("\n".join(prose)).strip()
            if len(occurrence["documentation_raw"]) > MAX_NOTES_CHARS:
                raise ValueError(f"Method notes exceed reviewed bound: {qualified}")
            declaration["occurrences"].append(occurrence)
    for method in methods.values():
        for declaration in method["declarations"]:
            docs = "\n".join(o["documentation_raw"] for o in declaration["occurrences"])
            annotations = [p.get("annotation_raw", "") for p in declaration["parameters"]]
            annotations.append(declaration["return_raw"])
            declaration["type_references"] = type_references(annotations, docs, known)
            declaration["parameter_docs_raw"] = re.findall(r"(?m)^\s*@param[^\n]*", docs)
            declaration["return_docs_raw"] = re.findall(r"(?m)^\s*@returns?[^\n]*", docs)
            declaration["parameter_docs_raw"] += re.findall(r"(?m)^- ``[^`]+``:[^\n]*", docs)
            declaration["return_docs_raw"] += re.findall(r"(?m)^\*\*Returns:\*\*[^\n]*", docs)
            issues = []
            if any(p.get("parse_status") == "ambiguous" for p in declaration["parameters"]):
                issues.append("unparsed_parameter")
            if any(r["status"] == "unresolved" for r in declaration["type_references"]):
                issues.append("unresolved_annotation_type")
            if "::" in declaration["signature_raw"] or "*" in declaration["return_raw"]:
                issues.append("cpp_spelling_in_python_declaration")
            declaration["documentation_issues"] = issues
            declaration["contract_status"] = "ambiguous" if issues else "documented_not_runtime_checked"
    for record in types:
        for member in record["members"]:
            annotations = [member.get("annotation_raw", ""), member.get("return_raw", "")]
            annotations += [p.get("annotation_raw", "") for p in member.get("parameters", [])]
            member["type_references"] = type_references(annotations, member["documentation_raw"], known)
    interfaces = build_interfaces(sources)
    catalog = {"schema_version": SCHEMA_VERSION, "target": TARGET,
               "evidence_scope": "official_documentation_only_no_runtime_acceptance",
               "provenance": {"sdk_version": version[1], "clo_version": version[2],
                              "release_date_raw": release[1], "documentation_update_raw": update[1],
                              "checked_on": checked_on,
                              "version_evidence_raw": version[0],
                              "sdk_download_urls_not_fetched": sorted(set(re.findall(
                                  r"https://[^>\s]+CLO_SDK_v2026\.1\.336[^>\s]+", download)))},
               "sources": source_records(sources, checked_on),
               "methods": sorted(methods.values(), key=lambda m: m["id"]),
               "types": sorted(types, key=lambda t: t["id"]), "interfaces": interfaces}
    catalog["counts"] = catalog_counts(catalog)
    validate_catalog(catalog)
    return catalog


def build_interfaces(sources):
    records = []
    # Only explicit interface names, not calls appearing inside example bodies.
    specs = [("library", "CLOAPI::LibraryWindowImplPlugin", "LibraryWindowInterface"),
             ("library", "LibraryWindowInterface", "LibraryWindowInterface"),
             ("library", "Create", "Create()"),
             ("eventplugin", "CloEventPlugin", "CloEventPlugin.h"),
             ("eventplugin", "CloEventPlugin::MouseDropEventOn2DView", "MouseDropEventOn2DView"),
             ("eventplugin", "CloEventPlugin::MouseDropEventOn3DView", "MouseDropEventOn3DView")]
    for page, name, needle in specs:
        text = sources[page + ".rst.txt"].decode("utf-8-sig")
        evidence = [{"source_id": page + ".rst.txt", "line": i + 1, "raw": line}
                    for i, line in enumerate(text.splitlines()) if needle in line]
        if not evidence:
            raise ValueError(f"Interface evidence disappeared: {name}")
        records.append({"id": "interface:" + name, "name": name, "classification": "cpp_only",
                        "binding_status": "not_documented_as_python", "evidence": evidence,
                        "docs_url": BASE_URL + page + ".html",
                        "signature_raw": None, "details_status": "not_fully_declared_in_web_docs"})
    blocks = reconcile_blocks("eventplugin", sources)
    example = blocks[0]
    signature = example["raw"].split("{", 1)[0].strip()
    event = next(r for r in records if r["name"] == "CloEventPlugin::MouseDropEventOn2DView")
    event.update(signature_raw=signature, signature_basis="cpp_example_definition",
                 details_status="example_signature_only", occurrences=[{"sources": example["sources"]}])
    return records


def catalog_counts(catalog):
    by_module = {}
    for module in sorted({m["module"] for m in catalog["methods"]}):
        methods = [m for m in catalog["methods"] if m["module"] == module]
        by_module[module] = {"names": len(methods),
                             "unique_declarations": sum(len(m["declarations"]) for m in methods),
                             "python_blocks": sum(len(d["occurrences"]) for m in methods for d in m["declarations"])}
    return {"modules": by_module, "python_names": len(catalog["methods"]),
            "unique_python_declarations": sum(len(m["declarations"]) for m in catalog["methods"]),
            "python_blocks": sum(v["python_blocks"] for v in by_module.values()),
            "type_records": len(catalog["types"]),
            "type_members": sum(len(t["members"]) for t in catalog["types"]),
            "cpp_interfaces": len(catalog["interfaces"])}


def validate_catalog(catalog):
    if catalog["schema_version"] != SCHEMA_VERSION or catalog["target"] != TARGET:
        raise ValueError("Unsupported schema/target")
    if catalog["counts"] != catalog_counts(catalog):
        raise ValueError("Counts do not match universe")
    ids = [r["id"] for kind in ("methods", "types", "interfaces") for r in catalog[kind]]
    ids += [d["id"] for m in catalog["methods"] for d in m["declarations"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate catalog IDs")
    type_ids = {t["id"] for t in catalog["types"]}
    source_ids = {s["id"] for s in catalog["sources"]}
    for source in catalog["sources"]:
        if (source["hash_scope"] != "fetched_source_bytes_not_normalized"
                or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"])
                or not source["url"].startswith(BASE_URL)):
            raise ValueError("Invalid official source provenance")

    def validate_refs(refs):
        for ref in refs:
            if ref["status"] not in ("resolved", "unresolved"):
                raise ValueError("Invalid type resolution status")
            if (ref["status"] == "resolved") != (ref["type_id"] in type_ids):
                raise ValueError("Invalid type resolution")
            if ref["status"] == "unresolved" and ref["type_id"] is not None:
                raise ValueError("Unresolved reference has target")

    def validate_sources(locations):
        if not locations or any(s["source_id"] not in source_ids or s["line"] <= 0 for s in locations):
            raise ValueError("Unknown or invalid source reference")

    for method in catalog["methods"]:
        if method["runtime_presence"] != "not_checked" or method["binding_status"] != "not_checked":
            raise ValueError("Official catalog must not claim runtime evidence")
        for declaration in method["declarations"]:
            if not declaration["occurrences"]:
                raise ValueError("Declaration without evidence")
            validate_refs(declaration["type_references"])
            for occurrence in declaration["occurrences"]:
                validate_sources(occurrence["sources"])
                if "cpp" in occurrence:
                    validate_sources(occurrence["cpp"]["sources"])
    for record in catalog["types"]:
        if record["binding_status"] != "not_checked":
            raise ValueError("Official type cannot claim runtime binding")
        for occurrence in record["occurrences"]:
            validate_sources(occurrence["sources"])
        for member in record["members"]:
            validate_refs(member["type_references"])
    for interface in catalog["interfaces"]:
        if interface["classification"] != "cpp_only" or interface["binding_status"] != "not_documented_as_python":
            raise ValueError("Invalid C++ interface classification")
        validate_sources(interface["evidence"])
    return catalog


def shard_catalog(catalog):
    index = {key: value for key, value in catalog.items() if key not in ("methods", "types", "interfaces")}
    index["shards"] = []
    files = {}
    for kind in ("methods", "types", "interfaces"):
        groups = {}
        for record in catalog[kind]:
            group = record["module"] if kind == "methods" else kind
            groups.setdefault(group, []).append(record)
        for group, records in sorted(groups.items()):
            chunks, chunk = [], []
            for record in records:
                if chunk and len(json_bytes({"kind": kind, "records": chunk + [record]})) > MAX_SHARD_BYTES:
                    chunks.append(chunk)
                    chunk = []
                chunk.append(record)
            if chunk:
                chunks.append(chunk)
            for number, chunk in enumerate(chunks, 1):
                path = f"official/{group}-{number:03}.json"
                data = json_bytes({"kind": kind, "records": chunk})
                if len(data) > MAX_SHARD_BYTES:
                    raise ValueError(f"Single record exceeds shard bound: {path}")
                files[path] = data
                index["shards"].append({"path": path, "kind": kind, "records": len(chunk),
                                        "bytes": len(data), "sha256": digest(data),
                                        "hash_scope": "normalized_json_shard_bytes"})
    return index, files


def load_catalog(path=DEFAULT_INDEX):
    """Load/check the normalized universe for an offline coverage join."""
    path = Path(path)
    catalog = json.loads(path.read_text(encoding="utf-8"))
    for kind in ("methods", "types", "interfaces"):
        catalog[kind] = []
    seen = set()
    for shard in catalog.pop("shards"):
        relative = Path(shard["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "official":
            raise ValueError("Unsafe shard path")
        if shard["path"] in seen or shard["kind"] not in ("methods", "types", "interfaces"):
            raise ValueError("Duplicate shard or invalid kind")
        if (not 0 < shard["bytes"] <= MAX_SHARD_BYTES
                or shard["hash_scope"] != "normalized_json_shard_bytes"):
            raise ValueError("Invalid normalized shard bounds/hash scope")
        seen.add(shard["path"])
        shard_path = path.parent / relative
        if not shard_path.resolve().is_relative_to(path.parent.resolve()):
            raise ValueError("Shard resolves outside index directory")
        if shard_path.stat().st_size != shard["bytes"]:
            raise ValueError(f"Shard integrity failure: {relative}")
        data = shard_path.read_bytes()
        if len(data) != shard["bytes"] or digest(data) != shard["sha256"]:
            raise ValueError(f"Shard integrity failure: {relative}")
        value = json.loads(data)
        if value["kind"] != shard["kind"] or len(value["records"]) != shard["records"]:
            raise ValueError("Shard metadata mismatch")
        catalog[shard["kind"]].extend(value["records"])
    return validate_catalog(catalog)


def fetch_sources(timeout=20, total_timeout=180):
    sources = {}
    deadline = time.monotonic() + total_timeout
    for page in PAGES:
        for ext in (".html", ".rst.txt"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Official source fetch total deadline exceeded")
            name = page + ext
            url = BASE_URL + ("_sources/" if ext == ".rst.txt" else "") + name
            with urlopen(url, timeout=min(timeout, remaining)) as response:
                if not response.url.startswith(BASE_URL):
                    raise ValueError("Unexpected redirect outside official documentation")
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Official source fetch total deadline exceeded")
                    chunk = response.read(min(65_536, MAX_SOURCE_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError(f"Official source too large: {name}")
                data = b"".join(chunks)
            if len(data) > MAX_SOURCE_BYTES:
                raise ValueError(f"Official source too large: {name}")
            sources[name] = data
    return sources


def render_report(catalog):
    counts = catalog["counts"]
    modules = counts["modules"]
    baseline_names = sum(v["names"] for k, v in modules.items() if k != "gui_api")
    baseline_blocks = sum(v["python_blocks"] for k, v in modules.items() if k != "gui_api")
    unresolved = Counter(ref["name"] for m in catalog["methods"] for d in m["declarations"]
                         for ref in d["type_references"] if ref["status"] == "unresolved")
    duplicate = [(m["id"], d) for m in catalog["methods"] for d in m["declarations"]
                 if len(d["occurrences"]) > 1]
    lines = ["# Официальная структурная спецификация CLO API", "",
             f"Target: **{TARGET} / SDK 11.0.1**. Проверено: {catalog['provenance']['checked_on']}.",
             "Источник — официальные публичные HTML и RST; это не SDK, не runtime inventory и не real acceptance.", "",
             "## Полнота и denominator", "",
             f"- API List: **{baseline_names} qualified names / {baseline_blocks} Python declaration blocks** (первичная оценка 851/1098 подтверждена).",
             f"- Отдельный GUI reference: **{modules['gui_api']['names']} names / {modules['gui_api']['python_blocks']} blocks** (39 подтверждены).",
             f"- Всего: **{counts['python_names']} names / {counts['python_blocks']} blocks / {counts['unique_python_declarations']} уникальных объявлений**.",
             f"- Option & Type: **{counts['type_records']} records / {counts['type_members']} members**, включая enum values и методы records (77 секций подтверждены).",
             f"- Дополнительные C++ interfaces: **{counts['cpp_interfaces']}**; не входят в Python denominator.", ""]
    for module, values in modules.items():
        lines.append(f"- `{module}`: {values['names']} names, {values['python_blocks']} blocks, {values['unique_declarations']} unique declarations.")
    lines += ["", "Один occurrence соответствует одному документированному Python-блоку с двумя source locations (HTML/RST); эти две ссылки не удваивают denominator.",
              "Повторы одного normalized signature объединены, но documentation и все occurrences сохранены. Разные overload/default/return spelling и W/non-W имена не объединяются.", "",
              "### Повторяющиеся объявления", ""]
    for name, declaration in duplicate:
        lines.append(f"- `{name}`: `{declaration['signature_raw']}` — {len(declaration['occurrences'])} occurrences.")
    lines += ["", "## Формат и использование", "",
              "`clo_official_api.json` — индекс с provenance, counts, относительными shard paths и SHA-256 каждого shard. Файлы `official/*.json` меньше 160000 bytes; полный сайт/SDK/assets не сохраняются.",
              "`scripts/build_official_api_catalog.py:load_catalog(path)` возвращает `methods`, `types`, `interfaces`, `sources`, `counts`, `provenance` после проверки hashes/IDs/references.",
              "Method ID — qualified name; declaration ID — qualified name + SHA-256 prefix normalized signature. Raw spelling и @param/@return docs сохранены; comments не интерпретируются как проверенные диапазоны/defaults.",
              "Type member содержит raw declaration, annotation/value raw и описание; продолжения комментариев сохраняются. Enum values присваиваются только при явном `=`, значения в комментариях остаются описанием.",
              "Type references: `resolved` только при наличии type record; `documentation_mention` не означает binding/parameter type. Неизвестные annotation identifiers — `unresolved`. `ApiTypes` — документированный namespace, не результат import/probe.", "",
              "Source `sha256` хеширует фактически скачанные HTML/RST bytes (`hash_scope=fetched_source_bytes_not_normalized`); shard `sha256` хеширует normalized JSON bytes (`hash_scope=normalized_json_shard_bytes`). Это разные уровни provenance. Method notes ограничены 16000 characters на occurrence, превышение вызывает ошибку, а не обрезание. Source anchors сохранены в HTML locations.", "",
              "## Ограничения и blockers", "",
              "- Весь runtime_presence/binding_status методов — not_checked. Наличие Python tab не доказывает callable/constructibility/совместимость build.",
              "- Сигнатуры с C++ spelling/pointers в Python tab и unresolved types помечены ambiguous; ошибки документации не исправляются догадками. parse_status параметра ambiguous сохраняет raw.",
              "- Параметры извлекаются текстовым bracket/quote-aware parser; ни eval, ни import, ни исполнение snippets не используются. Единицы/эффекты/семантика в raw docs, а не выдуманные контракты.",
              "- HTML/RST блоки сверяются по порядку, языку и тексту (игнорируются только trailing spaces). Различия/count drift приводят к ошибке, не к потере блока. Межстраничной пагинации в этих официальных reference sources нет; все секции читаются целиком.",
              "- Library: web docs называют интерфейсы/factory, но полный список их методов отсылает к SDK sample; signature null, явный blocker. Event: 2D signature только из C++ example, 3D signature не выведена по аналогии.",
              "- Парные C++ tabs сохранены как документация, не самостоятельные Python API. C++-only Library/Event не включены в methods. GUI callback/modal APIs не дают разрешение на UI automation/restart.",
              "- Public docs не pinned version archive: snapshot SHA-256 и download/changelog evidence связывают каталог с latest на дату проверки; будущий drift требует review, не автоматического расширения runtime whitelist.",
              "- Текстовые противоречия @return и сигнатур не разрешены автоматически; независимая контрактная проверка по каждой операции остаётся обязательной.", "",
              "Не разрешённые annotation identifiers (число объявлений/ссылок):"]
    lines += [f"- `{name}`: {count}." for name, count in sorted(unresolved.items())]
    lines += ["", "## Воспроизведение (без CLO)", "", "```powershell",
              "python scripts/build_official_api_catalog.py --check",
              "uv run --frozen --with pytest pytest -q tests/test_official_api_catalog.py",
              "python scripts/build_official_api_catalog.py --refresh --check",
              "python scripts/build_official_api_catalog.py --refresh --checked-on YYYY-MM-DD",
              "python scripts/build_official_api_catalog.py --source-dir <cached-source-dir> --checked-on YYYY-MM-DD --check",
              "```", "",
              "Без refresh/source-dir `--check` полностью offline, проверяет committed manifest и отчёт. С refresh/source-dir строит заново и сравнивает все bytes; `--check` никогда не пишет. Для сравнения берётся snapshot date индекса, если --checked-on не указан. Refresh — один bounded fetch каждого из 16 фиксированных source URLs, без retries: 20 s/socket, общий deadline 180 s проверяется между requests/64KB reads, до 4 MB/source. Socket timeout ограничивает бездействие, не всю длительность read при медленном потоке; не обещается hard wall-clock предел сетевого стека. Ошибка fetch/build не меняет committed files.",
              "Источники можно заранее сохранить вне repo в approved Temp/opencode. Для offline rebuild нужны все 16 исходных файлов, они не коммитятся. Generator не удаляет старые shards автоматически; индекс определяет активный набор.", "",
              "## Source provenance", "",
              f"Release: {catalog['provenance']['release_date_raw']}; documentation update: {catalog['provenance']['documentation_update_raw']}. SDK URLs извлечены только как ссылки, архивы не скачивались.", ""]
    for source in catalog["sources"]:
        lines.append(f"- [{source['id']}]({source['url']}): {source['bytes']} bytes; SHA-256 `{source['sha256']}`.")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Fetch fixed official sources once; no CLO calls")
    mode.add_argument("--source-dir", type=Path, help="Build from cached official HTML/RST sources")
    parser.add_argument("--check", action="store_true", help="Read/compare only, never write")
    parser.add_argument("--checked-on", help="ISO snapshot date; check defaults to committed date")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args(argv)
    report = args.index.parent / "CLO_OFFICIAL_API.md"
    if not args.refresh and not args.source_dir:
        if not args.check:
            parser.error("Choose --refresh, --source-dir, or offline --check")
        catalog = load_catalog(args.index)
        if report.read_text(encoding="utf-8") != render_report(catalog):
            raise ValueError("Generated report differs")
    else:
        checked_on = args.checked_on
        if checked_on is None and args.check and args.index.exists():
            checked_on = json.loads(args.index.read_text(encoding="utf-8"))["provenance"]["checked_on"]
        checked_on = checked_on or date.today().isoformat()
        sources = fetch_sources() if args.refresh else {
            page + ext: (args.source_dir / (page + ext)).read_bytes()
            for page in PAGES for ext in (".html", ".rst.txt")}
        if any(len(data) > MAX_SOURCE_BYTES for data in sources.values()):
            raise ValueError("Cached source exceeds source size bound")
        catalog = build_catalog(sources, checked_on)
        index, shards = shard_catalog(catalog)
        outputs = {args.index: json_bytes(index), report: render_report(catalog).encode("utf-8")}
        outputs.update({args.index.parent / path: data for path, data in shards.items()})
        if args.check:
            for path, data in outputs.items():
                if not path.exists() or path.read_bytes() != data:
                    raise ValueError(f"Generated catalog differs: {path.name}")
        else:
            for path, data in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
    print(json.dumps(catalog["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
