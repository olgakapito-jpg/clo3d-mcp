---
name: python-mcp-session
description: Build or review this project's official Python FastMCP HTTP server, async tools, bounded job queue, timeout semantics and CLO-bound process lifetime.
---

# Session-scoped Python MCP server

Read `AGENTS.md` and P2/P3 of `docs/PYTHON_TRANSPORT_PLAN.md` from repository root.

## Use the installed SDK, not a similarly named framework

- The baseline uses `mcp.server.fastmcp.FastMCP` in official `mcp` 1.26.0.
  Recheck uv.lock and installed signatures when implementing.
- Do not substitute the independent `fastmcp` package, SDK v2 examples,
  TypeScript, FastAPI or new dependencies without an actual requirement.
- Use Streamable HTTP on loopback for the CLO-launched external process.
  stdio is for client-launched processes, not our target launch sequence.
- One process/worker; no development reload. Queue ownership must not split.
- Use lifespan/startup/shutdown facilities supported by the installed SDK;
  inspect their signatures before coding. Do not create background tasks at import.

## Tool interface

- Publish only explicitly integrated, negotiated tools. Diagnostic MVP and the
  accepted first pattern package are documented in ../../../docs/CLO_MCP_TOOLS.md; the
  full-API roadmap does not enable future domains. Do not advertise legacy tools
  that the new executor cannot handle or load extension files automatically.
- Load clo-mcp-tool-design for descriptions/contracts and clo-tool-workflows
  for composition. Keep metadata, schemas, validators and examples consistent.
- Use async handlers. Await job results without blocking the HTTP event loop;
  no time.sleep or blocking pipe calls in async handlers.
- Describe parameters, units and structured results. Set supported read-only,
  destructive and idempotence annotations truthfully; these are hints, not ACLs.
- Return actionable errors distinguishing queue_full, queue_timeout,
  executor_unavailable, command_error and outcome_unknown.
- Keep health/status available while CLO is busy. A transport ping and an
  executor round trip measure different things; expose that distinction.

## Queue correctness

- Bounded FIFO, initially 32 waiting jobs; only one dispatched/running job.
- Give each job a session_id and job_id. Use monotonic deadlines.
- Track queued/dispatched/running/succeeded/failed/cancelled/unknown transitions.
- Remove cancelled jobs before dispatch. After dispatch, client cancellation
  stops waiting, NOT execution. Keep tracking completion before the next job.
- Do not resend dispatched jobs after timeout, disconnect or command error.
- Deduplicate known IDs using a bounded in-memory result cache. A new process
  loses memory; do not claim exactly-once or replay unknown jobs on reconnect.
- Ready/receipt and completion are different events. Preserve FIFO even when
  HTTP callers disconnect or a late result arrives.

## Lifecycle and local security

- Bind 127.0.0.1 and retain Host/Origin checks. Do not enable wildcard CORS.
  Document the local-user threat model; loopback alone is not authentication.
- Distinguish CLO session identity from MCP HTTP connection/session identity.
- Track a handle to the specific CLO process, not just a reusable PID.
- CLO death ends this MCP; slow callback or modal UI does not imply CLO death.
- A busy port is an error, not permission to kill a process or hijack a service.
- Readiness requires successful executor handshake AND a serving endpoint.
- Shut down queue, pipe and tasks explicitly; release pending callers with
  meaningful errors. Do not leave orphan processes or undrained output pipes.

## Version-specific references

- Inspect `.venv/Lib/site-packages/mcp/server/fastmcp/` for actual behavior.
- Baseline source: https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0
- Protocol: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Recheck the negotiated protocol and relevant docs before relying on features
  absent from installed SDK. Current upstream main may describe another major version.
