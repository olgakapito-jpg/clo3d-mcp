"""Synthetic metadata only; no installed assets, CLO, network or real scene calls."""

import importlib.util
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    "prepare_acceptance_assets", Path(__file__).parents[1] / "scripts" / "prepare_acceptance_assets.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def folders(tmp_path):
    assets = tmp_path / "assets"
    project = tmp_path / "project"
    output = project / "acceptance-output"
    assets.mkdir()
    output.mkdir(parents=True)
    return assets, project, output


def test_proposals_use_only_extension_filename_size_and_bound_count(folders, monkeypatch):
    assets, _, _ = folders
    for filename in ["b.ZFAB", "a.zfab", "c.zfab", "body.avt", "body.avac", "demo.zprj", "demo.zpac", "pose.pos", "pose.apf"]:
        (assets / filename).write_bytes(b"not a valid CLO file")
    (assets / "empty.zfab").touch()
    (assets / "ignore.txt").write_text("not an asset")

    def no_contents(*args, **kwargs):
        raise AssertionError("asset content was opened")

    monkeypatch.setattr(Path, "open", no_contents)
    result = module.inventory([assets], candidates_per_kind=2)
    assert result["format_counts_observed"] == {"fabric": 4, "avatar": 2, "project": 2, "pose": 2}
    assert [item["relative_path"] for item in result["candidates"]["fabric"]] == ["a.zfab", "b.ZFAB"]
    assert result["counters"]["size_rejected"] == 1
    assert result["inventory_complete"]
    for candidates in result["candidates"].values():
        for item in candidates:
            assert item["content_compatibility"] == item["official_provenance"] == "unknown"
            assert item["root_id"] == "root-1"
    assert str(assets) not in json.dumps(result)


def test_size_budget_and_smallest_selection(folders, monkeypatch):
    assets, _, _ = folders
    monkeypatch.setitem(module.SIZE_BUDGETS, "fabric", 5)
    for filename, size in [("big.zfab", 6), ("edge.zfab", 5), ("small.zfab", 1)]:
        (assets / filename).write_bytes(b"x" * size)
    result = module.inventory([assets], candidates_per_kind=1)
    assert result["candidates"]["fabric"][0]["relative_path"] == "small.zfab"
    assert result["counters"]["size_rejected"] == 1


def test_depth_zero_never_enters_child_and_higher_depth_finds_it(folders):
    assets, _, _ = folders
    (assets / "nested").mkdir()
    (assets / "nested" / "p.pos").write_bytes(b"x")
    shallow = module.inventory([assets], max_depth=0)
    assert shallow["candidates"]["pose"] == []
    assert shallow["counters"]["depth_skipped"] == 1
    assert not shallow["inventory_complete"]
    assert len(module.inventory([assets], max_depth=1)["candidates"]["pose"]) == 1


def test_global_entry_cap_across_roots(folders, tmp_path):
    assets, _, _ = folders
    other = tmp_path / "other"
    other.mkdir()
    for root in (assets, other):
        for number in range(4):
            (root / f"{number}.zfab").write_bytes(b"x")
    result = module.inventory([assets, other], max_entries=5)
    assert result["counters"]["entries_examined"] == 5
    assert result["entry_cap_reached"]
    assert not result["inventory_complete"]
    assert result["format_counts_observed"]["fabric"] == 5


@pytest.mark.parametrize("key,value", [
    ("max_entries", 0), ("max_entries", 10001), ("max_entries", True),
    ("max_depth", -1), ("max_depth", 13), ("max_depth", 1.5),
    ("candidates_per_kind", 0), ("candidates_per_kind", 6),
])
def test_invalid_caps_rejected(folders, key, value):
    with pytest.raises(module.InventoryError, match="bounds"):
        module.inventory([folders[0]], **{key: value})


def test_root_validation(folders):
    assets, _, _ = folders
    for roots in ([], [assets] * 5, [assets, assets]):
        with pytest.raises(module.InventoryError):
            module.inventory(roots)
    with pytest.raises(module.InventoryError):
        module.inventory([assets / "missing"])
    with pytest.raises(module.InventoryError, match="parent traversal"):
        module.inventory([assets / ".." / "assets"])
    child = assets / "child"
    child.mkdir()
    with pytest.raises(module.InventoryError, match="overlap"):
        module.inventory([assets, child])


