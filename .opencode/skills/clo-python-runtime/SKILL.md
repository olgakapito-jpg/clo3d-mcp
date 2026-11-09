---
name: clo-python-runtime
description: Develop or review Python running inside CLO, persistent callbacks, UI-thread dispatch, launcher startup and safe restart or shutdown.
---

# CLO embedded Python runtime

Read repository `AGENTS.md` and the relevant phase of
`docs/PYTHON_TRANSPORT_PLAN.md` first. Resolve paths from the project root.

## Before writing code

1. Inspect the current plugin and its auto-start guard. A diagnostic probe must
   not import the legacy file listener and accidentally start it.
2. From inside CLO, record Python version, architecture, PID, native thread ID,
   availability of ctypes and required CLO modules. The external venv is not
   the embedded environment. Do not add arbitrary external binary extensions.
3. Choose a small, explicit callback mechanism. Win32 timers in upstream were
   disabled for reported CLO 2024.1 failures. Treat these reports as evidence
   about that build, not a guarantee about CLO 2026.1 in either direction.

## Callback contract

- Registration success is not callback success. Observe callbacks AFTER the
  script returns; verify native thread identity before invoking CLO API.
- Hold strong references to native callback objects and their Python state.
  Killing a timer may leave queued messages: prevent stale dispatch and retain
  callback memory until safe. Do not free a callback still executing.
- Separate callback identity/generation from mutable current-session state.
  A retired callback must not dispatch work into a new session.
- Prevent reentrancy even when CLO API pumps GUI messages. One job at a time.
- Catch exceptions at the native callback boundary; record bounded diagnostics
  and return normally. Do not pretend an execution failure is success.
- Bound each tick's transport work. Never wait for a peer, sleep, read a pipe
  synchronously, or run dependency installation from a callback.
- No infinite blocking fallback when callback registration fails. Fail clearly.

## Launcher and lifetime

- Launch an explicit external `.venv/Scripts/python.exe`; embedded
  `sys.executable` may identify CLO rather than a Python interpreter.
- Resolve repository paths from a verified launcher location. If `__file__`
  is absent in Script Editor, report the problem or accept an explicit root;
  do not guess from an arbitrary current working directory.
- Define start, ready, stopping, stopped and failed states. Keep repeated
  starts idempotent for the same session, without silently killing strangers.
- Do not leave stdout/stderr pipes undrained. Failure diagnostics must remain
  available without silently introducing log files.
- Probe cleanup independently before adding MCP or Named Pipe dependencies.

## Native option types and diagnostic probes

- Option records may live in `ApiTypes` (for example
  `ApiTypes.ImportExportOption`), not in `export_api`. `describe_clo_api`/live
  `hasattr` can show an `Export*Option` factory unavailable while the documented
  type still constructs inside embedded Python. Check both before concluding a
  native operation is blocked; never substitute a fake option or a different
  overload silently.
- Adapter code runs inside CLO and may import a CLO module (e.g. `ApiTypes`);
  external server code must not. Keep imports inside the adapter call and map
  failure to `api_unavailable`.
- One-shot probe conventions: verified service/thread guards, marker before
  native entry, `stage` and sanitized `error_type`, no retry, no raw native text.
  If a probe bug is fixed before any native call, use a distinct v2 marker and
  say so; never reset the old marker.
- If the native effect has no objective getter (drape/simulation), label evidence
  visual-only and ask the user to confirm the 3D result; absence from the visible
  camera does not mean absence from the scene.

## P0 acceptance gate

Provide the user a diagnostic `.py` and a documented stop action. Verify:
callbacks after script return and Script Editor closure; callback thread;
short GetPatternCount calls; 10 minutes responsive operation; ten start/stop
cycles; no callbacks doing work after stop; no file IPC. A fresh CLO session
may be needed to validate callback cleanup. Mark this as pending until tested.

If no stable callback works, stop and propose options. Do not silently add C++,
UI automation or an application-blocking event loop.

## References

- CLO Python entry points: https://developer.clo3d.com/python.html
- Known upstream implementation: inspect the checked-out plugin, not just README.
