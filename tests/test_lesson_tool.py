"""Transport-level lesson tool: raw args, registration and no native mutation."""

import asyncio
import json

from clo3d_mcp.lessons import LessonRunner
from clo3d_mcp.transport_server import build_mcp


class FakeService:
    port = 8765
    pattern_package = True

    def __init__(self):
        self.lessons = LessonRunner()
        self.calls = []

    async def call(self, command, params):
        self.calls.append(command)
        return {"ok": False, "error": "executor_unavailable"}


def payload(result):
    if isinstance(result, tuple):
        result = result[1]
    if isinstance(result, dict):
        return result
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def test_lesson_raw_args_and_state_are_server_local():
    async def scenario():
        service = FakeService()
        mcp = build_mcp(service)
        tools = {tool.name for tool in await mcp.list_tools()}
        assert "lesson" in tools

        listed = payload(await mcp.call_tool("lesson", {"action": "list"}))
        assert listed["ok"] is True
        assert {item["id"] for item in listed["lessons"]} == {
            "tee_copy_place", "two_panel_tube"}

        bad = await mcp.call_tool("lesson", {"action": "list", "extra": True})
        assert bad.isError
        assert payload(bad)["error"] == "invalid_parameters"

        missing = await mcp.call_tool("lesson", {"action": "start"})
        assert missing.isError
        assert payload(missing)["error"] == "invalid_parameters"

        unknown = await mcp.call_tool("lesson", {
            "action": "start", "lesson_id": "missing"})
        assert unknown.isError
        assert payload(unknown)["error"] == "lesson_not_found"

        started = payload(await mcp.call_tool("lesson", {
            "action": "start", "lesson_id": "two_panel_tube"}))
        assert started["status"] == "in_progress"
        assert started["current_step"]["id"] == "panels"

        state = payload(await mcp.call_tool("lesson", {"action": "state"}))
        assert state["status"] == "in_progress"

        # A failed read must not advance or mutate the scene.
        failed = payload(await mcp.call_tool("lesson", {"action": "check"}))
        assert failed["error"] == "lesson_check_unavailable"
        assert service.calls == ["get_pattern_list"]

        reset = payload(await mcp.call_tool("lesson", {"action": "reset"}))
        assert reset["status"] == "not_started"

    asyncio.run(scenario())