@pytest.mark.parametrize("prefix", ["\\\\", "//", "\\/", "/\\"])
@pytest.mark.parametrize("tail", ["server/share", "?/C:/assets", "./pipe/name"])
@pytest.mark.parametrize("entrypoint", ["directory", "roots", "output", "project", "report"])
def test_network_and_device_paths_rejected_before_any_metadata_access(prefix, tail, entrypoint, monkeypatch):
    path = prefix + tail

    def forbidden(*args, **kwargs):
        raise AssertionError("network/device metadata access")

    monkeypatch.setattr(Path, "lstat", forbidden)
    assert module.main(["--root", path]) == 2
    assert module.main(["--root", "local-root", "--output-dir", path]) == 2
    with pytest.raises(module.InventoryError, match="network and device"):
        if entrypoint == "directory":
            module._directory(path)
        elif entrypoint == "roots":
            module.inventory(["local-root", path])
        elif entrypoint == "output":
            module.validate_output(path, [], "local-project")
        elif entrypoint == "project":
            module.validate_output("local-output", [], path)
        else:
            module.write_report({}, path, ["local-root"], project_dir="local-project")


def test_local_mixed_separators_are_normalized_lexically(folders):
    assets, _, _ = folders
    mixed = str(assets).replace("\\", "/") + "\\child"
    assert module._lexical_directory(mixed) == assets / "child"


def test_console_is_private_and_default_writes_nothing(folders, capsys):
    assets, project, output = folders
    (assets / "private-fixture.zfab").write_bytes(b"x")
    before = set(project.rglob("*"))
    assert module.main(["--root", str(assets)]) == 0
    captured = capsys.readouterr()
    assert str(assets) not in captured.out + captured.err
    assert "private-fixture" not in captured.out + captured.err
    assert "compatibility UNKNOWN" in captured.out
    assert set(project.rglob("*")) == before
    assert list(output.iterdir()) == []


def test_errors_do_not_print_input_paths(folders, capsys):
    missing = folders[0] / "private-directory"
    assert module.main(["--root", str(missing)]) == 2
    captured = capsys.readouterr()
    assert str(missing) not in captured.err
    assert "private-directory" not in captured.err


def test_output_is_explicit_private_relative_report_and_never_overwrites(folders):
    assets, project, output = folders
    (assets / "sample.apf").write_bytes(b"x")
    report = module.inventory([assets])
    module.write_report(report, output, [assets], project_dir=project)
    target = output / module.REPORT_NAME
    raw = target.read_bytes()
    assert len(raw) <= module.MAX_REPORT_BYTES < 200_000
    assert json.loads(raw)["candidates"]["pose"][0]["relative_path"] == "sample.apf"
    assert str(assets).encode() not in raw
    with pytest.raises(module.InventoryError, match="already exists"):
        module.write_report(report, output, [assets], project_dir=project)
    assert target.read_bytes() == raw


def test_output_must_be_existing_acceptance_output_or_descendant_and_disjoint(folders, tmp_path):
    assets, project, output = folders
    outsider = tmp_path / "outside"
    outsider.mkdir()
    for invalid in (assets, project, outsider, project / "missing"):
        with pytest.raises(module.InventoryError):
            module.validate_output(invalid, [assets], project)
    nested_input = output / "input"
    nested_input.mkdir()
    for input_root in (project, nested_input):
        with pytest.raises(module.InventoryError, match="overlap"):
            module.validate_output(output, [input_root], project)
    assert not (project / "missing").exists()


@pytest.mark.parametrize("relative", ["docs", "src", "docs/reports", "acceptance-output-other"])
def test_output_outside_acceptance_output_rejected_without_writing(folders, relative):
    assets, project, _ = folders
    forbidden = project / relative
    forbidden.mkdir(parents=True)
    with pytest.raises(module.InventoryError, match="acceptance-output"):
        module.write_report({}, forbidden, [assets], project_dir=project)
    assert list(forbidden.iterdir()) == []


@pytest.mark.parametrize("relative", ["", "run", "run/reports"])
def test_existing_acceptance_output_and_descendants_allowed(folders, relative):
    assets, project, output = folders
    chosen = output / relative
    chosen.mkdir(parents=True, exist_ok=True)
    assert module.validate_output(chosen, [assets], project) == chosen
    module.write_report({}, chosen, [assets], project_dir=project)
    assert (chosen / module.REPORT_NAME).read_text().strip() == "{}"


