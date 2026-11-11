"""Native pattern JSON artifact: export, destructive import and readback."""

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params


class FakePattern:
    def __init__(self, names, seam_count=0):
        self.names = list(names)
        self.seam_count = seam_count

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, index):
        return self.names[index]

    def GetSeamlinePairGroupCount(self):
        return self.seam_count


class FakeExport(FakePattern):
    def __init__(self, names, result=True):
        super().__init__(names)
        self.result = result

    def ExportPatternJSON(self, path):
        if self.result:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"patterns": [], "seams": []}')
        return self.result


class FakeImport(FakePattern):
    def __init__(self, names, replacement, seam_count=0, result=True):
        super().__init__(names, seam_count)
        self.replacement = list(replacement)
        self.result = result

    def ImportPatternJSON(self, path):
        if self.result:
            self.names = list(self.replacement)
        return self.result


def test_export_pattern_json_writes_bounded_artifact(tmp_path):
    output = tmp_path / "pattern.json"
    api = PatternAPI({"pattern_api": FakeExport(["A"])})
    result = api("export_pattern_json", {"output_path": str(output)})
    assert result == {"verified": True, "file_name": "pattern.json",
                      "bytes": output.stat().st_size}
    assert output.exists()


def test_export_pattern_json_false_is_an_error(tmp_path):
    output = tmp_path / "pattern.json"
    api = PatternAPI({"pattern_api": FakeExport(["A"], result=False)})
    with pytest.raises(CommandError) as exc:
        api("export_pattern_json", {"output_path": str(output)})
    assert exc.value.code == "invalid_native_result"


def test_import_pattern_json_replaces_and_reports_readback(tmp_path):
    source = tmp_path / "pattern.json"
    source.write_text('{"patterns": []}', encoding="utf-8")
    api = PatternAPI({"pattern_api": FakeImport(["OLD"], ["A", "B"], seam_count=3)})
    result = api("import_pattern_json", {"file_path": str(source)})
    assert result["imported"] is True
    assert result["pattern_count_before"] == 1
    assert result["pattern_count_after"] == 2
    assert result["patterns_after"] == [
        {"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert result["seam_count_after"] == 3
    assert result["executor_ms"] >= 0


def test_import_pattern_json_false_is_an_error(tmp_path):
    source = tmp_path / "pattern.json"
    source.write_text('{"patterns": []}', encoding="utf-8")
    api = PatternAPI({"pattern_api": FakeImport(["OLD"], [], result=False)})
    with pytest.raises(CommandError) as exc:
        api("import_pattern_json", {"file_path": str(source)})
    assert exc.value.code == "invalid_native_result"


def test_pattern_json_paths_are_strict(tmp_path):
    json_path = tmp_path / "pattern.json"
    json_path.write_text("{}", encoding="utf-8")
    with pytest.raises(CommandError):
        validate_params("import_pattern_json", {"file_path": "relative.json"})
    with pytest.raises(CommandError):
        validate_params("import_pattern_json", {"file_path": str(json_path.with_suffix(".dxf"))})
    with pytest.raises(CommandError):
        validate_params("import_pattern_json", {"file_path": str(json_path), "extra": True})
    with pytest.raises(CommandError):
        validate_params("export_pattern_json", {"output_path": str(json_path.with_suffix(".png"))})
