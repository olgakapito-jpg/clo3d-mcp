---
name: transport-verification
description: Test and debug CLO transport changes with deterministic protocol tests, real Windows pipe tests, MCP integration tests and explicit real-CLO acceptance gates.
---

# Transport verification and diagnosis

Read `AGENTS.md` and acceptance criteria in `docs/PYTHON_TRANSPORT_PLAN.md`
from repository root. Load the runtime/pipe/MCP skill relevant to the failure.

## Start with evidence

1. Read git status/diff. Separate user edits from the change under test.
2. Reproduce the smallest failure. Classify it: HTTP/MCP, queue, pipe,
   callback scheduling, CLO API, or process lifecycle.
3. Record session/job IDs and monotonic timing, but never tokens, full payloads
   by default or private scene paths. Keep diagnostics bounded and in memory.
4. State one hypothesis and a distinguishing test. Do not add blind retries,
   longer sleeps or a new architecture to make an intermittent failure disappear.

## Test layers

- Pure unit tests: framing, schema validation, queue transitions, correlation,
  deadlines, cancellation and bounded caches. Inject clock/transport failures.
- Simulated executor tests: responses, delayed completion, errors and disconnect.
- Real Windows pipe tests: actual handles, overlapped I/O, fragmentation,
  reconnect and shutdown. Skip explicitly on unsupported platforms.
- MCP HTTP tests: initialize, list tools, call tools, concurrent requests,
  busy executor with responsive status, occupied port and orderly shutdown.
- Real CLO checks: actual callback/thread, API reads and diagnostic mutation,
  responsive UI, repeat launch, modal UI and process exit. Mocks cannot pass this gate.

For one-shot native probes, require: verified service/idle/thread guards,
one native call budget, a one-shot builtins marker, sanitized JSON with `stage`
and `error_type`, and no retry. If the effect has no getter (drape, simulation,
UI layout), mark evidence visual-only and ask the user to confirm the view; a
camera/zoom miss is not evidence that the object is absent. Probe bugs fixed
before any native entry get a distinct v2 marker, never a reset.

Use synchronization events and bounded timeouts instead of scheduler-dependent
sleeps. Stress runs have a request/time limit and a stop mechanism.

## Failure matrix to cover as implementation grows

- Invalid length/UTF-8/JSON/object shape/version/session/job IDs.
- Disconnect before dispatch, mid-frame, while executing and after execution
  but before result delivery; report unknown outcome honestly.
- Queue full, queued deadline, running deadline, HTTP caller cancellation,
  late result, duplicate known job and new session with old jobs.
- Server restart, occupied port, dead CLO, reused PID, repeated launcher,
  pending read/write cancellation, stale callbacks and callback reentrancy.
- No writes of request/response/heartbeat/discovery files on the new path.
  Test the new path, not the legacy file mock; don't confuse source/venv writes
  or explicitly requested garment exports with IPC.

## Verification commands and reporting

Baseline full suite:
`uv run --frozen --with pytest pytest -q`

Focused tests use explicit new file paths, then run the full suite. Run commands
with timeouts. Do not add unrelated formatter/linter migrations to a bug fix.

For user-run CLO checks provide: script path, start action, expected output,
stop action, duration and failure criteria. Ask for only relevant redacted output.
Do not automate UI clicks or kill CLO just because the test scene is disposable.

Finish with changes, commands actually executed and outcomes, remaining skips,
and whether real-CLO acceptance is pending. Passing fake API handlers establishes
Python contracts, not validity of every real CLO call.
