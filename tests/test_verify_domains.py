"""Offline/fake acceptance-client tests. Never connects to CLO or imports native API."""

import asyncio
import builtins
import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys

import httpx
from mcp import types
import pytest


SPEC = importlib.util.spec_from_file_location("verify_domains", Path(__file__).parents[1] / "scripts/verify_domains.py")
vd = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = vd
SPEC.loader.exec_module(vd)


def status():
    return dict(session_id="private-session", ready=True, connected=True, closed=False,
                quarantined=False, http_serving=True, executor_verified=True, waiting=0,
                capacity=32, waiters=0, active_id=None, active_state=None, error=None,
                capabilities=sorted(vd.CURRENT_TOOLS - vd.BASE), endpoint="C:/PRIVATE/secret")


def geometry(index, name):
    return dict(index=index, name=name, position_mm=[60, 40], area_mm2=7800,
                bounding_box={"Width": "120mm", "Height": "80mm"})


def tools():
    result = []
    for name in sorted(vd.CURRENT_TOOLS):
        if name == "create_pattern":
            fields = {"points": {"type": "array"}, "name": {"type": "string"},
                      "vertex_types": {"anyOf": [{"type": "array"}, {"type": "null"}]}}
            required = ["points", "name"]
        else:
            required = None
            fields = ({"pattern_index": {"type": "integer"}} if name == "get_pattern_geometry"
                      else {"module": {"type": "string"}, "functions": {"type": "array"}} if name == "describe_clo_api"
                      else {"pattern_index": {"type": "integer"}, "expected_name": {"type": "string"}} if name == "get_pattern_fabric"
                      else {})
        result.append(types.Tool(name=name, inputSchema={
            "type": "object", "properties": fields,
            "required": list(fields) if required is None else required}))
    return types.ListToolsResult(tools=result)


class Fake:
    def __init__(self, fault=None, transform=None, initial=0):
        self.calls = []
        self.fault = fault
        self.transform = transform
        self.pieces = [dict(index=i, name="PRIVATE_NAME_" + str(i)) for i in range(initial)]
        self.mutation_count = 0
        self.listing = tools()

    async def list_tools(self):
        self.calls.append("tools/list")
        return self.inject(self.listing)

    def inject(self, result):
        if len(self.calls) == self.fault:
            raise ConnectionError("C:/PRIVATE secret token")
        return self.transform(self.calls[-1], result, len(self.calls)) if self.transform else result

    async def call_tool(self, name, args):
        self.calls.append(name)
        if name in vd.BASE:
            value = status()
        elif name == "get_pattern_list":
            value = dict(ok=True, pattern_count=len(self.pieces), patterns=copy.deepcopy(self.pieces))
        elif name == "get_pattern_geometry":
            target = self.pieces[args["pattern_index"]]
            value = dict(ok=True, pattern=geometry(target["index"], target["name"]))
        elif name == "create_pattern":
            self.mutation_count += 1
            target = dict(index=len(self.pieces), name=args["name"])
            self.pieces.append(target)
            value = dict(ok=True, verified=True, pattern_count=len(self.pieces),
                          pattern=geometry(target["index"], target["name"]), executor_ms=1.2)
        elif name == "get_fabric_list":
            value = dict(ok=True, fabric_count=1,
                         fabrics=[dict(index=0, name="PRIVATE_FABRIC")])
        elif name == "get_avatars":
            value = dict(ok=True, avatar_count=1,
                          avatars=[dict(index=0, name="PRIVATE_AVATAR")])
        elif name == "get_pattern_fabric":
            target = self.pieces[args["pattern_index"]]
            value = dict(ok=True, pattern_index=target["index"], pattern_name=target["name"],
                         fabric_index=0, fabric_name="PRIVATE_FABRIC")
        elif name == "list_clo_api":
            value = dict(ok=True, modules={m: list(vd.DESCRIPTIONS.get(m, [])) for m in vd.MODULES})
        elif name == "describe_clo_api":
            value = dict(ok=True, module=args["module"],
                         functions={n: dict(available=True, doc="C:/PRIVATE secret") for n in args["functions"]})
        else:
            raise AssertionError("unexpected command")
        return self.inject(types.CallToolResult(structuredContent=value, content=[]))


