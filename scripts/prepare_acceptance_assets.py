"""Bounded, metadata-only asset proposals; never imports CLO or opens asset contents.

Console output has counts only. A relative-name report is written exclusively on
explicit request under the existing project acceptance-output directory, without
overwrite or link traversal.
Run outside CLO. Filesystem paths must not be concurrently changed during a scan;
stdlib path checks do not provide a sandbox against hostile directory replacement.
"""

import argparse
import json
import os
from pathlib import Path
import stat
import sys


PROJECT_DIR = Path(__file__).absolute().parents[1]
REPORT_NAME = "acceptance-assets.json"
MAX_REPORT_BYTES = 180_000
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
FORMATS = {
    "fabric": {".zfab"},
    "avatar": {".avt", ".avac"},
    "project": {".zprj", ".zpac"},
    "pose": {".pos", ".apf"},
}
# Proposal budgets, not CLO format/compatibility limits.
SIZE_BUDGETS = {
    "fabric": 64 * 1024 * 1024,
    "avatar": 128 * 1024 * 1024,
    "project": 128 * 1024 * 1024,
    "pose": 16 * 1024 * 1024,
}


class InventoryError(ValueError):
    """Fixed public message, without private paths or native exception text."""


def _bounded_int(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise InventoryError(f"{label} outside allowed bounds")
    return value


def _is_link(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & REPARSE_POINT
    )


def _lexical_directory(path):
    """Normalize both Windows separators before any filesystem access."""
    normalized = os.fspath(path).replace("\\", "/")
    if normalized.startswith("//"):
        raise InventoryError("network and device paths are not allowed")
    path = Path(normalized)
    if ".." in path.parts:
        raise InventoryError("parent traversal is not allowed")
    return path


def _directory(path):
    """Reject links/reparse points in *every* component, including ancestors."""
    path = _lexical_directory(path)
    path = Path(os.path.abspath(path))
    try:
        for part in [*reversed(path.parents), path]:
            info = part.lstat()
            if _is_link(info) or not stat.S_ISDIR(info.st_mode):
                raise InventoryError("directory or ancestor is not a plain directory")
    except OSError:
        raise InventoryError("directory unavailable") from None
    return path


def _overlap(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def validate_roots(roots):
    if not 1 <= len(roots) <= 4:
        raise InventoryError("one to four input roots required")
    lexical = [_lexical_directory(root) for root in roots]
    checked = [_directory(root) for root in lexical]
    for index, root in enumerate(checked):
        if any(_overlap(root, earlier) for earlier in checked[:index]):
            raise InventoryError("input roots must not overlap")
    return checked


def validate_output(output_dir, roots, project_dir=PROJECT_DIR):
    # Preflight both caller paths before even inspecting the project ancestors.
    output_path = _lexical_directory(output_dir)
    project_path = _lexical_directory(project_dir)
    project = _directory(project_path)
    output = _directory(output_path)
    allowed = project / "acceptance-output"
    if not output.is_relative_to(allowed):
        raise InventoryError("output must be project acceptance-output or its descendants")
    if any(_overlap(output, root) for root in roots):
        raise InventoryError("output and input roots must not overlap")
    return output


def inventory(roots, *, max_entries=2000, max_depth=4, candidates_per_kind=3):
    """Inspect <= max_entries globally; root files have depth zero.

    No ordering guarantee for a capped filesystem walk. Selection is smallest
    positive file, then relative filename, among *observed* format candidates.
    Nothing here validates file contents, provenance, license or native support.
    """
    _bounded_int(max_entries, 1, 10_000, "max_entries")
    _bounded_int(max_depth, 0, 12, "max_depth")
    _bounded_int(candidates_per_kind, 1, 5, "candidates_per_kind")
    roots = validate_roots(roots)
    counters = {
        "entries_examined": 0,
        "directories_scanned": 0,
        "files_seen": 0,
        "links_skipped": 0,
        "depth_skipped": 0,
        "metadata_errors": 0,
        "names_skipped": 0,
        "size_rejected": 0,
        "other_entries_skipped": 0,
    }
    counts = {kind: 0 for kind in FORMATS}
    candidates = {kind: [] for kind in FORMATS}
    capped = False
    for number, root in enumerate(roots, 1):
        stack = [(root, 0)]
        while stack:
            if counters["entries_examined"] >= max_entries:
                capped = True
                break
            directory, depth = stack.pop()
            try:
                # Check again before opening: never intentionally follow links.
                _directory(directory)
                with os.scandir(directory) as entries:
                    counters["directories_scanned"] += 1
                    for entry in entries:
                        if counters["entries_examined"] >= max_entries:
                            capped = True
                            break
                        counters["entries_examined"] += 1
                        try:
                            info = entry.stat(follow_symlinks=False)
                        except OSError:
                            counters["metadata_errors"] += 1
                            continue
                        if _is_link(info):
                            counters["links_skipped"] += 1
                            continue
                        path = Path(entry.path)
                        relative = path.relative_to(root).as_posix()
                        # Bound metadata and avoid unsafe/control-bearing names.
                        if len(relative) > 512 or any(
                            not character.isprintable() for character in relative
                        ):
                            counters["names_skipped"] += 1
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if depth < max_depth:
                                stack.append((path, depth + 1))
                            else:
                                counters["depth_skipped"] += 1
                            continue
                        if not stat.S_ISREG(info.st_mode):
                            counters["other_entries_skipped"] += 1
                            continue
                        counters["files_seen"] += 1
                        extension = path.suffix.lower()
                        for kind, formats in FORMATS.items():
                            if extension not in formats:
                                continue
                            counts[kind] += 1
                            if not 0 < info.st_size <= SIZE_BUDGETS[kind]:
                                counters["size_rejected"] += 1
                                break
                            candidates[kind].append({
                                "root_id": f"root-{number}",
                                "relative_path": relative,
                                "format_hint": extension,
                                "size_bytes": info.st_size,
                                "content_compatibility": "unknown",
                                "official_provenance": "unknown",
                            })
                            candidates[kind].sort(key=lambda item: (
                                item["size_bytes"], item["relative_path"].casefold(),
                                item["root_id"],
                            ))
                            del candidates[kind][candidates_per_kind:]
                            break
            except (OSError, InventoryError):
                counters["metadata_errors"] += 1
        if capped:
            break
    # Reaching the cap is conservatively marked even if it was the final entry.
    capped = capped or counters["entries_examined"] >= max_entries
    return {
        "schema_version": 1,
        "mode": "metadata_only_proposals",
        "root_count": len(roots),
        "limits": {
            "max_entries": max_entries, "max_depth": max_depth,
            "candidates_per_kind": candidates_per_kind,
            "size_budgets_bytes": SIZE_BUDGETS.copy(),
        },
        "counters": counters,
        "entry_cap_reached": capped,
        "inventory_complete": not capped and not any(counters[key] for key in (
            "depth_skipped", "metadata_errors", "names_skipped", "links_skipped",
            "other_entries_skipped",
        )),
        "format_counts_observed": counts,
        "selection_basis": "extension, positive size budget, smallest size, filename tie-break",
        "candidates": candidates,
        "user_gate": "Choose explicit files and verify provenance, license and compatibility before loading.",
    }


def write_report(report, output_dir, roots, *, project_dir=PROJECT_DIR):
    _lexical_directory(output_dir)
    _lexical_directory(project_dir)
    roots = validate_roots(roots)
    output = validate_output(output_dir, roots, project_dir)
    payload = (json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise InventoryError("report exceeds byte limit")
    try:
        # Exclusive create also rejects a pre-existing file, symlink or directory.
        with (output / REPORT_NAME).open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        raise InventoryError("report already exists; choose a new output subdirectory") from None
    except OSError:
        raise InventoryError("report write failed; inspect explicit output directory") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", required=True, help="explicit local read-only input root; repeat up to four times")
    parser.add_argument("--output-dir", help="existing project acceptance-output or descendant; optional relative-name JSON report, never overwrite")
    parser.add_argument("--max-entries", type=int, default=2000)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--candidates-per-kind", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.output_dir:
            _lexical_directory(args.output_dir)
        roots = validate_roots(args.root)
        if args.output_dir:
            validate_output(args.output_dir, roots)
        report = inventory(roots, max_entries=args.max_entries, max_depth=args.max_depth,
                           candidates_per_kind=args.candidates_per_kind)
        if args.output_dir:
            write_report(report, args.output_dir, roots)
        print("Metadata only; no asset contents read, copied, downloaded or loaded.")
        print(f"Entries examined: {report['counters']['entries_examined']}; "
              f"entry cap reached: {report['entry_cap_reached']}; "
              f"inventory complete: {report['inventory_complete']}")
        print("Skipped: " + ", ".join(
            f"{key}={report['counters'][key]}" for key in (
                "depth_skipped", "links_skipped", "metadata_errors", "names_skipped",
                "size_rejected", "other_entries_skipped",
            )
        ))
        for kind in FORMATS:
            print(f"{kind}: format hints {report['format_counts_observed'][kind]}, "
                  f"proposals {len(report['candidates'][kind])}; compatibility UNKNOWN")
        print("Relative filenames are private local metadata; keep reports untracked.")
        print("Report written to explicit output directory." if args.output_dir else
              "No report written. Console summary omits all roots and filenames.")
        return 0
    except InventoryError as exc:
        print(f"Inventory refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
