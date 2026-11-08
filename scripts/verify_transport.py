"""Bounded read-only real-CLO checks through official MCP HTTP; never retries.

Run externally from repository root with uv, NOT inside CLO Script Editor.
No exports, filesystem IPC, log files, scene mutation or process termination.
"""

import argparse
import asyncio
from collections import deque
import json
import math
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def data(reply):
    value = reply.structuredContent
    if reply.isError or not isinstance(value, dict) or value.get("ok") is False:
        code = value.get("error", "invalid_result") if isinstance(value, dict) else "invalid_result"
        raise RuntimeError("MCP check failed: " + str(code))
    return value


async def check(args):
    started = time.monotonic()
    samples = deque(maxlen=1000)
    completed = 0
    pattern_count = None
    async with streamable_http_client("http://127.0.0.1:8765/mcp") as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            identity = data(await client.call_tool("get_session_info"))
            if not identity.get("ready"):
                raise RuntimeError("Executor not ready; start CLO launcher first")
            session_id = identity["session_id"]
            print("START " + json.dumps({"mode": args.mode, "session_id": session_id,
                                        "server_pid": identity["server_pid"], "clo_pid": identity["clo_pid"]}), flush=True)

            async def request(index):
                nonlocal completed, pattern_count
                then = time.monotonic()
                command = "ping" if index % 2 else "get_pattern_count"
                reply = data(await asyncio.wait_for(client.call_tool(command), 65))
                if command == "ping" and reply != {"ok": True, "pong": True}:
                    raise RuntimeError("Invalid ping result")
                if command == "get_pattern_count":
                    count = reply.get("pattern_count")
                    if type(count) is not int or count < 0:
                        raise RuntimeError("Invalid pattern count")
                    pattern_count = count
                samples.append((time.monotonic() - then) * 1000)
                completed += 1

            async def status():
                result = data(await asyncio.wait_for(client.call_tool("transport_status"), 5))
                if (result.get("session_id") != session_id or not result.get("ready")
                        or result.get("quarantined") or result.get("error")):
                    raise RuntimeError("Session changed or executor unavailable; no automatic retry")
                print("PROGRESS " + json.dumps({"completed": completed,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "pattern_count": pattern_count, "waiting": result["waiting"],
                    "cached": result["cached"]}), flush=True)

            if args.mode == "load":
                # 1000 total calls; ten concurrent, below FIFO capacity32.
                for start in range(0, 1000, 10):
                    await asyncio.gather(*(request(i) for i in range(start, start + 10)))
                    if completed % 100 == 0:
                        await status()
            else:
                # 30 wall-clock minutes; at most 360 reads/pings, no catch-up burst
                # after modal UI delays. Entire command also has a hard deadline.
                deadline = time.monotonic() + 1800
                next_report = time.monotonic() + 60
                for index in range(360):
                    if time.monotonic() >= deadline:
                        break
                    await request(index)
                    if time.monotonic() >= next_report:
                        await status()
                        next_report = time.monotonic() + 60
                    remaining = deadline - time.monotonic()
                    if remaining > 0:
                        await asyncio.sleep(min(5, remaining))
            await status()
    ordered = sorted(samples)
    print("PASS " + json.dumps({"mode": args.mode, "completed": completed,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "sample_count": len(ordered), "latency_max_ms": round(max(ordered), 2),
        "latency_p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2)}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("load", "soak"))
    args = parser.parse_args()

    async def bounded():
        await asyncio.wait_for(check(args), 900 if args.mode == "load" else 1900)

    try:
        asyncio.run(bounded())
    except KeyboardInterrupt:
        print("STOPPED by user; any dispatched read may still complete", flush=True)
        return 130
    except Exception as exc:
        # Local SDK errors may contain scene/server text: print only type.
        print("FAIL %s; no automatic retry; inspect transport_status" % type(exc).__name__, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