def run(client=None, mode="run", scenario="scene-inspection", **kwargs):
    client = client or Fake()
    return asyncio.run(vd.Runner(client, kwargs.pop("limits", vd.Limits())).execute(mode, scenario, **kwargs))


def test_dry_run_has_zero_network_import_or_native_and_honest_blockers(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket, "socket", forbidden)
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name.startswith(("mcp", "httpx", "clo3d_mcp")) or name in vd.MODULES:
            raise AssertionError("offline mode must not import MCP/native contracts")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert vd.main(["dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["network_calls"] == report["native_calls"] == 0
    plans = {p["scenario"]: p for p in report["plans"]}
    assert plans["scene-inspection"]["state"] == "completed"
    assert plans["current-pattern-fixture"]["state"] == "blocked"
    assert plans["avatar-import-future"]["asset"] == "missing"
    assert not plans["fabric-assignment-future"]["missing_tools"]
    assert "domain_contract_and_runner_not_integrated" in plans["fabric-assignment-future"]["blockers"]


def test_future_and_permission_failure_before_network(monkeypatch, capsys):
    async def forbidden(*args):
        raise AssertionError("must not open connection")
    monkeypatch.setattr(vd, "online", forbidden)
    for args in (["run"], ["run", "--scenario", "current-pattern-fixture"],
                 ["run", "--scenario", "avatar-import-future", "--allow-mutations"],
                 ["run", "--scenario", "fabric-assignment-future", "--allow-mutations"]):
        assert vd.main(args) == 2
    assert "secret" not in capsys.readouterr().out


def test_discover_is_bounded_read_only_not_native_execution():
    client = Fake()
    report = run(client, "discover", None)
    assert report["state"] == "completed"
    assert set(client.calls) <= {"tools/list", "get_session_info", "transport_status", "list_clo_api", "describe_clo_api"}
    assert client.calls.count("describe_clo_api") == 2
    assert client.mutation_count == 0
    text = vd.report_text(report, 16384)
    assert "PRIVATE" not in text and "private-session" not in text and "secret" not in text
    for step in range(1, len(client.calls) + 1):
        failed = Fake(fault=step)
        observed = run(failed, "discover", None)
        assert observed["state"] == "unknown"
        assert failed.calls == client.calls[:step] and failed.mutation_count == 0


def test_inventory_readonly_runner_and_fault_at_every_step():
    client = Fake()
    report = run(client, scenario="fabric-avatar-inventory")
    assert report["state"] == "verified" and report["rpc_steps"] == 11
    assert report["summary"]["nonempty_fabric_checked"] is True
    assert report["summary"]["nonempty_avatar_checked"] is True
    assert "PRIVATE" not in vd.report_text(report, 16384)
    for step in range(1, len(client.calls) + 1):
        failed = Fake(fault=step)
        observed = run(failed, scenario="fabric-avatar-inventory")
        assert observed["state"] == "unknown"
        assert failed.calls == client.calls[:step] and failed.mutation_count == 0


def test_inventory_runner_changed_list_stops_without_following_calls():
    def transform(name, reply, step):
        if step == 8:
            assert name == "get_fabric_list"
            reply.structuredContent["fabrics"][0]["name"] = "changed"
        return reply
    client = Fake(transform=transform)
    report = run(client, scenario="fabric-avatar-inventory")
    assert report["state"] == "failed" and len(client.calls) == 8
    assert report["code"] == "inventory_changed_between_calls"


@pytest.mark.parametrize("initial", [0, 2, 4])
def test_pattern_fabric_inspection_serial_readonly_fault_at_every_step(initial):
    client = Fake(initial=initial)
    report = run(client, scenario="pattern-fabric-inspection")
    assert report["state"] == "verified" and report["mutation_submissions"] == 0
    assert report["rpc_steps"] == 11 + 4 * initial
    assert report["summary"]["mapping_objects_checked"] == initial
    assert report["summary"]["mapping_passes"] == 2
    assert report["summary"]["nonempty_mapping_checked"] == bool(initial)
    assert "PRIVATE" not in vd.report_text(report, 16384)
    assert set(client.calls) <= {"tools/list", *vd.BASE, "get_pattern_list",
                                  "get_fabric_list", "get_pattern_fabric"}
    for step in range(1, len(client.calls) + 1):
        failed = Fake(initial=initial, fault=step)
        observed = run(failed, scenario="pattern-fabric-inspection")
        assert observed["state"] == "unknown"
        assert failed.calls == client.calls[:step] and failed.mutation_count == 0


@pytest.mark.parametrize("fault,code", [
    ("identity", "fabric_mapping_identity"), ("name", "fabric_mapping_identity"),
    ("fabric", "fabric_mapping_identity"), ("bool", "invalid_command_schema"),
    ("changed", "fabric_mapping_changed"), ("list", "scene_list_changed"),
    ("inventory", "inventory_changed_between_calls"), ("duplicate", "ambiguous_pattern_names"),
    ("session", "session_changed"), ("error", "tool_error"),
])
def test_pattern_fabric_runner_stops_on_mismatch_without_following_call(fault, code):
    seen = {}
    def transform(name, reply, step):
        if name == "tools/list":
            return reply
        seen[name] = seen.get(name, 0) + 1
        value = reply.structuredContent
        if name == "get_pattern_fabric":
            if fault == "identity":
                value["pattern_index"] = 1
            elif fault == "name":
                value["pattern_name"] = "wrong"
            elif fault == "fabric":
                value["fabric_name"] = "wrong"
            elif fault == "bool":
                value["fabric_index"] = True
            elif fault == "error":
                return types.CallToolResult(isError=True, content=[],
                                            structuredContent={"ok": False, "error": "stale_pattern"})
            elif fault == "changed" and seen[name] == 3:
                value.update(fabric_index=1, fabric_name="second")
        if name == "get_pattern_list":
            if fault == "duplicate":
                value["patterns"][1]["name"] = value["patterns"][0]["name"]
            elif fault == "list" and seen[name] == 2:
                value["patterns"][1]["name"] = "changed"
        if name == "get_fabric_list":
            value.update(fabric_count=2, fabrics=[dict(index=0, name="PRIVATE_FABRIC"),
                                                dict(index=1, name="second")])
            if fault == "inventory" and seen[name] == 2:
                value["fabrics"][1]["name"] = "changed"
        if name == "transport_status" and fault == "session":
            value["session_id"] = "changed"
        return reply
    client = Fake(initial=2, transform=transform)
    report = run(client, scenario="pattern-fabric-inspection")
    assert report["code"] == code and client.mutation_count == 0
    assert report["state"] != "verified"
    # No reads or cleanup after the precise failing step.
    assert report["rpc_steps"] == len(client.calls)
    expected_steps = {"duplicate": 4, "session": 3, "changed": 12,
                      "list": 16, "inventory": 18}
    assert len(client.calls) == expected_steps.get(fault, 8)


def test_mapping_runner_requires_live_mapping_schema_and_capability_before_native_reads():
    for fault in ("missing_tool", "schema", "capability"):
        client = Fake(initial=2)
        if fault == "missing_tool":
            client.listing.tools = [t for t in client.listing.tools if t.name != "get_pattern_fabric"]
        elif fault == "schema":
            target = next(t for t in client.listing.tools if t.name == "get_pattern_fabric")
            target.inputSchema["properties"]["expected_name"]["type"] = "integer"
        else:
            def transform(name, result, step):
                if name == "get_session_info":
                    result.structuredContent["capabilities"].remove("get_pattern_fabric")
                return result
            client.transform = transform
        report = run(client, scenario="pattern-fabric-inspection")
        assert report["state"] in ("blocked", "unsupported")
        assert set(client.calls) <= {"tools/list", "get_session_info"}


def test_mapping_runner_bounds_before_mapping_reads_and_without_network(monkeypatch, capsys):
    client = Fake(initial=5)
    assert run(client, scenario="pattern-fabric-inspection")["code"] == "object_bound"
    assert "get_pattern_fabric" not in client.calls
    async def forbidden(*args):
        raise AssertionError("offline preflight must block")
    monkeypatch.setattr(vd, "online", forbidden)
    assert vd.main(["run", "--scenario", "pattern-fabric-inspection", "--max-steps", "27"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "blocked"


@pytest.mark.parametrize("scenario,initial,allowed", [("scene-inspection", 2, False), ("current-pattern-fixture", 0, True)])
def test_success_and_injected_failure_at_every_step_stop_without_cleanup(scenario, initial, allowed):
    success = Fake(initial=initial)
    report = run(success, scenario=scenario, allow_mutations=allowed)
    assert report["state"] == "verified"
    assert "delete_pattern" not in success.calls
    assert not set(success.calls) & {"copy_pattern_with_offset", "move_pattern_relative", "set_pattern_name", "create_test_rectangle"}
    for step in range(1, len(success.calls) + 1):
        client = Fake(fault=step, initial=initial)
        report = run(client, scenario=scenario, allow_mutations=allowed)
        assert report["state"] == "unknown", (step, report)
        assert client.calls == success.calls[:step]
        assert client.mutation_count <= 1
        assert "delete_pattern" not in client.calls


@pytest.mark.parametrize("change,code", [
    ({"ready": False}, "session_not_ready"), ({"quarantined": True}, "session_not_ready"),
    ({"closed": True}, "session_not_ready"), ({"error": "PRIVATE"}, "session_not_ready"),
    ({"waiting": 1}, "unexpected_queue_work"), ({"waiters": 1}, "unexpected_queue_work"),
    ({"active_id": "job_2", "active_state": "dispatched"}, "unexpected_queue_work"),
    ({"session_id": "new-session"}, "session_changed"),
])
def test_each_guard_blocks_before_mutation(change, code):
    for guard_number in (3, 5):
        def transform(name, result, step):
            if step == guard_number:
                result.structuredContent.update(change)
            return result
        client = Fake(transform=transform)
        report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
        assert report["code"] == code
        assert client.mutation_count == 0
        assert len(client.calls) == guard_number


@pytest.mark.parametrize("outcome", ["succeeded", "failed"])
def test_result_before_ready_is_valid_status_but_never_opens_next_guard(outcome):
    from clo3d_mcp.jobs import JobQueue
    from clo3d_mcp.protocol import message

    queue = JobQueue("test-session")
    queue.on_connected()
    queue.on_ready()
    job = queue.submit("get_pattern_count")
    queue.dispatch()
    frame = (message("RESULT", "test-session", job_id=job, result={"pattern_count": 0})
             if outcome == "succeeded" else
             message("ERROR", "test-session", job_id=job, code="command_error"))
    queue.receive(frame)
    snapshot = {**status(), **queue.status()}
    assert snapshot["active_state"] == outcome and not snapshot["ready"]
    vd.status_schema(snapshot)  # RESULT is published before a separate READY releases the slot.

    def transform(name, result, step):
        if step == 3:
            result.structuredContent.update(snapshot, session_id="private-session")
        return result

    client = Fake(transform=transform)
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert report["code"] == "session_not_ready"
    assert client.mutation_count == 0 and len(client.calls) == 3
    queue.on_ready()
    assert queue.status()["active_state"] is None and queue.status()["ready"]


@pytest.mark.parametrize("code,state", [("outcome_unknown", "unknown"), ("scene_change_unverified", "unknown"),
                                        ("api_unavailable", "unsupported"), ("command_error", "failed"),
                                        ("queue_timeout", "failed"), ("SECRET", "failed")])
def test_mutation_errors_stop_no_cleanup_or_replay(code, state):
    def transform(name, result, step):
        if name == "create_pattern":
            return types.CallToolResult(isError=True, structuredContent={"ok": False, "error": code}, content=[])
        return result
    client = Fake(transform=transform)
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert report["state"] == state
    assert client.calls[-1] == "create_pattern" and client.mutation_count == 1
    assert "SECRET" not in vd.report_text(report, 16384)


@pytest.mark.parametrize("command,change", [
    ("create_pattern", {"verified": False}),
    ("create_pattern", {"pattern_count": True}),
    ("get_pattern_geometry", {"pattern": geometry(0, "WRONG")}),
    ("get_pattern_list", {"pattern_count": True}),
    ("get_session_info", {"ready": 1}),
    ("get_session_info", {"capabilities": "create_pattern"}),
])
def test_invalid_schema_or_failed_readback_no_further_calls(command, change):
    def transform(name, result, step):
        if name == command:
            result.structuredContent.update(change)
        return result
    client = Fake(transform=transform)
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert report["state"] in ("failed", "unknown")
    assert client.calls[-1] == command
    assert client.mutation_count <= 1


def test_missing_tools_profile_changed_schema_and_pagination():
    cases = []
    client = Fake()
    client.listing.tools = [t for t in client.listing.tools if t.name != "create_pattern"]
    cases.append((client, "missing_tools"))
    client = Fake()
    client.listing.nextCursor = "PRIVATE"
    cases.append((client, "inventory_not_bounded_profile"))
    client = Fake()
    next(t for t in client.listing.tools if t.name == "create_pattern").inputSchema["properties"]["new"] = {}
    cases.append((client, "tool_schema_changed"))
    def transform(name, result, step):
        if name == "get_session_info":
            result.structuredContent["capabilities"] = []
        return result
    cases.append((Fake(transform=transform), "missing_capabilities"))
    for client, code in cases:
        report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
        assert report["code"] == code
        assert client.mutation_count == 0


def test_unknown_scenario_and_missing_asset_never_calls():
    client = Fake()
    assert run(client, scenario="not-allowed")["state"] == "unsupported"
    assert run(client, scenario="avatar-import-future", allow_mutations=True)["state"] == "blocked"
    assert not client.calls


def test_assets_stat_only_no_content_and_never_print_paths(tmp_path, monkeypatch):
    path = tmp_path / "PRIVATE.avt"
    path.write_bytes(b"chosen fake asset")
    def forbidden(*args, **kwargs):
        raise AssertionError("must not read content")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    report = vd.dry_run("avatar-import-future", True, path)
    assert report["plans"][0]["asset"] == "selected_read_only"
    assert report["plans"][0]["state"] == "blocked"
    assert "PRIVATE" not in vd.report_text(report, 16384)
    assert vd.asset_state(path.with_suffix(".unknown")) == "unsupported_format_pending_contract"
    assert vd.asset_state("\\\\PRIVATE\\share\\avatar.avt") == "local_asset_required"


def test_output_response_report_and_object_bounds():
    def oversized(name, result, step):
        if name == "get_session_info":
            result.structuredContent["PRIVATE"] = "secret" * 4000
        return result
    client = Fake(transform=oversized)
    report = run(client, limits=vd.Limits(response_bytes=16384))
    assert report["code"] == "response_bound" and len(client.calls) == 2
    assert vd.report_text({"x": "secret" * 1000}, 2048).find("secret") == -1
    assert len(vd.report_text({"x": "x" * 3000}, 2048)) <= 2048
    client = Fake(initial=5)
    assert run(client)["code"] == "object_bound"
    assert "get_pattern_geometry" not in client.calls


def test_report_overflow_cli_must_not_return_success(monkeypatch, capsys):
    monkeypatch.setattr(vd, "dry_run", lambda *args: {"state": "completed", "x": "x" * 20000})
    assert vd.main(["dry-run"]) == 1
    assert json.loads(capsys.readouterr().out)["code"] == "report_bound"


def test_clock_total_bound_no_following_call():
    times = iter([0, 0, 100])
    client = Fake()
    runner = vd.Runner(client, clock=lambda: next(times))
    result = asyncio.run(runner.execute("run", "scene-inspection"))
    assert result["code"] == "client_deadline" and client.calls == ["tools/list"]


def test_step_bound_and_invalid_limits():
    client = Fake()
    report = run(client, limits=vd.Limits(steps=1))
    assert report["state"] == "blocked" and not client.calls
    for limits in (vd.Limits(steps=True), vd.Limits(step_seconds=float("nan")), vd.Limits(objects=17)):
        with pytest.raises(vd.Halt):
            limits.validate()


def test_timeout_after_dispatch_no_native_cancel_claim():
    class TimeoutFake(Fake):
        async def call_tool(self, name, args):
            result = await super().call_tool(name, args)
            if name == "create_pattern":
                raise TimeoutError("PRIVATE")
            return result
    client = TimeoutFake()
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert report["state"] == "unknown" and client.mutation_count == 1
    assert client.calls[-1] == "create_pattern"
    assert "not native cancellation" in report["note"]


def test_actual_step_timeout_with_event_no_sleeps_or_following_calls():
    class WaitingFake(Fake):
        async def call_tool(self, name, args):
            result = await super().call_tool(name, args)
            if name == "create_pattern":
                await asyncio.Event().wait()
            return result
    client = WaitingFake()
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True,
                 limits=vd.Limits(step_seconds=.02))
    assert report["state"] == "unknown"
    assert report["scene_may_have_changed"] is True
    assert client.calls[-1] == "create_pattern" and client.mutation_count == 1


@pytest.mark.parametrize("step", [7, 9])
def test_session_change_after_mutation_blocks_all_readback_or_cleanup(step):
    def transform(name, result, index):
        if index == step:
            result.structuredContent["session_id"] = "changed"
        return result
    client = Fake(transform=transform)
    report = run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert report["code"] == "session_changed"
    assert report["scene_may_have_changed"] is True
    assert len(client.calls) == step and client.mutation_count == 1


@pytest.mark.parametrize("invalid", [None, {"ok": False}, {"ok": True}, {"ok": False, "error": "secret"}])
def test_invalid_structured_or_error_envelope_stops(invalid):
    def transform(name, result, step):
        if name == "get_session_info":
            result.structuredContent = invalid
        return result
    client = Fake(transform=transform)
    report = run(client)
    assert report["state"] == "failed" and len(client.calls) == 2
    assert "secret" not in vd.report_text(report, 16384)


def test_cancel_propagates_no_finally_mutation():
    class CancelFake(Fake):
        async def call_tool(self, name, args):
            result = await super().call_tool(name, args)
            if name == "create_pattern":
                raise asyncio.CancelledError()
            return result
    client = CancelFake()
    with pytest.raises(asyncio.CancelledError):
        run(client, scenario="current-pattern-fixture", allow_mutations=True)
    assert client.calls[-1] == "create_pattern" and client.mutation_count == 1


def test_cli_ctrl_c_and_discover_invalid_flags(monkeypatch, capsys):
    async def interrupted(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(vd, "online", interrupted)
    assert vd.main(["run", "--scenario", "scene-inspection"]) == 130
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "unknown"
    assert vd.main(["discover", "--allow-mutations"]) == 2


def test_json_client_initializes_inventory_single_post_no_get_or_delete():
    requests = []
    async def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        if payload["method"] == "initialize":
            result = dict(protocolVersion=types.LATEST_PROTOCOL_VERSION, capabilities={},
                          serverInfo={"name": "fake", "version": "1"})
        else:
            result = tools().model_dump(mode="json", exclude_none=True)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result},
                              headers={"mcp-session-id": "private-http-session"})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = vd.JsonMCPClient(http, vd.Limits())
            runner = vd.Runner(client)
            await runner.rpc("initialize", client.initialize)
            assert len((await client.list_tools()).tools) == 44
    asyncio.run(scenario())
    assert [r.method for r in requests] == ["POST"] * 3
    assert "Mcp-Session-Id" in requests[-1].headers


def test_current_server_generated_inventory_schema_matches_client_without_server_start():
    from clo3d_mcp.transport_server import Service, build_mcp
    # Definition-only FastMCP metadata. No HTTP listener, queue dispatch, pipe,
    # launcher import, process ownership or CLO native calls.
    service = Service("unused", "fake-session", b"k" * 32, 123, None, pattern_package=True)
    async def scenario():
        published = await build_mcp(service).list_tools()
        assert {t.name for t in published} == vd.CURRENT_TOOLS
        for mode, name, allowed in (("discover", None, False),
                                    ("run", "scene-inspection", False),
                                    ("run", "pattern-fabric-inspection", False),
                                    ("run", "current-pattern-fixture", True)):
            client = Fake()
            client.listing = types.ListToolsResult(tools=published)
            result = await vd.Runner(client).execute(mode, name, allowed)
            assert result["state"] in ("completed", "verified"), result
    asyncio.run(scenario())


def test_json_client_official_fastmcp_asgi_handshake_session_protocol_and_tools():
    from clo3d_mcp.transport_server import Service, build_mcp
    # Actual installed SDK ASGI app/lifespan/session manager and JSON responses.
    # ASGITransport invokes this app in-process: NO socket is opened, not even
    # the real CLO endpoint. Service port only configures the Host allowlist.
    service = Service("unused", "fake-clo-session", b"k" * 32, 123, None,
                      port=8765, pattern_package=True)
    service.http_serving = service.executor_verified = service.ready_acknowledged = True
    service.queue.on_connected()
    service.queue.on_ready()
    app = build_mcp(service).streamable_http_app()
    exchanges = []

    async def observe_response(response):
        request = response.request
        exchanges.append((request.method, json.loads(request.content), dict(request.headers),
                          response.status_code, dict(response.headers)))

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), trust_env=False,
                follow_redirects=False, timeout=3,
                event_hooks={"response": [observe_response]},
            ) as http:
                client = vd.JsonMCPClient(http, vd.Limits())
                initialized = await client.initialize()
                assert initialized.serverInfo.name == "CLO session"
                assert initialized.protocolVersion == types.LATEST_PROTOCOL_VERSION
                inventory = await client.list_tools()
                assert {tool.name for tool in inventory.tools} == vd.CURRENT_TOOLS
                info = await client.call_tool("get_session_info", {})
                vd.validate_result("get_session_info", info, {})
                assert info.structuredContent["session_id"] == "fake-clo-session"
                assert info.structuredContent["ready"] is True
                state = await client.call_tool("transport_status", {})
                vd.validate_result("transport_status", state, {})
                assert state.structuredContent["waiting"] == 0
                # Error envelope through official FastMCP too, with dispatch
                # prevented by not-ready. No fake/native queue execution.
                service.executor_verified = False
                failed = await client.call_tool("ping", {})
                assert failed.isError is True
                assert failed.structuredContent == {"ok": False, "error": "executor_unavailable"}
                assert service.queue.status()["waiting"] == 0
                assert service.queue.status()["active_id"] is None

    asyncio.run(asyncio.wait_for(scenario(), 5))
    assert [entry[0] for entry in exchanges] == ["POST"] * 6
    assert [entry[1]["method"] for entry in exchanges] == [
        "initialize", "notifications/initialized", "tools/list",
        "tools/call", "tools/call", "tools/call",
    ]
    session = exchanges[0][4]["mcp-session-id"]
    assert session and session != "fake-clo-session"
    assert exchanges[0][1]["params"]["protocolVersion"] == types.LATEST_PROTOCOL_VERSION
    assert exchanges[0][3] == 200
    notification = exchanges[1]
    assert notification[3] == 202 and "id" not in notification[1]
    for _, _, headers, status_code, response_headers in exchanges[1:]:
        assert headers["mcp-session-id"] == session
        assert headers["mcp-protocol-version"] == types.LATEST_PROTOCOL_VERSION
        if status_code == 200:
            assert response_headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("raw", [
    b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"ok":true,"ok":false}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"value":NaN}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"value":Infinity}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"value":-Infinity}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"value":1e400}}',
    b'{"jsonrpc":"2.0","id":1,"result":{"value":"\xff"}}',
])
def test_json_client_rejects_duplicate_keys_and_nonfinite_before_models_no_retry(raw):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = vd.JsonMCPClient(http, vd.Limits())
            with pytest.raises(vd.Halt) as exc:
                await client.list_tools()
            assert exc.value.code == "invalid_response_json"
    asyncio.run(scenario())
    assert len(requests) == 1


@pytest.mark.parametrize("response,code", [
    (lambda: httpx.Response(200, text="event: message\n", headers={"content-type": "text/event-stream"}), "json_response_profile_required"),
    (lambda: httpx.Response(307, headers={"location": "http://PRIVATE"}), "http_failure"),
    (lambda: httpx.Response(404), "http_failure"),
    (lambda: httpx.Response(200, json={"jsonrpc": "2.0", "id": 999, "result": {}}), "response_id_mismatch"),
    (lambda: httpx.Response(200, text="x" * 2000, headers={"content-type": "application/json"}), "response_bound"),
])
def test_json_client_failure_never_retry_reconnect_or_follow_redirect(response, code):
    calls = []
    def handler(request):
        calls.append(request)
        return response()
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as http:
            client = vd.JsonMCPClient(http, vd.Limits(response_bytes=1024))
            with pytest.raises(vd.Halt) as exc:
                await client.list_tools()
            assert exc.value.code == code
    asyncio.run(scenario())
    assert len(calls) == 1 and calls[0].method == "POST"
