"""Contracts/faults for view images, camera, cloth reset, measurements and mesh tools."""

import json
import sys

import pytest

from clo3d_mcp.pattern_api import PatternAPI
from clo3d_mcp.pattern_contract import CommandError, validate_result

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Native:
    def __init__(self):
        self.names = ["panel"]
        self.grain = 0.0
        self.particle = 20.0
        self.body = {"upperBody": [{"patternName": "panel", "patternIndex": 0,
                                   "arrangementPosition": "Body_Front_Center_2",
                                   "semanticLabel": "bodice_front",
                                   "bodyRegion": "torso_front",
                                   "patternPosition": "front"}],
                     "lowerBody": []}

    def GetPatternCount(self):
        return len(self.names)

    def GetPatternPieceName(self, i):
        return self.names[i]

    def GetPatternPiecePos(self, i):
        return [0.0, 0.0]

    def GetPatternPieceArea(self, i):
        return 100.0

    def GetBoundingBoxOfPattern(self, i):
        return {"Width": "10.000000", "Height": "10.000000"}

    def GetPatternOnBodyDetails(self):
        return json.dumps(self.body)

    def GetPatternPieceGrainDirection(self, i):
        return self.grain

    def SetPatternPieceGrainDirection(self, i, degrees):
        self.grain = float(degrees)

    def GetPatternPieceCategory(self, i):
        return 1

    def GetPatternPieceClassification(self, i):
        return "bodice_front"

    def GetMeshCountByType(self, i):
        return {"render": "12,8"}

    def GetParticleDistanceOfPattern(self, i):
        return self.particle

    def SetParticleDistanceOfPattern(self, i, distance):
        self.particle = float(distance)


class Export:
    def __init__(self):
        self.calls = []
        self.avatars = ["avatar"]
        self.measurements = [object()]

    def GetAvatarCount(self):
        return len(self.avatars)

    def GetAvatarNameList(self):
        return list(self.avatars)

    def GetCurrentColorwayIndex(self):
        return 0

    def ExportStdViewImage(self, view, path, colorway, width, height, fit):
        self.calls.append(("view", view, colorway, width, height, fit))
        with open(path, "wb") as file:
            file.write(PNG)
        return path

    def ExportThumbnail2D(self, path):
        self.calls.append(("2d", path))
        with open(path, "wb") as file:
            file.write(PNG)
        return path


class Utility:
    def __init__(self):
        self.calls = []

    def SetCamViewPoint(self, view):
        self.calls.append(("view", view))

    def SetZoomView(self):
        self.calls.append(("zoom",))

    def Refresh3DWindow(self):
        self.calls.append(("refresh",))

    def ResetClothArrangement(self):
        self.calls.append(("reset",))

    def GetAvatarMeasurements(self, index):
        return [object() for _ in range(len(self.measurements))]


class Importer:
    def __init__(self, export):
        self.export = export
        self.calls = []

    def ImportMeasurement(self, path):
        self.calls.append(path)
        self.export.measurements.append(object())
        return True


def layer(tmp_path):
    export, utility = Export(), Utility()
    importer = Importer(export)
    native = Native()
    utility.measurements = export.measurements
    api = PatternAPI({"pattern_api": native, "export_api": export,
                      "utility_api": utility, "import_api": importer})
    return api, native, export, utility, importer


def test_view_and_2d_images(tmp_path):
    api, native, export, utility, importer = layer(tmp_path)
    view_path = tmp_path / "view.png"
    view = api("export_view_image", {"output_path": str(view_path), "view": 2,
                                     "width": 800, "height": 600, "fit_all_objects": True})
    assert view == {"verified": True, "view": 2, "width": 800, "height": 600,
                    "file_name": "view.png", "bytes": len(PNG)}
    flat = api("export_snapshot_2d", {"output_path": str(tmp_path / "flat.png")})
    assert flat["file_name"] == "flat.png" and flat["bytes"] == len(PNG)


