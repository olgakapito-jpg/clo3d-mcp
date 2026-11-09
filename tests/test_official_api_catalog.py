"""Offline specification/extractor checks, never native acceptance."""

from copy import deepcopy
import html
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("official_catalog", ROOT / "scripts/build_official_api_catalog.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
FIXTURES = Path(__file__).parent / "fixtures/api_catalog"


@pytest.fixture
def catalog():
    return builder.load_catalog()


def fake_html(rst):
    """Sphinx-shaped miniature, not a copy of the official website."""
    return ('<section id="test-anchor">' + "".join(
        '<div class="highlight-' + block["language"] + '"><pre><span></span>'
        + html.escape(block["raw"]) + '</pre></div>'
        for block in builder.rst_blocks(rst)) + '</section>').encode()


def fixture_sources():
    # Only small, handwritten test sources; all missing facts stay missing.
    snippets = {"list": (FIXTURES / "mini_list.rst.txt").read_text(encoding="utf-8"),
                "optiontype": (FIXTURES / "mini_type.rst.txt").read_text(encoding="utf-8"),
                "gui_api_reference": "Availability\n------------\n\n.. code-block:: python\n\n   gui_api.Read() -> Thing\n\nRead a GUI value.\n\n**Returns:** A record.\n",
                "library": "Implement CLOAPI::LibraryWindowImplPlugin from LibraryWindowInterface; export Create().\n",
                "eventplugin": "CloEventPlugin.h\nMouseDropEventOn2DView\nMouseDropEventOn3DView\n\n.. code-block:: cpp\n\n   bool CloEventPlugin::MouseDropEventOn2DView(float x)\n   { return true; }\n",
                "download": "**SDK v11.0.1** — *CLO 2026.1.336 Official Release*\n",
                "changelog": "Documentation update, October 2026\n-----\nV11.0.1, October 2026\n-----\n",
                "python": "Python API\n"}
    sources = {}
    for page, rst in snippets.items():
        sources[page + ".rst.txt"] = rst.encode()
        sources[page + ".html"] = fake_html(rst)
    return sources


def test_full_primary_denominators_and_dedup(catalog):
    assert catalog["counts"]["modules"] == {
        "export_api": {"names": 91, "python_blocks": 123, "unique_declarations": 123},
        "fabric_api": {"names": 134, "python_blocks": 284, "unique_declarations": 284},
        "gui_api": {"names": 39, "python_blocks": 39, "unique_declarations": 39},
        "import_api": {"names": 38, "python_blocks": 44, "unique_declarations": 42},
        "pattern_api": {"names": 217, "python_blocks": 233, "unique_declarations": 233},
        "rest_api": {"names": 7, "python_blocks": 8, "unique_declarations": 8},
        "utility_api": {"names": 364, "python_blocks": 406, "unique_declarations": 405},
    }
    assert catalog["counts"]["python_names"] == 890
    assert catalog["counts"]["unique_python_declarations"] == 1134
    assert catalog["counts"]["type_records"] == 77
    assert catalog["counts"]["type_members"] == 582
    duplicates = {m["id"]: len(d["occurrences"]) for m in catalog["methods"]
                  for d in m["declarations"] if len(d["occurrences"]) > 1}
    assert duplicates == {"import_api.ImportAVAC": 2, "import_api.ImportGraphicStyleFromImage": 2,
                          "utility_api.SaveCLOFileThumbnail": 2}


def test_manifest_provenance_and_every_occurrence(catalog):
    assert catalog["target"] == "CLO2026.1.336"
    assert catalog["provenance"]["sdk_version"] == "11.0.1"
    assert catalog["provenance"]["release_date_raw"] == "October 2026"
    assert len(catalog["sources"]) == 16
    assert len(catalog["provenance"]["sdk_download_urls_not_fetched"]) == 4
    for source in catalog["sources"]:
        assert source["url"].startswith("https://developer.clo3d.com/")
        assert source["hash_scope"] == "fetched_source_bytes_not_normalized"
        assert len(source["sha256"]) == 64
    for method in catalog["methods"]:
        assert method["runtime_presence"] == method["binding_status"] == "not_checked"
        assert method["semantic_contract_status"] == "not_checked"
        for declaration in method["declarations"]:
            assert declaration["signature_raw"]
            assert declaration["return_raw"]
            for occurrence in declaration["occurrences"]:
                assert occurrence["documentation_raw"]
                assert len(occurrence["documentation_raw"]) <= builder.MAX_NOTES_CHARS
                assert len(occurrence["sources"]) == 2
                assert all(s["line"] > 0 and s["block"] > 0 for s in occurrence["sources"])
                assert occurrence["sources"][1]["anchor"]
                if method["module"] != "gui_api":
                    assert occurrence["cpp"]["signature_raw"]
    ids = {m["id"] for m in catalog["methods"]}
    assert "export_api.ExportZPac" in ids and "export_api.ExportZPacW" in ids
    assert "utility_api.AddGraphicStyleToPattern" in ids and "pattern_api.AddGraphicStyleToPattern" in ids


def test_types_have_real_members_enums_and_explicit_unresolved(catalog):
    types = {t["name"]: t for t in catalog["types"]}
    weld = {m["name"]: m for m in types["WELD_TYPE"]["members"]}
    assert weld["FULLY_WELDED"]["value_raw"] == "2"
    assert weld["FULLY_WELDED"]["kind"] == "enum_value"
    options = {m["name"]: m for m in types["ImportExportOption"]["members"]}
    assert options["weldType"]["annotation_raw"] == "WELD_TYPE"
    assert any(r["type_id"] == "type:WELD_TYPE" for r in options["weldType"]["type_references"])
    assert "millimeters" in options["scale"]["documentation_raw"]
    assert "gltf" in options["scale"]["raw"]
    assert any(m["kind"] == "method" for m in types["MaterialFaceOptions"]["members"])
    assert all(t["members"] for t in catalog["types"])
    assert not any(m["kind"] == "ambiguous" for t in catalog["types"] for m in t["members"])
    refs = [r for m in catalog["methods"] for d in m["declarations"] for r in d["type_references"]]
    assert any(r["name"] == "QWidget" and r["status"] == "unresolved" and r["type_id"] is None for r in refs)
    assert any(r["basis"] == "documentation_mention" and r["status"] == "resolved" for r in refs)


def test_cpp_interfaces_are_not_python_and_missing_signatures_stay_missing(catalog):
    interfaces = {r["name"]: r for r in catalog["interfaces"]}
    assert len(interfaces) == 6
    assert all(r["classification"] == "cpp_only" for r in interfaces.values())
    assert interfaces["CloEventPlugin::MouseDropEventOn3DView"]["signature_raw"] is None
    assert interfaces["LibraryWindowInterface"]["signature_raw"] is None
    assert "std::unordered_map" in interfaces["CloEventPlugin::MouseDropEventOn2DView"]["signature_raw"]


def test_gui_notes_and_docs_anomalies_not_silently_corrected(catalog):
    methods = {m["id"]: m for m in catalog["methods"]}
    ask = methods["gui_api.AskConfirm"]["declarations"][0]
    assert "block until" in ask["occurrences"][0]["documentation_raw"]
    assert ask["parameters"][2]["default_raw"] == '"OK"'
    assert ask["parameter_docs_raw"] and ask["return_docs_raw"]
    nesting = methods["utility_api.GetNestingFabricBufferSpacing"]["declarations"][0]
    assert nesting["return_raw"] == "std::array[float, 4]"
    assert nesting["contract_status"] == "ambiguous"
    seam = methods["pattern_api.AddSeamlinePairGroup"]["declarations"][0]
    assert seam["return_raw"] == "bool"
    assert "wide string" in " ".join(seam["return_docs_raw"])


def test_fixture_rst_html_and_dedup_preserve_all_notes():
    catalog = builder.build_catalog(fixture_sources(), "2026-11-09")
    declaration = next(m for m in catalog["methods"] if m["id"] == "export_api.Export")["declarations"][0]
    assert len(declaration["occurrences"]) == 2
    assert "Second occurrence" in declaration["occurrences"][1]["documentation_raw"]
    assert declaration["parameters"][1]["default_raw"] == '"two  spaces"'
    assert declaration["occurrences"][0]["sources"][1]["anchor"] == "test-anchor"
    members = catalog["types"][0]["members"]
    assert "more detail" in members[0]["documentation_raw"]
    assert members[1]["type_references"][0]["status"] == "unresolved"
    assert members[2]["value_raw"] == "0"
    assert members[4]["kind"] == "method"


@pytest.mark.parametrize("raw,expected", [
    ('x: Callable[[int, str], None], y: list[int] = [], label: str = "a,b"', 3),
    ('x: dict[str, tuple[int, int]], y: str = "a\\\"b,c"', 2),
    ('', 0),
])
def test_bracket_quote_aware_parameter_split(raw, expected):
    assert len(builder.split_parameters(raw)) == expected


def test_signature_normalization_never_changes_quoted_spaces():
    assert builder.signature_key('def  A(x : str = "a  b") -> str') == 'def A(x : str = "a  b") -> str'


def test_html_rst_disagreement_and_unrecognized_signatures_fail_closed():
    sources = fixture_sources()
    sources["list.html"] = sources["list.html"].replace(b"distance in mm", b"distance in inches")
    with pytest.raises(ValueError, match="disagree"):
        builder.build_catalog(sources, "2026-11-09")
    with pytest.raises(ValueError, match="Unrecognized"):
        builder.parse_signature("some unsupported declaration")
    with pytest.raises(ValueError, match="Unbalanced"):
        builder.split_parameters("x: list[int")


def test_latest_version_and_missing_source_are_explicit_blockers():
    sources = fixture_sources()
    sources["download.rst.txt"] = sources["download.rst.txt"].replace(b"2026.1.336", b"2026.2.001")
    with pytest.raises(ValueError, match="Latest official SDK changed"):
        builder.build_catalog(sources, "2026-11-09")
    del sources["download.html"]
    with pytest.raises(ValueError, match="Missing source"):
        builder.build_catalog(sources, "2026-11-09")


def test_offline_roundtrip_no_assets_size_and_tamper(tmp_path, catalog):
    index, files = builder.shard_catalog(catalog)
    assert len(files) > 20
    assert len(builder.json_bytes(index)) < 200_000
    for relative, data in files.items():
        assert len(data) <= builder.MAX_SHARD_BYTES < 200_000
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    path = tmp_path / "index.json"
    path.write_bytes(builder.json_bytes(index))
    assert builder.load_catalog(path) == catalog
    first = tmp_path / index["shards"][0]["path"]
    first.write_bytes(first.read_bytes() + b" ")
    with pytest.raises(ValueError, match="integrity"):
        builder.load_catalog(path)


def test_unsafe_shard_path_and_invalid_resolution_rejected(tmp_path, catalog):
    index, _ = builder.shard_catalog(catalog)
    index["shards"][0]["path"] = "../outside.json"
    path = tmp_path / "index.json"
    path.write_bytes(builder.json_bytes(index))
    with pytest.raises(ValueError, match="Unsafe"):
        builder.load_catalog(path)
    invalid = deepcopy(catalog)
    refs = next(d["type_references"] for m in invalid["methods"] for d in m["declarations"] if d["type_references"])
    refs[0].update(status="resolved", type_id="type:DefinitelyMissing")
    with pytest.raises(ValueError, match="type resolution"):
        builder.validate_catalog(invalid)


def test_offline_check_never_networks_or_writes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline check attempted side effect")
    monkeypatch.setattr(builder, "urlopen", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    assert builder.main(["--check"]) == 0


def test_cached_source_check_is_nonmutating_and_reproducible(tmp_path, monkeypatch):
    sources = fixture_sources()
    for name, data in sources.items():
        (tmp_path / name).write_bytes(data)
    index_path = tmp_path / "out/index.json"
    args = ["--source-dir", str(tmp_path), "--index", str(index_path), "--checked-on", "2026-11-09"]
    assert builder.main(args) == 0
    def forbidden(*args, **kwargs):
        raise AssertionError("--check attempted write")
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    assert builder.main(args + ["--check"]) == 0


def test_fetch_is_once_bounded_and_no_retry(monkeypatch):
    calls = []
    def broken(url, timeout):
        calls.append((url, timeout))
        raise socket.timeout("injected")
    monkeypatch.setattr(builder, "urlopen", broken)
    with pytest.raises(socket.timeout):
        builder.fetch_sources(timeout=2, total_timeout=5)
    assert len(calls) == 1 and 0 < calls[0][1] <= 2


def test_fetch_limits_redirects_and_total_deadline(monkeypatch):
    class Response:
        url = builder.BASE_URL + "list.html"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return b"x" * size
    monkeypatch.setattr(builder, "MAX_SOURCE_BYTES", 8)
    monkeypatch.setattr(builder, "urlopen", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="too large"):
        builder.fetch_sources()
    Response.url = "https://example.invalid/redirect"
    with pytest.raises(ValueError, match="redirect"):
        builder.fetch_sources()
    clock = iter([0, 181])
    monkeypatch.setattr(builder.time, "monotonic", lambda: next(clock))
    with pytest.raises(TimeoutError, match="deadline"):
        builder.fetch_sources()


def test_orphan_cpp_and_missing_html_block_are_not_silently_dropped():
    sources = fixture_sources()
    sources["list.rst.txt"] += b"\n\n.. code-block:: c++\n\n   CppOnly()\n"
    sources["list.html"] = fake_html(sources["list.rst.txt"].decode())
    with pytest.raises(ValueError, match="Unclassified"):
        builder.build_catalog(sources, "2026-11-09")
    sources = fixture_sources()
    sources["list.html"] = b"<section></section>"
    with pytest.raises(ValueError, match="count differs"):
        builder.build_catalog(sources, "2026-11-09")


def test_untracked_generated_files_also_pass_no_assets_guard():
    spec = importlib.util.spec_from_file_location("no_assets", ROOT / "tests/test_no_assets.py")
    no_assets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(no_assets)
    paths = ["scripts/build_official_api_catalog.py", "tests/test_official_api_catalog.py"]
    paths += [str(p.relative_to(ROOT)).replace("\\", "/")
              for p in (ROOT / "docs/api/official").glob("*.json")]
    paths += ["docs/api/clo_official_api.json", "docs/api/CLO_OFFICIAL_API.md"]
    assert no_assets.faults(paths) == []


def test_cli_check_subprocess_offline():
    completed = subprocess.run([sys.executable, "scripts/build_official_api_catalog.py", "--check"],
                               cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["python_names"] == 890
