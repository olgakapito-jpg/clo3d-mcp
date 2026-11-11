"""DXF append adapter: strict path, append option and list-growth readback."""

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params


class FakePattern:
    def __init__(self, names):
        self.names = names

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, index):
        return self.names[index]


class FakeImport:
    def __init__(self, names, imported, result=True):
        self.names = names
        self.imported = imported
        self.result = result
        self.option = None

    def ImportDXF(self, path, option):
        self.option = option
        self.names.extend(self.imported)
        return self.result


class ImportDxfOption:
    def __init__(self):
        self.m_bAppend = False
        self.m_bImportNotchTo = False
        self.m_eNotchImportPlacement = 0


class FakeApiTypes:
    ImportDxfOption = ImportDxfOption


def make_api(tmp_path, imported=("FRONT_L", "BACK_L"), result=True):
    source = tmp_path / "input.dxf"
    source.write_bytes(b"0\nSECTION\n0\nENDSECTION\n")
    names = ["OLD"]
    imp = FakeImport(names, list(imported), result=result)
    api = PatternAPI({
        "pattern_api": FakePattern(names),
        "import_api": imp,
        "ApiTypes": FakeApiTypes,
    })
    return api, imp, source


def test_import_dxf_appends_and_sets_options(tmp_path):
    api, imp, source = make_api(tmp_path)
    result = api("import_dxf", {"file_path": str(source)})
    assert result["imported"] is True
    assert result["pattern_count_before"] == 1
    assert result["pattern_count_after"] == 3
    assert result["imported_count"] == 2
    assert result["imported_names"] == ["FRONT_L", "BACK_L"]
    assert imp.option.m_bAppend is True
    assert imp.option.m_bImportNotchTo is True
    assert imp.option.m_eNotchImportPlacement == 2
    assert "path" not in result


def test_import_dxf_requires_dxf_and_absolute_path(tmp_path):
    api, _, source = make_api(tmp_path)
    with pytest.raises(CommandError) as exc:
        api("import_dxf", {"file_path": "relative.dxf"})
    assert exc.value.code == "invalid_parameters"
    with pytest.raises(CommandError):
        api("import_dxf", {"file_path": str(source.with_suffix(".txt"))})
    with pytest.raises(CommandError):
        validate_params("import_dxf", {"file_path": str(source), "extra": True})


def test_import_dxf_false_or_no_growth_is_not_success(tmp_path):
    api, _, source = make_api(tmp_path, result=False)
    with pytest.raises(CommandError) as exc:
        api("import_dxf", {"file_path": str(source)})
    assert exc.value.code == "invalid_native_result"

    api, _, source = make_api(tmp_path, imported=())
    with pytest.raises(CommandError) as exc:
        api("import_dxf", {"file_path": str(source)})
    assert exc.value.code == "scene_change_unverified"


def test_import_dxf_missing_file_is_invalid_before_native(tmp_path):
    api, imp, _ = make_api(tmp_path)
    missing = tmp_path / "missing.dxf"
    with pytest.raises(CommandError) as exc:
        api("import_dxf", {"file_path": str(missing)})
    assert exc.value.code == "invalid_parameters"
    assert imp.option is None
