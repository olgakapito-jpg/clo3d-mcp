"""Bounded acceptance PREPARATION, not full-domain or real-CLO certification.

dry-run is stdlib-only/offline. discover and run are explicit loopback HTTP
clients. No retries, GET/SSE reconnect, native imports, scene cleanup or files.
Only the JSON-response Streamable HTTP profile of the current server is used.
"""

import argparse
import asyncio
from dataclasses import dataclass
import json
import logging
import math
from pathlib import Path
import time
import uuid


CURRENT_TOOLS = frozenset((
    "get_session_info", "transport_status", "ping", "get_pattern_count",
    "create_test_rectangle", "list_clo_api", "describe_clo_api",
    "get_pattern_list", "get_pattern_geometry", "create_pattern",
    "set_pattern_name", "copy_pattern_with_offset", "move_pattern_relative",
    "delete_pattern", "get_fabric_list", "get_avatars",
    "get_pattern_fabric", "assign_pattern_fabric",
    "get_pattern_outline", "get_pattern_lines",
    "add_seamline_pair", "import_avatar",
))
MODULES = ("pattern_api", "export_api", "fabric_api", "import_api", "utility_api")
DESCRIPTIONS = {
    "fabric_api": ["GetFabricCount", "GetFabricName"],
    "export_api": ["GetCurrentColorwayIndex", "GetAvatarCount", "GetAvatarNameList"],
}
BASE = frozenset(("get_session_info", "transport_status"))
SCENARIOS = {
    "fabric-avatar-inventory": {
        "tools": BASE | {"get_fabric_list", "get_avatars"},
        "mutations": 0, "steps": 12, "dependencies": [],
    },
    "scene-inspection": {
        "tools": BASE | {"get_pattern_list", "get_pattern_geometry"},
        "mutations": 0, "steps": 15, "dependencies": [],
    },
    "pattern-fabric-inspection": {
        "tools": BASE | {"get_pattern_list", "get_fabric_list", "get_pattern_fabric"},
        "mutations": 0, "steps": 28, "dependencies": [],
    },
    "current-pattern-fixture": {
        "tools": BASE | {"get_pattern_list", "get_pattern_geometry", "create_pattern"},
        "mutations": 1, "steps": 11, "dependencies": ["explicit one-piece scene permission"],
    },
    "fabric-assignment-future": {
        "tools": BASE | {"get_fabric_list", "get_pattern_fabric", "assign_pattern_fabric"},
        "mutations": 1, "steps": 12,
        "dependencies": ["mutating client execution recipe and visual acceptance", "chosen unique pattern and fabric",
                         "current-pattern-fixture is optional, never automatic"],
    },
    "avatar-import-future": {
        "tools": BASE | {"get_avatars", "import_avatar"},
        "mutations": 1, "steps": 10,
        "dependencies": ["A0/A1/A3 contracts and integration", "chosen avatar asset and format semantics"],
    },
}
FUTURE = frozenset(("fabric-assignment-future", "avatar-import-future"))
STATES = ("verified", "completed", "unsupported", "blocked", "failed", "unknown")
POINTS = [[0, 0], [120, 0], [100, 80], [0, 60]]
NOTE = "client-only session guard; not atomic; client stop is not native cancellation"


class Halt(Exception):
    def __init__(self, state, code):
        self.state, self.code = state, code
        super().__init__(code)


@dataclass(frozen=True)
class Limits:
    steps: int = 32
    objects: int = 4
    mutations: int = 1
    response_bytes: int = 262144
    report_bytes: int = 16384
    step_seconds: float = 15
    total_seconds: float = 90

    def validate(self):
        for key, low, high in (("steps", 1, 64), ("objects", 1, 16),
                               ("mutations", 0, 1), ("response_bytes", 1024, 1048576),
                               ("report_bytes", 2048, 65536)):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise Halt("blocked", "invalid_limits")
        for key, high in (("step_seconds", 65), ("total_seconds", 300)):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= high:
                raise Halt("blocked", "invalid_limits")


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii")