def test_camera_and_reset(tmp_path):
    api, native, export, utility, importer = layer(tmp_path)
    assert api("set_camera_view", {"view": 2, "zoom_to_fit": True})["verified"] is True
    assert utility.calls == [("view", 2), ("zoom",), ("refresh",)]
    assert api("reset_cloth_arrangement", {}) == {"verified": True, "pattern_count": 1}
    assert utility.calls[-1] == ("reset",)


def test_import_measurements(tmp_path):
    api, native, export, utility, importer = layer(tmp_path)
    path = tmp_path / "m.csv"
    path.write_text("name,value\n", encoding="utf-8")
    result = api("import_avatar_measurements", {"csv_path": str(path)})
    assert result["verified"] is True and result["added"] == 1
    assert importer.calls == [str(path)]


def test_body_details_and_pattern_details(tmp_path):
    api, native, export, utility, importer = layer(tmp_path)
    body = api("get_pattern_body_details", {})
    assert body["upperBody"][0]["semanticLabel"] == "bodice_front"
    details = api("get_pattern_details", {"pattern_index": 0, "expected_name": "panel"})
    assert details == {"pattern_index": 0, "pattern_name": "panel",
                       "grain_direction": 0.0, "category": 1,
                       "classification": "bodice_front"}


def test_grain_mesh_and_particle(tmp_path):
    api, native, export, utility, importer = layer(tmp_path)
    grain = api("set_pattern_grain_direction", {"pattern_index": 0,
                                                "expected_name": "panel", "degrees": 90})
    assert grain["verified"] is True and native.grain == 90.0
    mesh = api("get_mesh_counts", {"pattern_index": 0, "expected_name": "panel"})
    assert mesh["meshes"] == [{"type": "render", "value": "12,8"}]
    particle = api("set_particle_distance", {"pattern_index": 0,
                                             "expected_name": "panel", "distance": 10})
    assert particle["verified"] is True and native.particle == 10.0


@pytest.mark.parametrize("command,params", [
    ("export_view_image", {"output_path": "relative.png", "view": 2, "width": 800,
                           "height": 600, "fit_all_objects": True}),
    ("export_view_image", {"output_path": "C:\\x.png", "view": 9, "width": 800,
                           "height": 600, "fit_all_objects": True}),
    ("set_camera_view", {"view": 2, "zoom_to_fit": 1}),
    ("import_avatar_measurements", {"csv_path": "relative.csv"}),
    ("set_pattern_grain_direction", {"pattern_index": 0, "expected_name": "panel",
                                     "degrees": 360}),
    ("set_particle_distance", {"pattern_index": 0, "expected_name": "panel",
                               "distance": 0}),
])
def test_invalid_params(tmp_path, command, params):
    api, *_ = layer(tmp_path)
    with pytest.raises(CommandError, match="invalid_parameters"):
        api(command, params)


def test_result_validators():
    validate_result("export_view_image", {"verified": True, "view": 2, "width": 800,
                                          "height": 600, "file_name": "v.png", "bytes": 10})
    validate_result("export_snapshot_2d", {"verified": True, "file_name": "v.png", "bytes": 10})
    validate_result("set_camera_view", {"verified": True, "view": 2, "zoom_to_fit": True})
    validate_result("reset_cloth_arrangement", {"verified": True, "pattern_count": 1})
    validate_result("import_avatar_measurements", {"verified": True, "avatar_index": 0,
                                                   "before_count": 1, "after_count": 2,
                                                   "added": 1})
    validate_result("get_pattern_body_details", {"upperBody": [], "lowerBody": []})
    validate_result("get_pattern_details", {"pattern_index": 0, "pattern_name": "a",
                                            "grain_direction": 0.0, "category": 1,
                                            "classification": ""})
    validate_result("set_pattern_grain_direction", {"verified": True, "pattern_index": 0,
                                                    "pattern_name": "a", "grain_direction": 90.0})
    validate_result("get_mesh_counts", {"pattern_index": 0, "pattern_name": "a",
                                        "meshes": [{"type": "render", "value": "1,2"}]})
    validate_result("set_particle_distance", {"verified": True, "pattern_index": 0,
                                              "pattern_name": "a", "distance": 20.0})
