"""Real-CLO first package acceptance. External client, no files or retries.

inspect: read-only method inventory. smoke: one create/name/copy/move/delete
scenario. load: ten bounded copy/move/name/delete cycles. Does not reset the
scene or delete unrelated pieces. On ANY error stops without cleanup/replay:
a dispatched command may have changed the scene. Ctrl+C stops only the client.
"""

import argparse
import asyncio
import json
import math
import time
import uuid

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


REQUIRED = ["GetPatternCount", "GetPatternPieceName", "GetPatternPiecePos", "GetPatternPieceArea",
            "GetBoundingBoxOfPattern", "CreatePatternWithPoints", "SetPatternPieceName",
            "CopyPatternPieceMove", "SetPatternPieceMove", "DeletePatternPiece"]
POINTS = [[0, 0], [120, 0], [100, 80], [0, 60]]


def data(reply):
    value = reply.structuredContent
    if reply.isError or not isinstance(value, dict) or value.get("ok") is False:
        raise RuntimeError("Command failed; no automatic retry or cleanup")
    return value


async def scenario(client, mode, report=print):
    identity = data(await client.call_tool("get_session_info"))
    if not identity.get("ready") or "create_pattern" not in identity.get("capabilities", []):
        raise RuntimeError("Restart CLO and run updated launcher first")
    session_id = identity["session_id"]
    docs = data(await client.call_tool("describe_clo_api", {"module": "pattern_api", "functions": REQUIRED}))
    report("API " + json.dumps(docs, ensure_ascii=True), flush=True)
    if not all(docs["functions"][n]["available"] for n in REQUIRED):
        raise RuntimeError("Required native methods unavailable")
    before = data(await client.call_tool("get_pattern_list"))
    # Read existing geometry first, when available. Empty-scene create remains
    # an explicit native compatibility gate, not a guarantee inferred from docs.
    if before["patterns"]:
        value = data(await client.call_tool("get_pattern_geometry", {"pattern_index": 0}))
        report("GEOMETRY " + json.dumps(value, ensure_ascii=True), flush=True)
    if mode == "inspect":
        report("PASS inspect; methods present is not mutation acceptance", flush=True)
        return
    if before["pattern_count"] > 254:
        raise RuntimeError("Need room for two diagnostic pieces within limit256")
    prefix = "mcp_test_" + uuid.uuid4().hex[:10]
    report("START " + json.dumps({"mode": mode, "session_id": session_id, "prefix": prefix,
                                  "cycles": 1 if mode == "smoke" else 10}), flush=True)
    latencies, executor = [], []

    async def call(command, params):
        # A changed/restarted session must never receive the remaining mutations.
        status = data(await client.call_tool("transport_status"))
        if (status["session_id"] != session_id or not status["ready"]
                or status["quarantined"] or status.get("error")):
            raise RuntimeError("Session unavailable or changed")
        then = time.monotonic()
        value = data(await client.call_tool(command, params))
        latencies.append((time.monotonic() - then) * 1000)
        if "executor_ms" in value:
            executor.append(value["executor_ms"])
        report("STEP " + json.dumps({"command": command, "verified": value.get("verified"),
                                      "pattern_count": value.get("pattern_count")}), flush=True)
        return value

    base_name = prefix + "_source"
    created = await call("create_pattern", {"points": POINTS, "name": base_name})
    base = created["pattern"]
    # Independent post-command read through another queued round trip.
    observed = await call("get_pattern_geometry", {"pattern_index": base["index"]})
    if not math.isclose(observed["pattern"]["area_mm2"], 7800.0, abs_tol=0.05):
        raise RuntimeError("Area mismatch")
    for cycle in range(1 if mode == "smoke" else 10):
        copy_name = prefix + "_copy_%d" % cycle
        copied = await call("copy_pattern_with_offset", {"pattern_index": base["index"],
            "expected_name": base_name, "name": copy_name, "dx": 250, "dy": 30})
        piece = copied["pattern"]
        moved = await call("move_pattern_relative", {"pattern_index": piece["index"],
            "expected_name": copy_name, "dx": -15, "dy": 20})
        expected = [a + b for a, b in zip(base["position_mm"], (235, 50))]
        if not all(math.isclose(a, b, abs_tol=0.05) for a, b in zip(expected, moved["pattern"]["position_mm"])):
            raise RuntimeError("Displacement mismatch")
        final_name = copy_name + "_renamed"
        await call("set_pattern_name", {"pattern_index": piece["index"],
                   "expected_name": copy_name, "name": final_name})
        observed = await call("get_pattern_geometry", {"pattern_index": piece["index"]})
        if observed["pattern"]["name"] != final_name:
            raise RuntimeError("Rename mismatch")
        await call("delete_pattern", {"pattern_index": piece["index"], "expected_name": final_name})
        current = await call("get_pattern_list", {})
        source = [v for v in current["patterns"] if v["name"] == base_name]
        if len(source) != 1:
            raise RuntimeError("Source identity changed")
        base["index"] = source[0]["index"]
    await call("delete_pattern", {"pattern_index": base["index"], "expected_name": base_name})
    after = await call("get_pattern_list", {})
    if after["patterns"] != before["patterns"] or after["pattern_count"] != before["pattern_count"]:
        raise RuntimeError("Remaining scene list differs; inspect manually")
    ordered = sorted(latencies)
    report("PASS " + json.dumps({"mode": mode, "calls": len(ordered),
        "latency_p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
        "latency_max_ms": round(max(ordered), 2),
        "executor_max_ms": max(executor), "scene_list_restored": True,
        "note": "executor includes preflight/setter/readback; UI responsiveness requires user confirmation"}), flush=True)


async def check(mode):
    async with streamable_http_client("http://127.0.0.1:8765/mcp") as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            await scenario(client, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "smoke", "load"))
    args = parser.parse_args()
    try:
        asyncio.run(asyncio.wait_for(check(args.mode), 180 if args.mode == "load" else 60))
    except KeyboardInterrupt:
        print("STOPPED; dispatched work may still finish. No retry/automatic cleanup.", flush=True)
        return 130
    except Exception as exc:
        print("FAIL %s; scene may have changed. Inspect list/status, do not replay." % type(exc).__name__, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
