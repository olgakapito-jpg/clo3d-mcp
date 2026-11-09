"""Bounded offline integrity audit of acceptance source code and documentation.

Does not contact MCP, CLO or the network, import plugin/legacy code, or execute
commands from documentation. Run from any cwd; files are relative to checkout.
"""

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 200000
MAX_FILES = 4000
ALLOWED_EXTENSIONS = {".py", ".md", ".toml", ".lock", ".json", ".yml", ".yaml", ".txt", ".cfg", ".ini", ".sh", ".ps1", ""}
ALLOWED_NAMES = {"LICENSE", ".gitignore", ".gitattributes", ".python-version"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def inventory(source):
    tree = ast.parse(source)
    return sorted(node.name for node in ast.walk(tree)
                  if isinstance(node, ast.AsyncFunctionDef)
                  and any(isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                          and dec.func.attr == "tool" for dec in node.decorator_list))


def audit(root, paths):
    """Return portable faults; never print source snippets or absolute paths."""
    root = Path(root).resolve()
    if len(paths) > MAX_FILES:
        return ["Too many source files; stop instead of unbounded scan"]
    faults = []
    for name in sorted(set(paths)):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            faults.append("Unsafe source-relative path")
            continue
        path = root / relative
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            faults.append(name + ": source symlink/escape rejected")
            continue
        if not path.is_file():
            faults.append(name + ": not a regular source file")
            continue
        if path.name == "acceptance-assets.json" or "acceptance-output" in relative.parts:
            faults.append(name + ": runtime asset/report metadata must remain ignored, not source")
            continue
        if path.name not in ALLOWED_NAMES and path.suffix.lower() not in ALLOWED_EXTENSIONS:
            faults.append(name + ": asset/binary extension rejected")
            continue
        if path.stat().st_size > MAX_FILE_BYTES and path.suffix != ".lock":
            faults.append(name + ": source exceeds per-file size limit")
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            faults.append(name + ": non-UTF8 source")
            continue
        if re.search(r"(?im)^(<<<<<<< |=======\s*$|>>>>>>> )", text):
            faults.append(name + ": conflict marker")
        if re.search(r"(?i)[A-Z]:[\\/]+Users[\\/]+(?!Public(?:[\\/]|\b))[^\s\\/]+[\\/]", text):
            faults.append(name + ": machine-specific user profile path")
        if path.suffix == ".json":
            try:
                json.loads(text, object_pairs_hook=unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except ValueError:
                faults.append(name + ": invalid or nonfinite JSON")
        if path.suffix != ".md":
            continue
        if any(line != line.rstrip() for line in text.splitlines()):
            faults.append(name + ": trailing whitespace")
        if len(re.findall(r"^\s*```", text, re.M)) % 2:
            faults.append(name + ": unbalanced fenced blocks")
        for destination in re.findall(r"\]\(([^)]+)\)", text):
            if re.match(r"^[A-Za-z]+:", destination) or destination.startswith("#"):
                continue
            target = destination.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                faults.append(name + ": missing/escaping relative Markdown link")
    return faults


def source_paths(root):
    completed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                               check=True, capture_output=True, timeout=15)
    return [name for name in completed.stdout.decode("utf-8").split("\0") if name]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-source", action="store_true", help="Audit every tracked/unignored source, not only new preparation files")
    args = parser.parse_args(argv)
    paths = source_paths(ROOT)
    if not args.all_source:
        paths = [name for name in paths if name.startswith(("docs/api/", "tests/evals/"))
                 or name in {"docs/CLO_COMPREHENSIVE_CHECK.md", "docs/CLO_ACCEPTANCE_PACKAGES.md", "docs/DOMAIN_BATCH_CHECK.md", "docs/CLO_API_PROBE_CHECK.md", "docs/CLO_TOOL_EVALUATION.md"}
                 or name.startswith(("scripts/build_", "scripts/check_acceptance", "scripts/prepare_acceptance", "scripts/verify_domains", "scripts/evaluate_tool", "diagnostics/clo3d_mcp"))]
    faults = audit(ROOT, paths)
    registered = inventory((ROOT / "src/clo3d_mcp/transport_server.py").read_text(encoding="utf-8"))
    cards = re.findall(r"^## \d+\. (\w+)$", (ROOT / "docs/CLO_MCP_TOOLS.md").read_text(encoding="utf-8"), re.M)
    if sorted(cards) != registered:
        faults.append("Current tool catalog and AST inventory differ")
    output = {"ok": not faults, "mode": "offline_source_audit", "files_checked": len(paths),
              "current_tools": len(registered), "faults": faults,
              "real_clo_tested": False}
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
