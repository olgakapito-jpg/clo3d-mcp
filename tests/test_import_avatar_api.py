"""Bounded avatar import contracts/faults; synthetic native, not real CLO."""

from types import SimpleNamespace

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params, validate_result


class ImportAPI:
    def __init__(self, value=True, fail=False):
        self.value = value
        self.fail = fail
        self.calls = []

    def ImportAvatar(self, path, option):
        self.calls.append((path, option))
        if self.fail:
            raise RuntimeError("private path")
        return self.value


class ExportAPI:
    def __init__(self, counts=(0, 1), option=True):
        self.counts = list(counts)
        self.option = option
        self.option_calls = 0

    def GetAvatarCount(self):
        return self.counts.pop(0) if self.counts else 1

    def ImportExportOption(self):
        self.option_calls += 1
        return "option"


class Native:
    pass


def api(import_api, export_api):
    return PatternAPI({"pattern_api": Native(), "import_api": import_api,
                       "export_api": export_api})


def params(tmp_path):
    path = tmp_path / "avatar.avt"
    path.write_bytes(b"x" * 32)
    return {"file_path": str(path)}


def test_import_avatar_success_count_and_option(tmp_path):
    imp, exp = ImportAPI(), ExportAPI()
    result = api(imp, exp)("import_avatar", params(tmp_path))
    assert result == {"verified": True, "avatar_count": 1}
    assert len(imp.calls) == 1 and imp.calls[0][1] == "option"
    assert exp.option_calls == 1


def test_import_avatar_new_option_factory_fallback(tmp_path):
    exp = ExportAPI()
    exp.ImportExportOption = None
    exp.NewImportExportOption = lambda: "new-option"
    result = api(ImportAPI(), exp)("import_avatar", params(tmp_path))
    assert result["verified"] is True


@pytest.mark.parametrize("value", [False, 0, "name", None])
def test_import_avatar_false_or_nonbool_rejected(tmp_path, value):
    with pytest.raises(CommandError, match="invalid_native_result"):
        api(ImportAPI(value), ExportAPI())("import_avatar", params(tmp_path))


def test_import_avatar_native_exception_is_unknown(tmp_path):
    with pytest.raises(CommandError, match="scene_change_unverified"):
        api(ImportAPI(fail=True), ExportAPI())("import_avatar", params(tmp_path))


@pytest.mark.parametrize("counts", [[0, 0], [1, 1], [0, 2], [64, 1]])
def test_import_avatar_count_must_increase_by_one(tmp_path, counts):
    exp = ExportAPI(counts=counts)
    with pytest.raises(CommandError, match="(scene_change_unverified|invalid_native_result)"):
        api(ImportAPI(), exp)("import_avatar", params(tmp_path))


def test_import_avatar_missing_file_or_relative_path_rejected(tmp_path):
    imp = ImportAPI()
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(imp, ExportAPI())("import_avatar", {"file_path": str(tmp_path / "missing.avt")})
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(imp, ExportAPI())("import_avatar", {"file_path": "avatar.avt"})
    assert imp.calls == []


@pytest.mark.parametrize("file_path", ["", "x.avac", "x/y.avt", "\ud800.avt", "x" * 261])
def test_import_avatar_contract_rejects_bad_paths(file_path):
    with pytest.raises(CommandError, match="invalid_parameters"):
        validate_params("import_avatar", {"file_path": file_path})


def test_import_avatar_missing_binding():
    imp = ImportAPI()
    imp.ImportAvatar = None
    with pytest.raises(CommandError, match="api_unavailable"):
        api(imp, ExportAPI())._import_avatar({"file_path": "C:/none.avt"})


def test_import_avatar_result_validator():
    validate_result("import_avatar", {"verified": True, "avatar_count": 1})
    for bad in ({"verified": False, "avatar_count": 1},
                {"verified": True, "avatar_count": -1},
                {"verified": True, "avatar_count": True},
                {"verified": True, "avatar_count": 65}):
        with pytest.raises(CommandError, match="invalid_result"):
            validate_result("import_avatar", bad)
