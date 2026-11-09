# CLO MCP: project instructions

## Goal and approval boundary

- Communicate with the user in Russian; keep code identifiers in English.
- Read `docs/PYTHON_TRANSPORT_PLAN.md` before changing transport architecture.
  It is a proposed plan, not approval to implement every phase.
- Target: Windows, one CLO session; a `.py` launched inside CLO starts an
  external Python MCP process. Queue in MCP, Named Pipe IPC, no IPC files.
- Use Python, not a custom C++ plugin. Do not introduce C++, UI automation,
  a different transport, SDK migration or Pattern Engine without agreement.
- The CLO scene is explicitly disposable: diagnostic scene changes need no
  checkpoints. This does NOT authorize deleting unrelated files, killing
  unrelated processes, publishing, or resetting repository changes.
- P0 (a viable in-CLO callback) must pass real CLO testing before proceeding
  with the runtime-dependent implementation. Do not silently bypass this gate.

## Repository map and known traps

- `plugin/clo3d_mcp_plugin.py`: existing API handlers plus legacy file listener.
- `src/clo3d_mcp/server.py`: existing MCP tools; `connection.py`: legacy file IPC.
- `src/clo3d_mcp/extensions.py`: optional extension loader, not needed for MVP.
- `tests/`: mock/contract checks, NOT evidence of real CLO compatibility.
- The existing listener is disabled by default on Windows. README is not proof
  it works. Importing the plugin with real CLO modules can invoke auto-start.
- Preserve useful handlers and existing tests; do not rewrite the repository
  just to introduce the new path. Never fall back to file IPC automatically.

## Load the relevant local skill

Skills live in `.opencode/skills/` and are discovered without extra config.
Before implementation or review, load the applicable skill with the skill tool;
if unavailable, read its `SKILL.md` directly. Do not load unrelated skills.

- `clo-python-runtime`: embedded Python, callbacks, UI thread and launcher.
- `windows-named-pipe`: Windows ctypes, framing, overlapped I/O and cleanup.
- `python-mcp-session`: FastMCP HTTP, external queue and session lifecycle.
- `transport-verification`: tests, fault injection and real-CLO acceptance.
- `clo-mcp-tool-design`: tool contracts/descriptions, API traceability,
  discoverability and composition examples; load before adding/documenting tools.
- `clo-tool-workflows`: safe tool selection/composition and domain skill
  templates; load before multi-tool CLO work or authoring workflow skills.

## Tool documentation and workflow quality

- Follow `docs/CLO_MCP_TOOL_AUTHORING.md`. Every new tool needs a precise
  description, parameter/result semantics, effects/limits, errors and a safe
  next action, plus valid/invalid/composition examples and coverage evidence.
- Keep live MCP metadata, validators, tool cards and workflow/skill references
  consistent. Documentation never enables a missing tool or expands permission.
- Use `docs/CLO_MCP_TOOLS.md` for current tools; native API introspection and
  legacy handlers are not proof a corresponding MCP tool is available.
- Compose mutations sequentially with readback; never pre-enqueue dependent
  changes or automatically clean up the scene after error/unknown outcome.
- A workflow recipe is not an atomic composite tool. Test selection/composition
  in fake evaluations; real CLO runs remain explicit acceptance gates.

## Engineering invariants

- CLO API calls only from a verified appropriate CLO thread. A Python
  background thread or successful SetTimer return is not proof of safety.
- No blocking pipe operations, sleeps, network requests or dependency installs
  in UI callbacks. A long synchronous CLO API call can still block the UI.
- Modules imported inside CLO must not depend on MCP, uvicorn or external venv
  packages. Inspect embedded Python version/modules instead of assuming them.
- Keep `mcp.server.fastmcp.FastMCP` from the official SDK. Read `uv.lock` and
  installed signatures before using examples; do not mix it with `fastmcp`
  or examples for SDK v2. No unrequested dependency upgrades.
- One executing CLO job; bounded external FIFO; separate queued and dispatched
  deadlines. A client timeout is not cancellation of a running CLO command.
- Never automatically resend an already dispatched command. Unknown outcomes
  remain explicit; do not claim exactly-once execution across crashes.
- No request, response, heartbeat, discovery or queue files in the new path.
  Source files, dependencies and user-requested exports are not IPC files.
- Loopback HTTP only; local-user pipe ACL; preserve Host/Origin protections.
  Do not expose arbitrary exec or log session tokens.
- Manage only the MCP process belonging to this CLO session; do not kill by
  port or process name. Repeated launch must not create duplicates.

## Verification and delivery

- Baseline command: `uv run --frozen --with pytest pytest -q` (88 tests passed
  before transport work; the count is historical, not a permanent assertion).
- Run focused tests for the change, then the full suite. Report failures and
  skips honestly; do not weaken tests to hide regressions.
- Add deterministic tests for framing, queue and shutdown. Real Windows pipe
  tests and real CLO checks are separate from mocks; identify which ran.
- For real CLO checks provide a short script path, expected output, stop method
  and failure criteria. No hidden app interaction or unbounded stress tests.
- Use PowerShell-compatible commands and explicit timeouts on Windows.
- Preserve `LICENSE` and upstream attribution. Do not commit SDKs, scenes,
  tokens, machine-specific paths, generated logs or virtual environments.
- Finish with changed files, tests actually run and the next acceptance gate.
  Do not commit or push unless asked.
