"""Lesson runner contract: pure snapshots, read-only checks, no scene mutation."""

import asyncio

import pytest

from clo3d_mcp.lessons import LessonError, LessonRunner, Snapshot, catalog


def results(patterns, seam_count=0, groups=None, arrangements=None, avatars=None):
    groups = groups or {}
    arrangements = arrangements or {}
    avatars = avatars or [{"index": 0, "name": "avatar"}]
    return {
        "get_pattern_list": {
            "ok": True, "pattern_count": len(patterns), "patterns": patterns,
        },
        "get_seamline_pairs": {
            "ok": True,
            "seam_count": seam_count,
            "groups": [{"index": i, "name": "Sewing_%d" % i} for i in sorted(groups)],
            "patterns": [
                {"pattern_index": item["index"], "pattern_name": item["name"],
                 "group_indices": list(groups.get(item["index"], [])),
                 "group_names": []}
                for item in patterns
            ],
        },
        "get_arrangement": {
            "ok": True, "pattern_count": len(patterns), "arrangement_library_count": 110,
            "pieces": [
                {"pattern_index": item["index"], "pattern_name": item["name"],
                 "arrangement_name": arrangements.get(item["index"], "Arrangement Point"),
                 "offset": {"x": 50, "y": 50, "z": 50}, "orientation": 180,
                 "type": "Curved"}
                for item in patterns
            ],
            "units": "native_unspecified",
        },
        "get_avatars": {
            "ok": True, "avatar_count": len(avatars), "avatars": avatars,
        },
    }


class FakeService:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def call(self, command, params=None):
        self.calls.append(command)
        return self.payload[command]


def tee_payload(copy_groups=None, original_count=5, copies=5, seam_count=16):
    originals = [{"index": i, "name": name} for i, name in enumerate(
        ["3", "4", "7", "1", "2"][:original_count])]
    copied = [{"index": 10 + i, "name": "LESSON_%s" % name} for i, name in enumerate(
        ["3", "4", "7", "1", "2"][:copies])]
    groups = {0: [0], 1: [10, 11, 12, 13, 14, 15],
              2: [1], 3: [2, 3, 6, 7, 8, 9, 10, 11],
              4: [4, 5, 6, 7, 8, 9, 12, 13, 14]}
    groups.update(copy_groups or {10 + i: [] for i in range(copies)})
    return results(originals + copied, seam_count=seam_count, groups=groups)


def run_tee_to_completion(runner):
    async def scenario():
        service = FakeService(tee_payload(copies=0))
        assert (await runner.check(service))["passed"] is True

        service.payload = tee_payload(
            copy_groups={10: [], 11: [20], 12: [], 13: [21], 14: [22]},
            seam_count=19)
        assert (await runner.check(service))["passed"] is True

        service.payload = results(
            [{"index": 10 + i, "name": "LESSON_%s" % name}
             for i, name in enumerate(["3", "4", "7", "1", "2"])],
            seam_count=3, groups={10: [20], 12: [21], 14: [22]},
        )
        assert (await runner.check(service))["passed"] is True

        service.payload = results(
            [{"index": 10 + i, "name": "LESSON_%s" % name}
             for i, name in enumerate(["3", "4", "7", "1", "2"])],
            seam_count=3, groups={10: [20], 12: [21], 14: [22]},
            arrangements={10: "Arm_Outside_1_L", 11: "Neck_R", 12: "Arm_Outside_1_R",
                          13: "Body_Front_Center_3", 14: "Body_Back_Center_3"},
        )
        state = await runner.check(service)
        return service, state

    return asyncio.run(scenario())


def test_catalog_has_stable_lessons():
    lessons = catalog()
    assert [item["id"] for item in lessons] == ["tee_copy_place", "two_panel_tube"]
    assert all(item["steps"] for item in lessons)


