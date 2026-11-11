"""Avatar .avs size import: native call plus measurement-count report."""

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_params


class NativeImport:
    def __init__(self, result=True, extra=0):
        self.result = result
        self.extra = extra
        self.calls = []
        self.measures = [1, 2]

    def ImportFile(self, path):
        self.calls.append(path)
        self.measures.extend(range(100, 100 + self.extra))
        return self.result


class NativeExport:
    def __init__(self):
        self.count = 1

    def GetAvatarCount(self):
        return self.count


class NativeUtility:
    def __init__(self, imp):
        self.imp = imp

    def GetAvatarMeasurements(self, index):
        return list(self.imp.measures)


def make(tmp_path, result=True, extra=0):
    path = tmp_path / "olga.avs"
    path.write_bytes(b"avs")
    imp = NativeImport(result, extra)
    api = PatternAPI({
        "pattern_api": object(),
        "import_api": imp,
        "export_api": NativeExport(),
        "utility_api": NativeUtility(imp),
    })
    return api, imp, path


def test_avatar_size_reports_measurement_delta(tmp_path):
    api, imp, path = make(tmp_path, extra=3)
    result = api("import_avatar_size", {"file_path": str(path)})
    assert result == {"verified": True, "measurement_count_before": 2,
                      "measurement_count_after": 5, "added": 3}
    assert imp.calls == [str(path)]


def test_avatar_size_zero_growth_is_reported_not_faked(tmp_path):
    api, _, path = make(tmp_path, extra=0)
    result = api("import_avatar_size", {"file_path": str(path)})
    assert result["added"] == 0


def test_avatar_size_false_is_an_error(tmp_path):
    api, _, path = make(tmp_path, result=False)
    with pytest.raises(CommandError) as exc:
        api("import_avatar_size", {"file_path": str(path)})
    assert exc.value.code == "invalid_native_result"


def test_avatar_size_path_is_strict(tmp_path):
    with pytest.raises(CommandError):
        validate_params("import_avatar_size", {"file_path": "relative.avs"})
    with pytest.raises(CommandError):
        validate_params("import_avatar_size", {"file_path": str(tmp_path / "x.txt")})
    with pytest.raises(CommandError):
        validate_params("import_avatar_size", {"file_path": str(tmp_path / "x.avs"), "extra": True})