def test_oversize_report_writes_nothing(folders):
    assets, project, output = folders
    with pytest.raises(module.InventoryError, match="byte limit"):
        module.write_report({"data": "x" * module.MAX_REPORT_BYTES}, output, [assets], project_dir=project)
    assert list(output.iterdir()) == []


def test_symlink_bit_and_windows_reparse_bit_are_both_links():
    assert module._is_link(SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0))
    assert module._is_link(SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400))
    assert not module._is_link(SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0))


def test_reparse_entries_are_not_descended_or_selected(folders, monkeypatch):
    assets, _, _ = folders
    real_scandir = module.os.scandir
    calls = []

    class Entry:
        path = str(assets / "junction")

        def stat(self, *, follow_symlinks):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)

    class Scan:
        def __enter__(self):
            return iter([Entry()])

        def __exit__(self, *args):
            pass

    def scan(path):
        calls.append(path)
        return Scan() if path == assets else real_scandir(path)

    monkeypatch.setattr(module.os, "scandir", scan)
    result = module.inventory([assets])
    assert calls == [assets]
    assert result["counters"]["links_skipped"] == 1
    assert not result["inventory_complete"]


def test_reparse_ancestor_rejected_without_following(folders, monkeypatch):
    assets, project, output = folders
    original = Path.lstat

    def fake_lstat(path):
        if path == output:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(module.InventoryError, match="plain directory"):
        module.inventory([output / "child"])
    with pytest.raises(module.InventoryError, match="plain directory"):
        module.validate_output(output, [assets], project)
    with pytest.raises(module.InventoryError, match="plain directory"):
        module.validate_output(output / "descendant", [assets], project)


def test_cli_explicit_output_and_bad_output_have_no_extra_writes(folders, monkeypatch, capsys):
    assets, project, output = folders
    original = module.validate_output
    monkeypatch.setattr(module, "validate_output", lambda directory, roots, project_dir=None:
                        original(directory, roots, project))
    assert module.main(["--root", str(assets), "--output-dir", str(output)]) == 0
    assert (output / module.REPORT_NAME).exists()
    assert module.main(["--root", str(assets), "--output-dir", str(assets)]) == 2
    assert list(assets.iterdir()) == []
    captured = capsys.readouterr()
    assert str(assets) not in captured.out + captured.err
    assert str(output) not in captured.out + captured.err


def test_metadata_error_is_counted_and_private(folders, monkeypatch):
    assets, _, _ = folders

    class Scan:
        def __enter__(self):
            raise PermissionError("private path must not appear in report")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(module.os, "scandir", lambda path: Scan())
    result = module.inventory([assets])
    assert result["counters"]["metadata_errors"] == 1
    assert not result["inventory_complete"]
    assert "private path" not in json.dumps(result)


def test_maximum_candidate_count_has_bounded_report(folders):
    assets, project, output = folders
    for kind, formats in module.FORMATS.items():
        extension = sorted(formats)[0]
        for number in range(8):
            (assets / f"{kind}-{number}{extension}").write_bytes(b"x")
    report = module.inventory([assets], candidates_per_kind=5)
    assert sum(map(len, report["candidates"].values())) == 20
    module.write_report(report, output, [assets], project_dir=project)
    assert (output / module.REPORT_NAME).stat().st_size <= module.MAX_REPORT_BYTES


def test_real_symlinks_not_followed_if_os_allows(folders, tmp_path):
    assets, project, output = folders
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.zfab").write_bytes(b"x")
    link = assets / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("real symlink creation unavailable; reparse contracts covered with fakes")
    result = module.inventory([assets])
    assert result["candidates"]["fabric"] == []
    assert result["counters"]["links_skipped"] == 1
    with pytest.raises(module.InventoryError):
        module.inventory([link])
    report_link = output / module.REPORT_NAME
    victim = outside / "do-not-overwrite.txt"
    victim.write_text("preserve")
    report_link.symlink_to(victim)
    with pytest.raises(module.InventoryError):
        module.write_report(result, output, [assets], project_dir=project)
    assert victim.read_text() == "preserve"