def test_unknown_lesson_is_rejected():
    runner = LessonRunner()
    with pytest.raises(LessonError) as exc:
        runner.start("missing")
    assert exc.value.code == "lesson_not_found"


def test_tee_lesson_advances_only_on_passed_checks():
    runner = LessonRunner()
    state = runner.start("tee_copy_place")
    assert state["status"] == "in_progress"
    assert state["current_step"]["id"] == "audit"

    service, final = run_tee_to_completion(runner)
    assert final["status"] == "completed"
    assert set(service.calls) == {
        "get_pattern_list", "get_seamline_pairs", "get_arrangement", "get_avatars"}
    assert len(service.calls) == 16
    assert runner.state()["status"] == "completed"


def test_tee_copy_shared_group_stops_the_step():
    async def scenario():
        runner = LessonRunner()
        runner.start("tee_copy_place")
        service = FakeService(tee_payload(copies=0))
        assert (await runner.check(service))["passed"] is True

        # Copy 10 shares a two-pattern group with original 3: must not advance.
        service.payload = tee_payload(
            copy_groups={10: [2], 11: [], 12: [], 13: [], 14: []},
            seam_count=17)
        return await runner.check(service)

    result = asyncio.run(scenario())
    assert result["passed"] is False
    assert result["current_step"]["id"] == "copy"
    assert "связана" in result["message"]


def test_tube_lesson_uses_first_snapshot_as_baseline():
    async def scenario():
        runner = LessonRunner()
        runner.start("two_panel_tube")
        panels = [{"index": 0, "name": "LESSON_TUBE_A"},
                  {"index": 1, "name": "LESSON_TUBE_B"}]
        service = FakeService(results(panels, seam_count=16))
        assert (await runner.check(service))["passed"] is True

        service.payload = results(panels, seam_count=17)
        assert (await runner.check(service))["passed"] is True

        service.payload = results(panels, seam_count=18)
        assert (await runner.check(service))["passed"] is True

        service.payload = results(panels, seam_count=18)
        state = await runner.check(service)
        return service, state

    service, state = asyncio.run(scenario())
    assert state["passed"] is True and state["status"] == "completed"
    assert len(service.calls) == 16


def test_tube_missing_second_seam_does_not_advance():
    async def scenario():
        runner = LessonRunner()
        runner.start("two_panel_tube")
        panels = [{"index": 0, "name": "LESSON_TUBE_A"},
                  {"index": 1, "name": "LESSON_TUBE_B"}]
        service = FakeService(results(panels, seam_count=16))
        assert (await runner.check(service))["passed"] is True

        service.payload = results(panels, seam_count=17)
        assert (await runner.check(service))["passed"] is True

        service.payload = results(panels, seam_count=17)
        return await runner.check(service)

    result = asyncio.run(scenario())
    assert result["passed"] is False
    assert result["current_step"]["id"] == "right_seam"


def test_read_failure_does_not_advance():
    class Failing:
        async def call(self, command, params=None):
            return {"ok": False, "error": "executor_unavailable"}

    async def scenario():
        runner = LessonRunner()
        runner.start("two_panel_tube")
        with pytest.raises(LessonError) as exc:
            await runner.check(Failing())
        return runner, exc

    runner, exc = asyncio.run(scenario())
    assert exc.value.code == "lesson_check_unavailable"
    assert runner.state()["current_step"]["id"] == "panels"


def test_snapshot_rejects_malformed_payload():
    with pytest.raises(LessonError) as exc:
        Snapshot.from_results(
            {"patterns": [{"index": True, "name": "x"}]},
            {"seam_count": 0, "patterns": []},
            {"pattern_count": 1, "pieces": []},
            {"avatars": []},
        )
    assert exc.value.code == "lesson_check_unavailable"


def test_reset_clears_progress():
    runner = LessonRunner()
    runner.start("two_panel_tube")
    assert runner.reset()["reset"] is True
    state = runner.state()
    assert state["status"] == "not_started" and state["lesson"] is None