def bounded(value, maximum):
    try:
        raw = encoded(value)
    except (TypeError, ValueError, RecursionError, OverflowError):
        raise Halt("failed", "invalid_json") from None
    if len(raw) > maximum:
        raise Halt("failed", "response_bound")
    return value


def strict_response_json(raw):
    """Reject ambiguous object keys and non-JSON/non-finite numeric literals."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("nonfinite_number")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite_number")
        return result

    try:
        return json.loads(raw, object_pairs_hook=object_pairs,
                          parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise Halt("failed", "invalid_response_json") from None


def asset_state(asset):
    """Only stat the explicit path; no scan, read, import, upload or copying."""
    if asset is None:
        return "missing"
    try:
        if str(asset).startswith(("\\\\", "//")) or "://" in str(asset):
            return "local_asset_required"
        path = Path(asset)
        if path.suffix.lower() not in (".avt", ".avac"):
            return "unsupported_format_pending_contract"
        if not path.is_file():
            return "missing"
        return "selected_read_only" if 0 < path.stat().st_size <= 268435456 else "size_bound"
    except (OSError, ValueError):
        return "unavailable"


def dry_run(scenario=None, allow_mutations=False, asset=None, limits=Limits()):
    limits.validate()
    plans = []
    for name in ([scenario] if scenario else SCENARIOS):
        if name not in SCENARIOS:
            raise Halt("unsupported", "scenario_not_whitelisted")
        plan = SCENARIOS[name]
        blockers = []
        missing = sorted(plan["tools"] - CURRENT_TOOLS)
        if missing:
            blockers.append("missing_current_tools")
        if name in FUTURE:
            blockers.append("domain_contract_and_runner_not_integrated")
        if plan["mutations"] and not allow_mutations:
            blockers.append("explicit_mutation_permission_required")
        steps = 7 + 2 * limits.objects if name == "scene-inspection" else plan["steps"]
        if name == "pattern-fabric-inspection":
            steps = 12 + 4 * limits.objects  # includes online initialize
        if steps > limits.steps or plan["mutations"] > limits.mutations:
            blockers.append("plan_exceeds_limits")
        selected = asset_state(asset) if name == "avatar-import-future" else "not_required"
        if name == "avatar-import-future" and selected != "selected_read_only":
            blockers.append("asset_not_ready")
        plans.append({"scenario": name, "state": "blocked" if blockers else "completed",
                      "blockers": blockers, "required_tools": sorted(plan["tools"]),
                      "missing_tools": missing, "dependencies": plan["dependencies"],
                      "asset": selected, "max_mutations": plan["mutations"],
                      "max_rpc_steps": steps})
    return {"mode": "dry-run", "state": "completed", "network_calls": 0,
            "native_calls": 0, "plans": plans, "note": NOTE,
            "target_build": "CLO2026.1.336 (not runtime-verified)"}


def status_schema(value, info=False):
    booleans = ("ready", "connected", "closed", "quarantined", "http_serving", "executor_verified")
    if (not isinstance(value, dict)
            or not isinstance(value.get("session_id"), str)
            or not 1 <= len(value["session_id"]) <= 128
            or any(type(value.get(key)) is not bool for key in booleans)
            or any(type(value.get(key)) is not int or value[key] < 0
                   for key in ("waiting", "capacity", "waiters"))
            or not 1 <= value["capacity"] <= 1024
            or "active_id" not in value or "active_state" not in value or "error" not in value
            or (value["active_id"] is not None and not isinstance(value["active_id"], str))
            or value["active_state"] not in (None, "dispatched", "running", "unknown", "succeeded", "failed")
            or (value["error"] is not None and not isinstance(value["error"], str))):
        raise Halt("failed", "invalid_status_schema")
    if info and (not isinstance(value.get("capabilities"), list)
                 or len(value["capabilities"]) > 64
                 or any(not isinstance(v, str) or len(v) > 128 for v in value["capabilities"])
                 or len(set(value["capabilities"])) != len(value["capabilities"])):
        raise Halt("failed", "invalid_capabilities_schema")


def validate_result(command, reply, params):
    """Validate structured success AND error, including command-specific invariants."""
    value = reply.structuredContent
    if not isinstance(value, dict) or type(reply.isError) is not bool:
        raise Halt("failed", "invalid_tool_result")
    if reply.isError or value.get("ok") is False:
        if (reply.isError is not True or value.get("ok") is not False
                or not isinstance(value.get("error"), str)):
            raise Halt("failed", "invalid_error_schema")
        code = value["error"]
        if code in ("outcome_unknown", "scene_change_unverified") or value.get("scene_may_have_changed") is True:
            raise Halt("unknown", "scene_outcome_unverified")
        if code == "api_unavailable":
            raise Halt("unsupported", "api_unavailable")
        raise Halt("failed", "tool_error")  # never echo untrusted server text
    if command in ("get_session_info", "transport_status"):
        status_schema(value, command == "get_session_info")
        return value
    if value.get("ok") is not True:
        raise Halt("failed", "missing_ok")
    # Existing stdlib contract, not a legacy listener or native module import.
    from clo3d_mcp.pattern_contract import CommandError, validate_result as pattern_result
    try:
        pattern_result(command, {key: v for key, v in value.items() if key != "ok"})
    except CommandError:
        # A setter result without verified cannot open a dependent gate.
        if command == "create_pattern" and value.get("verified") is not True:
            raise Halt("unknown", "mutation_not_verified") from None
        raise Halt("failed", "invalid_command_schema") from None
    if command == "describe_clo_api":
        if (value["module"] != params["module"] or set(value["functions"]) != set(params["functions"])
                or any(len(v["doc"]) > 8192 for v in value["functions"].values())):
            raise Halt("failed", "description_mismatch")
    return value


class Runner:
    def __init__(self, client, limits=Limits(), clock=time.monotonic):
        limits.validate()
        self.client, self.limits, self.clock = client, limits, clock
        self.started = clock()
        self.identity = None
        self.steps = []
        self.mutations = 0
        self.run_id = uuid.uuid4().hex
        self.summary = {}

    async def rpc(self, label, request):
        remaining = self.limits.total_seconds - (self.clock() - self.started)
        if remaining <= 0 or len(self.steps) >= self.limits.steps:
            raise Halt("blocked", "run_bound")
        self.steps.append({"step": label, "state": "unknown"})
        try:
            value = await asyncio.wait_for(request(), min(self.limits.step_seconds, remaining))
            if self.clock() - self.started > self.limits.total_seconds:
                raise Halt("unknown", "client_deadline")
            wire = value.model_dump(mode="json", by_alias=True, exclude_none=True)
            bounded(wire, self.limits.response_bytes)
            self.steps[-1]["state"] = "completed"
            return value
        except Halt:
            raise
        except (TimeoutError, ConnectionError, OSError):
            raise Halt("unknown", "timeout_or_disconnect") from None
        except Exception:
            raise Halt("unknown", "client_or_protocol_error") from None

    async def call(self, command, params=None, mutation=False):
        if command not in CURRENT_TOOLS:
            raise Halt("unsupported", "tool_not_whitelisted")
        params = {} if params is None else params
        if command not in BASE:
            from clo3d_mcp.pattern_contract import CommandError, validate_params
            try:
                validate_params(command, params)
            except CommandError:
                raise Halt("blocked", "invalid_plan_parameters") from None
        if mutation:
            if self.mutations >= self.limits.mutations:
                raise Halt("blocked", "mutation_bound")
            self.mutations += 1  # attempted submission; never interpreted as proven effect
        reply = await self.rpc(command, lambda: self.client.call_tool(command, params))
        result = validate_result(command, reply, params)
        self.steps[-1]["state"] = "verified"
        return result

    async def guard(self, initial=False):
        value = await self.call("get_session_info" if initial else "transport_status")
        if self.identity is None:
            self.identity = value["session_id"]
        elif value["session_id"] != self.identity:
            raise Halt("blocked", "session_changed")
        if (not value["ready"] or not value["connected"] or value["closed"]
                or value["quarantined"] or not value["http_serving"]
                or not value["executor_verified"] or value["error"]):
            raise Halt("blocked", "session_not_ready")
        if value["waiting"] or value["waiters"] or value["active_id"] is not None or value["active_state"] is not None:
            raise Halt("blocked", "unexpected_queue_work")
        return value

    async def inventory(self, required):
        listing = await self.rpc("tools/list", self.client.list_tools)
        if listing.nextCursor is not None or len(listing.tools) > 64:
            raise Halt("unsupported", "inventory_not_bounded_profile")
        tools = {tool.name: tool for tool in listing.tools}
        if len(tools) != len(listing.tools):
            raise Halt("failed", "duplicate_tool_name")
        missing = required - tools.keys()
        self.summary["current_tools_present"] = sorted(CURRENT_TOOLS & tools.keys())
        self.summary["missing_required_tools"] = sorted(missing)
        self.summary["extra_tool_count"] = len(tools.keys() - CURRENT_TOOLS)
        if missing:
            raise Halt("blocked", "missing_tools")
        for name in required:
            schema = tools[name].inputSchema
            if (not isinstance(schema, dict) or schema.get("type") != "object"
                    or not isinstance(schema.get("properties", {}), dict)):
                raise Halt("failed", "invalid_tool_schema")
            expected = {"pattern_index"} if name == "get_pattern_geometry" else set()
            if name == "create_pattern":
                expected = {"points", "name", "vertex_types"}
            if name == "describe_clo_api":
                expected = {"module", "functions"}
            if name == "get_pattern_fabric":
                expected = {"pattern_index", "expected_name"}
            required_props = expected - ({"vertex_types"} if name == "create_pattern" else set())
            if set(schema.get("properties", {})) != expected or set(schema.get("required", [])) != required_props:
                raise Halt("unsupported", "tool_schema_changed")
            expected_types = {"pattern_index": "integer", "points": "array", "name": "string",
                              "module": "string", "functions": "array", "expected_name": "string",
                              "vertex_types": "array"}
            def matches_type(prop, expected_type):
                if prop.get("type") == expected_type:
                    return True
                return (expected_type == "array"
                        and any(option.get("type") == "array" for option in prop.get("anyOf", [])))

            if any(not isinstance(schema["properties"][key], dict)
                   or not matches_type(schema["properties"][key], expected_types[key])
                   for key in expected):
                raise Halt("unsupported", "tool_schema_changed")

    async def inspect(self):
        await self.guard()
        before = await self.call("get_pattern_list")
        patterns = before["patterns"]
        self.summary["pattern_count"] = before["pattern_count"]
        if len(patterns) > self.limits.objects:
            raise Halt("blocked", "object_bound")
        for target in patterns:
            await self.guard()
            observed = (await self.call("get_pattern_geometry", {"pattern_index": target["index"]}))["pattern"]
            if observed["index"] != target["index"] or observed["name"] != target["name"]:
                raise Halt("failed", "stale_scene_read")
        await self.guard()
        after = await self.call("get_pattern_list")
        if before != after:
            raise Halt("failed", "scene_list_changed")
        self.summary["geometry_objects_checked"] = len(patterns)
        return before

    async def fixture(self):
        await self.guard()
        before = await self.call("get_pattern_list")
        if before["pattern_count"] >= min(256, self.limits.objects):
            raise Halt("blocked", "object_bound")
        name = "domain_fixture_" + self.run_id[:12]
        if any(p["name"] == name for p in before["patterns"]):
            raise Halt("blocked", "fixture_name_collision")
        await self.guard()  # client-only TOCTOU guard, not server-side fencing
        result = await self.call("create_pattern", {"points": POINTS, "name": name}, mutation=True)
        target = result["pattern"]
        if (result["pattern_count"] != before["pattern_count"] + 1
                or target["name"] != name
                or not math.isclose(target["area_mm2"], 7800, rel_tol=1e-5, abs_tol=.05)):
            raise Halt("unknown", "fixture_result_mismatch")
        await self.guard()
        observed = (await self.call("get_pattern_geometry", {"pattern_index": target["index"]}))["pattern"]
        if (observed["index"] != target["index"] or observed["name"] != name
                or not math.isclose(observed["area_mm2"], 7800, rel_tol=1e-5, abs_tol=.05)
                or any(not math.isclose(a, b, rel_tol=1e-5, abs_tol=.05)
                       for a, b in zip(observed["position_mm"], target["position_mm"]))):
            raise Halt("unknown", "fixture_readback_mismatch")
        await self.guard()
        after = await self.call("get_pattern_list")
        if (after["pattern_count"] != before["pattern_count"] + 1
                or [p for p in after["patterns"] if p["index"] != target["index"]] != before["patterns"]
                or after["patterns"][target["index"]]["name"] != name):
            raise Halt("unknown", "fixture_scene_list_mismatch")
        self.summary.update(fixture_left_in_scene=True, fixture_index=target["index"])

    async def inventories(self):
        before = {}
        for command in ("get_fabric_list", "get_avatars"):
            await self.guard()
            before[command] = await self.call(command)
        for command in ("get_fabric_list", "get_avatars"):
            await self.guard()
            if await self.call(command) != before[command]:
                raise Halt("failed", "inventory_changed_between_calls")
        await self.guard()
        self.summary.update(
            fabric_count=before["get_fabric_list"]["fabric_count"],
            avatar_count=before["get_avatars"]["avatar_count"],
            nonempty_fabric_checked=bool(before["get_fabric_list"]["fabric_count"]),
            nonempty_avatar_checked=bool(before["get_avatars"]["avatar_count"]),
        )

    async def pattern_fabrics(self):
        """Two serial mapping passes, bounded targets; no assignment or cleanup."""
        await self.guard()
        patterns = await self.call("get_pattern_list")
        if patterns["pattern_count"] > self.limits.objects:
            raise Halt("blocked", "object_bound")
        names = [p["name"] for p in patterns["patterns"]]
        if len(set(names)) != len(names):
            raise Halt("blocked", "ambiguous_pattern_names")
        await self.guard()
        fabrics = await self.call("get_fabric_list")
        baseline = []
        for cycle in range(2):
            observed = []
            for target in patterns["patterns"]:
                await self.guard()
                value = await self.call("get_pattern_fabric", {
                    "pattern_index": target["index"], "expected_name": target["name"]})
                f = value["fabric_index"]
                if (value["pattern_index"] != target["index"]
                        or value["pattern_name"] != target["name"]
                        or f >= fabrics["fabric_count"]
                        or value["fabric_name"] != fabrics["fabrics"][f]["name"]):
                    raise Halt("failed", "fabric_mapping_identity")
                if cycle == 1 and value != baseline[len(observed)]:
                    raise Halt("failed", "fabric_mapping_changed")
                observed.append(value)
            if cycle == 0:
                baseline = observed
            elif observed != baseline:
                raise Halt("failed", "fabric_mapping_changed")
        await self.guard()
        if await self.call("get_pattern_list") != patterns:
            raise Halt("failed", "scene_list_changed")
        await self.guard()
        if await self.call("get_fabric_list") != fabrics:
            raise Halt("failed", "inventory_changed_between_calls")
        await self.guard()
        self.summary.update(pattern_count=patterns["pattern_count"],
                            fabric_count=fabrics["fabric_count"],
                            mapping_objects_checked=len(baseline), mapping_passes=2,
                            nonempty_mapping_checked=bool(baseline))

    async def execute(self, mode, scenario=None, allow_mutations=False, asset=None):
        state, code = "failed", "invalid_mode"
        try:
            if mode not in ("discover", "run"):
                raise Halt("unsupported", "invalid_mode")
            if mode == "run":
                prep = dry_run(scenario, allow_mutations, asset, self.limits)
                if scenario is None:
                    raise Halt("blocked", "explicit_scenario_required")
                self.summary["plan"] = prep["plans"][0]
                if prep["plans"][0]["state"] == "blocked":
                    raise Halt("blocked", "plan_dependencies")
            required = (BASE | {"list_clo_api", "describe_clo_api"}
                        if mode == "discover" else SCENARIOS[scenario]["tools"])
            await self.inventory(required)
            info = await self.guard(initial=True)
            self.summary["profile_commands"] = sorted(set(info["capabilities"]) & CURRENT_TOOLS)
            if not (required - BASE) <= set(info["capabilities"]):
                raise Halt("blocked", "missing_capabilities")
            if mode == "discover":
                await self.guard()
                listing = await self.call("list_clo_api")
                self.summary["module_callable_counts"] = {m: len(v) for m, v in listing["modules"].items()}
                for module, functions in DESCRIPTIONS.items():
                    await self.guard()
                    docs = await self.call("describe_clo_api", {"module": module, "functions": functions})
                    self.summary[module] = {name: {"available": d["available"], "doc_chars": len(d["doc"])}
                                            for name, d in docs["functions"].items()}
                state, code = "completed", "discovery_is_not_native_acceptance"
            elif scenario == "fabric-avatar-inventory":
                await self.inventories()
                state, code = "verified", "bounded_inventory_observations_only"
            elif scenario == "scene-inspection":
                await self.inspect()
                state, code = "verified", "bounded_scene_observations_only"
            elif scenario == "pattern-fabric-inspection":
                await self.pattern_fabrics()
                state, code = "verified", "bounded_fabric_mapping_observations_only"
            else:
                await self.fixture()
                state, code = "verified", "one_fixture_readback_only"
        except Halt as exc:
            state, code = exc.state, exc.code
            if self.steps:
                self.steps[-1]["state"] = state
        except asyncio.CancelledError:
            raise  # outer client closes resources, never cancels CLO or resumes
        except Exception:
            state, code = "unknown", "client_or_schema_error"
        return {"mode": mode, "scenario": scenario, "run_id": self.run_id,
                "state": state, "code": code, "rpc_steps": len(self.steps),
                "mutation_submissions": self.mutations, "steps": self.steps,
                "scene_may_have_changed": self.mutations > 0 and state != "verified",
                "summary": self.summary, "note": NOTE,
                "session_observed": self.identity is not None,
                "target_build": "CLO2026.1.336 (not runtime-verified)"}


class JsonMCPClient:
    """POST-only JSON Streamable HTTP; official MCP result models, no SSE/resume.

    The SDK's convenience streamable_http_client reconnects GET/SSE internally.
    This small client deliberately rejects SSE, never opens GET, never resends
    POST, does not follow redirects, and bounds bytes BEFORE parsing responses.
    It is external acceptance tooling, not a replacement server/IPC transport.
    """

    def __init__(self, http, limits):
        self.http, self.limits = http, limits
        self.sequence = 0
        self.headers = {"Accept": "application/json, text/event-stream"}

    async def request(self, method, params=None, notification=False):
        from mcp import types
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        if not notification:
            self.sequence += 1
            payload["id"] = self.sequence
        async with self.http.stream("POST", "http://127.0.0.1:8765/mcp", json=payload,
                                    headers=self.headers) as response:
            if notification:
                if response.status_code != 202:
                    raise Halt("unknown", "notification_rejected")
                return None
            if response.status_code != 200:
                raise Halt("unknown", "http_failure")
            if not response.headers.get("content-type", "").lower().startswith("application/json"):
                raise Halt("unsupported", "json_response_profile_required")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw) + len(chunk) > self.limits.response_bytes:
                    raise Halt("failed", "response_bound")
                raw.extend(chunk)
            envelope = types.JSONRPCResponse.model_validate(strict_response_json(bytes(raw)))
            if type(envelope.id) is not int or envelope.id != self.sequence:
                raise Halt("failed", "response_id_mismatch")
            if method == "initialize":
                session = response.headers.get("mcp-session-id")
                if not session or len(session) > 256 or not session.isascii() or not session.isprintable():
                    raise Halt("failed", "invalid_http_session")
                self.headers["Mcp-Session-Id"] = session
            return envelope.result

    async def initialize(self):
        from mcp import types
        result = types.InitializeResult.model_validate(await self.request("initialize", {
            "protocolVersion": types.LATEST_PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "clo-domain-acceptance-prep", "version": "1"},
        }))
        if result.protocolVersion != types.LATEST_PROTOCOL_VERSION:
            raise Halt("unsupported", "protocol_version_changed")
        self.headers["MCP-Protocol-Version"] = result.protocolVersion
        await self.request("notifications/initialized", notification=True)
        return result

    async def list_tools(self):
        from mcp import types
        return types.ListToolsResult.model_validate(await self.request("tools/list"))

    async def call_tool(self, name, arguments):
        from mcp import types
        return types.CallToolResult.model_validate(await self.request("tools/call", {"name": name, "arguments": arguments}))


def report_text(report, maximum):
    """Reports contain only generated IDs, fixed labels, counts, never payloads."""
    text = encoded(report)
    if len(text) > maximum:
        text = encoded({"state": "failed", "code": "report_bound", "note": NOTE})
    return text.decode("ascii")


async def online(args, limits):
    # Imports/network are unreachable in dry-run. No external authentication,
    # proxy environment, retries, redirects, auto GET or session DELETE.
    import httpx
    async with httpx.AsyncClient(timeout=limits.step_seconds, trust_env=False,
                                 follow_redirects=False,
                                 transport=httpx.AsyncHTTPTransport(retries=0)) as http:
        client = JsonMCPClient(http, limits)
        runner = Runner(client, limits)
        await runner.rpc("initialize", client.initialize)
        return await runner.execute(args.mode, args.scenario, args.allow_mutations, args.avatar_asset)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dry-run", "discover", "run"))
    parser.add_argument("--scenario", choices=tuple(SCENARIOS))
    parser.add_argument("--allow-mutations", action="store_true")
    parser.add_argument("--avatar-asset", help="explicit existing local .avt/.avac; read-only stat only")
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument("--max-objects", type=int, default=4)
    parser.add_argument("--step-seconds", type=float, default=15)
    parser.add_argument("--total-seconds", type=float, default=90)
    args = parser.parse_args(argv)
    limits = Limits(steps=args.max_steps, objects=args.max_objects,
                    step_seconds=args.step_seconds, total_seconds=args.total_seconds)
    # SDK/http logs can contain payloads/headers: stdout is the only report.
    logging.disable(logging.CRITICAL)
    try:
        limits.validate()
        if args.mode == "dry-run":
            result = dry_run(args.scenario, args.allow_mutations, args.avatar_asset, limits)
        else:
            if args.mode == "discover" and (args.scenario or args.allow_mutations or args.avatar_asset):
                raise Halt("blocked", "discover_does_not_accept_scene_plan")
            if args.mode == "run":
                prep = dry_run(args.scenario, args.allow_mutations, args.avatar_asset, limits)
                if args.scenario is None or prep["plans"][0]["state"] == "blocked":
                    result = {"state": "blocked", "code": "plan_dependencies", "preparation": prep}
                    text = report_text(result, limits.report_bytes)
                    print(text, flush=True)
                    return 1 if json.loads(text)["state"] == "failed" else 2
            result = asyncio.run(asyncio.wait_for(online(args, limits), limits.total_seconds))
    except KeyboardInterrupt:
        result = {"state": "unknown", "code": "client_interrupted", "note": NOTE}
        print(report_text(result, limits.report_bytes), flush=True)
        return 130
    except Halt as exc:
        result = {"state": exc.state, "code": exc.code, "note": NOTE}
    except Exception:
        result = {"state": "unknown", "code": "client_failure", "note": NOTE}
    text = report_text(result, limits.report_bytes)
    print(text, flush=True)
    state = json.loads(text)["state"]
    return 0 if state in ("completed", "verified") else 2 if state in ("blocked", "unsupported") else 1


if __name__ == "__main__":
    raise SystemExit(main())
